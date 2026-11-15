"""CLI entry point: ./run <step> [project_id] [options]."""
from __future__ import annotations

import argparse
import sys

# Steps that exist in the design but are not built yet, with the roadmap step that adds them.
PLANNED = {
    "tts": 2, "subs": 2, "search": 3, "fetch": 3, "shots": 3,
    "assemble": 2, "all": 2, "publish": 4, "clean": 4, "qa": 5,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="./run", description="CineFacts video pipeline")
    sub = parser.add_subparsers(dest="step", required=True)

    doctor = sub.add_parser("doctor", help="check the environment and print fixes")
    doctor.add_argument("--offline", action="store_true", help="skip the live Pixabay call")

    for name, roadmap_step in PLANNED.items():
        p = sub.add_parser(name, help=f"(roadmap step {roadmap_step})")
        p.add_argument("project_id", nargs="?")
        p.add_argument("--preview", action="store_true")

    args = parser.parse_args(argv)
    if args.step == "doctor":
        from cinefacts import doctor as doctor_mod
        return doctor_mod.main(offline=args.offline)

    print(f"'{args.step}' is not implemented yet (roadmap step {PLANNED[args.step]}).",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
