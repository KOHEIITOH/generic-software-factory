"""Explicit opt-in AWS Bedrock inference smoke test."""

from __future__ import annotations

import sys

from sf_factory.bedrock_provider import BedrockModelProvider
from sf_factory.model_provider_status import bedrock_configuration


def run_bedrock_smoke(*, confirm_invoke: bool) -> int:
    """Invoke one short prompt only after explicit user confirmation."""
    if not confirm_invoke:
        print("Bedrock invocation requires --confirm-invoke (may incur AWS charges).",
              file=sys.stderr)
        return 2
    config = bedrock_configuration()
    if not config.configured or config.model_id is None or config.region_name is None:
        print("Configure SF_BEDROCK_MODEL_ID, region, and boto3 first.", file=sys.stderr)
        return 2
    try:
        result = BedrockModelProvider(
            model_id=config.model_id,
            region_name=config.region_name,
            max_tokens=32,
        ).generate("Reply with the single word OK.")
    except RuntimeError as exc:
        print(f"Bedrock smoke failed: {exc}", file=sys.stderr)
        return 1
    print("Bedrock inference succeeded.")
    print(f"Model: {result.model_id}")
    if result.input_tokens is not None:
        print(f"Input tokens: {result.input_tokens}")
    if result.output_tokens is not None:
        print(f"Output tokens: {result.output_tokens}")
    return 0
