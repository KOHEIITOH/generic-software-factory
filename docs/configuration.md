# Configuration model — v0.1

Configuration is deployment-specific. The package ships examples and schemas; users provide actual runtime, repository, provider, and project choices.

## Configuration layers

1. `factory.yaml`: deployment-level wiring and policy.
2. `project.yaml`: project-specific commands, conventions, and paths.
3. Harness files: instructions and knowledge documents.
4. Secret store/environment: credentials (never plaintext in YAML).

## Example `factory.yaml`

```yaml
apiVersion: generic-software-factory/v1alpha1
kind: Factory
metadata:
  name: my-factory
spec:
  runtime:
    agent:
      adapter: "<agent-runtime-adapter>"
      config: {}
    modelProvider:
      enabled: false
      adapter: null
      config: {}
  sourceControl:
    adapter: "<source-control-adapter>"
    config:
      provider: "<git-provider>"
      repository: "<owner>/<repository>"
      baseBranch: main
      credentialRef: "env:FACTORY_GIT_TOKEN"
  execution:
    adapter: "<execution-adapter>"
    config:
      isolation: required
      workspaceTtlMinutes: 60
      networkAccess: restricted
  workflow:
    definition: workflows/issue-to-pr.yaml
    maxRetries: 1
    requirePlanApproval: true
    requireHumanApprovalBeforeMerge: true
  harness:
    path: harness
  quality:
    gates:
      - id: tests
        required: true
        commandRef: project.test
      - id: lint
        required: true
        commandRef: project.lint
      - id: security
        required: true
        adapter: "<security-check-adapter>"
  policy:
    permissions: least-privilege
    allowProductionAccess: false
    requireApprovalFor:
      - git.merge
      - deployment
      - destructive-command
      - policy-change
  observability:
    adapter: "<observability-adapter>"
    retentionDays: 30
```

## Example `project.yaml`

```yaml
apiVersion: generic-software-factory/v1alpha1
kind: ProjectProfile
metadata:
  name: example-project
spec:
  repositoryRoot: .
  language: "<language>"
  framework: "<framework>"
  architectureDocs: []
  commands:
    test: "<project-test-command>"
    lint: "<project-lint-command>"
    build: "<project-build-command>"
  conventions:
    - "Follow existing patterns before introducing new abstractions."
    - "Do not change public APIs without an explicit requirement."
  definitionOfDone:
    - "Acceptance criteria are satisfied."
    - "Required quality gates pass."
    - "Known limitations are documented."
```

## Validation rules

- Unknown API versions or kinds are rejected.
- Required adapter references must resolve.
- Adapter configuration validates against that adapter's schema.
- Credentials must be references, not literal secrets.
- Isolation cannot silently fall back to host execution.
- Production access and destructive operations are denied unless explicitly authorized.
- Project commands run only inside the configured execution boundary.
