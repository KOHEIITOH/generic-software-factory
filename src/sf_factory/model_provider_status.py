"""Read-only local diagnostics for optional model providers."""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BedrockConfiguration:
    model_id: str | None
    region_name: str | None
    sdk_installed: bool

    @property
    def configured(self) -> bool:
        return bool(self.model_id and self.region_name and self.sdk_installed)


def bedrock_configuration() -> BedrockConfiguration:
    """Check settings only; do not resolve credentials or contact AWS."""
    model_id = os.environ.get("SF_BEDROCK_MODEL_ID", "").strip() or None
    region_name = (
        os.environ.get("SF_BEDROCK_REGION", "").strip()
        or os.environ.get("AWS_REGION", "").strip()
        or os.environ.get("AWS_DEFAULT_REGION", "").strip()
        or None
    )
    return BedrockConfiguration(
        model_id=model_id,
        region_name=region_name,
        sdk_installed=importlib.util.find_spec("boto3") is not None,
    )
