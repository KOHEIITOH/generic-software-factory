"""Bedrock configuration diagnostics are local and non-invasive."""

from sf_factory.model_provider_status import bedrock_configuration


def test_missing_configuration(monkeypatch):
    for name in ("SF_BEDROCK_MODEL_ID", "SF_BEDROCK_REGION", "AWS_REGION",
                 "AWS_DEFAULT_REGION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("sf_factory.model_provider_status.importlib.util.find_spec",
                        lambda name: None)
    result = bedrock_configuration()
    assert result.configured is False
    assert result.model_id is None
    assert result.region_name is None


def test_configured_with_explicit_region(monkeypatch):
    monkeypatch.setenv("SF_BEDROCK_MODEL_ID", "example-model")
    monkeypatch.setenv("SF_BEDROCK_REGION", "ap-northeast-1")
    monkeypatch.setattr("sf_factory.model_provider_status.importlib.util.find_spec",
                        lambda name: object())
    result = bedrock_configuration()
    assert result.configured is True
    assert result.model_id == "example-model"
    assert result.region_name == "ap-northeast-1"


def test_configured_does_not_mean_authenticated(monkeypatch):
    monkeypatch.setenv("SF_BEDROCK_MODEL_ID", "example-model")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.delenv("SF_BEDROCK_REGION", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.setattr("sf_factory.model_provider_status.importlib.util.find_spec",
                        lambda name: object())
    assert bedrock_configuration().configured is True
