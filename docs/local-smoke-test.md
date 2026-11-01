# Local Smoke Test — macOS / Python

This guide gets the first executable slice running locally. It does not connect to a
company repository, edit files, run shell tools through the agent, or create a PR.

## 0. Before starting

- Confirm that your organization's AI policy permits use of the GitHub Copilot SDK.
- Use an approved GitHub Copilot account or approved BYOK configuration.
- Do not use company source code, credentials, production endpoints, or customer data
  in this first test.
- The smoke test runs in a fresh temporary directory and explicitly provides an empty
  tool allowlist, disabling built-in, MCP, and custom tools for that session. Its prompt
  is also intentionally harmless.

The GitHub Copilot SDK requires Python 3.11 or later. The SDK may download and verify
its pinned Copilot runtime on first use. Runtime installation requires network access.

## 1. Install prerequisites

Install Python 3.13 (recommended baseline for this spike), uv, Git, and the
GitHub Copilot CLI. The Homebrew cask installs the CLI without requiring you to
install Node.js yourself:

```bash
brew install python@3.13 uv git
brew install --cask copilot-cli
```

Authenticate the CLI with the GitHub account whose Copilot access is approved by
your organization:

```bash
copilot login
```

Complete the browser/device flow, then start `copilot` and run `/user` to verify
the active account. The organization's Copilot CLI policy must be enabled. See
[GitHub's authentication guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli).

Check versions:

```bash
python3 --version
uv --version
git --version
```

Docker and GitHub CLI are not required for this first smoke test. The standalone
Copilot CLI is used to establish authentication; the Python SDK manages its own
pinned runtime when the smoke test starts.

## 2. Get the project

```bash
git clone https://github.com/KOHEIITOH/generic-software-factory.git
cd generic-software-factory
git switch feat/python-copilot-smoke
```

If the branch is not visible yet, open the pull request from the repository page and
use its branch checkout instructions.

## 3. Install and diagnose

```bash
uv sync --extra dev
uv run sf doctor
```

The doctor checks Python, Git, the standalone Copilot CLI, and the Copilot SDK
package. Docker and GitHub CLI are reported as optional for this test.

## 4. Run the Copilot smoke test

```bash
uv run sf copilot-smoke
```

Expected successful output includes:

```text
Copilot response:
FACTORY_SMOKE_OK

Smoke test completed.
```

The exact response formatting may vary. The important result is that the SDK starts,
creates a session with no available tools in an empty temporary directory, sends the
harmless prompt, and receives an assistant response.

## 5. Run local quality checks

```bash
uv run pytest
uv run ruff check .
uv run pyright
uv run pip-audit
```

## Troubleshooting

- **Authentication / authorization error**: run `copilot login`, then use
  `/user` to verify the active account. Confirm that your organization has enabled
  Copilot CLI and permits SDK use. A GitHub CLI login alone does not prove that
  Copilot CLI access is enabled.
- **Runtime download error**: check network access and proxy policy. Do not bypass
  corporate TLS or network controls.
- **Python version error**: use Python 3.11 or later; Python 3.13 is the baseline
  used for this spike.
- **Package install error**: capture the error and Python / uv versions. Do not paste
  access tokens or environment variables into chat.
- **Permission prompt**: do not approve broad tool permissions for this smoke test.
  The test is designed not to need file or shell tools.

## Scope boundary

Passing this smoke test proves only that the Python SDK can start and exchange a
simple message in this local environment. It does not prove that the Factory can
safely edit a repository, run tests in a sandbox, orchestrate workflows, or operate
as a shared Slack / Google Chat service.
