"""tts step: Kokoro per sentence (cached by content hash), narration.wav, timeline.json."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from cinefacts import config, timing
from cinefacts import plan as planmod

SAMPLE_RATE = 24000  # Kokoro's native rate
MODEL_FILE = "kokoro-v1.0.onnx"
VOICES_FILE = "voices-v1.0.bin"
TRIM_DB = -45.0
TRIM_KEEP_HEAD = 0.04  # seconds of the natural attack/release kept around the speech
TRIM_KEEP_TAIL = 0.08
SAMPLE_TEXT = ("Walk through any airport at sunrise and you'll notice something strange. "
               "Almost every airliner, from every country, wears the same colour.")


class StaleAudio(RuntimeError):
    pass


def voice_settings(plan: dict, style: dict) -> tuple[str, float]:
    return plan.get("voice") or style["voice"], float(plan.get("speed") or style["speed"])


def model_tag() -> str:
    p = config.MODELS_DIR / MODEL_FILE
    return f"{MODEL_FILE}:{p.stat().st_size if p.exists() else 0}"


def sentence_key(text: str, voice: str, speed: float, model: str) -> str:
    return planmod.digest({"text": text, "voice": voice, "speed": speed, "model": model,
                           "trim": [TRIM_DB, TRIM_KEEP_HEAD, TRIM_KEEP_TAIL]})


def trim_silence(x: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Drop leading/trailing near-silence, keeping a short natural margin."""
    if x.size == 0:
        return x
    peak = float(np.max(np.abs(x)))
    if peak == 0.0:
        return x[:0]
    loud = np.flatnonzero(np.abs(x) > peak * 10 ** (TRIM_DB / 20))
    a = max(0, loud[0] - int(TRIM_KEEP_HEAD * sr))
    b = min(x.size, loud[-1] + 1 + int(TRIM_KEEP_TAIL * sr))
    return x[a:b]


class Synth:
    """Lazy Kokoro wrapper: the model loads only if something actually needs rendering."""

    def __init__(self):
        self._k = None

    def __call__(self, text: str, voice: str, speed: float) -> np.ndarray:
        if self._k is None:
            from kokoro_onnx import Kokoro
            self._k = Kokoro(str(config.MODELS_DIR / MODEL_FILE),
                             str(config.MODELS_DIR / VOICES_FILE))
        samples, sr = self._k.create(text, voice=voice, speed=speed, lang="en-us")
        if sr != SAMPLE_RATE:
            raise RuntimeError(f"Kokoro returned {sr} Hz, expected {SAMPLE_RATE}")
        return np.asarray(samples, dtype=np.float32)


def _read_cached(audio_dir: Path, sid: str, key: str) -> np.ndarray | None:
    wav, meta = audio_dir / f"{sid}.wav", audio_dir / f"{sid}.json"
    if not (wav.is_file() and meta.is_file()):
        return None
    try:
        if json.loads(meta.read_text())["key"] != key:
            return None
    except (ValueError, KeyError):
        return None
    data, sr = sf.read(wav, dtype="float32")
    return data if sr == SAMPLE_RATE else None


