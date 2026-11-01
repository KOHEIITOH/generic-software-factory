"""A harmless connectivity smoke test for the GitHub Copilot Python SDK."""

from __future__ import annotations

import asyncio
import tempfile

EXPECTED_RESPONSE = "FACTORY_SMOKE_OK"

PROMPT = (
    "This is a connectivity smoke test. Do not access files or run commands. "
    "Reply with exactly: FACTORY_SMOKE_OK"
)


def is_expected_response(content: str) -> bool:
    """Return whether the assistant returned the exact smoke-test token."""
    return content.strip() == EXPECTED_RESPONSE


async def run_smoke_test() -> int:
    """Start a tool-restricted Copilot session in an empty temporary directory."""
    try:
        from copilot import CopilotClient
        from copilot.session_events import AssistantMessageData
    except ImportError:
        print("Copilot SDK is optional. Install it with: uv sync --extra dev --extra copilot")
        return 1

    print("Starting GitHub Copilot SDK...")
    print("The first run may download and verify the Copilot runtime.")

    # Never expose the Factory repository or the user's current directory to this test.
    # An explicit empty tool allowlist disables built-in, MCP, and custom tools.
    with tempfile.TemporaryDirectory(prefix="sf-copilot-smoke-") as workspace:
        async with CopilotClient() as client:
            async with await client.create_session(
                available_tools=[],
                working_directory=workspace,
                enable_file_change_tracking=False,
            ) as session:
                response = await session.send_and_wait(PROMPT, timeout=120)

    if response is None or not isinstance(response.data, AssistantMessageData):
        print("Copilot did not return an assistant message.")
        return 1

    print("\nCopilot response:")
    print(response.data.content)
    if not is_expected_response(response.data.content):
        print(f"\nUnexpected response; expected {EXPECTED_RESPONSE}.")
        return 1

    print("\nSmoke test completed.")
    return 0


def main() -> int:
    try:
        return asyncio.run(run_smoke_test())
    except KeyboardInterrupt:
        print("\nSmoke test interrupted.")
        return 130
