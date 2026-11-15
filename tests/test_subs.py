from cinefacts import subs


def test_short_text_is_one_line():
    assert subs.split_cues("Hello world.") == ["Hello world."]


def test_two_line_text_is_balanced():
    text = "Walk through any airport at sunrise and you will notice"
    [cue] = subs.split_cues(text)
    a, b = cue.split("\n")
    assert len(a) <= 42 and len(b) <= 42 and abs(len(a) - len(b)) < 15


def test_long_sentence_splits_into_valid_cues():
    text = ("Concorde cruised at about twice the speed of sound, and at that speed the air "
            "heated its skin far beyond anything a normal airliner experiences, so engineers "
            "gave it a special white paint that reflected about twice as much sunlight.")
    cues = subs.split_cues(text)
    assert len(cues) >= 3
    for c in cues:
        lines = c.split("\n")
        assert len(lines) <= 2 and all(len(x) <= 42 for x in lines)
    assert " ".join(c.replace("\n", " ") for c in cues) == text


def test_long_clause_without_punctuation_is_chopped():
    text = " ".join(["word"] * 60)
    cues = subs.split_cues(text)
    assert all(len(c.split("\n")) <= 2 for c in cues)
    assert sum(c.count("word") for c in cues) == 60


def test_cue_times_proportional_and_contiguous():
    times = subs.cue_times(10.0, 13.0, ["aa", "aaaa"])
    assert times == [(10.0, 11.0), (11.0, 13.0)]


def test_srt_time_format():
    assert subs.srt_time(0) == "00:00:00,000"
    assert subs.srt_time(3723.5) == "01:02:03,500"


def _tl():
    return {
        "fps": 24, "duration": 60.0,
        "sentences": [
            {"text": "First sentence here.", "start": 0.5, "end": 2.0},
            {"text": "Second one.", "start": 2.4, "end": 3.1},
        ],
        "chapters": [
            {"id": "c01", "title": "Intro", "start": 0.0},
            {"id": "c02", "title": "Middle", "start": 20.0},
            {"id": "c03", "title": "End", "start": 55.0},
        ],
    }


def test_build_srt_numbering_and_frame_snapping():
    srt = subs.build_srt(_tl())
    blocks = srt.strip().split("\n\n")
    assert [b.split("\n")[0] for b in blocks] == ["1", "2"]
    assert "00:00:00,500 --> 00:00:02,000" in blocks[0]
    assert "00:00:02,417 --> 00:00:03,083" in blocks[1]  # snapped to 1/24 s


def test_chapters_format_and_warnings():
    text, warnings = subs.build_chapters(_tl())
    assert text.splitlines() == ["0:00 Intro", "0:20 Middle", "0:55 End"]
    assert warnings == ["chapter c03 is shorter than 10s"]


def test_no_orphan_word_cue():
    text = ("But the next time you see a row of white jets at sunrise, you'll know that plain "
            "colour is one of the smartest engineering choices in the sky.")
    cues = subs.split_cues(text)
    assert all(len(c.replace("\n", " ")) >= 20 for c in cues)
    assert " ".join(c.replace("\n", " ") for c in cues) == text
