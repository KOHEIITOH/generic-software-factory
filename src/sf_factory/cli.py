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
    subparsers.add_parser("copilot-smoke", help="run a harmless Copilot SDK connectivity test")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "doctor":
        return run_doctor()

    if args.command == "copilot-smoke":
        from sf_factory.copilot_smoke import main as smoke_main

        return smoke_main()

    return 2


if __name__ == "__main__":
    sys.exit(main())
