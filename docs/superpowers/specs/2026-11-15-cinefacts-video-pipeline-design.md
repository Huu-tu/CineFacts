# CineFacts video pipeline: design

Date: 2026-11-15
Status: draft, awaiting the owner's approval

## 1. Intent

CineFacts is a faceless YouTube channel of English-language explainer documentaries
("Why are airplanes white?"). Each video runs 8–12 minutes in 16:9 and has a cinematic look:
warm graded footage, close-ups, occasional HUD-style graphics, calm narration, and chapters.
The reference style is `storyboard.md` plus six reference frames the owner shared (airport at
sunrise, a jet in steam, an AI-style HUD over carbon fibre, a macro crack on a fuselage, a
technician with a flashlight, a thermal-camera plane).

The owner wants to go from a storyboard to a publishable video with as little manual work as
possible. The work is split like this:

- **Claude** makes the creative decisions: the narration script, the fact-checking, the shot
  list, the search keywords, and which stock clip fits each shot.
- **Scripts** do everything deterministic: TTS, downloading, timing, rendering, mixing, QA.

Every step writes its result to a file in the project folder, so changing one sentence or one
shot only redoes the work that depends on it.

## 2. Goals, non-goals, anti-goals

**Goals**
- Turn `projects/<id>/storyboard.md` into `final.mp4` (1920x1080, 24 fps, H.264/AAC),
  `subs.srt`, `chapters.txt` (YouTube chapter timestamps), `credits.txt`, and `youtube.txt`
  (title, description with chapters and credits, tags; written by Claude).
- Archive every finished video to the owner's **Google Drive** (`CineFacts/<id>/`), so it can
  be watched or downloaded from a phone, and so the VPS disk can be cleaned.
- Run entirely on the owner's VPS: 2 vCPU, 3.8 GB RAM, 34 GB free disk, no GPU.
- Use only free tools and services.
- Make every step re-runnable and cached, with the same inputs giving the same timing and content.
- Let a fresh Claude Code session produce a video from `CLAUDE.md` and the `make-video` skill
  alone.

**Non-goals (for now)**
- Talking-head editing and silence trimming. That was the original idea and has been dropped.
- Vertical Shorts. They may come later as cut-downs of chapters.
- Burned-in captions. Captions ship as SRT and are uploaded to YouTube.
- A web UI. A small password-protected preview page may come at roadmap step 6.
- Generating AI images or video on the VPS. It is not viable on 2 old CPU cores.
- Paid APIs, and any language other than English for the content.

**Anti-goals (failure even if it "works")**
- Publishing unverified or false claims. The channel is called *Facts*. Doubtful points in the
  storyboard (for example "white paint is lighter" or "white helps birds avoid planes") must
  be checked and reworded or dropped.
- Breaking stock-provider terms: no mass downloading, no missing attribution.
- Making the owner hand-edit JSON. Claude edits plan files in conversation.
- A render that starves the VPS until SSH or tmux sessions die.
- Low-effort, repetitive output. YouTube's "inauthentic / mass-produced content" policy is the
  risk, and original, researched scripts are the defence.

## 3. Constraints

