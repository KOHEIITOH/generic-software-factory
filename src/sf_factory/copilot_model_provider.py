"""Text-only model inference using the existing tool-disabled Copilot SDK adapter."""
from __future__ import annotations

import tempfile
from pathlib import Path

from sf_factory.copilot_sdk import CopilotSdkRuntime
from sf_factory.model_provider import ModelResponse


class CopilotModelProvider:
    def __init__(self, *, timeout_seconds: int = 120):
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 600:
            raise ValueError('bounded inference timeout required')
        self.timeout_seconds = timeout_seconds

    def generate(self, prompt: str) -> ModelResponse:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 262144:
            raise ValueError('bounded inference prompt required')
        # Each SDK execute creates a new client/session with available_tools=[].
        # No repository path or files are supplied to that runtime workspace.
        with tempfile.TemporaryDirectory(prefix='sf-text-inference-') as directory:
            result = CopilotSdkRuntime().execute(prompt=prompt, workspace=Path(directory),
                                                timeout_seconds=self.timeout_seconds)
        if result.status != 'succeeded' or result.exit_code != 0:
            raise RuntimeError('Copilot text inference failed: ' + (result.error_kind or 'unknown'))
        if not result.output.strip() or len(result.output.encode()) > 524288:
            raise RuntimeError('Copilot response missing or exceeds budget')
        if not isinstance(result.session_id, str) or not result.session_id.strip():
            raise RuntimeError('Copilot session provenance missing')
        return ModelResponse('copilot', 'sdk-default', result.output, session_id=result.session_id)
