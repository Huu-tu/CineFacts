import copy
import json

import pytest

from cinefacts import config, guard, tts
from cinefacts import plan as planmod

PLAN = {
    "id": "t", "title": "Test", "voice": "am_michael", "target_minutes": 1,
    "chapters": [
        {"id": "c01", "title": "One", "sentences": [
            {"id": "c01s001", "text": "Hello there.", "shots": [
                {"id": "c01s001a", "kind": "video", "query": "a", "pick": None}]},
            {"id": "c01s002", "text": "Second.", "say": "Second!", "shots": [
                {"id": "c01s002a", "query": "b", "weight": 2},
                {"id": "c01s002b", "query": "c"}]},
        ]},
        {"id": "c02", "title": "Two", "sentences": [
            {"id": "c02s001", "text": "Bye.", "shots": [{"id": "c02s001a", "query": "d"}]},
        ]},
    ],
}


def test_valid_plan_has_no_errors():
    assert planmod.validate(PLAN) == []


@pytest.mark.parametrize("mutate,needle", [
    (lambda p: p["chapters"][1].update(id="c01"), "duplicate id c01"),
    (lambda p: p["chapters"][0]["sentences"][0].update(id="c02s001"), "must look like c01s001"),
    (lambda p: p["chapters"][0]["sentences"][0]["shots"][0].update(id="c01s001"), "shot id"),
    (lambda p: p["chapters"][0]["sentences"][1]["shots"][0].update(weight=0), "weight"),
    (lambda p: p["chapters"][0]["sentences"][0]["shots"][0].update(kind="gif"), "kind"),
    (lambda p: p["chapters"][0]["sentences"][0].update(text=" "), "empty text"),
    (lambda p: p["chapters"][0]["sentences"][0].update(shots=[]), "no shots"),
])
def test_invalid_plans_are_reported(mutate, needle):
    p = copy.deepcopy(PLAN)
    mutate(p)
    assert any(needle in e for e in planmod.validate(p))


def test_spoken_text_prefers_say():
    s = PLAN["chapters"][0]["sentences"]
    assert planmod.spoken_text(s[0]) == "Hello there."
    assert planmod.spoken_text(s[1]) == "Second!"


def test_bad_project_id_rejected():
    with pytest.raises(planmod.PlanError):
        planmod.project_dir("../etc")


def test_script_md_lists_every_sentence():
    md = planmod.render_script_md(PLAN)
    for _, s, _ in planmod.sentences(PLAN):
        assert s["id"] in md and s["text"] in md
    assert "generated from plan.json" in md


def test_sentence_key_changes_with_inputs():
    k = tts.sentence_key("hi", "am_michael", 1.0, "m:1")
    assert k == tts.sentence_key("hi", "am_michael", 1.0, "m:1")
    assert k != tts.sentence_key("hi!", "am_michael", 1.0, "m:1")
    assert k != tts.sentence_key("hi", "af_heart", 1.0, "m:1")
    assert k != tts.sentence_key("hi", "am_michael", 1.1, "m:1")
    assert k != tts.sentence_key("hi", "am_michael", 1.0, "m:2")


def test_trim_silence_keeps_margin():
    import numpy as np
    x = np.zeros(24000, dtype=np.float32)
    x[10000:12000] = 0.5
    y = tts.trim_silence(x)
    assert len(y) == 2000 + int(0.04 * 24000) + int(0.08 * 24000)


def test_make_timeline_fades_and_chapters():
    style = config.load_style()
    tl = tts.make_timeline(PLAN, style, [24000, 36000, 12000])
    assert [c["id"] for c in tl["chapters"]] == ["c01", "c02"]
    shots = tl["shots"]
    assert [s["id"] for s in shots] == ["c01s001a", "c01s002a", "c01s002b", "c02s001a"]
    assert shots[0]["start_frame"] == 0 and shots[-1]["end_frame"] == tl["total_frames"]
    fade = round(style["chapter_fade"] * 24)
    assert shots[0]["fade_in"] == fade and shots[0]["fade_out"] == 0
    assert shots[2]["fade_out"] == fade and shots[1]["fade_out"] == 0
    assert shots[3]["fade_in"] == fade and shots[3]["fade_out"] == fade
    assert tl["chapters"][1]["start_frame"] == shots[3]["start_frame"]
    # weight 2:1 split of sentence 2's spoken part
    assert shots[1]["frames"] > shots[2]["frames"] - 30


def test_wrapper_cmd():
    assert guard.wrapper_cmd("2500M", True)[:5] == ["systemd-run", "--scope", "--quiet", "-p",
                                                     "MemoryMax=2500M"]
    assert guard.wrapper_cmd("2500M", False) == ["nice", "-n", "10", "ionice", "-c3"]


def test_heavy_lock_is_exclusive(tmp_path):
    lock = tmp_path / "l"
    with guard.heavy_lock(lock):
        with pytest.raises(SystemExit):
            with guard.heavy_lock(lock):
                pass


def test_demo_plan_is_valid_if_present():
    path = config.PROJECTS_DIR / "demo" / "plan.json"
    if path.exists():
        assert planmod.validate(json.loads(path.read_text())) == []
