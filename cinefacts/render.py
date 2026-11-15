"""shots + assemble steps: one cached clip per shot, then concat and mux with the narration.

Every shot clip of one mode (preview/final) uses identical codec parameters, so concat is a
stream copy. Roadmap step 2 renders every shot as a placeholder card; real footage arrives in
step 3.
"""
from __future__ import annotations

import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from cinefacts import config, tts
from cinefacts import plan as planmod

CARD_VERSION = 1
AUDIO_RATE = 48000
AUDIO_BITRATE = "192k"
# Audio aims below the style's true-peak ceiling: TP_MARGIN of headroom for AAC encoding,
# plus LIMITER_MARGIN because a gain correction after limiting can lift peaks slightly.
TP_MARGIN = 0.5
LIMITER_MARGIN = 0.5
COMPRESSOR = "acompressor=threshold=-30dB:ratio=3:attack=5:release=150:knee=4"


def mode_settings(style: dict, preview: bool) -> dict:
    res = style["preview"]["resolution"] if preview else style["resolution"]
    enc = style["preview"] if preview else style["final"]
    return {"mode": "preview" if preview else "final", "width": int(res[0]),
            "height": int(res[1]), "fps": int(style["fps"]), "preset": enc["x264_preset"],
            "crf": int(enc["crf"]), "threads": int(style["resources"]["ffmpeg_threads"])}


def ffmpeg(args: list[str], threads: int = 2) -> subprocess.CompletedProcess:
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
           "-filter_threads", str(threads), *args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({r.returncode}): {' '.join(cmd)}\n{r.stderr[-2000:]}")
    return r


def video_codec_args(m: dict) -> list[str]:
    return ["-c:v", "libx264", "-preset", m["preset"], "-crf", str(m["crf"]),
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-r", str(m["fps"]),
            "-g", str(m["fps"] * 2), "-threads", str(m["threads"]),
            "-video_track_timescale", str(m["fps"] * 1000), "-an"]


# ---------- placeholder cards ----------

@lru_cache(maxsize=None)
def font_path(bold: bool = False) -> str | None:
    pattern = "Inter:style=Bold" if bold else "Inter:style=Regular"
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True,
                             text=True, timeout=10).stdout.strip()
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None


def _font(size: int, bold: bool = False):
    p = font_path(bold)
    return ImageFont.truetype(p, size) if p else ImageFont.load_default(size)


def _wrap_px(draw, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        cand = f"{cur} {w}" if cur else w
        if cur and draw.textlength(cand, font=font) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    return lines + ([cur] if cur else [])


def placeholder_card(path: Path, w: int, h: int, *, shot_id: str, query: str, text: str,
                     chapter: str) -> None:
    img = Image.new("RGB", (w, h), (17, 20, 24))
    d = ImageDraw.Draw(img)
    u = h / 1080
    pad = int(90 * u)
    d.text((pad, pad), chapter.upper(), font=_font(int(34 * u), True), fill=(200, 160, 90))
    d.text((pad, pad + int(70 * u)), shot_id, font=_font(int(96 * u), True),
           fill=(235, 235, 235))
    qf = _font(int(44 * u))
    y = pad + int(210 * u)
    for line in _wrap_px(d, f"search: {query}", qf, w - 2 * pad)[:2]:
        d.text((pad, y), line, font=qf, fill=(150, 170, 190))
        y += int(58 * u)
    tf = _font(int(40 * u))
    y = h - pad - int(52 * u) * 4
    for line in _wrap_px(d, f"“{text}”", tf, w - 2 * pad)[:4]:
        d.text((pad, y), line, font=tf, fill=(120, 120, 120))
        y += int(52 * u)
    label = "PLACEHOLDER"
    lf = _font(int(30 * u), True)
    d.text((w - pad - d.textlength(label, font=lf), pad), label, font=lf, fill=(200, 70, 60))
    img.save(path)


def fade_filter(frames: int, fade_in: int, fade_out: int) -> str:
    f = []
    if fade_in:
        f.append(f"fade=t=in:s=0:n={fade_in}")
    if fade_out:
        f.append(f"fade=t=out:s={frames - fade_out}:n={fade_out}")
    return ",".join(f)


def render_card_clip(card: Path, out: Path, m: dict, frames: int, fade_in: int = 0,
                     fade_out: int = 0) -> None:
    vf = ",".join(x for x in [f"scale={m['width']}:{m['height']}", "format=yuv420p",
                              fade_filter(frames, fade_in, fade_out)] if x)
    tmp = out.with_suffix(".tmp.mp4")
    ffmpeg(["-loop", "1", "-framerate", str(m["fps"]), "-i", str(card), "-vf", vf,
            "-frames:v", str(frames), "-tune", "stillimage", *video_codec_args(m), str(tmp)],
           m["threads"])
    tmp.replace(out)


# ---------- steps ----------

def render_shots(project_id: str, preview: bool, log=print) -> list[Path]:
    plan = planmod.load(project_id)
    style = config.load_style(plan.get("style", "documentary"))
    tl = tts.ensure_timeline(project_id)
    m = mode_settings(style, preview)
    pdir = planmod.project_dir(project_id)
    shot_dir, card_dir = pdir / "cache" / "shots", pdir / "cache" / "cards"
    shot_dir.mkdir(parents=True, exist_ok=True)
    card_dir.mkdir(parents=True, exist_ok=True)

    info = {}
    for ch, s, _ in planmod.sentences(plan):
        for sh in s["shots"]:
            info[sh["id"]] = (ch, s, sh)

    paths, rendered = [], 0
    for n, t in enumerate(tl["shots"], 1):
        ch, s, sh = info[t["id"]]
        card = {"v": CARD_VERSION, "shot": sh["id"], "query": sh["query"], "text": s["text"],
                "chapter": ch["title"], "w": m["width"], "h": m["height"]}
        key = planmod.digest({"card": card, "mode": m, "frames": t["frames"],
                              "fade": [t["fade_in"], t["fade_out"]]})
        out = shot_dir / f"{sh['id']}-{m['mode']}-{key}.mp4"
        if not out.is_file():
            card_png = card_dir / f"{sh['id']}-{planmod.digest(card)}.png"
            if not card_png.is_file():
                placeholder_card(card_png, m["width"], m["height"], shot_id=sh["id"],
                                 query=sh["query"], text=s["text"], chapter=ch["title"])
            render_card_clip(card_png, out, m, t["frames"], t["fade_in"], t["fade_out"])
            rendered += 1
            if rendered % 10 == 1:
                log(f"shots {n}/{len(tl['shots'])} ({m['mode']})")
        paths.append(out)
    _prune(shot_dir, {p.name for p in paths}, m["mode"])
    log(f"shots done: {rendered} rendered, {len(paths) - rendered} cached")
    return paths


def _prune(shot_dir: Path, keep: set[str], mode: str) -> None:
    """Delete outdated clips of this mode so the cache does not grow without bound."""
    for p in shot_dir.glob(f"*-{mode}-*.mp4"):
        if p.name not in keep:
            p.unlink()


def loudness_targets(style: dict) -> tuple[float, float]:
    ln = style["loudness"]
    return float(ln["integrated_lufs"]), float(ln["true_peak_db"]) - TP_MARGIN


def _audio_chain(gain_db: float, limit_db: float) -> str:
    # The limiter runs at 192 kHz so it catches inter-sample (true) peaks, not just samples.
    return (f"{COMPRESSOR},volume={gain_db:.2f}dB,aresample=192000,"
            f"alimiter=limit={limit_db:.2f}dB:attack=3:release=60:level=false,"
            f"aresample={AUDIO_RATE}")


def measure_loudness(src: Path, af: str, threads: int = 2) -> tuple[float, float]:
    """(integrated LUFS, true peak dBTP) of src after the filter chain af."""
    r = ffmpeg(["-loglevel", "info", "-i", str(src), "-af", f"{af},ebur128=peak=true",
                "-f", "null", "-"], threads)
    summary = r.stderr[r.stderr.rindex("Summary:"):]
    i = float(re.search(r"I:\s+(-?[\d.]+) LUFS", summary).group(1))
    tp = float(re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary).group(1))
    return i, tp


