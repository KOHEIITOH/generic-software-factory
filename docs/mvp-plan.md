# MVP plan — v0.1

## Objective

Demonstrate that a user can configure an arbitrary supported agent runtime and target repository, submit one bounded task, and receive a tested pull request without changing Factory Core.

## MVP workflow

`Task → Validate → Plan → Human plan approval → Implement → Test → Review → PR creation → Human merge approval`

## Milestones

### M0 — Specification and contracts
- Freeze core vocabulary and boundaries.
- Define configuration schema and adapter contracts.
- Define workflow state machine and event format.
- Document security baseline.

### M1 — Thin vertical slice
- Implement CLI: `init`, `validate`, `doctor`, `run`, `status`, `cancel`.
- Support one AgentRuntime adapter and one SourceControl adapter as reference implementations.
- Support one isolated Execution adapter.
- Run one workflow from task input to PR creation.
- Keep runtime/provider/project choices configurable, never hard-coded into Core.

### M2 — Reliability
- Add retries, timeouts, cancellation, resumability.
- Add audit log and artifact manifest.
- Add deterministic quality gates and failure evidence.
- Add permission tests and secret redaction.

### M3 — Replaceability proof
- Add a second AgentRuntime adapter or contract-tested mock.
- Demonstrate that switching runtime requires configuration/adapter changes only, not Core changes.
- Add adapter conformance tests.

## Acceptance criteria

1. Clean checkout can be initialized using documented steps.
2. `validate` catches missing/invalid configuration before execution.
3. `doctor` checks adapter connectivity and required capabilities.
4. A bounded task runs in an isolated workspace.
5. Agent role instructions and Harness version are recorded per run.
6. Tests/lint/security gates produce machine-readable evidence.
7. Failure, timeout, cancellation and retry states are recorded.
8. PR creation is supported; merge and production deployment remain approval-gated.
9. Secrets do not appear in logs, prompts, artifacts or committed files.
10. Replacing the AgentRuntime adapter does not require changes to Factory Core.

## Out of scope

Autonomous merge/deploy, dynamic self-editing of core policy, unbounded agent loops, multi-repository orchestration, and a general-purpose dashboard.

## Open decisions before implementation

Implementation language and distribution model; first reference AgentRuntime; first SourceControl provider; execution backend; state store; workflow definition format; license and repository visibility.
