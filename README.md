# Generic Software Factory

**Generic AI Software Development Platform**

A reusable, vendor-agnostic and project-agnostic package for orchestrating governed software delivery workflows across configurable AI agents, model providers, repositories, and execution environments.

> The factory defines **how work is governed and delivered**. A deployment supplies **which agents, models, repositories, and tools perform that work**.

## Design principles

1. **Vendor Agnostic** — no mandatory dependency on one AI vendor or agent runtime.
2. **Project Agnostic** — no mandatory dependency on one language, framework, or repository.
3. **Modular** — core orchestration, adapters, policies, and workflows have clear boundaries.
4. **Configurable** — deployment-specific choices are supplied as configuration.
5. **Self-improving** — run evidence can propose improvements; changes to core and safety policies require review.

## Architecture

- **Factory Core**: workflow lifecycle, task state, policy enforcement, audit events, retries, approvals.
- **Factory Adapters**: agent runtime, model provider, source control, execution environment, and observability integrations.
- **Factory Configuration**: deployment-specific project, runtime, provider, workflow, and policy settings.
- **Harness**: shared instructions, domain context, engineering standards, and tool-use constraints.
- **Quality Gates**: deterministic checks and independent review before work can advance.

See [Architecture](docs/architecture.md), [Configuration](docs/configuration.md), [Adapter Contracts](docs/adapter-contracts.md), [Security](docs/security.md), and [MVP Plan](docs/mvp-plan.md).

## Status

**v0.1 — specification-first scaffold.** The first implementation should prove one end-to-end workflow while keeping provider and project choices replaceable. The CLI and reference adapters are not implemented yet.

## Planned CLI

```bash
sf init
sf validate --config factory.yaml
sf doctor --config factory.yaml
sf run --config factory.yaml --task "Implement the requested change"
sf status <run-id>
sf cancel <run-id>
```

These commands describe the intended interface; they are not implemented in this specification scaffold.

## Safety baseline

- Run untrusted code only in an isolated execution environment.
- Use least-privilege credentials and secret references; never store plaintext secrets in configuration.
- Restrict network access by default.
- Require human approval for merge, deployment, destructive operations, and policy changes.
- Treat task input, repository content, tool output, and model output as untrusted data.
- Require deterministic quality gates; an agent's self-review is not sufficient.

## Repository map

```text
core/          Core contracts and lifecycle specification
adapters/      Integration contracts and adapter documentation
harness/       Reusable instructions, policies, and knowledge templates
agents/        Role definitions, independent of agent products
workflows/     Reusable workflow definitions
config/        Example deployment configuration
quality/       Quality gate specifications and templates
docs/          Architecture, security, configuration, roadmap, ADRs
```

## Contributing

Changes to core contracts, security policies, and workflow semantics require an Architecture Decision Record (ADR).