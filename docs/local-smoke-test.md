# Local Smoke Test — macOS / Python

This guide verifies that the local Factory package can call the installed Agent Runtimes. Smoke tests use empty temporary directories and restricted or disabled tool access. They do not connect to a company repository, edit files, or create a PR.

## 0. Before starting

- Use approved accounts and follow your organization's AI usage policy.
- Do not use company source code, credentials, production endpoints, or customer data in these first tests.
- The smoke tests use fresh temporary directories and explicitly restricted read-only tool access.
- The selected CLI must already be installed and authenticated.

## 1. Install prerequisites

Install Python 3.13 (recommended baseline), uv, and Git:

```bash
brew install python@3.13 uv git
```

Check the base tool versions:

```bash
python3.13 --version
uv --version
git --version
```

Install and authenticate only the Runtime you intend to test. For Codex, use the
[official installation guide](https://chatgpt.com/codex/cli):

```bash
codex --version
codex login
codex login status
```

For Grok Build, use the [official xAI CLI guide](https://docs.x.ai/build/cli):

```bash
grok --version
grok login
```

For Copilot, install the optional SDK dependency **after cloning the project**
(see step 6). Install the Copilot CLI using its official instructions, then
check its version and authenticate:

```bash
copilot --version
copilot login
```

## 2. Get the project

```bash
git clone https://github.com/KOHEIITOH/generic-software-factory.git
cd generic-software-factory
```

## 3. Install and diagnose

```bash
uv python install 3.13
uv sync --python 3.13 --extra dev
uv run sf doctor
```

Git is required for the initial setup. Codex, Grok Build, and Copilot CLI / SDK are optional;
install and authenticate only the Runtime you intend to use. Docker and GitHub CLI are also optional.

## 4. Optional: run the Codex smoke test

```bash
uv run sf codex-smoke
```

Expected successful output:

```text
Codex response:
FACTORY_CODEX_SMOKE_OK

Codex smoke test completed.
```

The test uses codex exec with JSONL output, ephemeral session storage, and the read-only sandbox in a temporary directory. It does not grant write access to the repository.

## 5. Optional: run the Grok Build smoke test

```bash
uv run sf grok-smoke
```

Expected successful output:

```text
Grok Build response:
FACTORY_GROK_SMOKE_OK

Grok Build smoke test completed.
```

The adapter uses Grok's headless JSON output and an explicit allowlist containing only `read_file`, `grep`, and `list_dir`. It also blocks subagent spawning and MCP tool calls. It does not enable always-approve mode, shell access, file editing, or writing. The optional OS-level sandbox is not configured by this adapter yet; this smoke test only validates a harmless read-only prompt in an empty temporary directory.

## 6. Optional: run the Copilot SDK smoke test

The Copilot SDK is not required for the default setup. It uses the local Copilot CLI authentication; credentials are not stored in Factory configuration or its database. To install and use it:

```bash
uv sync --python 3.13 --extra dev --extra copilot
copilot login
uv run sf copilot-smoke
```

Use an organization-approved GitHub Copilot account and confirm that SDK / CLI use is permitted.

The Factory Runtime Adapter can also run a persisted Task with `--runtime copilot`:

```bash
uv run sf task create "Explain this project"
uv run sf task run <task-id> --runtime copilot
```

This currently runs against the Factory-created empty workspace, not a cloned or imported repository. The SDK session is configured with an empty tool allowlist and file-change tracking disabled. This does not establish OS-level process isolation or prove safety equivalent to Codex or Grok; repository intake, editing, and workflow execution are not included.

Each Task execution requires an explicit runtime selection, for example
`uv run sf task run <task-id> --runtime copilot`. Omitting `--runtime` is an
error; Factory does not automatically select Codex or any other agent.

## 7. Run local quality checks

```bash
uv run pytest
uv run ruff check .
uv run pyright
uv run pip-audit
```

## Troubleshooting

- **CLI not found**: confirm the relevant CLI version command works in the same terminal and that it is on PATH.
- **Authentication error**: authenticate using the relevant CLI login command. Do not paste credentials or tokens into chat.
- **Runtime / network error**: check network and proxy policy. Do not bypass corporate TLS or network controls.
- **Python version error**: use Python 3.11 or later; Python 3.13 is the baseline used for this spike.
- **Smoke test timeout**: retry after checking CLI authentication and network connectivity.

## Scope boundary

Passing a smoke test proves only that the corresponding CLI can start and return a response in this local environment. It does not prove that the Factory can safely edit a repository, run project tests in a sandbox, orchestrate workflows, perform independent review, or create a PR.
