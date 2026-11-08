# ADR 0042: One-level external Issue plan and finite serial advance

Accepted. Reuse existing DevelopmentConfig, TaskSourceAdapter, IssueTracker,
CollaborationSourceControl, Run/snapshot/evidence and bounded automation journal.
Local origin is verified through the existing repository binding before planning.
Completed child creation receipts bind exact external identities during recovery.
The parent remains the external requirement; 1..8 native children are execution
units. This is not standalone Task CRUD. The independent planning review must
confirm full coverage, concrete acceptance, completable units and valid scope/DAG.
The parser additionally enforces exact schema, known checks/paths and acyclicity.

A single advance performs at most one candidate or one review/merge state step.
Only verified merge of the exact expected child PR head unlocks dependencies.
No auto merge, recursive subdivision, background polling or unlimited retries.
All children are serialized even when their DAG allows concurrency. Issue and
parent-link changes are rechecked before execution/review. Code may advance to
remote default after a merge; approved Harness inventory and operator policy may
not silently change. Source/check failure stops with Run/session evidence.

Workflow-wide limits: 32 model calls, 6m conservative token reservations including
SDK retries/max output, 2500 API requests, 128 logical write actions, 8 children,
7 days. Child review also retains its own three-round/eight-call budget. The
nested transport guard counts requests against both journals. No dynamic budget
increase is performed. Creation/link unknown outcomes stay pending and reconcile
read-only. Unknown candidate evaluation/commit preparation stops rather than
paying or writing again. Planning receipts are deterministic and cached.

Judgment: keep parent requirements separate from even a one-unit child, keeping
native hierarchy and execution evidence uniform. Plan-only does not require
Docker; first execute checks Docker before spending planning inference. Human
review/merge remain external events. UI controls, distributed workers, S3/CAS
leases and automatic rebasing are future scope. No new provider dependency in Core.
