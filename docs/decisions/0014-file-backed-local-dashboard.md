# ADR 0014: Local dashboard persistence without a required database

Status: accepted for the local Web subset; full workflow migration remains pending.

## Decision

Keep `uv run sf web --rebuild` as the normal entry point. Select File for new POSIX
roots, preserve SQLite when an existing database is present, and keep SQLite as
an explicit option (and the new-root default on non-POSIX platforms). Never
migrate or discard existing state automatically. Web and normal task/run CLI
commands use the same selector and data directory configuration.

Reuse FileStateStore for immutable tasks and external identity imports. A versioned,
bounded dashboard document stores projects, repositories, task bindings, read-only
Runs and their audit events. A shared local process lock and durable replacement
protect each document mutation. File does not emulate SQL or create an in-memory DB.
Registration and source lookup move behind domain methods rather than exposing SQL
to the Web routes. Runtime policy and adapters remain unchanged.

## Boundaries

The trusted Harness approval/prepare/evidence/snapshot services still depend on
SQLite transactions. File refuses these operations explicitly. Do not weaken
single-use approval or claim full workflow equivalence until these operations
have a shared domain contract and non-SQL atomicity tests.

File is a bounded local preview, not a distributed state store. A crash-persisted
running Run is retained and blocks further Runs; no automatic retry/approval or
success inference is permitted. Worker reconciliation and explicit recovery,
full workflow state migration, export/import and S3 are subsequent work.

See [local Web operation and limitations](../local-web-storage.md).
