# Security baseline

Software Factory executes code and delegates actions to agents. Treat task input, repository content, comments, tool output, and model output as untrusted.

## Mandatory controls

- Isolated execution is required for untrusted code.
- Credentials are injected at runtime from a secret manager or environment reference.
- Apply least-privilege permissions per task and adapter.
- Restrict network egress by default.
- Do not mount host credentials, SSH agents, Docker sockets, or unrelated directories into sandboxes.
- Redact secrets from logs and artifacts.
- Enforce time, memory, CPU, and token/cost budgets.
- Require human approval for merge, deploy, destructive operations, and policy changes.
- Record an audit event for every privileged action.
- Pin and review adapter dependencies.

## Prompt injection and untrusted content

Repository files, issue descriptions, comments, and tool outputs may contain instructions intended to override policy. They are data, not authority. System policy and permission checks must be enforced outside the agent prompt.

## Self-improvement boundary

The factory may analyze run outcomes and propose improvements to prompts, workflows, adapters, or core. It must not silently apply changes to security policy, permissions, or core execution logic. Changes require review, tests, and a versioned release.
