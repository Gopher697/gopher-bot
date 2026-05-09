from __future__ import annotations

import argparse
import json

from .run_mission import SUPPORTED_MISSION_TYPE, run_mission


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="U.S.S. Wayfarer command entrypoint.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    mission_parser = subparsers.add_parser("run-mission", help="Run one read-only v0 mission.")
    mission_parser.add_argument("--target", required=True, help="Target project to survey.")
    mission_parser.add_argument("--type", default=SUPPORTED_MISSION_TYPE, help="Mission type to run.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run-mission":
        report = run_mission(
            {
                "mission_type": args.type,
                "target_project": args.target,
                "mode": "read_only",
            }
        )
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "succeeded" else 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
