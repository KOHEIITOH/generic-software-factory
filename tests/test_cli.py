from sf_factory.cli import build_parser


def test_doctor_command_parses() -> None:
    args = build_parser().parse_args(["doctor"])
    assert args.command == "doctor"


def test_codex_smoke_command_parses() -> None:
    args = build_parser().parse_args(["codex-smoke"])
    assert args.command == "codex-smoke"


def test_copilot_smoke_command_parses() -> None:
    args = build_parser().parse_args(["copilot-smoke"])
    assert args.command == "copilot-smoke"


def test_grok_smoke_command_parses() -> None:
    args = build_parser().parse_args(["grok-smoke"])
    assert args.command == "grok-smoke"
