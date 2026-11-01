"""Command-line entry point for Generic Software Factory."""

from __future__ import annotations

import argparse
import sys

from sf_factory.doctor import run_doctor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sf",
        description="Generic Software Factory — local development CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="check local prerequisites")
    subparsers.add_parser("codex-smoke", help="run a harmless, read-only Codex CLI test")
    subparsers.add_parser("copilot-smoke", help="run a harmless Copilot SDK connectivity test")
    subparsers.add_parser("grok-smoke", help="run a harmless, read-only Grok Build CLI test")
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

    return 2


if __name__ == "__main__":
    sys.exit(main())
