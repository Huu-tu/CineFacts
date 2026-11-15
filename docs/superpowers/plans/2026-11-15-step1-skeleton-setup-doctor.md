# Step 1: Skeleton, setup.sh, doctor (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay down the repo skeleton, a one-command `setup.sh` for Ubuntu 24.04, and `./run doctor`. This plan is done when, on the owner's VPS, setup installs everything, doctor passes, and the VPS can push to GitHub.

**Architecture:**
- A Python package `cinefacts/` behind a bash entry point `./run`.
- `doctor` uses **only the standard library**, so it can still report a missing venv. Every check is a pure function over injected inputs (command runner, file sizes, HTTP getter), so all checks unit-test on any OS.
- `setup.sh` is idempotent bash. Downloads go to `*.part` files and are renamed only once complete.

**Tech Stack:** bash, Python 3.12 (stdlib + pytest), apt (ffmpeg, tmux, fonts-inter), kokoro-onnx model files, the Claude Code native installer.

**Spec:** `docs/superpowers/specs/2026-11-15-cinefacts-video-pipeline-design.md` (sections 3, 9, 10, 11, 12)

## Global Constraints

- Target OS: Ubuntu 24.04. Hardware: 2 vCPU, 3.8 GB RAM. Repo path on the VPS: `/root/CineFacts`.
- Ask the owner before any single install larger than ~500 MB, and before using any paid service.
- Never commit `.env`, media, `models/`, `.venv/`, `assets/reference/`, or anything under `projects/*/` except `storyboard.md`, `facts.md`, `plan.json` and `script.md`.
- `*.sh` and `run` must have LF line endings (the repo is edited on Windows).
- Doctor output and errors must never print the Pixabay key.
- Output format constants from the spec: 1920x1080, 24 fps; preview 1280x720; loudness -14 LUFS, ≤ -1 dBTP; ffmpeg threads 2; memory cap `2500M`.
- Kokoro files: `models/kokoro-v1.0.onnx` and `models/voices-v1.0.bin`, from the kokoro-onnx GitHub release `model-files-v1.0`.
- Talk to the owner in Vietnamese. Code, comments and docs are in English.

## Review Focus

1. **`.env` edited on Windows or in nano** (CRLF line endings, `export ` prefix, quotes, spaces around `=`, comments, blank key). It should parse to the right value, and a blank key should count as missing. Pinned in Task 1.
2. **An interrupted model download** leaves a truncated file. Doctor should FAIL it on size, and re-running setup should replace it. Pinned in Task 2 (size check) and Task 3 (`.part` download).
3. **The network is down, or the Pixabay key is invalid.** Doctor should report a FAIL with a fix line, not crash with a traceback, and should not leak the key. Pinned in Task 2.
4. **`./run doctor` before the venv exists** (first run, or a failed pip install). It should fall back to system `python3` and still report everything. Verified in Task 5, step 3.
5. **Running from another directory** (`/root/CineFacts/run doctor` from `~`). Paths should resolve from the repo root, not the working directory. Pinned in Task 1.

---

## File map

| File | Responsibility |
|---|---|
| `.gitattributes` | add `*.sh text eol=lf`, `run text eol=lf` |
| `.gitignore` | secrets, media, models, venv, project artifacts (whitelisting the 4 text files) |
| `.env.example` | `PIXABAY_API_KEY=` |
| `requirements.txt` | `kokoro-onnx>=0.4`, `onnxruntime>=1.18`, `soundfile>=0.12`, `requests>=2.31`, `Pillow>=10`, `pytest>=8` |
| `run` | bash entry point: `cd` into the repo dir, use `.venv/bin/python` if present, else `python3`; `exec python -m cinefacts "$@"` |
| `cinefacts/__init__.py` | `__version__ = "0.1.0"` |
| `cinefacts/__main__.py` | argparse CLI: `doctor [--offline]`. Stubs for `tts search fetch shots assemble subs qa all` print "not implemented yet (roadmap step N)" and exit 2 |
| `cinefacts/config.py` | repo paths, `.env` parsing, style loading (stdlib only) |
| `cinefacts/doctor.py` | checks + report (stdlib only) |
| `styles/documentary.json` | default style preset |
| `projects/demo/storyboard.md` | moved from the repo root with `git mv` |
| `assets/{fonts,music,sfx}/.gitkeep` | empty asset folders |
| `setup.sh` | the idempotent installer |
| `CLAUDE.md` | run commands, conventions, an "Errors we hit" log |
| `.claude/skills/make-video/SKILL.md` | workflow outline with the 3 checkpoints (completed in roadmap step 4) |
| `tests/test_config.py`, `tests/test_doctor.py` | unit tests |

