"""Environment checks. Standard library only, so it runs before setup.sh has built the venv.

Every check is a pure function over injected inputs; run_checks() wires in the real system.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from cinefacts import config

GIB = 1024 ** 3
PIXABAY_TEST_URL = "https://pixabay.com/api/videos/?key={key}&q=airplane&per_page=3"
FFMPEG_ENCODERS = ("libx264",)
FFMPEG_FILTERS = ("loudnorm", "drawtext", "ass", "scale", "crop", "concat")
PY_MODULES = ("kokoro_onnx", "onnxruntime", "soundfile", "requests", "PIL", "pytest")
MODEL_FILES = (("kokoro-v1.0.onnx", 300_000_000), ("voices-v1.0.bin", 25_000_000))
BINARIES = (
    ("ffmpeg", "sudo apt install -y ffmpeg"),
    ("ffprobe", "sudo apt install -y ffmpeg"),
    ("tmux", "sudo apt install -y tmux"),
    ("git", "sudo apt install -y git"),
    ("fc-list", "sudo apt install -y fontconfig"),
    ("rclone", "sudo apt install -y rclone"),
)
CLAUDE_FIX = "curl -fsSL https://claude.ai/install.sh | bash"
RCLONE_FIX = 'rclone config  # new remote "gdrive", type drive, scope drive.file; see CLAUDE.md'


@dataclass
class Check:
    name: str
    status: str  # "ok" | "warn" | "fail"
    detail: str
    fix: str = ""


def check_binary(name: str, fix: str, which=shutil.which) -> Check:
    path = which(name)
    if path:
        return Check(name, "ok", path)
    return Check(name, "fail", "not found on PATH", fix)


def check_ffmpeg_features(encoders_out: str, filters_out: str) -> Check:
    enc_words = set(encoders_out.split())
    flt_words = set(filters_out.split())
    missing = [e for e in FFMPEG_ENCODERS if e not in enc_words]
    missing += [f for f in FFMPEG_FILTERS if f not in flt_words]
    if missing:
        return Check("ffmpeg features", "fail", "missing: " + ", ".join(missing),
                     "sudo apt install -y ffmpeg")
    return Check("ffmpeg features", "ok", "libx264 + required filters present")


def check_python_modules(find_spec=importlib.util.find_spec) -> Check:
    missing = []
    for mod in PY_MODULES:
        try:
            if find_spec(mod) is None:
                missing.append(mod)
        except (ImportError, ValueError):
            missing.append(mod)
    if missing:
        return Check("python modules", "fail", "missing: " + ", ".join(missing), "./setup.sh")
    return Check("python modules", "ok", ", ".join(PY_MODULES))


def check_model_file(path: Path, min_bytes: int) -> Check:
    name = f"model {path.name}"
    if not path.is_file():
        return Check(name, "fail", "missing", "./setup.sh")
    size = path.stat().st_size
    if size < min_bytes:
        return Check(name, "fail", f"truncated ({size} bytes < {min_bytes})",
                     "./setup.sh  # re-downloads it")
    return Check(name, "ok", f"{size / 1e6:.0f} MB")


def check_font(fc_list_out: str) -> Check:
    if any("Inter" in line for line in fc_list_out.splitlines()):
        return Check("font Inter", "ok", "installed")
    return Check("font Inter", "fail", "not found by fc-list", "sudo apt install -y fonts-inter")


def check_env(env: dict) -> Check:
    if env.get("PIXABAY_API_KEY", "").strip():
        return Check(".env PIXABAY_API_KEY", "ok", "set")
    return Check(".env PIXABAY_API_KEY", "fail", "missing or blank",
                 f"nano {config.REPO_ROOT / '.env'}")


def check_pixabay(key: str, http_get) -> Check:
    name = "pixabay api"
    fix = "check PIXABAY_API_KEY in .env and the network (curl -I https://pixabay.com)"

    def scrub(text: str) -> str:
        text = text.replace(key, "***") if key else text
        return text.replace(urllib.parse.quote(key), "***") if key else text

    try:
        status, body = http_get(PIXABAY_TEST_URL.format(key=urllib.parse.quote(key)))
    except Exception as e:  # network errors, timeouts, DNS: report, never crash
        return Check(name, "fail", scrub(f"request failed: {e}"), fix)
    if status != 200:
        return Check(name, "fail", scrub(f"HTTP {status}: {body[:120]}"), fix)
    try:
        hits = json.loads(body).get("totalHits", 0)
    except (ValueError, AttributeError):
        return Check(name, "fail", "unexpected response (not JSON)", fix)
    if hits > 0:
        return Check(name, "ok", f"key works ({hits} hits for 'airplane')")
    return Check(name, "fail", "key accepted but no results", fix)


def check_disk(free_bytes: int) -> Check:
    detail = f"{free_bytes / GIB:.1f} GiB free"
    if free_bytes < 5 * GIB:
        return Check("disk", "warn", detail, "./run clean <id> for finished projects")
    return Check("disk", "ok", detail)


def check_memory(meminfo_text: str) -> Check:
    for line in meminfo_text.splitlines():
        if line.startswith("MemTotal:"):
            gib = int(line.split()[1]) * 1024 / GIB
            detail = f"{gib:.1f} GiB total"
            if gib < 3:
                return Check("memory", "warn", detail, "renders may swap; keep one job at a time")
            return Check("memory", "ok", detail)
    return Check("memory", "warn", "MemTotal not found")


def check_systemd_run(run_cmd) -> Check:
    code, _out = run_cmd(["systemd-run", "--scope", "-p", "MemoryMax=100M", "--quiet", "true"])
    if code == 0:
        return Check("systemd-run", "ok", "memory caps available")
    return Check("systemd-run", "warn", "unavailable; heavy steps use nice/ionice only")


def check_os(os_release_text: str) -> Check:
    if 'VERSION_ID="24.04"' in os_release_text:
        return Check("os", "ok", "Ubuntu 24.04")
    return Check("os", "warn", "not Ubuntu 24.04; setup.sh targets 24.04")


def check_rclone_remote(listremotes_out: str) -> Check:
    if any(line.strip() == "gdrive:" for line in listremotes_out.splitlines()):
        return Check("rclone gdrive", "ok", "remote configured")
    return Check("rclone gdrive", "warn", "remote 'gdrive:' not configured", RCLONE_FIX)


# ---- wiring to the real system -------------------------------------------------------------

def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return p.returncode, p.stdout + p.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def _http_get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _guard(name: str, fn) -> Check:
    """Run a check; an unexpected error becomes a warn line instead of a traceback."""
    try:
        return fn()
    except Exception as e:
        return Check(name, "warn", f"could not check: {e}")


def run_checks(offline: bool) -> list[Check]:
    checks = [_guard("os", lambda: check_os(_read("/etc/os-release")))]
    present = {}
    for name, fix in BINARIES:
        c = check_binary(name, fix)
        present[name] = c.status == "ok"
        checks.append(c)
    claude = check_binary("claude", CLAUDE_FIX)
    if claude.status != "ok" and (Path.home() / ".local/bin/claude").is_file():
        claude = Check("claude", "warn", "installed in ~/.local/bin but not on PATH",
                       'echo \'export PATH="$HOME/.local/bin:$PATH"\' >> ~/.bashrc')
    elif claude.status != "ok":
        claude.status = "warn"
    checks.append(claude)

    if present["ffmpeg"]:
        checks.append(check_ffmpeg_features(_run(["ffmpeg", "-hide_banner", "-encoders"])[1],
                                            _run(["ffmpeg", "-hide_banner", "-filters"])[1]))
    else:
        checks.append(Check("ffmpeg features", "fail", "ffmpeg missing", "sudo apt install -y ffmpeg"))
    if present["fc-list"]:
        checks.append(check_font(_run(["fc-list"])[1]))
    else:
        checks.append(Check("font Inter", "fail", "fc-list missing", "sudo apt install -y fontconfig fonts-inter"))

    checks.append(check_python_modules())
    for fname, min_bytes in MODEL_FILES:
        checks.append(check_model_file(config.MODELS_DIR / fname, min_bytes))

    env = config.load_env()
    checks.append(check_env(env))
    if offline:
        checks.append(Check("pixabay api", "warn", "skipped (--offline)"))
    elif env.get("PIXABAY_API_KEY", "").strip():
        checks.append(check_pixabay(env["PIXABAY_API_KEY"].strip(), _http_get))
    else:
        checks.append(Check("pixabay api", "fail", "no key to test", f"nano {config.REPO_ROOT / '.env'}"))

    if present["rclone"]:
        checks.append(check_rclone_remote(_run(["rclone", "listremotes"])[1]))
    checks.append(_guard("disk", lambda: check_disk(shutil.disk_usage(config.REPO_ROOT).free)))
    checks.append(_guard("memory", lambda: check_memory(_read("/proc/meminfo"))))
    checks.append(_guard("systemd-run", lambda: check_systemd_run(_run)))
    return checks


def format_report(checks: list[Check]) -> str:
    tag = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]"}
    lines = []
    for c in checks:
        lines.append(f"{tag[c.status]} {c.name}: {c.detail}")
        if c.status != "ok" and c.fix:
            lines.append(f"       fix: {c.fix}")
    fails = sum(c.status == "fail" for c in checks)
    warns = sum(c.status == "warn" for c in checks)
    lines.append("")
    lines.append(f"{len(checks)} checks: {fails} fail, {warns} warn"
                 + (" -- ready" if fails == 0 else " -- fix the FAIL lines above"))
    return "\n".join(lines)


def exit_code(checks: list[Check]) -> int:
    return 1 if any(c.status == "fail" for c in checks) else 0


def main(offline: bool = False) -> int:
    checks = run_checks(offline)
    print(format_report(checks))
    return exit_code(checks)
