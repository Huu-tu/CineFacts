import random

import pytest

from cinefacts import timing as t

SR, FPS = 24000, 24


def test_samples_to_frame_rounds_to_nearest_half_up():
    assert t.samples_to_frame(0, SR, FPS) == 0
    assert t.samples_to_frame(499, SR, FPS) == 0
    assert t.samples_to_frame(500, SR, FPS) == 1   # exactly half a frame rounds up
    assert t.samples_to_frame(1000, SR, FPS) == 1
    assert t.samples_to_frame(48000, SR, FPS) == 48


def test_non_integer_ratio_44100():
    # 44100 / 24 = 1837.5 samples per frame
    assert t.samples_to_frame(1837, 44100, 24) == 1
    assert t.samples_to_frame(44100, 44100, 24) == 24
    assert t.frame_to_samples(1, 44100, 24) == 1838


def test_split_by_weights_proportional():
    assert t.split_by_weights(0, 1000, [1, 1]) == [500]
    assert t.split_by_weights(100, 400, [1, 2]) == [200]
    assert t.split_by_weights(0, 10, [1]) == []
    with pytest.raises(ValueError):
        t.split_by_weights(0, 10, [1, 0])


def _layout(durs, last=None, **kw):
    last = last or [False] * (len(durs) - 1) + [True]
    args = dict(sample_rate=SR, fps=FPS, lead_in=0.5, pause_sentence=0.35, pause_chapter=1.2)
    args.update(kw)
    return t.layout_sentences(durs, last, **args)


def test_layout_places_pauses_and_pads_to_frame_grid():
    lay = _layout([24000, 12345], [True, True])
    assert lay.starts[0] == 12000                    # 0.5 s lead-in
    assert lay.starts[1] == 12000 + 24000 + 28800    # chapter pause 1.2 s
    end = lay.ends[1] + 28800
    assert lay.total >= end and lay.total % 1000 == 0
    assert lay.total - end < 1000


def test_shots_tile_the_video_exactly():
    lay = _layout([30000, 50000, 41234])
    fr = t.shot_frames(lay, [[1], [1, 1], [2, 1, 1]], sample_rate=SR, fps=FPS)
    flat = [x for row in fr for x in row]
    assert flat[0][0] == 0
    assert flat[-1][1] == lay.total // 1000
    for (a, b), (c, d) in zip(flat, flat[1:]):
        assert b == c and b > a  # contiguous, no gaps, no empty shots


def test_pause_belongs_to_preceding_shot():
    lay = _layout([24000, 24000])
    fr = t.shot_frames(lay, [[1], [1]], sample_rate=SR, fps=FPS)
    # second sentence starts at 0.5 + 1 + 0.35 = 1.85 s -> frame 44.4 -> 44
    assert fr[0][0] == (0, 44)
    assert fr[1][0][0] == 44


def test_cumulative_rounding_does_not_drift():
    """150 shots of awkward lengths: every shot boundary stays within half a frame of the
    true sample position, so picture never drifts from voice."""
    rng = random.Random(7)
    durs = [rng.randint(40000, 200000) for _ in range(150)]
    lay = _layout(durs)
    fr = t.shot_frames(lay, [[1]] * 150, sample_rate=SR, fps=FPS)
    for i in range(1, 150):
        true_frame = lay.starts[i] / (SR / FPS)
        assert abs(fr[i][0][0] - true_frame) <= 0.5
    # durations derived from boundaries add up exactly to the total
    assert sum(b - a for row in fr for a, b in row) == lay.total // 1000


def test_too_many_shots_raises():
    lay = _layout([1000], lead_in=0, pause_chapter=0)
    with pytest.raises(ValueError):
        t.shot_frames(lay, [[1, 1, 1]], sample_rate=SR, fps=FPS)


def test_tiny_shot_gets_at_least_one_frame():
    lay = _layout([24000], lead_in=0)
    fr = t.shot_frames(lay, [[1000, 1]], sample_rate=SR, fps=FPS)[0]
    assert all(b - a >= 1 for a, b in fr)


def test_fmt_clock():
    assert t.fmt_clock(0) == "0:00"
    assert t.fmt_clock(65.9) == "1:05"
    assert t.fmt_clock(3725) == "1:02:05"
    assert t.fmt_clock(5, force_hours=True) == "0:00:05"