---

### Task 1: Skeleton, config, CLI entry point

**Files:**
- Create: `.gitignore`, `.env.example`, `requirements.txt`, `run`, `cinefacts/__init__.py`, `cinefacts/__main__.py`, `cinefacts/config.py`, `styles/documentary.json`, `assets/fonts/.gitkeep`, `assets/music/.gitkeep`, `assets/sfx/.gitkeep`, `tests/test_config.py`
- Modify: `.gitattributes`
- Move: `storyboard.md` → `projects/demo/storyboard.md`

**Interfaces:**
- Produces (in `cinefacts/config.py`):
  - `REPO_ROOT: Path`, computed as `Path(__file__).resolve().parent.parent`
  - `MODELS_DIR`, `STYLES_DIR`, `ASSETS_DIR`, `PROJECTS_DIR: Path`, all under `REPO_ROOT`
  - `parse_env(text: str) -> dict[str, str]`
  - `load_env(path: Path | None = None) -> dict[str, str]`: defaults to `REPO_ROOT/".env"`, returns `{}` if missing
  - `load_style(name: str = "documentary") -> dict`: raises `ValueError` naming any missing key
  - `REQUIRED_STYLE_KEYS: tuple[str, ...]`

`styles/documentary.json` content (values from the spec, with Claude's defaults for the rest):
```json
{
  "resolution": [1920, 1080],
  "fps": 24,
  "preview": { "resolution": [1280, 720], "x264_preset": "veryfast", "crf": 23 },
  "final": { "x264_preset": "medium", "crf": 18 },
  "voice": "am_michael",
  "speed": 1.0,
  "pause_sentence": 0.35,
  "pause_chapter": 1.2,
  "chapter_fade": 0.5,
  "grade": { "contrast": 1.05, "saturation": 0.95, "warmth": 0.06, "shadow_lift": 0.03 },
  "kenburns": { "zoom_from": 1.0, "zoom_to": 1.08 },
  "music": { "level_db": -20, "duck": true },
  "loudness": { "integrated_lufs": -14, "true_peak_db": -1 },
  "resources": { "ffmpeg_threads": 2, "memory_max": "2500M" }
}
```
`REQUIRED_STYLE_KEYS` = every top-level key above.

`.gitignore` must contain:
```
.env
.venv/
models/
__pycache__/
*.pyc
assets/reference/
assets/music/*
!assets/music/.gitkeep
projects/*/*
!projects/*/storyboard.md
!projects/*/facts.md
!projects/*/plan.json
!projects/*/script.md
```

- [ ] **Step 1: Write the failing tests** in `tests/test_config.py`

```python
from pathlib import Path
from cinefacts import config

def test_parse_env_handles_windows_and_shell_styles():
    text = ('# comment\r\n'
            'export PIXABAY_API_KEY = "abc-123"\r\n'
            "OTHER='x y'\r\n"
            '\r\n'
            'EMPTY=\r\n')
    env = config.parse_env(text)
    assert env["PIXABAY_API_KEY"] == "abc-123"
    assert env["OTHER"] == "x y"
    assert env["EMPTY"] == ""
    assert "# comment" not in env

def test_load_env_missing_file_returns_empty(tmp_path):
    assert config.load_env(tmp_path / "nope.env") == {}

def test_repo_root_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert (config.REPO_ROOT / "cinefacts" / "config.py").is_file()
    assert config.STYLES_DIR == config.REPO_ROOT / "styles"

def test_load_style_documentary_has_spec_values():
    s = config.load_style("documentary")
    assert s["resolution"] == [1920, 1080]
    assert s["fps"] == 24
    assert s["preview"]["resolution"] == [1280, 720]
    assert s["loudness"] == {"integrated_lufs": -14, "true_peak_db": -1}
    assert s["resources"]["memory_max"] == "2500M"

def test_load_style_missing_key_names_it(tmp_path, monkeypatch):
    (tmp_path / "bad.json").write_text('{"fps": 24}')
    monkeypatch.setattr(config, "STYLES_DIR", tmp_path)
    try:
        config.load_style("bad")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "resolution" in str(e)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL / ImportError (`cinefacts.config` does not exist yet)

- [ ] **Step 3: Implement the skeleton files and `cinefacts/config.py`**

`parse_env` does the following, in order:
- strips `\r`;
- skips blank lines and lines starting with `#`;
- drops a leading `export `;
- splits on the first `=`;
- strips whitespace around the key and the value;
- strips one pair of matching surrounding quotes.

`run` is bash with `set -euo pipefail` and `cd "$(dirname "$(readlink -f "$0")")"`. It picks the interpreter as described in the file map, then runs `exec "$PY" -m cinefacts "$@"`. Run `git update-index --chmod=+x run`.

`__main__.py` dispatches `doctor` to `cinefacts.doctor.main(offline: bool) -> int`; Task 2 creates that module, so until then import it lazily inside the handler.

Move the storyboard with `git mv storyboard.md projects/demo/storyboard.md`.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: repo skeleton, config loader, style preset, run entry point"
```

---

### Task 2: Doctor

**Files:**
- Create: `cinefacts/doctor.py`, `tests/test_doctor.py`

**Interfaces:**
- Consumes: `config.REPO_ROOT`, `config.MODELS_DIR`, `config.load_env()`
- Produces (in `cinefacts/doctor.py`):
  - `@dataclass class Check: name: str; status: str  # "ok" | "warn" | "fail"; detail: str; fix: str = ""`
  - `check_binary(name: str, fix: str, which=shutil.which) -> Check`
  - `check_ffmpeg_features(encoders_out: str, filters_out: str) -> Check`. Requires the encoder `libx264` and the filters `loudnorm`, `drawtext`, `ass`, `scale`, `crop`, `concat`. Fix: `sudo apt install -y ffmpeg`
  - `check_python_modules(find_spec=importlib.util.find_spec) -> Check`. Modules: `kokoro_onnx`, `onnxruntime`, `soundfile`, `requests`, `PIL`, `pytest`. Fix: `./setup.sh`
  - `check_model_file(path: Path, min_bytes: int) -> Check`. Thresholds: `kokoro-v1.0.onnx` ≥ 300_000_000; `voices-v1.0.bin` ≥ 25_000_000. Fix: `./setup.sh` (it re-downloads)
  - `check_font(fc_list_out: str) -> Check`: ok if any line contains `Inter`. Fix: `sudo apt install -y fonts-inter`
  - `check_env(env: dict) -> Check`: fails if `PIXABAY_API_KEY` is missing or blank. Fix: `nano /root/CineFacts/.env`
  - `check_pixabay(key: str, http_get) -> Check`: `http_get(url) -> (status:int, body:str)`. Calls `https://pixabay.com/api/videos/?key=<key>&q=airplane&per_page=3`; ok when status 200 and the JSON has `totalHits` > 0. Any exception or non-200 → fail. **Detail and fix never contain the key.**
  - `check_disk(free_bytes: int) -> Check`: warn below 5 GiB
  - `check_memory(meminfo_text: str) -> Check`: reports MemTotal; warn below 3 GiB
  - `check_systemd_run(run_cmd) -> Check`: runs `systemd-run --scope -p MemoryMax=100M --quiet true`; failure → warn (heavy steps fall back to nice/ionice only)
  - `check_os(os_release_text: str) -> Check`: warn unless it contains `VERSION_ID="24.04"`
  - `run_checks(offline: bool) -> list[Check]`: wires the real inputs, and skips `check_pixabay` (status warn, detail "skipped (--offline)") when offline
  - `format_report(checks: list[Check]) -> str`: one line per check, `[ OK ]`/`[WARN]`/`[FAIL]` name: detail; then, for each non-ok check, `  fix: <fix>`; a final summary line
  - `exit_code(checks) -> int`: 1 if any fail, else 0
  - `main(offline: bool = False) -> int`

Binaries checked by `run_checks`: `ffmpeg`, `ffprobe`, `tmux`, `git`, `fc-list`, plus `claude` (warn only; fix: `curl -fsSL https://claude.ai/install.sh | bash`). Each binary's fix is its apt line.

- [ ] **Step 1: Write the failing tests** in `tests/test_doctor.py`

```python
from pathlib import Path
from cinefacts import doctor as d

def test_binary_missing_gives_fail_with_fix():
    c = d.check_binary("ffmpeg", which=lambda n: None, fix="sudo apt install -y ffmpeg")
    assert c.status == "fail" and "apt install -y ffmpeg" in c.fix

def test_ffmpeg_features_missing_libx264():
    c = d.check_ffmpeg_features("V..... libx265", "loudnorm drawtext ass scale crop concat")
    assert c.status == "fail" and "libx264" in c.detail

def test_ffmpeg_features_all_present():
    enc = " V....D libx264  H.264"
    flt = " loudnorm\n drawtext\n ass\n scale\n crop\n concat\n"
    assert d.check_ffmpeg_features(enc, flt).status == "ok"

def test_truncated_model_fails(tmp_path):
    f = tmp_path / "kokoro-v1.0.onnx"; f.write_bytes(b"x" * 1000)
    c = d.check_model_file(f, 300_000_000)
    assert c.status == "fail" and "setup.sh" in c.fix

def test_missing_model_fails(tmp_path):
    assert d.check_model_file(tmp_path / "none.bin", 1).status == "fail"

def test_env_blank_key_fails():
    assert d.check_env({"PIXABAY_API_KEY": ""}).status == "fail"
    assert d.check_env({"PIXABAY_API_KEY": "k"}).status == "ok"

def test_pixabay_ok():
    c = d.check_pixabay("SECRETKEY", lambda url: (200, '{"totalHits": 5, "hits": []}'))
    assert c.status == "ok"

def test_pixabay_network_error_fails_without_leaking_key():
    def boom(url): raise OSError("Name or service not known for " + url)
    c = d.check_pixabay("SECRETKEY", boom)
    assert c.status == "fail"
    assert "SECRETKEY" not in c.detail + c.fix

def test_pixabay_bad_key_fails_without_leaking_key():
    c = d.check_pixabay("SECRETKEY", lambda url: (400, "[ERROR 400] Invalid or missing API key"))
    assert c.status == "fail" and "SECRETKEY" not in c.detail + c.fix

def test_disk_warn_below_5gib():
    assert d.check_disk(4 * 1024**3).status == "warn"
    assert d.check_disk(20 * 1024**3).status == "ok"

def test_memory_parsed_from_meminfo():
    c = d.check_memory("MemTotal:        3984588 kB\nMemFree: 1 kB\n")
    assert c.status == "ok" and "3.8" in c.detail

def test_font_detection():
    assert d.check_font("/usr/share/fonts/opentype/inter/Inter-Bold.otf: Inter:style=Bold").status == "ok"
    assert d.check_font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf: DejaVu Sans").status == "fail"

def test_report_and_exit_code():
    checks = [d.Check("a", "ok", "fine"), d.Check("b", "warn", "meh", "do x"), d.Check("c", "fail", "bad", "do y")]
    out = d.format_report(checks)
    assert "[ OK ] a" in out and "[WARN] b" in out and "[FAIL] c" in out
    assert "fix: do y" in out and "fix: do x" in out
    assert d.exit_code(checks) == 1
    assert d.exit_code(checks[:2]) == 0
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/test_doctor.py -v`
Expected: FAIL / ImportError

- [ ] **Step 3: Implement `cinefacts/doctor.py`** (stdlib only)

- `http_get` in `run_checks` uses `urllib.request.urlopen(url, timeout=10)`; a 4xx `HTTPError` maps to `(code, body)`.
- `check_pixabay` builds the URL internally, and replaces `key` with `***` in any message derived from exceptions or bodies.
- `run_cmd` uses `subprocess.run(..., capture_output=True, text=True, timeout=30)`. A missing binary means the dependent checks (features, font) report fail with that binary's fix, not a traceback.
- When a step outside the injected inputs blows up unexpectedly (a non-Linux path such as `/proc/meminfo` missing on Windows), it becomes a warn check whose detail is the error message.

- [ ] **Step 4: Run all tests and confirm they pass**

Run: `python -m pytest -v`
Expected: 18 passed (5 config + 13 doctor)

- [ ] **Step 5: Smoke run on Windows** (expected to report failures, but must not crash)

Run: `python -m cinefacts doctor --offline`
Expected: a report with FAIL lines (ffmpeg missing, etc.), no traceback, exit code 1

- [ ] **Step 6: Commit**

```bash
git add cinefacts/doctor.py tests/test_doctor.py && git commit -m "feat: doctor environment checks with fix commands"
```

---

### Task 3: setup.sh

**Files:**
- Create: `setup.sh` (executable, LF)

**Interfaces:**
- Consumes: `requirements.txt`, `.env.example`, `./run doctor`
- Produces: the installed system, plus `./setup.sh --deploy-key` (used in Task 5)

Behaviour, in order. Every section prints a `==>` header, and the script uses `set -euo pipefail`.
1. Refuse to run unless on Linux with `apt-get`, and run as root (or via sudo).
2. `apt-get update` (skipped if it ran less than 6 h ago, judged from `/var/lib/apt/periodic/update-success-stamp` or the lists mtime), then `apt-get install -y --no-install-recommends ffmpeg python3-venv python3-pip tmux curl ca-certificates git fontconfig fonts-inter espeak-ng`. If `fonts-inter` is not available, download `https://github.com/rsms/inter/releases/download/v4.0/Inter-4.0.zip`, extract the TTFs to `/usr/local/share/fonts/inter/`, and run `fc-cache -f`.
3. `python3 -m venv .venv` if it is missing; then `.venv/bin/pip install --upgrade pip` and `.venv/bin/pip install -r requirements.txt`.
4. Models: `download URL DEST MIN_BYTES` skips the download if DEST exists and is ≥ MIN_BYTES. Otherwise it runs `curl -fL --retry 3 -o DEST.part URL`, checks the size, then `mv DEST.part DEST`. URLs:
   - `https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx` (300000000)
   - `https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin` (25000000)
5. Claude Code: if `claude` is not on PATH (also check `~/.local/bin/claude`), run `curl -fsSL https://claude.ai/install.sh | bash`. *(The spec says "Node.js LTS + Claude Code". The native installer needs no Node, so Node is skipped. This is Claude's call, recorded in CLAUDE.md.)*
6. `cp -n .env.example .env`, then `chmod 600 .env`.
7. `./run doctor --offline || true`.
8. Print the next steps: (a) put `PIXABAY_API_KEY` in `.env`, then run `./run doctor`; (b) run `claude` once to log in; (c) optionally run `./setup.sh --deploy-key`.

`--deploy-key` mode (runs only this, then exits):
- If `/root/.ssh/cinefacts_deploy` is missing, run `ssh-keygen -t ed25519 -N "" -C cinefacts-vps -f /root/.ssh/cinefacts_deploy`.
- Append this block to `/root/.ssh/config` if it is not already there: `Host github-cinefacts` / `HostName github.com` / `User git` / `IdentityFile /root/.ssh/cinefacts_deploy` / `IdentitiesOnly yes`.
- Run `git remote set-url origin git@github-cinefacts:Huu-tu/CineFacts.git`.
- Print the public key and the instruction: GitHub repo → Settings → Deploy keys → Add → tick "Allow write access".
- Print the test command: `ssh -T git@github-cinefacts`.

- [ ] **Step 1: Write `setup.sh`** as specified above. Then run `git update-index --chmod=+x setup.sh`.
- [ ] **Step 2: Syntax check.** Run `bash -n setup.sh`. Expected: no output.
- [ ] **Step 3: Check that the Windows checkout has LF line endings.** Run `git add setup.sh run && git ls-files --eol setup.sh run`. Expected: both show `i/lf`.
- [ ] **Step 4: Commit.** `git commit -m "feat: idempotent setup.sh for Ubuntu 24.04"`

(The real test of setup.sh is Task 5 on the VPS.)

---

### Task 4: CLAUDE.md and the make-video skill outline

**Files:**
- Create: `CLAUDE.md`, `.claude/skills/make-video/SKILL.md`

`CLAUDE.md` sections:
1. **What this is**: 2 lines, plus a link to the spec.
2. **Commands**: `./setup.sh`, `./setup.sh --deploy-key`, `./run doctor [--offline]`, `.venv/bin/python -m pytest`.
3. **Conventions**:
   - the project folder layout (copied from spec section 6);
   - `plan.json` is the source of truth;
   - IDs are stable;
   - reply to the owner in Vietnamese;
   - give absolute paths for SFTP;
   - commit and push after each step;
   - never print or commit the Pixabay key.
4. **Resource rules**: nice/ionice, `MemoryMax=2500M`, 2 ffmpeg threads, one heavy job at a time.
5. **Decisions log**: "Claude Code via the native installer, no Node".
6. **Errors we hit and fixes**: an empty table to start with.

`SKILL.md` has frontmatter (`name: make-video`, plus a description saying it produces a CineFacts video from a storyboard or topic). Its body lists the workflow from spec section 5, with the 3 checkpoints, each step marked "(available from roadmap step N)".

- [ ] **Step 1: Write both files.**
- [ ] **Step 2: Commit.** `git add CLAUDE.md .claude && git commit -m "docs: CLAUDE.md and make-video skill outline"`

---

### Task 5: Verify on the VPS (needs the owner's go-ahead for SSH)

- [ ] **Step 1: Push the branch.** `git push -u origin step-1-setup`
- [ ] **Step 2: Clone on the VPS.** `git clone -b step-1-setup https://github.com/Huu-tu/CineFacts.git /root/CineFacts`
- [ ] **Step 3: Doctor before setup** (Review Focus 4). Run `cd /root/CineFacts && ./run doctor --offline`. Expected: it runs on system python3, ends with FAIL lines and fixes, and shows no traceback.
- [ ] **Step 4: First setup run.** Run `./setup.sh 2>&1 | tee /root/setup-1.log`. Expected: exit code 0, and doctor (offline) shows only the `.env` key FAIL and the `claude` login WARN.
- [ ] **Step 5: Second run (idempotency).** Run `./setup.sh`. Expected: exit code 0, no re-download of the models, and noticeably faster.
- [ ] **Step 6: Write the Pixabay key into `.env`** over SSH, piped through stdin so it never lands in shell history or command arguments. Then run `./run doctor`. Expected: all OK, except `claude` (WARN until the owner logs in).
- [ ] **Step 7: Tests on the VPS.** Run `.venv/bin/python -m pytest -v`. Expected: 18 passed.
- [ ] **Step 8: Check the Kokoro model loads.** Run `.venv/bin/python -c "from kokoro_onnx import Kokoro; k=Kokoro('models/kokoro-v1.0.onnx','models/voices-v1.0.bin'); s,sr=k.create('Hello from CineFacts.', voice='am_michael', speed=1.0, lang='en-us'); print(len(s)/sr, sr)"`. Expected: prints a duration of about 1–2 s and `24000`. If the kokoro-onnx API differs, record the fix in CLAUDE.md under "Errors we hit".
- [ ] **Step 9: Record problems.** Every problem hit in steps 3–8 goes into the "Errors we hit" table in `CLAUDE.md`. Then commit and push from Windows.
- [ ] **Step 10: Deploy key.** Run `./setup.sh --deploy-key`. The owner adds the printed key on GitHub with write access. Then run `ssh -T git@github-cinefacts`. Expected: "successfully authenticated".
- [ ] **Step 11: Owner logs in to Claude Code.** The owner runs `claude` in tmux in Termius. Then `./run doctor` should be all OK.

### Task 6: Merge

- [ ] **Step 1: Merge to main and push** (after the owner confirms step 1 is accepted): `git checkout main && git merge --ff-only step-1-setup && git push origin main`. Then run `git checkout main && git pull` on the VPS.
