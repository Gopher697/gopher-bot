from __future__ import annotations

import argparse

try:
    from .starship_core import (
        build_codex_prompt,
        build_session_handoff,
        build_specialist_brief,
        format_route,
        list_stations,
        load_registry,
        route_task,
    )
except ImportError:  # pragma: no cover - direct script execution path
    from starship_core import (
        build_codex_prompt,
        build_session_handoff,
        build_specialist_brief,
        format_route,
        list_stations,
        load_registry,
        route_task,
    )


def run_handoff(registry: dict) -> str:
    fields = [
        "Project",
        "Mission",
        "Stardate/Date",
        "Current State",
        "Open Threads",
        "Next Action",
        "Suggested Next Station",
    ]
    answers = {field: input(f"{field}: ").strip() for field in fields}
    return build_session_handoff(answers, registry)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local rule-based Starship Command console.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-stations", help="List configured bridge divisions.")

    route_parser = subparsers.add_parser("route", help="Route a mission to bridge divisions.")
    route_parser.add_argument("task")

    specialist_parser = subparsers.add_parser(
        "spawn-specialist",
        help="Generate a specialist brief without launching an autonomous process.",
    )
    specialist_parser.add_argument("task")

    prompt_parser = subparsers.add_parser("codex-prompt", help="Generate a template-based Codex mission order.")
    prompt_parser.add_argument("task")

    subparsers.add_parser("handoff", help="Prompt for a compact bridge log / handoff.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    registry = load_registry()

    if args.command == "list-stations":
        print(list_stations(registry))
    elif args.command == "route":
        print(format_route(route_task(args.task, registry)))
    elif args.command == "spawn-specialist":
        print(build_specialist_brief(args.task, registry))
    elif args.command == "codex-prompt":
        print(build_codex_prompt(args.task, registry))
    elif args.command == "handoff":
        print(run_handoff(registry))
    else:
        parser.error(f"unknown command: {args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
