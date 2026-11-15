# CineFacts

Automated pipeline for faceless English explainer documentaries: storyboard in, 1920x1080 / 24 fps
`final.mp4` + SRT + chapters + credits out. Claude makes the creative calls (script, facts, shot
list, clip picks); scripts do everything deterministic. Full design:
`docs/superpowers/specs/2026-11-15-cinefacts-video-pipeline-design.md`.

## Commands

| Command | What it does |
|---|---|
| `./setup.sh` | install or repair everything (Ubuntu 24.04, run as root, safe to re-run) |
| `./setup.sh --deploy-key` | create the GitHub deploy key so the VPS can push |
| `./run doctor` | check the environment; every FAIL line prints its fix |
| `./run doctor --offline` | same, without the live Pixabay call |
| `.venv/bin/python -m pytest -q` | run the tests |

Pipeline steps (`tts`, `search`, `fetch`, `shots`, `assemble`, `subs`, `qa`, `publish`, `clean`,
`all`) are wired into `./run` but print "not implemented yet" until their roadmap step lands.

### Google Drive setup (one time, owner)

1. On the VPS, run `rclone config` and create a new remote:
   - name `gdrive`
   - storage `drive`
   - leave client id and secret empty
   - scope `drive.file` (rclone sees only files it creates)
   - answer **n** to "Use auto config?"
2. rclone prints an `rclone authorize "drive" "..."` command. Run it on a PC with a browser
   (rclone must be installed there; on Windows, `winget install Rclone.Rclone`). Log in, then
   paste the token it prints back into the VPS prompt.
3. Test with `rclone mkdir gdrive:CineFacts && rclone lsd gdrive:`.

## Conventions

- One folder per video: `projects/<id>/`, where `<id>` is a short ASCII slug. Layout:
  - `storyboard.md`, `facts.md`, `plan.json`, `script.md`: committed
  - `audio/`, `narration.wav`, `timeline.json`, `media/`, `cache/`, `out/`, `qa.json`: ignored
    and rebuildable
- `plan.json` is the single source of truth. `script.md` is generated from it. IDs (`c01`,
  `c01s001`, `c01s001a`) never change once written.
- Video content is English. Talk to the owner in **Vietnamese**.
- When the owner must check a file, give its **absolute path** (they download it over SFTP),
  or the Drive folder once publish exists.
- Commit and push after each completed step. Never commit `.env`, media, models or videos.
- Never print, log or commit the Pixabay key.

## Resource rules (2 vCPU, 3.8 GB RAM VPS)

- Heavy steps run under `nice -n 10 ionice -c3`, inside
  `systemd-run --scope -p MemoryMax=2500M` when available.
- ffmpeg gets `-threads 2`.
- Only one heavy job at a time.
- Long renders run in the background in tmux and log to `projects/<id>/render.log`.

## Decisions log

- Claude Code is installed with the native installer (`curl -fsSL https://claude.ai/install.sh | bash`).
  No Node.js is needed, which differs from the spec's "Node.js LTS".
- Pexels API key issuance is paused (2026-11), so Pixabay is the primary stock provider.

## Errors we hit and fixes

| Date | Symptom | Cause | Fix |
|---|---|---|---|
