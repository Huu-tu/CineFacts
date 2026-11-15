---
name: make-video
description: Produce a CineFacts documentary video (16:9, English narration) from a storyboard or just a topic, with three owner checkpoints. Use when the owner asks to make, continue, or fix a video.
---

# make-video

Talk to the owner in Vietnamese. Video content is English. Read `CLAUDE.md` first.
Steps marked *(roadmap step N)* are not built yet. Tell the owner which step is missing
instead of improvising.

## 0. Project
- Pick a short ASCII slug `<id>` and create `projects/<id>/`.
- The storyboard comes from the owner (pasted, or an uploaded file) and is saved as
  `projects/<id>/storyboard.md`.
- If the owner gives only a topic and length, research it and draft `storyboard.md`
  yourself. **Checkpoint 1:** owner approves the storyboard.

## 1. Script and facts *(roadmap step 2)*
- List every factual claim in `facts.md` with a verdict (true / misleading / false) and a
  source URL. Reword or drop anything not well supported.
- Write `plan.json` (chapters → sentences → shots with search queries), then generate
  `script.md` from it.
- For the first project only, render 3 short voice samples.
- **Checkpoint 2:** owner approves `script.md` and `facts.md` (and picks a voice).

## 2. Voice and timeline *(roadmap step 2)*
- `./run tts <id>` writes `audio/`, `narration.wav` and `timeline.json`.

## 3. Visuals *(roadmap step 3)*
- `./run search <id>` writes candidates and per-chapter contact sheets in `media/sheets/`.
- Review each sheet image. Override bad auto picks in `plan.json`, re-query empty rows,
  then run `./run fetch <id>`.

## 4. Preview *(roadmap steps 2–4)*
- `./run all <id> --preview` produces `out/preview_720p.mp4`.
- **Checkpoint 3:** give the owner the absolute path, then apply their corrections by
  editing `plan.json` and re-running.

## 5. Final and delivery *(roadmap steps 4–5)*
- `./run all <id>` produces the final; then run `./run qa <id>` and fix any failures.
- Write `out/youtube.txt` (title, description with chapters and credits, tags).
- `./run publish <id>` uploads to Drive `CineFacts/<id>/`. Report the folder.
- Commit the text files and push.
- After the owner confirms the video is posted: `./run clean <id>`.
