# ADR 0016: File approvals and prepared Runs share one durable document

Status: accepted for trusted local controllers.

Implement HarnessState with the existing File dashboard lock and atomic document
replacement. Approval decisions/events, Task/Project associations and approved Run
manifests live beside Run/audit state. Preparing a Run rechecks registered scope and
consumes the exact active decision in the same update that inserts Run/manifest/audit.
Git revision and bundle recomposition stay in HarnessRunService for both adapters.

Preserve the SQLite approval contract: explicit boolean decisions, exact bounded
scope, verified actor supplied by the caller, timezone-aware lifetime up to 24h,
revocation, rejection, expiry and one-time consumption. Actor strings are not a
new authentication mechanism. Approval denial is a domain PermissionError subtype
so process-lock OS error normalization cannot disguise an authorization decision.

Validated schema-1 local documents upgrade atomically to schema 2 with empty new
Harness collections, retaining Task IDs, existing Runs, Project data and version
history. Newer schemas fail closed. Existing SQL data is not migrated. Old code
refuses schema 2; back up a stopped Writer before upgrading or rolling back.

Test SQLite and File against the same decision contract; use real independent
processes to race preparation and terminate before/after replacement. A failed
pre-publication write leaves neither claim nor Run; an uncertain post-publication
result may contain both, never just one. No retry automatically executes a Run.
No HTTP approval/execution endpoint, quality-evidence adapter or delivery permission
is added by this decision.
