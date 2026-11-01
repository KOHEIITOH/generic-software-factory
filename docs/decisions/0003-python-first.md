# ADR 0003: Python-first Factory Core

- Status: Accepted
- Date: 2026-11-01

## Context

Generic Software Factory is an AI-native software development platform. Its core responsibilities include Agent orchestration, workflow execution, policy evaluation, approval handling, event processing, and integration with multiple Agent runtimes.

The project selected Python as the first implementation language for the Factory Core and local CLI.

## Decision

- Implement the Factory Core, local CLI, and Agent Runtime Adapters in Python.
- Use Python 3.11+; use Python 3.13 as the initial local development baseline.
- Use uv for environment and dependency management.
- Use Pydantic for typed boundary models when domain contracts are introduced.
- Use pytest, Ruff, Pyright, and pip-audit for initial quality and dependency checks.
- Keep Agent Runtime contracts independent of vendor-specific SDK types.
- Keep Web UI as a separate TypeScript application if / when it is implemented.

The initial Runtime choice is recorded separately in ADR 0004.

## Rationale

Python is a strong fit for the AI-centric orchestration and Agent integration layer. TypeScript remains appropriate for a future React / Next.js Web UI and is not required in the Factory Core.

## Consequences

- The repository uses a Python package and executable sf CLI.
- Agent SDKs are optional dependencies unless the default Runtime requires them.
- The team monitors Python package vulnerabilities and each Runtime's external installation / update lifecycle.

## Security constraints

- Never use broad auto-approval in company repositories.
- Repository editing, shell execution, Docker isolation, shared triggers, and production actions require explicit policy and implementation.