def normalize_audio(src: Path, dst: Path, style: dict, threads: int = 2) -> tuple[float, float]:
    """Gentle compression, gain to the LUFS target, oversampled true-peak limiter.

    Kokoro speech has a ~24 dB peak-to-loudness ratio, so plain linear loudnorm cannot reach
    -14 LUFS under -1 dBTP, and its dynamic mode undershoots (-15.3 measured). The gain is
    corrected from measurements until within 0.15 LU (at most 3 passes)."""
    target, tp_max = loudness_targets(style)
    i, _ = measure_loudness(src, COMPRESSOR, threads)
    gain = target - i
    for _ in range(3):
        i, tp = measure_loudness(src, _audio_chain(gain, tp_max - LIMITER_MARGIN), threads)
        if abs(target - i) < 0.15:
            break
        gain += target - i
    tmp = dst.with_suffix(".tmp.wav")
    ffmpeg(["-i", str(src), "-af", _audio_chain(gain, tp_max - LIMITER_MARGIN),
            "-c:a", "pcm_s16le", str(tmp)], threads)
    tmp.replace(dst)
    return i, tp


def assemble(project_id: str, preview: bool, clips: list[Path] | None = None,
             log=print) -> Path:
    plan = planmod.load(project_id)
    style = config.load_style(plan.get("style", "documentary"))
    tl = tts.ensure_timeline(project_id)
    m = mode_settings(style, preview)
    pdir = planmod.project_dir(project_id)
    cache = pdir / "cache"
    if clips is None:
        clips = render_shots(project_id, preview, log)

    lst = cache / f"concat-{m['mode']}.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in clips))
    video = cache / f"video-{m['mode']}.mp4"
    ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(video)],
           m["threads"])

    narration = pdir / "narration.wav"
    akey = planmod.digest({"wav": _file_digest(narration), "ln": loudness_targets(style),
                          "chain": _audio_chain(0, 0)})
    norm = cache / f"narration-norm-{akey}.wav"
    if not norm.is_file():
        for old in cache.glob("narration-norm-*.wav"):
            old.unlink()
        log("assemble: loudness normalisation")
        i, tp = normalize_audio(narration, norm, style, m["threads"])
        log(f"assemble: narration at {i:.1f} LUFS, {tp:.1f} dBTP")

    out_dir = pdir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / ("preview_720p.mp4" if preview else "final.mp4")
    tmp = out.with_suffix(".tmp.mp4")
    ffmpeg(["-i", str(video), "-i", str(norm), "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", str(AUDIO_RATE),
            "-t", f"{tl['duration']:.6f}", "-movflags", "+faststart", str(tmp)], m["threads"])
    tmp.replace(out)
    log(f"assemble: wrote {out} ({tl['duration'] / 60:.2f} min)")
    return out


def _file_digest(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,width,height,r_frame_rate,nb_frames,duration",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)
