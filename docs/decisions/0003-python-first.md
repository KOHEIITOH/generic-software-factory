# ADR 0003: Python-first Factory Core

- Status: Proposed for MVP implementation
- Date: 2026-11-01

## Context

Generic Software Factory is an AI-native software development platform. Its core
responsibilities include Agent orchestration, workflow execution, policy evaluation,
approval handling, event processing, and integration with multiple Agent runtimes.

The project previously deferred its implementation language pending SDK and local
environment validation. The team has now selected Python as the first implementation
language for the Factory Core and local CLI spike.

## Decision

- Implement the Factory Core, local CLI, and initial Agent Runtime Adapter in Python.
- Use Python 3.11+; use Python 3.13 as the initial local development baseline.
- Use uv for environment and dependency management.
- Use Pydantic for typed boundary models when domain contracts are introduced.
- Use pytest, Ruff, Pyright, and pip-audit for initial quality and dependency checks.
- Use the official GitHub Copilot Python SDK as the first Runtime spike, subject to
  organization policy and account authorization.
- Keep Web UI as a separate TypeScript application if / when it is implemented.
- Keep Runtime Adapter contracts independent of Copilot-specific SDK types.

## Rationale

Python is a strong fit for the AI-centric orchestration and Agent integration layer.
The official Copilot SDK supports Python, so choosing Python does not prevent the
initial Copilot experiment. TypeScript remains appropriate for a future React / Next.js
Web UI and is not required in the Factory Core.

## Consequences

- The repository gains a Python package and executable `sf` CLI.
- The first executable milestone is a harmless Copilot connectivity smoke test.
- Node.js is not a direct prerequisite for the Factory Python package. The Copilot SDK
  manages its own pinned runtime, which is a separate dependency to track and update.
- The team must monitor both Python package vulnerabilities and the SDK-managed
  Copilot runtime.
- The decision can be revisited if local testing, company policy, SDK capability, or
  operational requirements reveal a material disadvantage.

## Security constraints

- Never use broad auto-approval (for example, approve-all permissions) in company
  repositories.
- The initial smoke test sends no company source code and asks the Agent not to use
  tools.
- Repository editing, shell execution, Docker isolation, shared triggers, and
  production actions are explicitly outside this milestone.
