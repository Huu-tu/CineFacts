"""Frame-accurate timeline. Pure functions, no I/O.

All audio positions are integer sample counts, so the narration layout is exact. Picture
boundaries are snapped to the frame grid one boundary at a time (cumulative rounding), and every
duration is derived from two snapped boundaries. Rounding each shot's duration separately is
not allowed: over ~150 shots it would drift the picture away from the voice.
"""
from __future__ import annotations

from dataclasses import dataclass


def samples_to_frame(samples: int, sample_rate: int, fps: int) -> int:
    """Nearest frame boundary to a sample position (ties round up). Integer maths, no floats."""
    return (2 * samples * fps + sample_rate) // (2 * sample_rate)


def frame_to_samples(frame: int, sample_rate: int, fps: int) -> int:
    return (2 * frame * sample_rate + fps) // (2 * fps)


def split_by_weights(start: int, end: int, weights: list[float]) -> list[int]:
    """Interior boundaries (in samples) that split [start, end) in proportion to weights."""
    if not weights or any(w <= 0 for w in weights):
        raise ValueError("weights must be a non-empty list of positive numbers")
    total = float(sum(weights))
    bounds, acc = [], 0.0
    for w in weights[:-1]:
        acc += w
        bounds.append(start + round((end - start) * acc / total))
    return bounds


@dataclass
class Layout:
    """Where each sentence sits in narration.wav, in samples."""
    lead_in: int
    starts: list[int]   # sentence audio start
    ends: list[int]     # sentence audio end (= start + its sample count)
    total: int          # narration length, padded to a whole number of frames


def layout_sentences(durations: list[int], chapter_last: list[bool], *, sample_rate: int,
                     fps: int, lead_in: float, pause_sentence: float,
                     pause_chapter: float) -> Layout:
    """Place sentences back to back with pauses. The last sentence of a chapter is followed by
    the chapter pause (the very last one too, as an outro tail)."""
    if len(durations) != len(chapter_last):
        raise ValueError("durations and chapter_last differ in length")
    sec = lambda s: round(s * sample_rate)  # noqa: E731
    pos = sec(lead_in)
    starts, ends = [], []
    for n, last in zip(durations, chapter_last):
        starts.append(pos)
        pos += n
        ends.append(pos)
        pos += sec(pause_chapter if last else pause_sentence)
    frames = samples_to_frame(pos, sample_rate, fps)
    if frame_to_samples(frames, sample_rate, fps) < pos:
        frames += 1  # never cut the tail short
    return Layout(sec(lead_in), starts, ends, frame_to_samples(frames, sample_rate, fps))


def shot_frames(layout: Layout, shot_weights: list[list[float]], *, sample_rate: int,
                fps: int) -> list[list[tuple[int, int]]]:
    """(start_frame, end_frame) for every shot of every sentence.

    A sentence's spoken span is split among its shots by weight. The lead-in belongs to the
    first shot of the video, and each pause belongs to the shot before it, so the picture never
    goes empty. Every boundary is snapped independently; every shot gets at least one frame.
    """
    n = len(layout.starts)
    if len(shot_weights) != n:
        raise ValueError("one weight list per sentence is required")
    total_frames = samples_to_frame(layout.total, sample_rate, fps)
    raw: list[int] = []  # sample boundaries, starting at 0 and ending at layout.total
    for i in range(n):
        seg_start = 0 if i == 0 else layout.starts[i]
        raw.append(seg_start)
        raw.extend(split_by_weights(layout.starts[i], layout.ends[i], shot_weights[i]))
    frames = [samples_to_frame(s, sample_rate, fps) for s in raw] + [total_frames]
    frames[0] = 0
    for k in range(1, len(frames)):  # enforce >= 1 frame per shot, pushing forward
        frames[k] = max(frames[k], frames[k - 1] + 1)
    if frames[-1] != total_frames:
        raise ValueError("too many shots for the narration length (less than 1 frame each)")
    out, k = [], 0
    for w in shot_weights:
        row = []
        for _ in w:
            row.append((frames[k], frames[k + 1]))
            k += 1
        out.append(row)
    return out


def fmt_clock(seconds: float, force_hours: bool = False) -> str:
    """YouTube chapter style: M:SS, or H:MM:SS for long videos."""
    s = int(seconds)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    if h or force_hours:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"
