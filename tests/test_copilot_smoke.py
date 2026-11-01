from sf_factory.copilot_smoke import is_expected_response


def test_accepts_expected_token() -> None:
    assert is_expected_response("FACTORY_SMOKE_OK")


def test_ignores_surrounding_whitespace() -> None:
    assert is_expected_response("\n FACTORY_SMOKE_OK \t")


def test_rejects_unexpected_response() -> None:
    assert not is_expected_response("The SDK is working.")
