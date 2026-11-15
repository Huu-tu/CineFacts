"""subs step: subs.srt and chapters.txt from timeline.json. Pure helpers plus a thin run()."""
from __future__ import annotations


from cinefacts import timing

LINE_WIDTH = 42
MAX_LINES = 2
MIN_CHAPTER_SECONDS = 10  # YouTube ignores chapter lists with shorter chapters


def wrap(text: str, width: int = LINE_WIDTH) -> list[str]:
    """Greedy word wrap. A single word longer than width gets its own line."""
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        lines.append(cur)
    return lines


def _balance(text: str, width: int) -> str:
    """Render text that fits in 2 lines as 1 or 2 lines of similar length."""
    if len(text) <= width:
        return text
    words = text.split()
    best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        if len(a) <= width and len(b) <= width:
            score = abs(len(a) - len(b))
            if best is None or score < best[0]:
                best = (score, a, b)
    return f"{best[1]}\n{best[2]}" if best else "\n".join(wrap(text, width))


PUNCT_END = (",", ";", ":", ".", "!", "?", "\u2014")


def _fits(words: list[str], width: int, max_lines: int) -> bool:
    return len(wrap(" ".join(words), width)) <= max_lines


def split_cues(text: str, width: int = LINE_WIDTH, max_lines: int = MAX_LINES) -> list[str]:
    """Split a sentence into cues of at most max_lines lines of width characters.

    Uses the fewest cues possible, of similar length, preferring to break after clause
    punctuation (dynamic programming over word boundaries). No orphan one-word cues."""
    words = text.split()
    if not words:
        return []
    if _fits(words, width, max_lines):
        return [_balance(" ".join(words), width)]
    n, total = len(words), len(" ".join(words))
    bonus = (0.35 * width) ** 2  # how much unevenness a punctuation break is worth
    k = max(2, -(-total // (width * max_lines)))
    while k <= n:
        mean = total / k
        # best[j][c] = (cost, prev_i): words[:j] split into c chunks
        inf = float("inf")
        best = [[(inf, -1)] * (k + 1) for _ in range(n + 1)]
        best[0][0] = (0.0, -1)
        for j in range(1, n + 1):
            for i in range(j):
                chunk = words[i:j]
                if not _fits(chunk, width, max_lines):
                    continue
                c_len = len(" ".join(chunk))
                cost = (c_len - mean) ** 2
                if j < n and chunk[-1].endswith(PUNCT_END):
                    cost -= bonus
                for c in range(1, k + 1):
                    prev = best[i][c - 1][0]
                    if prev + cost < best[j][c][0]:
                        best[j][c] = (prev + cost, i)
        if best[n][k][0] < inf:
            cuts, j, c = [], n, k
            while j > 0:
                i = best[j][c][1]
                cuts.append(" ".join(words[i:j]))
                j, c = i, c - 1
            return [_balance(x, width) for x in reversed(cuts)]
        k += 1
    return [_balance(w, width) for w in words]


def cue_times(start: float, end: float, cues: list[str]) -> list[tuple[float, float]]:
    """Share [start, end] among cues in proportion to their character count."""
    weights = [max(1, len(c.replace("\n", " "))) for c in cues]
    total = sum(weights)
    out, acc = [], 0
    for w in weights:
        a = start + (end - start) * acc / total
        acc += w
        out.append((a, start + (end - start) * acc / total))
    return out


def srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def snap(t: float, fps: int) -> float:
    return round(t * fps) / fps


def build_srt(timeline: dict) -> str:
    fps = timeline["fps"]
    blocks, n = [], 0
    for s in timeline["sentences"]:
        cues = split_cues(s["text"])
        for text, (a, b) in zip(cues, cue_times(s["start"], s["end"], cues)):
            a, b = snap(a, fps), snap(b, fps)
            if b <= a:
                b = a + 1 / fps
            n += 1
            blocks.append(f"{n}\n{srt_time(a)} --> {srt_time(b)}\n{text}\n")
    return "\n".join(blocks)


def build_chapters(timeline: dict) -> tuple[str, list[str]]:
    """YouTube chapter list (first at 0:00) and a list of warnings."""
    chs = timeline["chapters"]
    long_video = timeline["duration"] >= 3600
    lines = [f"{timing.fmt_clock(c['start'], long_video)} {c['title']}" for c in chs]
    warnings = []
    if len(chs) < 3:
        warnings.append("YouTube needs at least 3 chapters")
    ends = [c["start"] for c in chs[1:]] + [timeline["duration"]]
    for c, end in zip(chs, ends):
        if end - c["start"] < MIN_CHAPTER_SECONDS:
            warnings.append(f"chapter {c['id']} is shorter than {MIN_CHAPTER_SECONDS}s")
    return "\n".join(lines) + "\n", warnings


def run(project_id: str, log=print) -> None:
    from cinefacts import plan as planmod
    from cinefacts import tts

    tl = tts.ensure_timeline(project_id)
    out = planmod.project_dir(project_id) / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "subs.srt").write_text(build_srt(tl), encoding="utf-8")
    chapters, warnings = build_chapters(tl)
    (out / "chapters.txt").write_text(chapters, encoding="utf-8")
    for w in warnings:
        log(f"warning: {w}")
    log(f"subs: wrote {out / 'subs.srt'} and {out / 'chapters.txt'}")
