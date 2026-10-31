# ADR-0001: Package boundaries

- Status: Accepted for v0.1
- Decision: Separate Factory Core, Factory Adapters, and Factory Configuration.
- Context: The package must remain independent of specific AI vendors, agent products, and target projects.
- Consequences:
  - Core owns lifecycle, policy, state, and workflow semantics.
  - Adapters own vendor/product integration.
  - Configuration selects adapters and project-specific behavior.
  - Harness supplies instructions/context but does not replace orchestration.
  - Adapter contracts must be versioned and conformance-tested.
