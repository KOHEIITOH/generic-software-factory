# Adapter contracts — v0.1

This document defines language-neutral contracts. Concrete SDK interfaces will be specified with the first implementation.

## Common requirements

Every adapter:
- declares `id`, `type`, and `contractVersion`;
- exposes a configuration schema and supported capabilities;
- implements `healthCheck`;
- reports required permissions;
- returns normalized errors: `AUTH`, `RATE_LIMIT`, `TIMEOUT`, `UNAVAILABLE`, `INVALID_CONFIG`, `PERMISSION_DENIED`, `EXECUTION_FAILED`, `UNKNOWN`;
- identifies retryable errors;
- emits structured events without leaking secrets.

## AgentRuntime

**Purpose:** execute a logical agent role using a selected agent product/runtime.

Input: run/task IDs, role and role instructions, task description and acceptance criteria, scoped context/artifact references, allowed tools and permissions, timeout and resource limits.

Output: status (`SUCCEEDED`, `NEEDS_INPUT`, `BLOCKED`, `FAILED`), structured summary, artifact references, usage metadata when available, warnings and unresolved questions.

The adapter must not receive broader permissions than the run policy grants.

## ModelProvider (optional)

Used for direct model inference only when the chosen AgentRuntime does not own model access. Output includes response, provider/model identity, usage, finish reason and normalized errors. Factory must work when this adapter is disabled.

## SourceControl

Capabilities may include repository inspection, branch/worktree creation, diff retrieval, commit creation, and PR creation. Merge is separately permissioned and human-approved by default.

## Execution

Create isolated workspace, mount scoped repository/artifacts, run allowlisted commands, capture output, enforce CPU/memory/time/network limits, destroy workspace and report cleanup. Host execution is not an implicit fallback.

## Observability

Accept structured lifecycle events, metrics, traces and artifact references. Secret redaction occurs before persistence/export.

## Compatibility

Adapters declare a semantic contract version. Core rejects incompatible major versions and validates required capabilities at startup.
