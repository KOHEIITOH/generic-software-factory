# ADR 0020: Late Runtime completion cannot resurrect a terminal Run

Status: accepted; automatic Worker recovery remains pending.

SQLite completion must atomically match Run ID, Task ID and running state before
updating the result and appending its audit. Zero matching rows raises a conflict
without a success event. File already checks these conditions under its document
lock. Test both adapters for terminal state races, wrong Task callbacks and unknown
Runs. Normal synchronous Runtime behavior remains unchanged.

This is a safety prerequisite, not a cancellation or recovery feature. AgentRuntime
currently exposes only synchronous execute; it has no durable provider-neutral
execution handle, ownership epoch or restart-safe stop/observe operation. A stale
running record, expired lease, missing PID or controller death does not establish
that the Runtime/descendants stopped. Do not automatically reset/retry a Run based
on these hints or infer that an unknown outcome succeeded.

Future Execution adapters must persist execution identity, reconcile liveness and
termination, and reject old-owner callbacks before enabling recovery. Retries need
new Run identities and explicit policy. Status CAS alone does not fence an old
Worker's filesystem/network side effects or authorize new work.