def build(project_id: str, synth=None, log=print) -> dict:
    """Make sure every sentence has audio, then write narration.wav and timeline.json.

    With synth=None nothing is rendered: missing or outdated sentence audio raises StaleAudio.
    That lets shots/subs/assemble rebuild the timeline cheaply after a plan edit.
    """
    plan = planmod.load(project_id)
    style = config.load_style(plan.get("style", "documentary"))
    pdir = planmod.project_dir(project_id)
    audio_dir = pdir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    voice, speed = voice_settings(plan, style)
    mtag = model_tag()

    rows = list(planmod.sentences(plan))
    clips: list[np.ndarray] = []
    keys: list[str] = []
    rendered = 0
    for n, (ch, s, _) in enumerate(rows, 1):
        text = planmod.spoken_text(s)
        key = sentence_key(text, voice, speed, mtag)
        audio = _read_cached(audio_dir, s["id"], key)
        if audio is None:
            if synth is None:
                raise StaleAudio(f"audio for {s['id']} is missing or outdated; "
                                 f"run ./run tts {project_id}")
            log(f"tts {n}/{len(rows)} {s['id']}: {text[:60]}")
            audio = trim_silence(synth(text, voice, speed))
            sf.write(audio_dir / f"{s['id']}.wav", audio, SAMPLE_RATE, subtype="PCM_16")
            (audio_dir / f"{s['id']}.json").write_text(json.dumps(
                {"key": key, "text": text, "voice": voice, "speed": speed, "model": mtag}))
            audio = sf.read(audio_dir / f"{s['id']}.wav", dtype="float32")[0]
            rendered += 1
        clips.append(audio)
        keys.append(key)

    tl = make_timeline(plan, style, [len(c) for c in clips])
    tl["audio_keys"] = planmod.digest(keys)
    narration = pdir / "narration.wav"
    old = _load_json(pdir / "timeline.json")
    if rendered or not narration.is_file() or not old \
            or old.get("audio_keys") != tl["audio_keys"] or old.get("layout") != tl["layout"]:
        buf = np.zeros(tl["layout"]["total_samples"], dtype=np.float32)
        for clip, s in zip(clips, tl["sentences"]):
            buf[s["start_sample"]:s["start_sample"] + len(clip)] = clip
        sf.write(narration, buf, SAMPLE_RATE, subtype="PCM_16")
    if old != tl:
        (pdir / "timeline.json").write_text(json.dumps(tl, indent=1, ensure_ascii=False))
    (pdir / "script.md").write_text(planmod.render_script_md(plan, tl), encoding="utf-8")
    if synth is not None:
        log(f"tts done: {rendered} rendered, {len(rows) - rendered} cached, "
            f"{tl['duration'] / 60:.2f} min narration")
    return tl


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def make_timeline(plan: dict, style: dict, durations: list[int]) -> dict:
    fps, sr = int(style["fps"]), SAMPLE_RATE
    rows = list(planmod.sentences(plan))
    lay = timing.layout_sentences(
        durations, [last for _, _, last in rows], sample_rate=sr, fps=fps,
        lead_in=style.get("lead_in", 0.0), pause_sentence=style["pause_sentence"],
        pause_chapter=style["pause_chapter"])
    frames = timing.shot_frames(
        lay, [[sh.get("weight", 1) for sh in s["shots"]] for _, s, _ in rows],
        sample_rate=sr, fps=fps)
    fade = round(style["chapter_fade"] * fps)

    sentences, shots, chapters = [], [], []
    for i, ((ch, s, last), fr) in enumerate(zip(rows, frames)):
        first_in_ch = s is ch["sentences"][0]
        if first_in_ch:
            chapters.append({"id": ch["id"], "title": ch["title"], "start_frame": fr[0][0],
                             "start": fr[0][0] / fps})
        sentences.append({
            "id": s["id"], "chapter": ch["id"], "text": s["text"],
            "start_sample": lay.starts[i], "end_sample": lay.ends[i],
            "start": lay.starts[i] / sr, "end": lay.ends[i] / sr,
        })
        for j, (sh, (a, b)) in enumerate(zip(s["shots"], fr)):
            n = b - a
            fin = min(fade, n // 2) if first_in_ch and j == 0 else 0
            fout = min(fade, n - fin) if last and j == len(fr) - 1 else 0
            shots.append({"id": sh["id"], "sentence": s["id"], "chapter": ch["id"],
                          "start_frame": a, "end_frame": b, "frames": n,
                          "fade_in": fin, "fade_out": fout})
    total_frames = timing.samples_to_frame(lay.total, sr, fps)
    return {
        "fps": fps, "sample_rate": sr, "total_frames": total_frames,
        "duration": total_frames / fps,
        "layout": {"total_samples": lay.total, "lead_in_samples": lay.lead_in},
        "chapters": chapters, "sentences": sentences, "shots": shots,
    }


def ensure_timeline(project_id: str) -> dict:
    """Rebuild timeline.json from cached audio (no TTS). Raises StaleAudio if TTS is needed."""
    return build(project_id, synth=None)


def voice_samples(project_id: str, voices: list[str], text: str = SAMPLE_TEXT,
                  log=print) -> list[Path]:
    plan = planmod.load(project_id)
    style = config.load_style(plan.get("style", "documentary"))
    _, speed = voice_settings(plan, style)
    out = planmod.project_dir(project_id) / "out" / "voices"
    out.mkdir(parents=True, exist_ok=True)
    synth, paths = Synth(), []
    for v in voices:
        path = out / f"{v}.wav"
        log(f"voice sample {v}")
        sf.write(path, trim_silence(synth(text, v, speed)), SAMPLE_RATE, subtype="PCM_16")
        paths.append(path)
    return paths
