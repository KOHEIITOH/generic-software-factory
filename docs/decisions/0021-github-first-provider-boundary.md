# ADR 0021: GitHub first, with provider rules outside Core

Status: accepted.

GitHub Issues, repositories and Pull Requests are the supported initial remote
integration. This is a default product choice, not a GitHub dependency in Factory
or shared Workflow. Preserve TaskSourceAdapter, ExternalIssue, Repository and
Project contracts. Add only the missing RepositoryBindingAdapter operation needed
by existing task/repository binding, and wire GitHub through integration_defaults.

Core persists an adapter-verified canonical path and external identity. The GitHub
adapter owns origin URL parsing, source provider checks and case-insensitive GitHub
repository matching. Both SQLite and File use the same injected contract; a fixture
adapter with case-sensitive identity proves Core does not enforce GitHub rules.

GitHub remains the no-configuration default for existing callers and UI. No GitLab,
Bitbucket or Jira implementation, schema migration, new authentication mechanism,
execution permission or external write is added. SourceControl and initial default
configuration will be connected in the following small PRs.
