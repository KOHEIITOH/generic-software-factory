from sf_factory.doctor import collect_checks


def test_codex_cli_is_optional(monkeypatch) -> None:
    monkeypatch.setattr("sf_factory.doctor.shutil.which", lambda name: None)
    monkeypatch.setattr("sf_factory.doctor.importlib.util.find_spec", lambda name: None)

    checks = {check.name: check for check in collect_checks()}

    assert checks["Codex CLI"].required is False
    assert checks["Codex CLI"].ok is False


def test_missing_optional_runtimes_do_not_fail_required_checks(monkeypatch) -> None:
    monkeypatch.setattr(
        "sf_factory.doctor.shutil.which",
        lambda name: "/usr/bin/git" if name == "git" else None,
    )
    monkeypatch.setattr("sf_factory.doctor.importlib.util.find_spec", lambda name: None)

    checks = collect_checks()

    assert not any(not check.ok and check.required for check in checks)
