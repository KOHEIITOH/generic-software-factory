# ADR 0024: Issue is the request; Run is execution history

Status: accepted for the read model; execution remains gated separately.

The primary dashboard no longer asks users to maintain an independent local Task
backlog. Import/identify the external Issue and group its repeated Runs underneath.
Keep legacy Task APIs, IDs, source identity, requirement snapshot and approvals for
compatibility and audit. Do not rewrite old Task prompts on refresh or infer a
new execution from import/read-only preflight.

The issue read projection filters external sources before limiting and returns
bounded recent Runs with exact totals per Issue. SQLite and File retain their
storage contracts. Local-only Tasks remain available through legacy APIs and their
Runs remain visible in global history; no data migration/deletion is involved.

This is the first slice of the Issue-to-PR workflow, not a newly enabled executor.
Actual Issue execution must separately establish operator approval, verified
isolation, real AI/check/review provenance and safe delivery. See the vertical-slice
checklist for the remaining acceptance conditions.
