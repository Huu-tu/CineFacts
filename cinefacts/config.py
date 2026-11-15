"""Repo paths, .env parsing and style loading. Standard library only (doctor depends on it)."""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
MODELS_DIR: Path = REPO_ROOT / "models"
STYLES_DIR: Path = REPO_ROOT / "styles"
ASSETS_DIR: Path = REPO_ROOT / "assets"
PROJECTS_DIR: Path = REPO_ROOT / "projects"

# Sent on every HTTP request. Pixabay (Cloudflare) rejects the default "Python-urllib" agent.
USER_AGENT = "CineFacts/0.1 (+https://github.com/Huu-tu/CineFacts)"

REQUIRED_STYLE_KEYS: tuple[str, ...] = (
    "resolution", "fps", "preview", "final", "voice", "speed",
    "pause_sentence", "pause_chapter", "chapter_fade", "grade",
    "kenburns", "music", "loudness", "resources",
)


def parse_env(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines, tolerating CRLF, comments, `export`, spaces and quotes."""
    env: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.replace("\r", "").strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            env[key] = value
    return env


def load_env(path: Path | None = None) -> dict[str, str]:
    path = path or REPO_ROOT / ".env"
    try:
        return parse_env(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def load_style(name: str = "documentary") -> dict:
    style = json.loads((STYLES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_STYLE_KEYS if k not in style]
    if missing:
        raise ValueError(f"style '{name}' is missing keys: {', '.join(missing)}")
    return style
