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

## 1. Script and facts
- Research the topic first (web search). List every factual claim in `facts.md`: one table row
  per claim with the sentence ID(s), a verdict (true / plausible / misleading / unproven) and
  source URL(s). Doubtful storyboard claims get their own table saying what the script does
  instead. Check anything time-sensitive against the current date (e.g. the Air Force One
  livery changed in 2026). See `projects/demo/facts.md` for the format.
- Write `plan.json` (shape: spec section 7; example: `projects/demo/plan.json`):
  - 8–12 min: about 1,500–1,700 words; Kokoro `am_michael` reads ~150 wpm, plus pauses.
  - One sentence per narration line; IDs `c01`, `c01s001`, `c01s001a`, never renumbered once
    committed (add new sentences at the end of a chapter or accept a gap).
  - Shots of 4–8 s: one shot per sentence, a second shot only when the sentence runs over
    ~8 s (about 20+ words). Queries are short concrete stock-footage phrases.
  - Use `say` for anything Kokoro misreads: model numbers ("seven eighty-seven"), years
    ("nineteen ninety-six"), "Mach two", flight numbers, non-English names.
  - New shots: `"pick": null`, `"kind": "video"`, `"providers": ["pixabay"]`.
- `./run script <id>` validates the plan and regenerates `script.md`.
- For the first project only: `./run voices <id>` renders samples to `out/voices/`.
- **Checkpoint 2:** owner approves `script.md` and `facts.md` (and picks a voice; set
  `"voice"` in plan.json).

## 2. Voice and timeline
- `./run tts <id>` writes `audio/`, `narration.wav`, `timeline.json` and `script.md` (with the
  real chapter start times). It takes ~1 min per minute of narration the first time, then
  only changed sentences are re-rendered. Run it in the background; it logs to `render.log`.
- If the narrated length misses `target_minutes` by more than ~15%, trim or extend the script.

## 3. Visuals *(roadmap step 3)*
- `./run search <id>` writes candidates and per-chapter contact sheets in `media/sheets/`.
- Review each sheet image. Override bad auto picks in `plan.json`, re-query empty rows,
  then run `./run fetch <id>`.

## 4. Preview
- `./run all <id> --preview` produces `out/preview_720p.mp4`, `out/subs.srt` and
  `out/chapters.txt`. Shots without a `pick` render as placeholder cards.
- **Checkpoint 3:** give the owner the absolute path, then apply their corrections by
  editing `plan.json` and re-running.

## 5. Final and delivery *(roadmap steps 4–5)*
- `./run all <id>` produces the final; then run `./run qa <id>` and fix any failures.
- Write `out/youtube.txt` (title, description with chapters and credits, tags).
- `./run publish <id>` uploads to Drive `CineFacts/<id>/`. Report the folder.
- Commit the text files and push.
- After the owner confirms the video is posted: `./run clean <id>`.
