# ADR 0015: Atomic Harness operations behind a persistence boundary

Status: accepted.

The Harness controller revalidates the registered repository, exact Git revision
and composed bundle before preparing a Run. Storage operations now sit behind
`HarnessState`: registration lookup, Task/Project associations, approval decisions,
and one `commit_prepared_run` operation. The latter must recheck registration and
consume the matching single-use approval together with Run, manifest and audit.

The first adapter extracts the existing SQLite transaction without changing its
schema or decision rules. It keeps legacy standalone approval/registry classes
and tests usable. No SQL connection or generic transaction handle is exposed to
the controller or in the shared contract. Subsequent File support must provide
this operation in the same durable document as approval state; separate writes
for approval consumption and Run creation are not permitted.

This boundary does not authenticate reviewers, grant workspace writes, authorize
GitHub actions, start a Runtime, or make File Harness workflows available by itself.
The dashboard startup command is unchanged.