| Constraint | Detail |
|---|---|
| Hardware | Intel Xeon E5-2696 v4, 2 vCPU (AVX2), 3.8 GB RAM plus 2 GB swap, 38 GB disk with 34 GB free, Ubuntu 24.04.4. Nothing else runs on it now. |
| Installed already | Python 3.12.3, git, Docker (unused). Missing: ffmpeg, pip/venv, tmux, Node. |
| Installs | Ask the owner before any single install larger than ~500 MB, and before using any paid service. |
| Pixabay API | Free key, already obtained. 100 requests per 60 s. Search results must be cached for 24 h. Files must be downloaded rather than hotlinked. Systematic mass downloads are forbidden. Video "medium" is 1920x1080 (older clips 1280x720). Photos are at most 1280 px wide without "full API access", so photos look soft at 1080p and video clips are preferred. |
| Pexels | New API keys are paused. The design keeps providers pluggable so Pexels can be added later. |
| Wikimedia Commons | Free, no key. Used for specific subjects (Concorde, a named aircraft) that stock sites lack. Assume the channel will be monetised, so **only CC0, Public Domain and CC BY (any version) are allowed**. CC BY-SA, any NC, any ND, and unknown licences are filtered out at search time and rejected by QA. Author and licence go into credits. *(Claude's call: the safe default.)* |
| Storage | Owner chose **Google Drive via rclone** for long-term storage (free 15 GB, shared with Gmail, so about 20 finals). rclone uses the `drive.file` scope, so it can only see files it created itself. Authorisation is a one-time owner step (headless flow: `rclone authorize "drive"` on a machine with a browser). A final is about 0.4–0.8 GB and a project's media and cache 2–5 GB, so the VPS keeps only active projects. |
| Claude usage | The owner is on **Claude Pro**, so Claude's per-video work must be economical (see the pick step in section 8). |
| Secrets | `.env` on the VPS only, never committed. Holds `PIXABAY_API_KEY`. |
| Repo | `github.com/Huu-tu/CineFacts`, public. The repo root *is* the pipeline (no `video-factory/` subfolder). The VPS clones it to `/root/CineFacts` and **has push rights through a write-enabled deploy key** (owner approved). Commits made during video work are pushed from the VPS. |
| Public repo hygiene | No secrets, no media, and no third-party copyrighted material in git. That includes the six reference frames, which are screenshots of someone else's video. |
| Language | Video content is English. Claude talks to the owner in Vietnamese. |

## 4. Approaches considered

Each was discussed with the owner, and the owner chose.

**Visual source**
| Option | Trade-off | Decision |
|---|---|---|
| Stock video API (Pixabay; Pexels is paused) | Real cinematic footage, free, automatable. Specific subjects may be missing. | **Chosen as the primary source.** |
| AI images from a free online service (Pollinations, Cloudflare Workers AI…) | Covers concepts no footage shows (HUD, thermal simulation, bird's-eye view). Free tiers are unstable. | Supplementary, at roadmap step 6. |
| The owner generates AI media by hand | Best control, heavy manual work (100–150 assets per video). | Rejected as the default. The pipeline still accepts manually dropped files. |
| Local Stable Diffusion on CPU | Minutes per image, low quality, RAM-bound. | Rejected. |

**Voice**
| Option | Trade-off | Decision |
|---|---|---|
| Kokoro via `kokoro-onnx` (local, CPU) | Natural English voices, about 350 MB, no PyTorch. | **Chosen.** |
| `edge-tts` | Very natural, gives word timings. Unofficial use of a Microsoft service that could break. | Optional second engine, later. |
| Piper | Very light, but sounds robotic. | Rejected. |
| The owner records the narration | Most authentic, but manual. | Not now. |

**How the owner drives it**
| Option | Trade-off | Decision |
|---|---|---|
| Claude Code in tmux on the VPS, by conversation | Nothing extra to build, and the creative steps need Claude anyway. Previews must be downloaded over SFTP. | **Chosen.** |
| Drop files over SFTP and run commands | Still needs Claude for the creative steps. | Covered by the above. |
| Web UI | Needs auth, a job queue, and either a paid Claude API or headless Claude. | Rejected for now. |

**Render architecture** (Claude's call)
| Option | Trade-off | Decision |
|---|---|---|
| Render each shot to its own cached clip, then concat and mux | Changing one shot re-renders only that shot. Memory stays small. | **Chosen.** |
| One big ffmpeg filtergraph for the whole video | Simpler, but any change re-renders 10 minutes, and memory use is high on 3.8 GB. | Rejected. |

## 5. How the owner uses it

1. The owner opens Termius, SSHs to the VPS, runs `tmux attach` (or `tmux new -s cf`), then
   `cd /root/CineFacts && claude`.
2. The owner either pastes a storyboard, points at a file uploaded over SFTP, or just names a
   topic and target length. In the last case Claude researches and drafts the storyboard first.
3. Claude runs the `make-video` skill and stops at **three approval checkpoints**:
   1. **Storyboard** (only when Claude drafted it).
   2. **Script and facts:** the owner reads `script.md` and `facts.md`. For the first project,
      Claude also renders 3 short voice samples for the owner to pick from.
   3. **Preview:** `out/preview_720p.mp4`. Claude gives the absolute path for SFTP download.
4. After the preview is approved, Claude renders `final.mp4`, runs QA, writes `youtube.txt`,
   runs `./run publish <id>` (uploads `out/` to Drive at `CineFacts/<id>/`), and reports the
   Drive folder and the local paths.
5. Once the owner says the video is posted, Claude runs `./run clean <id>`. This deletes
   `media/`, `audio/`, `cache/` and `narration.wav` (all rebuildable), and deletes `out/` only
   if the Drive copy is verified with `rclone check`. The text files stay in git.
6. Corrections are plain conversation ("use a different clip for the crack shot", "slower
   voice"). Claude edits `plan.json` and re-runs only the affected steps.

## 6. Project folder and artifacts

```
projects/<id>/                       <id> = short ASCII slug, e.g. why-planes-white
  storyboard.md        committed     input (owner or Claude)
  facts.md             committed     Claude: each factual claim, verdict, source URL
  plan.json            committed     Claude: THE single source of truth (chapters, narration, shots, picks)
  script.md            committed     generated from plan.json, for human reading only
  audio/<sentence_id>.wav            TTS per sentence (cached by content hash)
  narration.wav                      sentences joined with configured pauses
  timeline.json                      start/end of every sentence and shot, in seconds and frames
  media/candidates/<shot_id>.json    search results (provider metadata)
  media/sheets/<chapter_id>.jpg      per-chapter contact sheet Claude reviews (auto pick highlighted)
  media/<shot_id>.<ext>              downloaded chosen asset
  media/<shot_id>.meta.json          provider, asset id, page URL, author, licence
  cache/shots/<shot_id>-<hash>.mp4   rendered shot clips (separate keys for preview and final)
  out/preview_720p.mp4
  out/final.mp4
  out/subs.srt
  out/chapters.txt
  out/credits.txt
  out/youtube.txt                    Claude: title, description (chapters + credits), tags
  qa.json                            QA report
```

`.gitignore` ignores everything under `projects/*/` except `storyboard.md`, `facts.md`,
`plan.json` and `script.md`. Text is versioned. Media, audio, cache and output are not, and
can always be rebuilt from the text files.

The current root `storyboard.md` moves to `projects/demo/storyboard.md` and becomes the MVP
sample.

## 7. plan.json (shape)

The builder may refine field names but must keep these concepts.

```json
{
  "id": "why-planes-white",
  "title": "Why Are Airplanes Painted White?",
  "style": "documentary",
  "voice": "am_michael",
  "target_minutes": 10.5,
  "chapters": [
    {
      "id": "c01",
      "title": "The Secret in the Paint",
      "sentences": [
        {
          "id": "c01s001",
          "text": "Walk through any airport at sunrise and you'll notice something strange.",
          "shots": [
            {
              "id": "c01s001a",
              "kind": "video",
              "query": "airport sunrise airplanes aerial",
              "providers": ["pixabay"],
              "weight": 1,
              "pick": { "provider": "pixabay", "asset_id": "123456" },
              "in_point": 2.0,
              "motion": "none",
              "overlay": null
            }
          ]
        }
      ]
    }
  ]
}
```

Rules:
- IDs are stable once written. Re-ordering never renames, so caches and picks survive.
- A sentence has one or more shots. Its spoken duration is split among its shots by `weight`.
  Aim for shots of **4–8 s** (about 100 shots for 10 minutes, which keeps Claude's work
  within a Pro plan). Split long sentences into more shots. The same asset may be reused by
  several shots with different `in_point`s.
- Pauses between sentences and chapters belong to the shot that precedes them, so the picture
  never goes empty.
- `pick: null` means not chosen yet, and the shot renders as a **placeholder card** (shot ID
  and query on a dark background). Previews therefore always work. QA fails a final render
  that still has placeholders.
- `kind: "image"` shots get a slow Ken Burns move (`motion`: push_in, pull_out, pan_left…).
- A file the owner drops at `media/<shot_id>.<ext>` with `pick: {"provider": "local"}` is used
  as-is (the manual AI-asset escape hatch).
- `overlay` is reserved for roadmap step 6 (text callouts, HUD). MVP ignores it.

## 8. Pipeline steps

All steps are run as `./run <step> <project_id> [--preview]`. `./run all <id> --preview` runs
every step that is out of date. Each step reads files and writes files, and skips work whose
input hash has not changed.

1. **tts:** each sentence is rendered with Kokoro to `audio/<id>.wav`. The cache key is
   hash(text, voice, speed, model). The sentences are joined into `narration.wav` with
   style-defined pauses (one value between sentences, a longer one between chapters).
   `timeline.json` gets each sentence's exact start and end.
2. **search:** for each shot without a `pick`, the configured providers are queried. Results
   go to `media/candidates/` (cached, never re-queried within 24 h). The step respects
   provider rate limits by reading the rate-limit headers and backing off on 429. Each
   candidate gets a script score from: clip length ≥ shot length, resolution ≥ 1080p for
   video, landscape orientation, tag/keyword overlap, and not already used elsewhere in the
   video. The top-scoring candidate is written as a provisional `pick` marked `"auto": true`.
3. **review picks (Claude, economical by design for a Pro plan):** contact sheets are made
   **per chapter, not per shot**. Each sheet is one image: one row per shot, with the shot ID,
   the narration snippet, and its top 4 candidates numbered, with the auto pick highlighted.
   That comes to about 7–12 images per video. Claude reviews each sheet and overrides only
   bad auto picks by writing `pick` (with `"auto": false`) and `in_point`. Rows whose
   candidates are all poor get a new `query` and are searched again. This is the only creative
   step inside the render loop.
4. **fetch:** only the picked asset is downloaded (1080p video preferred), along with
   `.meta.json`.
5. **shots:** each shot is rendered to a clip of exactly its timeline duration, in 1920x1080 at
   24 fps (1280x720 in preview mode). Video is trimmed from `in_point`; a clip that is too
   short is slowed slightly or looped. Images get Ken Burns. The style's colour grade is
   applied. Every clip uses identical codec parameters so concat needs no re-encode.
   **Transitions** *(Claude's call)*: hard cuts within a chapter, which is the norm for this
   documentary style. At chapter boundaries there is a short dip to black, baked into the
   last and first shot clips of the chapters as a fade, so no clips overlap and the
   frame-boundary model stays simple. The owner can override this; crossfades are out of scope.
6. **assemble:** the shots are concatenated. Narration is mixed with the music bed (ducked
   under the voice, music optional) and normalised to **-14 LUFS integrated, ≤ -1 dBTP**
   (two-pass loudnorm). The result is muxed to `out/preview_720p.mp4` or `out/final.mp4`.
7. **subs / chapters / credits:**
   - `subs.srt` is built from the sentence timings. Long sentences are split into cues of at
     most 2 lines of 42 characters, with timing proportional to character count.
   - `chapters.txt` lists chapter start times in YouTube format (the first one at 0:00).
   - `credits.txt` lists every external asset with its author, licence and URL, plus the
     Pixabay attribution line.
8. **qa:** writes `qa.json` and prints pass/fail for:
   - the duration is within ±15% of `target_minutes`;
   - loudness is -14 ±1 LUFS and true peak ≤ -1 dBTP;
   - resolution and fps match the style;
   - audio and video lengths match within one frame;
   - there are no black stretches over 0.5 s;
   - there are no placeholders (final only);
   - every external asset has a credit;
   - the SRT is valid and ends before the video does.
9. **publish:** runs `rclone copy out/ gdrive:CineFacts/<id>/`, then `rclone check` to verify
   it, and prints the Drive folder.
10. **clean:** as described in section 5. It refuses to delete `out/` unless `rclone check`
    passes.

**Frame-accurate timing** is the computational heart and must be unit-tested. All durations
are snapped to the 1/24 s grid using cumulative rounding (each boundary is rounded, then
durations are derived from boundaries). Rounding each shot separately is not allowed, because
over about 150 shots it drifts the picture away from the voice.

## 9. Styles, assets, resources

- `styles/documentary.json` holds: resolution, fps, voice, speech speed, sentence and chapter
  pauses, colour-grade parameters (warm, slightly lifted shadows), Ken Burns range, music level
  and ducking, preview settings. More presets come later.
- `assets/fonts/`: an OFL font (Inter or Montserrat), downloaded by `setup.sh`, for placeholder
  cards now and overlays later.
- `assets/music/`: the owner adds 3–5 royalty-free instrumental tracks by hand from
  pixabay.com/music (the API has no music). Without music, the mix is narration only.
- **Resource guard:** heavy steps run under `nice`/`ionice`, inside
  `systemd-run --scope -p MemoryMax=2500M` when available. ffmpeg is capped at 2 threads, and
  a lock file allows one heavy job at a time.
- **Determinism:** "same result" means the same timeline, the same picks, the same audio and
  the same frames' content. Byte-identical MP4s are not required, since multi-threaded x264
  may differ bit-for-bit.
- **Render-time budget** *(Claude's call; measure in step 2 and adjust presets)*: the
  preview of a 10-minute video should take about 20 minutes or less. The final should take
  about 2 hours or less and may run unattended. Long renders run in the background inside
  tmux and log progress to `projects/<id>/render.log`, so Claude and the owner can check on
  them without blocking.
- **Style reference:** the six reference frames live on the VPS in `assets/reference/`, which
  is gitignored because they are third-party screenshots. The colour grade is tuned by eye
  against them.
- **TTS text vs. subtitle text:** the narration text in `plan.json` is what appears in the
  SRT. An optional per-sentence `say` field overrides what Kokoro reads aloud (numbers,
  acronyms, pronunciations).

## 10. Repo layout

```
CLAUDE.md                         run commands, conventions, errors hit and fixes (kept current)
.claude/skills/make-video/SKILL.md the step-by-step workflow with the 3 checkpoints
run                               single CLI entry point (wraps python -m cinefacts)
cinefacts/                        python package: tts, providers/{pixabay,wikimedia}, timing, shots, assemble, subs, qa, doctor
styles/documentary.json
assets/fonts/  assets/music/  assets/sfx/
projects/demo/storyboard.md
tests/                            pytest: timing/frame snapping, weight split, SRT splitting, plan validation, cache keys, credits; ffmpeg smoke test on tiny lavfi inputs
setup.sh                          one-command install on Ubuntu 24.04
.env.example  .gitignore          (.env, projects/*/ media, models/, .venv never committed)
models/                           Kokoro model files (ignored)
prompt.md                         the original brief, updated to these decisions
docs/superpowers/specs/           this document
```

## 11. setup.sh and doctor

`setup.sh` is idempotent and safe to re-run. It:
- installs via apt: ffmpeg, python3-venv, python3-pip, tmux, curl, fonts tooling;
- installs Node.js LTS and Claude Code;
- creates `.venv` and installs `kokoro-onnx`, `onnxruntime`, `requests`, `Pillow`, `pytest`;
- downloads the Kokoro model and voice files to `models/` (about 340 MB in total);
- downloads the font;
- copies `.env.example` to `.env` if missing.

It prints the remaining manual steps: put the Pixabay key in `.env`, and run `claude` once to
log in.

`setup.sh` also installs `rclone`.

`./run doctor` checks binaries and versions, the venv, model files, the font, `.env` keys, a
live Pixabay test call, free disk (warn below 5 GB), RAM, that systemd-run is available, and
that the rclone remote `gdrive:` is configured (warn until the owner authorises it).
For every failure it prints the exact command that fixes it.

## 12. Where the building happens

- **Step 1** (skeleton, setup.sh, doctor) is written in the owner's Windows checkout by the
  current Claude session and pushed to GitHub. With the owner's go-ahead, that session then
  SSHs into the VPS to clone, run `setup.sh` and run doctor, and reports the result. The
  owner then logs in to Claude Code on the VPS once.
- **From step 2 on**, building and testing happen in Claude Code on the VPS, with full shell
  access, the real hardware, and the Pixabay key in `.env`. That makes performance, Kokoro
  model choice and `systemd-run` behaviour measured, not guessed.
- The VPS gets a write-enabled deploy key for this repo. The Windows checkout must
  `git pull` before anyone edits it.
- Recommended to the owner, though not blocking: rotate the root password (it was shared in
  chat) and switch SSH to key-only login.

## 13. Roadmap

Each step ends with a commit and a report to the owner.

1. **Skeleton + setup.sh + doctor:** clone on the VPS, owner logs in to Claude Code, doctor
   passes.
2. **Voice and timing:** plan.json for `demo`, written by Claude from the storyboard, plus
   `facts.md` and `script.md`. Then tts, timeline, and a preview made of placeholder cards
   with the real narration, SRT and chapters.
3. **Real visuals:** Pixabay search, contact sheets, Claude picks, fetch, Ken Burns, colour
   grade, credits. Wikimedia provider.
4. **Preview → approve → final loop**, plus `youtube.txt`, `publish` to Google Drive and
   `clean`, with `make-video` SKILL.md and CLAUDE.md complete enough for a fresh session.
5. **QA** as in section 8.
6. **Polish:** music ducking, overlays and HUD callouts, chapter title cards, AI-image
   provider, more styles, optional web preview page, Shorts cut-downs, and optional direct
   YouTube upload (private).

**MVP is done when:**
- `setup.sh` on a clean Ubuntu 24.04 VPS installs everything;
- `./run all demo` produces `out/final.mp4` with English narration, Pixabay footage, SRT,
  chapters, credits and `youtube.txt`, and `./run publish demo` puts them on Google Drive;
- QA passes;
- a fresh Claude Code session can make a new video from `CLAUDE.md` and SKILL.md without the
  owner explaining anything.

## 14. Left to the builder

- ffmpeg filter details: the Ken Burns method (avoid slow `zoompan` at 1080p if a scale+crop
  expression is faster), the colour-grade filters, and the intermediate codec settings.
- The default Kokoro voice (the owner picks from samples) and its speed.
- Package structure, CLI parsing, and the contact-sheet layout.
- Whether to use the int8 or fp32 Kokoro model, after a quick quality and speed check on the VPS.
- The exact Pixabay query strategy (video first, then photo).
