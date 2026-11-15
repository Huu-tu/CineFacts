"""ffmpeg smoke test on tiny inputs: placeholder clips keep exact frame counts through concat."""
import shutil
import subprocess

import pytest

from cinefacts import render

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")

M = {"mode": "preview", "width": 160, "height": 90, "fps": 24, "preset": "ultrafast",
     "crf": 30, "threads": 2}


def count_frames(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                        "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return int(r.stdout.strip())


def test_fade_filter():
    assert render.fade_filter(48, 0, 0) == ""
    assert render.fade_filter(48, 12, 12) == "fade=t=in:s=0:n=12,fade=t=out:s=36:n=12"


def test_cards_render_concat_and_mux(tmp_path):
    clips = []
    for i, frames in enumerate([7, 31]):
        card = tmp_path / f"c{i}.png"
        render.placeholder_card(card, 160, 90, shot_id=f"c01s00{i}a", query="q", text="t",
                                chapter="Intro")
        clip = tmp_path / f"s{i}.mp4"
        render.render_card_clip(card, clip, M, frames, fade_in=3 if i == 0 else 0,
                                fade_out=5 if i == 1 else 0)
        assert count_frames(clip) == frames
        clips.append(clip)
    lst = tmp_path / "list.txt"
    lst.write_text("".join(f"file '{c}'\n" for c in clips))
    video = tmp_path / "v.mp4"
    render.ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(video)])
    assert count_frames(video) == 38

    wav = tmp_path / "a.wav"
    render.ffmpeg(["-f", "lavfi", "-i", "sine=f=440:d=1.583333", "-ar", "24000", str(wav)])
    norm = tmp_path / "n.wav"
    render.normalize_audio(wav, norm, {"loudness": {"integrated_lufs": -14,
                                                    "true_peak_db": -1}})
    info = render.probe(norm)["streams"][0]
    assert info["codec_type"] == "audio"
