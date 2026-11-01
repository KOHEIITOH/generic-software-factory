# Local Smoke Test — macOS / Python

This guide verifies that the local Factory package can call Codex CLI. The smoke test uses an empty temporary directory and Codex's read-only sandbox. It does not connect to a company repository, edit files, or create a PR.

## 0. Before starting

- Use an approved Codex account and follow your organization's AI usage policy.
- Do not use company source code, credentials, production endpoints, or customer data in this first test.
- The smoke test asks Codex not to inspect or modify files and uses a fresh temporary directory with the read-only sandbox.
- Codex CLI must already be installed and authenticated.

## 1. Install prerequisites

Install Python 3.13 (recommended baseline), uv, and Git:

```bash
brew install python@3.13 uv git
```

Install Codex CLI using the [official installation guide](https://chatgpt.com/codex/cli), then authenticate:

```bash
codex login
codex login status
```

Check versions:

```bash
python3.13 --version
uv --version
git --version
codex --version
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

Codex CLI and Git are required. Copilot CLI / SDK, Docker, and GitHub CLI are optional.

## 4. Run the Codex smoke test

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

## 5. Optional: run the Copilot SDK smoke test

The Copilot SDK is not required for the default setup. To install and use it:

```bash
uv sync --python 3.13 --extra dev --extra copilot
copilot login
uv run sf copilot-smoke
```

Use an organization-approved GitHub Copilot account and confirm that SDK / CLI use is permitted.

## 6. Run local quality checks

```bash
uv run pytest
uv run ruff check .
uv run pyright
uv run pip-audit
```

## Troubleshooting

- **Codex not found**: confirm codex --version works in the same terminal and that the CLI is on PATH.
- **Authentication error**: run codex login and codex login status. Do not paste credentials or tokens into chat.
- **Runtime / network error**: check network and proxy policy. Do not bypass corporate TLS or network controls.
- **Python version error**: use Python 3.11 or later; Python 3.13 is the baseline used for this spike.
- **Smoke test timeout**: retry after checking Codex CLI authentication and network connectivity.

## Scope boundary

Passing this smoke test proves only that the Codex CLI can start and return a response in this local environment. It does not prove that the Factory can safely edit a repository, run project tests in a sandbox, orchestrate workflows, perform independent review, or create a PR.
