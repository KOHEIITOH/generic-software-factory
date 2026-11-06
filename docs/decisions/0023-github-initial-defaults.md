# ADR 0023: GitHub defaults with minimal configuration

Status: accepted for the initial supported remote integration.

Composition selects GitHub for TaskSource, repository binding and SourceControl.
Web Issue fetch uses the default TaskSource; GitHub-specific listing stays inside
its adapter. Project repository registration initially selects GitHub/private
metadata, while Local Git remains available. The existing startup command is
unchanged and does not contact GitHub or run an agent.

GitHub adapters share GH_TOKEN-first / GITHUB_TOKEN-fallback credentials. No token
is embedded in config; the Issue adapter suppresses token repr. Optional local
CLI/API diagnostics report provider IDs, credential variable names and configured
presence only, explicitly leaving authentication not_checked. No database or
network is needed for this inspection.

Configuration examples now name GitHub, but the existing conceptual factory.yaml
is not an implemented loader. Do not imply changing YAML configures the running
application. Runtime/execution/policy selection and approval are separate from
choosing the initial SCM. No other remote adapter or generic plugin machinery is
introduced. See github-first-integration-policy.md for the acceptance checklist.
