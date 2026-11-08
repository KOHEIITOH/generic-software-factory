# ADR 0038: Project rules and actual changed-directory scope

Accepted. Project-common guidance is an optional operator-owned JSON document,
shared by reference outside the target repositories. Its exact contents are frozen
into the existing Harness composition and Run manifest, included in the bundle
hash, and supplied to both implementation and independent review. A Project ID
is derived from its stable name; repository identities remain distinct.

Repository and nested directory instructions retain existing explicit selection
or reasoned exclusion. Applicability considers every operator-allowed change path,
not just the repository root. No layer adds commands, credentials, permissions,
or implicit precedence. Existing Factory policy and approved checks remain binding.
Changing shared rules changes the configuration fingerprint and requires a new
scoped invocation rather than silently changing a resumed Run.

Operator config may include `project_harness_file: /absolute/outside/repo/project.json`
(or inline `project_harness`, never both). Example document:

```json
{"project":"payments","rules":[{"name":"quality","text":"Preserve public API and approved tests."}]}
```

Judgment: use a small typed text layer instead of introducing a second Harness
registry or task system. Existing registry, approval, composition, and snapshot
contracts continue to provide authority and evidence.
