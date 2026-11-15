"""Protect the VPS: run heavy steps niced, memory-capped, one at a time."""
from __future__ import annotations

import contextlib
import fcntl
import os
import shutil
import sys
import time
from pathlib import Path

from cinefacts import config

LOCK_PATH = config.REPO_ROOT / ".heavy.lock"
ENV_FLAG = "CINEFACTS_GUARDED"


def wrapper_cmd(memory_max: str, has_systemd_run: bool) -> list[str]:
    cmd: list[str] = []
    if has_systemd_run:
        cmd += ["systemd-run", "--scope", "--quiet", "-p", f"MemoryMax={memory_max}"]
    return cmd + ["nice", "-n", "10", "ionice", "-c3"]


def _systemd_ok() -> bool:
    return bool(shutil.which("systemd-run")) and Path("/run/systemd/system").is_dir() \
        and os.geteuid() == 0


def reexec_guarded(argv: list[str]) -> None:
    """Re-run this CLI call under nice/ionice (+ systemd-run MemoryMax). Returns only if
    already guarded or if guarding is disabled with CINEFACTS_NO_GUARD=1."""
    if os.environ.get(ENV_FLAG) == "1" or os.environ.get("CINEFACTS_NO_GUARD") == "1":
        return
    mem = config.load_style()["resources"]["memory_max"]
    cmd = wrapper_cmd(mem, _systemd_ok()) + [sys.executable, "-m", "cinefacts", *argv]
    env = dict(os.environ, **{ENV_FLAG: "1"})
    sys.stdout.flush()
    sys.stderr.flush()
    os.execvpe(cmd[0], cmd, env)


@contextlib.contextmanager
def heavy_lock(path: Path = LOCK_PATH):
    """Only one heavy job at a time across the machine."""
    f = open(path, "w")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another heavy CineFacts job is running (lock: .heavy.lock); "
                             "wait for it to finish")
        f.write(f"{os.getpid()}\n")
        f.flush()
        yield
    finally:
        f.close()


class Log:
    """Print progress and append it to projects/<id>/render.log."""

    def __init__(self, path: Path | None):
        self.path = path
        self.t0 = time.monotonic()

    def __call__(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')} +{time.monotonic() - self.t0:6.1f}s] {msg}"
        print(line, flush=True)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
