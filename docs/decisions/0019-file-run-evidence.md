# ADR 0019: File check/review evidence with shared authorization rules

Status: accepted for trusted local collectors.

Implement EvidenceState with the same File document/lock used by prepared Runs.
Freeze check/review plans once, append unique observations and audit in a single
update, and assess a consistent read snapshot. Share exact subject, producer,
Run/attempt and review-identity/path rules with SQLite; retain the shared assessment
algorithm and strict review parser. Observations from earlier attempts never
satisfy a new attempt, and terminal Runs cannot accept or reuse evidence.

File schema 4 validates collections, references, canonical plans, bounded attempts,
observation types and review summaries. Upgrade verified older local documents
atomically, preserving approval consumption, Runs and source references. Unknown
schema/corruption fails closed; no SQL migration is implied.

This is persistence and assessment, not an authenticated collector or proof of
actual execution. The trusted controller must establish producer identity and
checked artifacts. Delivery eligibility remains false. No Web approval/execution
endpoint, model inference or GitHub write is introduced.
