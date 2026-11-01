"""Command-line entry point for Generic Software Factory."""
from __future__ import annotations

import argparse
import json
import sys

from sf_factory.doctor import run_doctor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sf", description="Generic Software Factory CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check local prerequisites")
    sub.add_parser("codex-smoke", help="read-only Codex test")
    sub.add_parser("copilot-smoke", help="Copilot SDK test")
    sub.add_parser("grok-smoke", help="read-only Grok test")
    sub.add_parser("dev-smoke", help="isolated fixture code-editing smoke test")
    task = sub.add_parser("task", help="manage tasks")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    create = task_sub.add_parser("create")
    create.add_argument("prompt")
    show = task_sub.add_parser("show")
    show.add_argument("task_id")
    run = task_sub.add_parser("run")
    run.add_argument("task_id")
    run.add_argument("--runtime", choices=("codex", "grok"), default="codex")
    run.add_argument("--timeout", type=int, default=120)
    run_group = sub.add_parser("run", help="inspect runs")
    run_sub = run_group.add_subparsers(dest="run_command", required=True)
    run_show = run_sub.add_parser("show")
    run_show.add_argument("run_id")
    return parser

def main() -> int:
    args = build_parser().parse_args()
    if args.command == "doctor":
        return run_doctor()
    if args.command == "codex-smoke":
        from sf_factory.codex_smoke import run_smoke_test
        return run_smoke_test()
    if args.command == "copilot-smoke":
        from sf_factory.copilot_smoke import main as smoke_main
        return smoke_main()
    if args.command == "grok-smoke":
        from sf_factory.grok_smoke import run_smoke_test
        return run_smoke_test()
    if args.command == "dev-smoke":
        from sf_factory.dev_smoke import run_dev_smoke

        return run_dev_smoke()
    from sf_factory.factory import Factory
    factory = Factory(__import__("pathlib").Path(".sf-factory"))
    try:
        if args.command == "task":
            if args.task_command == "create":
                print(factory.create_task(args.prompt))
            elif args.task_command == "show":
                print(json.dumps(factory.show_task(args.task_id), indent=2))
            elif args.task_command == "run":
                result = factory.run_task(args.task_id, args.runtime, args.timeout)
                print(json.dumps(result, indent=2))
                return 0 if result["status"] == "succeeded" else 1
        elif args.command == "run":
            print(json.dumps(factory.show_run(args.run_id), indent=2))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
