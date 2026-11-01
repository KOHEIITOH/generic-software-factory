from sf_factory.codex_smoke import EXPECTED_RESPONSE


def test_codex_smoke_token_is_specific() -> None:
    assert EXPECTED_RESPONSE == "FACTORY_CODEX_SMOKE_OK"
