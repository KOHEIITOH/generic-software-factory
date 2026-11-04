"""Command-line entry point for Generic Software Factory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sf_factory.doctor import run_doctor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sf", description="Generic Software Factory CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check local prerequisites")
    web = sub.add_parser("web", help="start the local dashboard (builds UI if needed)")
    web.add_argument("--rebuild", action="store_true", help="rebuild frontend assets")
    runtime = sub.add_parser("runtime", help="inspect registered runtimes")
    runtime.add_subparsers(dest="runtime_command", required=True).add_parser("list")
    sub.add_parser("codex-smoke", help="read-only Codex test")
    sub.add_parser("copilot-smoke", help="Copilot SDK test")
    sub.add_parser("grok-smoke", help="read-only Grok test")
    dev = sub.add_parser("dev-smoke", help="opt-in fixture code-editing smoke test")
    dev.add_argument("--runtime", required=True, choices=("codex",))
    analyze = sub.add_parser("analyze", help="analyze a local Git repository read-only")
    analyze.add_argument("repository", type=Path, help="path to the local repository root")
    analyze.add_argument(
        "--confirm-send",
        action="store_true",
        help="confirm that the selected repository text may be sent to GitHub Copilot",
    )
    analyze.add_argument("--timeout", type=int, default=120)
    task = sub.add_parser("task", help="manage tasks")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    create = task_sub.add_parser("create")
    create.add_argument("prompt")
    show = task_sub.add_parser("show")
    show.add_argument("task_id")
    run = task_sub.add_parser("run")
    run.add_argument("task_id")
    run.add_argument(
        "--runtime", required=True,
        help="registered runtime name (required; choose explicitly)",
    )
    run.add_argument("--timeout", type=int, default=120)
    run_group = sub.add_parser("run", help="inspect runs")
    run_sub = run_group.add_subparsers(dest="run_command", required=True)
    run_show = run_sub.add_parser("show")
    run_show.add_argument("run_id")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "web":
        from sf_factory.web_launcher import launch_web

        return launch_web(rebuild=args.rebuild)
    if args.command == "doctor":
        return run_doctor()
    if args.command == "runtime":
        from sf_factory.runtime_status import list_runtimes

        print(json.dumps(list_runtimes(), indent=2))
        return 0
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
        from sf_factory.codex_cli import CodexCliRuntime
        from sf_factory.dev_smoke import run_dev_smoke

        # Editing capabilities require explicit per-adapter review. Only Codex
        # workspace-write has been verified; other adapters are not promoted
        # from read-only just because they implement AgentRuntime.
        return run_dev_smoke(runtime=CodexCliRuntime(sandbox="workspace-write"))
    if args.command == "analyze":
        from sf_factory.repo_analysis import analyze_repository

        try:
            analysis = analyze_repository(
                args.repository,
                timeout_seconds=args.timeout,
                confirm_send=args.confirm_send,
            )
        except (OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        print(
            json.dumps(
                {
                    "files_included": analysis.files_included,
                    "exclusions": analysis.exclusions,
                    "limits_reached": analysis.limits_reached,
                    "bytes_included": analysis.bytes_included,
                },
                indent=2,
            )
        )
        result = analysis.runtime_result
        if result.status != "succeeded":
            message = result.error_message or "Copilot analysis failed."
            print(f"Analysis failed: {message}", file=sys.stderr)
            return 1
        print("\nAnalysis:\n" + result.output)
        return 0
    from sf_factory.factory import Factory

    factory = Factory(Path(".sf-factory"))
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
