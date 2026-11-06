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
    provider = sub.add_parser("provider", help="inspect model providers")
    provider.add_subparsers(dest="provider_command", required=True).add_parser("list")
    bedrock_smoke = sub.add_parser("bedrock-smoke", help="opt-in Bedrock inference test")
    bedrock_smoke.add_argument("--confirm-invoke", action="store_true")
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
    repo = sub.add_parser("repo", help="inspect a local Git repository")
    repo_sub = repo.add_subparsers(dest="repo_command", required=True)
    detect = repo_sub.add_parser("detect", help="detect Git root from current directory")
    detect.add_argument("--path", type=Path, default=Path.cwd())
    harness = sub.add_parser(
        "harness", help="inspect local harness candidates without applying them"
    )
    harness_sub = harness.add_subparsers(dest="harness_command", required=True)
    discover = harness_sub.add_parser("discover", help="emit a bounded read-only inventory as JSON")
    discover.add_argument("repository", type=Path, help="explicit repository root")
    discover.add_argument("--max-entries", type=int, default=10000)
    discover.add_argument("--max-depth", type=int, default=32)
    discover.add_argument("--max-file-bytes", type=int, default=65536)
    discover.add_argument("--max-total-bytes", type=int, default=1048576)
    validate = harness_sub.add_parser("validate", help="validate candidates without applying them")
    validate.add_argument("repository", type=Path, help="explicit repository root")
    compose = harness_sub.add_parser("compose", help="explicitly select validated rule sources")
    compose.add_argument("repository", type=Path, help="explicit repository root")
    compose.add_argument("--target", default=".", help="relative target scope")
    compose.add_argument("--select", action="append", default=[], help="ordered rule source path")
    compose.add_argument("--exclude", nargs=2, action="append", default=[],
                         metavar=("PATH", "REASON"), help="excluded source and explicit reason")
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
    evidence = run_sub.add_parser(
        "evidence", help="inspect revision-bound check and review results"
    )
    evidence.add_argument("run_id")
    evidence.add_argument("--revision", required=True)
    evidence.add_argument("--bundle-hash", required=True)
    evidence.add_argument("--diff-sha256", required=True)
    state = sub.add_parser("state", help="preview task storage; does not execute workflows")
    state.add_argument("--backend", choices=("file", "sqlite"), default="file")
    state.add_argument("--root", type=Path, required=True, help="explicit storage root")
    state_sub = state.add_subparsers(dest="state_command", required=True)
    state_create = state_sub.add_parser("create", help="persist a task")
    state_create.add_argument("prompt")
    state_show = state_sub.add_parser("show", help="read a stored task")
    state_show.add_argument("task_id")
    state_import = state_sub.add_parser(
        "import", help="import external task metadata without network"
    )
    state_import.add_argument("--provider", required=True)
    state_import.add_argument("--instance", required=True)
    state_import.add_argument("--external-id", required=True)
    state_import.add_argument("--prompt", required=True)
    state_import.add_argument("--external-url")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "state":
        from dataclasses import asdict

        from sf_factory.state_store import StateConflict, StateStore, StateUnavailable

        try:
            store: StateStore
            if args.backend == "file":
                from sf_factory.file_state import FileStateStore

                store = FileStateStore(args.root)
            else:
                from sf_factory.sqlite_state import SqliteStateStore

                args.root.mkdir(parents=True, exist_ok=True)
                store = SqliteStateStore(args.root / "factory.sqlite3")
            if args.state_command == "create":
                print(json.dumps({"task_id": store.create_task(args.prompt)}))
            elif args.state_command == "show":
                print(json.dumps({"task": asdict(store.get_task(args.task_id))}, indent=2))
            else:
                task_id = store.import_external_task(
                    provider=args.provider, instance=args.instance, external_id=args.external_id,
                    prompt=args.prompt, external_url=args.external_url,
                )
                print(json.dumps({"task_id": task_id}))
        except (ValueError, OSError, StateUnavailable, StateConflict) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "harness":
        from dataclasses import asdict

        from sf_factory.harness_discovery import DiscoveryLimits, discover_harness

        try:
            if args.harness_command == "compose":
                from sf_factory.harness_composition import compose_harness
                from sf_factory.harness_validation import validate_harness

                composition = compose_harness(
                    validate_harness(args.repository.absolute()), target=args.target,
                    selected=tuple(args.select), excluded=tuple(tuple(e) for e in args.exclude),
                )
                print(json.dumps({**asdict(composition), "bundle_hash": composition.bundle_hash},
                                 ensure_ascii=True, indent=2))
                return 0
            if args.harness_command == "validate":
                from sf_factory.harness_validation import validate_harness

                validation = validate_harness(args.repository.absolute())
                print(json.dumps(asdict(validation), ensure_ascii=True, indent=2))
                return 0 if validation.valid else 1
            limits = DiscoveryLimits(
                entries=args.max_entries, depth=args.max_depth,
                file_bytes=args.max_file_bytes, total_bytes=args.max_total_bytes,
            )
            # Make relative input absolute without resolving away symlinks or parent traversal.
            result = discover_harness(args.repository.absolute(), limits=limits)
        except (OSError, ValueError, NotImplementedError):
            print(
                "Error: cannot discover harness; check root, platform and limits", file=sys.stderr
            )
            return 2
        print(json.dumps(asdict(result), ensure_ascii=True, indent=2))
        return 0 if result.complete else 1
    if args.command == "web":
        from sf_factory.web_launcher import launch_web

        return launch_web(rebuild=args.rebuild)
    if args.command == "doctor":
        return run_doctor()
    if args.command == "runtime":
        from sf_factory.runtime_status import list_runtimes

        print(json.dumps(list_runtimes(), indent=2))
        return 0
    if args.command == "provider":
        from dataclasses import asdict

        from sf_factory.model_provider_status import bedrock_configuration

        config = bedrock_configuration()
        print(json.dumps({"providers": [{
            "name": "bedrock", **asdict(config),
            "configured": config.configured,
            "authenticated": "not_checked",
        }]}, indent=2))
        return 0
    if args.command == "bedrock-smoke":
        from sf_factory.bedrock_smoke import run_bedrock_smoke

        return run_bedrock_smoke(confirm_invoke=args.confirm_invoke)
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
    if args.command == "repo":
        from sf_factory.repo_discovery import discover_git_root

        try:
            root = discover_git_root(args.path)
        except (OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({"repository_root": str(root), "provider": "local-git"}, indent=2))
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
            if args.run_command == "evidence":
                from sf_factory.run_evidence import EvidenceSubject, RunEvidenceService

                subject = EvidenceSubject(args.revision, args.bundle_hash, args.diff_sha256)
                report = RunEvidenceService(factory).assess(args.run_id, subject)
                print(json.dumps(report, indent=2))
                return 0 if report["evidence_complete"] else 1
            print(json.dumps(factory.show_run(args.run_id), indent=2))
    except (ValueError, PermissionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
