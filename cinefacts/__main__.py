"""CLI entry point: ./run <step> [project_id] [options]."""
from __future__ import annotations

import argparse
import sys

# Steps that exist in the design but are not built yet, with the roadmap step that adds them.
PLANNED = {"search": 3, "fetch": 3, "publish": 4, "clean": 4, "qa": 5}
# Steps that need the CPU/RAM guard (nice, ionice, MemoryMax, one at a time).
HEAVY = {"tts", "voices", "shots", "assemble", "all"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="./run", description="CineFacts video pipeline")
    sub = parser.add_subparsers(dest="step", required=True)

    doctor = sub.add_parser("doctor", help="check the environment and print fixes")
    doctor.add_argument("--offline", action="store_true", help="skip the live Pixabay call")

    def project_step(name: str, help_: str, preview: bool = False):
        p = sub.add_parser(name, help=help_)
        p.add_argument("project_id")
        if preview:
            p.add_argument("--preview", action="store_true", help="720p preview render")
        return p

    project_step("script", "validate plan.json and regenerate script.md")
    v = project_step("voices", "render short voice samples to out/voices/")
    v.add_argument("--voices", default="am_michael,bm_george,af_heart",
                   help="comma-separated Kokoro voice names")
    project_step("tts", "narration per sentence, narration.wav, timeline.json")
    project_step("shots", "render one clip per shot (cached)", preview=True)
    project_step("assemble", "concat shots, normalise and mux the narration", preview=True)
    project_step("subs", "write out/subs.srt and out/chapters.txt")
    project_step("all", "run every step that is out of date", preview=True)

    for name, roadmap_step in PLANNED.items():
        p = sub.add_parser(name, help=f"(roadmap step {roadmap_step})")
        p.add_argument("project_id", nargs="?")
        p.add_argument("--preview", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv)

    if args.step == "doctor":
        from cinefacts import doctor as doctor_mod
        return doctor_mod.main(offline=args.offline)
    if args.step in PLANNED:
        print(f"'{args.step}' is not implemented yet (roadmap step {PLANNED[args.step]}).",
              file=sys.stderr)
        return 2

    from cinefacts import guard
    from cinefacts import plan as planmod
    from cinefacts.tts import StaleAudio

    try:
        pdir = planmod.project_dir(args.project_id)
        if args.step == "script":
            plan = planmod.load(args.project_id)
            try:  # with cached audio, script.md also gets real chapter times
                from cinefacts import tts
                tts.ensure_timeline(args.project_id)
            except StaleAudio:
                (pdir / "script.md").write_text(planmod.render_script_md(plan),
                                                encoding="utf-8")
            print(f"plan OK; wrote {pdir / 'script.md'}")
            return 0
        if args.step == "subs":
            from cinefacts import subs
            subs.run(args.project_id)
            return 0

        if args.step in HEAVY:
            guard.reexec_guarded(argv)
        log = guard.Log(pdir / "render.log")
        with guard.heavy_lock():
            log(f"=== {' '.join(argv)}")
            return _heavy(args, log)
    except (planmod.PlanError, StaleAudio) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _heavy(args, log) -> int:
    from cinefacts import render, subs, tts

    pid = args.project_id
    if args.step == "voices":
        for p in tts.voice_samples(pid, [v.strip() for v in args.voices.split(",") if v.strip()],
                                   log=log):
            log(f"wrote {p}")
        return 0
    if args.step in ("tts", "all"):
        tts.build(pid, synth=tts.Synth(), log=log)
    if args.step == "shots":
        render.render_shots(pid, args.preview, log)
    if args.step in ("assemble", "all"):
        if args.step == "all":
            log("search/fetch: not built yet (roadmap step 3); shots render as placeholders")
        render.assemble(pid, args.preview, log=log)
    if args.step == "all":
        subs.run(pid, log=log)
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
