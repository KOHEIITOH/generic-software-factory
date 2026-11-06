# ADR 0018: Persist Run evidence through domain operations

Status: accepted.

RunEvidenceService retains input validation, review coverage rules and assessment
calculation, including its unconditional delivery-ineligible result. EvidenceState
provides atomic registration of a frozen plan, append-only check/review recording,
and one consistent assessment snapshot. SqliteEvidenceState preserves the existing
schema, transactions, immutable keys, producer/subject/attempt checks and audit.
No generic SQL connection or transaction handle reaches the service contract.

This extraction prepares the File adapter as a separate implementation step.
Registering evidence does not execute checks, verify producer identity by itself,
grant delivery permission or make a self-reported result trustworthy. Collectors
must remain authenticated by the trusted controller and bound to actual artifacts.
