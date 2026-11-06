# ADR 0017: Publish durable source payload before registering its reference

Status: accepted for local SQLite and File adapters.

SourceSnapshotService keeps its bounded approved-Git-blob extraction, sensitive
path rejection, Harness source hash checks and no-follow content verification.
A SourceState boundary handles atomic snapshot reference/audit registration and
lookup; it rechecks prepared Run state and exact approved subject at commit.

Payload and state are separate durable resources, so this is not a fictitious
cross-resource transaction. First fsync all staged files and directories, reserve
an unused snapshot ID with mkdir, install into that owned directory and fsync it
and its parent. Then register the immutable reference and audit atomically.
Incomplete/orphan payload cannot be used through the state lookup.

On failure after installation, delete only this operation's payload if an
authoritative state read confirms it is not referenced. A committed/uncertain
registration or unreadable state must never cause deletion of possibly referenced
source. Keep the original failure, inspect/verify registered payload on recovery,
and defer orphan GC. Unique-ID collisions never overwrite an existing directory.

File dashboard schema 3 adds source references while retaining existing Harness
approvals, consumed flags, Runs and all earlier data. No SQL data migration or
remote artifact backend is introduced. This enables source preparation without
SQL, not agent execution, test collection, delivery or automatic retry.
