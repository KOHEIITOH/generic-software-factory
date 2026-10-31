# Architecture — Generic Software Factory v0.1

## 1. Product definition

Generic Software Factory is a reusable development-factory package. It is not a single coding agent, model gateway, IDE extension, or project template. It coordinates a governed workflow across pluggable capabilities.

A deployment supplies:
- one or more agent runtimes;
- optional direct model-provider access;
- a source-control repository;
- an isolated execution backend;
- project-specific context and quality commands;
- approval and security policies.

The package must not assume these choices are known at build time.

## 2. Architectural principles

| Principle | Required property |
|---|---|
| Vendor Agnostic | Provider- and runtime-specific behavior stays behind adapters. |
| Project Agnostic | Language/framework commands and conventions are configuration or project context. |
| Modular | Components communicate through versioned contracts. |
| Configurable | No project-specific secrets or assumptions are embedded in core. |
| Self-improving | Run evidence can propose improvements; changes to core and safety policy require review. |

## 3. Package boundaries

### Factory Core
Owns task lifecycle, workflow transitions, policy enforcement, approvals, audit events, retry, timeout, and cancellation. Core must not import provider SDKs or project-specific code.

### Factory Adapters
Translate stable Factory contracts into vendor/product-specific APIs:
- AgentRuntime
- ModelProvider (optional)
- SourceControl
- Execution
- Observability

### Factory Configuration
Selects and wires adapter implementations, project profiles, workflows, and policies for a deployment.

### Harness
Supplies shared principles, role instructions, project context, engineering standards, constraints, and tool-use guidance. Harness is not the orchestrator.

## 4. Logical architecture

```text
                    HUMAN / OPERATOR
             goals, approvals, policy decisions
                            |
                            v
+-------------------------------------------------------+
|                 FACTORY CONFIGURATION                 |
| project | runtime | provider | workflow | policies    |
+-------------------------------------------------------+
                            |
                            v
+-------------------------------------------------------+
|                    FACTORY CORE                       |
| Orchestrator | Task State | Policy Engine | Audit Log |
| Workflow Engine | Approval Gate | Retry / Recovery    |
+-------------------------------------------------------+
           |                |                 |
           v                v                 v
     Agent Adapter     SCM Adapter      Execution Adapter
           |                |                 |
           v                v                 v
     Agent Runtime      Git Provider      Isolated Sandbox
           |
           v
    Model Provider Adapter (optional; runtime may own model access)

Harness: role instructions, project context, standards, constraints.
Quality Gates: deterministic checks and independently recorded review.
```

## 5. Workflow lifecycle

Minimum states:

`CREATED → VALIDATING → PLANNING → PLAN_REVIEW → IMPLEMENTING → TESTING → REVIEWING → PR_READY → APPROVAL_PENDING → COMPLETED`

Control states: `BLOCKED`, `FAILED`, `CANCELLED`, `RETRYING`.

Every transition records run/task ID, previous and next state, actor, timestamp, reason, evidence/artifact references, and policy decision.

## 6. Logical agent roles

- **Planner** — turns request into scoped tasks and acceptance criteria.
- **Architect** — identifies constraints, dependencies, and design implications.
- **Developer** — implements approved work.
- **Tester** — creates/runs tests and reports evidence.
- **Reviewer** — independently reviews diff and evidence.
- **Security Reviewer** — checks security-sensitive changes.

These are role definitions, not product names. A deployment may map several roles to one runtime or one role to multiple agents.

## 7. Quality gates

Configuration validation; plan approval; tests/lint/type checks/build; secret/dependency/security checks; diff review; human approval for merge/deploy/destructive actions.

Agent assertions are evidence, not authoritative gate results. Prefer deterministic command outputs and independently recorded review outcomes.

## 8. Extension model

Each adapter declares its ID, type, contract version, supported capabilities, configuration schema, required permissions, health-check behavior, normalized errors, and retryability.

Unknown capabilities fail closed. Core rejects incompatible contract versions during validation.

## 9. Non-goals for v0.1

- Fully autonomous production deployment.
- Mandatory multi-agent debate/swarm behavior.
- Built-in support for every provider/runtime.
- A universal IDE or project generator.
- Self-modification of core code or security policy without human review.
