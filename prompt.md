I want you to build an automated video-creation repo with me, running on my VPS. The full, agreed design is in `docs/superpowers/specs/2026-11-15-cinefacts-video-pipeline-design.md`. Read it before doing anything. This file is the short brief.

## Context
- Channel: **CineFacts**. Faceless English explainer documentaries in the style of `projects/demo/storyboard.md`, for example "Why are airplanes white?".
- Output: horizontal **1920x1080, 24 fps, 8–12 minutes**, with chapters and a cinematic look (warm grade, close-ups, calm narration).
- Content language: **English** (narration and captions). Captions ship as an **SRT file** uploaded to YouTube, not burned in.
- Machine: Ubuntu 24.04 VPS with 2 vCPU (Xeon E5-2696 v4, AVX2), 3.8 GB RAM plus 2 GB swap, about 34 GB free disk, no GPU. Nothing else runs on it.
- Repo: `github.com/Huu-tu/CineFacts` (public). On the VPS it lives at `/root/CineFacts`.
- I work over SSH (Termius) in tmux, move files with SFTP, and drive everything by talking to Claude Code running on the VPS.

## Decisions already made
- **Visuals:** stock footage from the **Pixabay API** (free key in `.env`), plus **Wikimedia Commons** for specific subjects. Providers are pluggable (Pexels key issuance is paused; it may be added later). No local AI image generation.
- **Voice:** **Kokoro TTS via kokoro-onnx**, running locally on the CPU.
- **Free tools and services only.** Ask me before installing anything larger than ~500 MB or using a paid service.

## Design principles
- You (Claude) handle the creative work: research and fact-check, write the narration, write `plan.json` (chapters, sentences, shots, search keywords), and pick the best clip for each shot from the contact sheets. Scripts handle the deterministic work: TTS, search, download, timing, rendering, mixing, subtitles, credits, QA.
- `plan.json` is the single source of truth. Every step saves its result as a file in `projects/<id>/` and is cached by input hash, so fixing one sentence or shot only redoes what depends on it.
- Timing must be frame-accurate (1/24 s grid, cumulative rounding) and unit-tested.
- Facts matter: every factual claim goes into `facts.md` with a verdict and a source. Doubtful claims get reworded or cut.
- Respect provider terms: cache searches, download only the picked assets, and credit everything in `credits.txt`.
- Protect the VPS: heavy steps run with nice/ionice and a memory cap, ffmpeg uses at most 2 threads, one heavy job at a time.
- Keep it simple. Don't add heavy libraries or services until they're needed.

## Workflow per video
1. I paste a storyboard, point to a file I uploaded, or just give a topic (then you draft the storyboard).
2. You run the `make-video` skill and stop at three checkpoints: **storyboard** (if you drafted it) → **script.md + facts.md** (plus voice samples for the first project) → **out/preview_720p.mp4**.
3. After I approve the preview, you render `final.mp4`, run QA, and give me the paths of `final.mp4`, `subs.srt`, `chapters.txt` and `credits.txt` for SFTP download.

## Roadmap (one step at a time; tell me when each step is done)
1. Repo skeleton, `setup.sh` (one-command install on Ubuntu 24.04, including Node and Claude Code) and `./run doctor` (reports what's missing and the command to fix it).
2. Voice and timing: Claude writes `plan.json`, `facts.md` and `script.md` for the demo. Then TTS, the timeline, and a placeholder-card preview with real narration, SRT and chapters.
3. Real visuals: Pixabay and Wikimedia search, contact sheets, Claude picks, fetch, Ken Burns, colour grade, credits.
4. The preview → approve → final loop, with `CLAUDE.md` and `.claude/skills/make-video/SKILL.md` complete.
5. Automated QA: duration, loudness (-14 LUFS, ≤ -1 dBTP), resolution/fps, A/V sync, black frames, no placeholders, credits complete.
6. Only once the core is stable: music ducking, overlays/HUD, chapter cards, an AI-image provider, more styles, a web preview page, Shorts cut-downs.

## MVP is done when
- Running `setup.sh` on a clean VPS installs everything.
- `./run all demo` produces `out/final.mp4` from `projects/demo/`, with English narration, Pixabay footage, SRT, chapters and credits, and QA passes.
- `CLAUDE.md` and SKILL.md are good enough that a fresh Claude session can make a new video without me explaining anything again.

## How to work with me
- Reply to me in Vietnamese.
- Before each major step, briefly say what you're about to do.
- When you need me to check a video, give me the absolute file path so I can download it over SFTP.
- Use git: commit after each completed step, with clear messages. Never commit `.env`, media, models or rendered videos.
