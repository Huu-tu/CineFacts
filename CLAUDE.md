# CineFacts

Automated pipeline for faceless English explainer documentaries: storyboard in, 1920x1080 / 24 fps
`final.mp4` + SRT + chapters + credits out. Claude makes the creative calls (script, facts, shot
list, clip picks); scripts do everything deterministic. Full design:
`docs/superpowers/specs/2026-11-15-cinefacts-video-pipeline-design.md`.

## Commands

| Command | What it does |
|---|---|
| `./setup.sh` | install or repair everything (Ubuntu 24.04, run as root, safe to re-run) |
| `./run doctor` | check the environment; every FAIL line prints its fix |
| `./run doctor --offline` | same, without the live Pixabay call |
| `.venv/bin/python -m pytest -q` | run the tests |

Pipeline steps (all take a project id; `shots`, `assemble`, `all` take `--preview` for 720p):

| Command | What it does |
|---|---|
| `./run script <id>` | validate `plan.json`, regenerate `script.md` (cheap, no lock) |
| `./run voices <id> [--voices a,b,c]` | short voice samples to `out/voices/<voice>.wav` |
| `./run tts <id>` | Kokoro per sentence (`audio/`, cached by text+voice+speed+model), `narration.wav`, `timeline.json`, `script.md` |
| `./run shots <id> [--preview]` | one cached clip per shot in `cache/shots/` (placeholder cards until step 3) |
| `./run assemble <id> [--preview]` | concat clips, normalise narration (compressor → gain → 192 kHz true-peak limiter), mux to `out/preview_720p.mp4` / `out/final.mp4` |
| `./run subs <id>` | `out/subs.srt`, `out/chapters.txt` (cheap, no lock) |
| `./run all <id> [--preview]` | tts → shots → assemble → subs, redoing only what changed |

`search`, `fetch` (step 3), `publish`, `clean` (step 4) and `qa` (step 5) still print
"not implemented yet". Heavy steps re-exec themselves under `systemd-run --scope -p MemoryMax`
+ `nice`/`ionice` and take `.heavy.lock`; progress is appended to `projects/<id>/render.log`.
Set `CINEFACTS_NO_GUARD=1` to skip the wrapper (tests, debugging). Editing `plan.json` never
needs a full re-run: shots/subs/assemble rebuild `timeline.json` from cached audio, and only
sentences whose spoken text changed are re-synthesised.

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
- Commit after each completed step, but **never push**. The VPS has no deploy key (owner's
  choice); the owner pushes from the VPS with their own GitHub credentials. When a step is
  done, tell the owner it is committed and ready for them to `git push`. Run `git pull` at the
  start of a session. Never commit `.env`, media, models or videos.
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
- 2026-11-15: the repo was made public and the deploy key was dropped (owner's decision).
- 2026-11-15: Kokoro **fp32** model kept (`kokoro-v1.0.onnx`): ~0.9x real time on 2 vCPU,
  ~600 MB RSS, so a 10-min narration takes ~10 min once and is cached per sentence afterwards.
- 2026-11-15: timing model. Audio positions are integer samples (24 kHz = 1000 samples per
  frame); each shot boundary is snapped to the frame grid independently (cumulative rounding).
  0.5 s lead-in belongs to the first shot; each pause belongs to the shot before it. Chapter
  boundaries dip to black (`chapter_fade` each side, baked into the clips). Kokoro output is
  trimmed at -45 dB with 40/80 ms margins so pauses come only from the style.
- 2026-11-15: audio normalisation is not ffmpeg `loudnorm` (see errors table). The chain is a
  gentle compressor, gain measured with `ebur128` (corrected up to 3 times), and an `alimiter`
  at 192 kHz set 1 dB under the ceiling: demo narration lands at -14.2 LUFS, -1.8 dBTP after AAC.
- 2026-11-15: plan.json for a new project may be authored from a compact text draft, but once
  committed, plan.json is edited directly and IDs never change.

## Errors we hit and fixes

| Date | Symptom | Cause | Fix |
|---|---|---|---|
| 2026-11-15 | Pixabay API returns `HTTP 403`, body `error code: 1010` (curl works) | Cloudflare blocks the default `Python-urllib` User-Agent | Send `config.USER_AGENT` on **every** HTTP request (providers too) |
| 2026-11-15 | `claude: command not found` after setup | the native installer puts it in `~/.local/bin`, which is not on PATH in minimal Ubuntu | setup.sh appends the PATH line to `~/.bashrc`; open a new shell or `source ~/.bashrc` |
| 2026-11-15 | `git clone` asks for a username | repo was private | owner made the repo public (no deploy key) |
| 2026-11-15 | `rclone config create gdrive drive token='eyJ...'` hangs | `rclone authorize` prints a base64 wrapper `{client_id, client_secret, token}`; `config create` wants the inner `token` JSON and otherwise waits for interactive auth | decode it: `T=$(echo '<blob>' \| base64 -d \| python3 -c 'import json,sys;print(json.load(sys.stdin)["token"])')`, then `rclone config create gdrive drive scope=drive.file token="$T" --non-interactive` (or paste the blob into the interactive `rclone config` prompt) |
| 2026-11-15 | preview at -15.3 LUFS instead of -14; later true peak +0.2 dBTP | Kokoro speech has a ~24 dB peak-to-loudness ratio, so two-pass `loudnorm` falls back to dynamic mode and undershoots; `alimiter` at 24 kHz only limits sample peaks | compressor + measured gain + limiter run at 192 kHz (`render.normalize_audio`) |
