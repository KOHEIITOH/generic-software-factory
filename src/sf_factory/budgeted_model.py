"""Reserve bounded inference before calling a text-only provider; cache exact receipts."""
from __future__ import annotations

from dataclasses import asdict

from sf_factory.automation_state import AutomationSession, fingerprint
from sf_factory.model_provider import ModelProvider, ModelResponse
from sf_factory.state_store import StateConflict
from sf_factory.usage import TokenUsage


class BudgetedModel:
    def __init__(self, provider: ModelProvider, session: AutomationSession, *, role: str,
                 max_output_tokens: int = 8192):
        if (not role or len(role) > 64 or type(max_output_tokens) is not int
                or not 1 <= max_output_tokens <= 32768):
            raise ValueError('bounded model role/output required')
        self.provider, self.session = provider, session
        self.role, self.max_output_tokens = role, max_output_tokens

    def generate(self, prompt: str) -> ModelResponse:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 262144:
            raise ValueError('bounded automation prompt required')
        key = 'model:' + self.role + ':' + fingerprint(prompt)
        existing = self.session.snapshot()['actions'].get(key)
        if existing is not None:
            if existing['status'] != 'completed':
                raise StateConflict('inference outcome unknown; do not replay')
            data = existing['receipt']
            return ModelResponse(**{**data,
                'usage': TokenUsage(**data['usage']) if data['usage'] is not None else None})
        # Conservative byte-based reservation, including up to three Bedrock SDK
        # attempts and protocol overhead. This is not a currency billing guarantee.
        reserved = 3 * (len(prompt.encode()) + self.max_output_tokens + 1024)
        self.session.reserve('model', key, tokens=reserved)
        result = self.provider.generate(prompt)
        if not isinstance(result.text, str) or len(result.text.encode()) > 524288:
            raise ValueError('model response exceeds budget')
        self.session.complete_action(key, asdict(result))
        return result
