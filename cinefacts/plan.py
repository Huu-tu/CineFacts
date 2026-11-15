"""plan.json: loading, validation, script.md generation, and project paths."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from cinefacts import config

CHAPTER_ID = re.compile(r"^c\d{2}$")
SENTENCE_ID = re.compile(r"^c\d{2}s\d{3}$")
SHOT_ID = re.compile(r"^c\d{2}s\d{3}[a-z]$")
SHOT_KINDS = ("video", "image")
MOTIONS = ("none", "push_in", "pull_out", "pan_left", "pan_right", "pan_up", "pan_down")


class PlanError(ValueError):
    pass


def project_dir(project_id: str) -> Path:
    if not project_id or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", project_id):
        raise PlanError(f"bad project id {project_id!r}: use a short lowercase ASCII slug")
    return config.PROJECTS_DIR / project_id


def load(project_id: str) -> dict:
    path = project_dir(project_id) / "plan.json"
    if not path.is_file():
        raise PlanError(f"{path} not found")
    plan = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(plan)
    if errors:
        raise PlanError("plan.json is invalid:\n  " + "\n  ".join(errors))
    return plan


def validate(plan: dict) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()

    def dup(i: str) -> None:
        if i in seen:
            errors.append(f"duplicate id {i}")
        seen.add(i)

    for key in ("id", "title", "chapters"):
        if key not in plan:
            errors.append(f"missing top-level key '{key}'")
    if not plan.get("chapters"):
        errors.append("plan has no chapters")
        return errors
    for ch in plan["chapters"]:
        cid = ch.get("id", "?")
        if not CHAPTER_ID.match(cid):
            errors.append(f"chapter id {cid!r} must look like c01")
        dup(cid)
        if not ch.get("title"):
            errors.append(f"{cid}: missing title")
        if not ch.get("sentences"):
            errors.append(f"{cid}: no sentences")
            continue
        for s in ch["sentences"]:
            sid = s.get("id", "?")
            if not SENTENCE_ID.match(sid) or not sid.startswith(cid):
                errors.append(f"sentence id {sid!r} must look like {cid}s001")
            dup(sid)
            if not str(s.get("text", "")).strip():
                errors.append(f"{sid}: empty text")
            if not s.get("shots"):
                errors.append(f"{sid}: no shots")
                continue
            for sh in s["shots"]:
                hid = sh.get("id", "?")
                if not SHOT_ID.match(hid) or not hid.startswith(sid):
                    errors.append(f"shot id {hid!r} must look like {sid}a")
                dup(hid)
                if sh.get("kind", "video") not in SHOT_KINDS:
                    errors.append(f"{hid}: kind must be one of {SHOT_KINDS}")
                if sh.get("motion", "none") not in MOTIONS:
                    errors.append(f"{hid}: motion must be one of {MOTIONS}")
                w = sh.get("weight", 1)
                if not isinstance(w, (int, float)) or w <= 0:
                    errors.append(f"{hid}: weight must be a positive number")
                if not str(sh.get("query", "")).strip():
                    errors.append(f"{hid}: empty query")
    return errors


def sentences(plan: dict):
    """Yield (chapter, sentence, is_last_in_chapter) in order."""
    for ch in plan["chapters"]:
        for i, s in enumerate(ch["sentences"]):
            yield ch, s, i == len(ch["sentences"]) - 1


def spoken_text(sentence: dict) -> str:
    """What Kokoro reads: the optional `say` override, else the subtitle text."""
    return (sentence.get("say") or sentence["text"]).strip()


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()[:16]


def word_count(plan: dict) -> int:
    return sum(len(s["text"].split()) for _, s, _ in sentences(plan))


def render_script_md(plan: dict, timeline: dict | None = None) -> str:
    """Human-readable script. Generated from plan.json; never edit it by hand."""
    starts = {}
    if timeline:
        starts = {c["id"]: c["start"] for c in timeline["chapters"]}
    n_shots = sum(len(s["shots"]) for _, s, _ in sentences(plan))
    words = word_count(plan)
    lines = [
        f"# {plan['title']}",
        "",
        "<!-- generated from plan.json by ./run script; edit plan.json instead -->",
        "",
        f"- Project: `{plan['id']}`  ·  voice `{plan.get('voice', 'style default')}`"
        f"  ·  target {plan.get('target_minutes', '?')} min",
        f"- {len(plan['chapters'])} chapters · {sum(len(c['sentences']) for c in plan['chapters'])}"
        f" sentences · {n_shots} shots · {words} words (~{words / 150:.1f} min at 150 wpm)",
    ]
    if timeline:
        lines.append(f"- Narrated length: {timeline['duration'] / 60:.2f} min")
    for ch in plan["chapters"]:
        lines += ["", f"## {ch['id']} · {ch['title']}"]
        if ch["id"] in starts:
            from cinefacts.timing import fmt_clock
            lines[-1] += f"  ({fmt_clock(starts[ch['id']])})"
        lines.append("")
        for s in ch["sentences"]:
            say = f"  \n  _say:_ {s['say']}" if s.get("say") else ""
            shots = "; ".join(f"`{sh['id'][-1]}` {sh['query']}" for sh in s["shots"])
            lines.append(f"- **{s['id']}** {s['text']}{say}  \n  <sub>shots: {shots}</sub>")
    return "\n".join(lines) + "\n"
