# ADR 0004: Minimal Agent Runtime Contract and Codex-first Implementation

- Status: Accepted
- Date: 2026-11-01

## Context

The architecture intends to support multiple Coding Agent products, but the first Python implementation and local smoke test were coupled to the GitHub Copilot SDK. This created unnecessary setup requirements for users who want to run another agent.

The project needs a practical first Runtime without building a generic orchestration framework before a real workflow exists.

## Decision

- Keep Agent Runtime and Model Provider as separate concepts.
- Start with one minimal Agent Runtime contract: execute a prompt in a supplied workspace and return a normalized result.
- Implement Codex CLI as the first executable Runtime Adapter, using its non-interactive exec interface.
- Keep GitHub Copilot SDK as an optional dependency and preserve its smoke test.
- Plan Claude Code, GitHub Copilot Runtime integration, Gemini CLI, and Grok Build as additional Runtime Adapters. Grok Build can be integrated through its headless CLI or Agent Client Protocol (ACP).
- Treat AWS Bedrock and the xAI API as Model Providers for Custom Agent use cases, not as Coding Agent Runtimes. Grok Build is the separate xAI Agent Runtime option.
- Do not implement automatic model routing, cross-provider model substitution, Agent Swarms, or a large capability framework in the MVP.

## Rationale

Codex CLI is already available in the initial local development environment. Its documented non-interactive command supports machine-readable JSONL output and explicit sandbox selection, making it suitable for a small first Adapter.

A small contract lets the Core remain independent while avoiding premature abstractions. Additional methods and capability declarations can be introduced when a second Runtime demonstrates a concrete need.

## Consequences

- The default development setup no longer requires Copilot SDK or Copilot CLI.
- Codex CLI is required for the initial Runtime smoke test.
- Copilot can be installed separately with the copilot optional dependency group.
- The initial Codex smoke test uses a temporary workspace and read-only sandbox.
- A successful smoke test proves connectivity only; it does not prove safe repository editing, Factory workflow orchestration, or production readiness.

## Security constraints

- Never use Codex full-access / sandbox-bypass mode in the Factory's initial implementation.
- Smoke tests must use a temporary directory and read-only sandbox.
- Real repository editing must wait for an explicit workspace isolation, permission, and approval design.
