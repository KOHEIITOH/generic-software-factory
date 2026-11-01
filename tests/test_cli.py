from sf_factory.cli import build_parser


def test_doctor_command_parses() -> None:
    args = build_parser().parse_args(["doctor"])
    assert args.command == "doctor"


def test_copilot_smoke_command_parses() -> None:
    args = build_parser().parse_args(["copilot-smoke"])
    assert args.command == "copilot-smoke"
