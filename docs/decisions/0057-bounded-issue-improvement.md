# 0057: Bounded unattended improvement inside an approved Issue

Accepted: 2026-11-17

Previously a selected Issue stopped after the first failed candidate or independent review.
A second click often returned the same terminal session without a reason. Add an explicit
repair policy to the existing DevelopmentConfig, selected-Issue Web job and controller.
Use existing snapshots, model providers, evidence collectors, delivery receipts and budgets;
create neither a second task database nor a Runtime-specific execution path.

The Web checkbox defaults on for new selected-Issue submissions. Initial execution consent
covers failure evidence being sent to AI and up to three attempts, eight provider calls,
3,000,000 conservatively reserved tokens (including SDK retry allowance), 2,500 API calls
and a one-hour session deadline. The worker also enforces its existing one-hour alarm.
These are usage bounds, not a currency billing guarantee. API clients omit the policy to
retain the old single-attempt behavior; existing journals/fingerprints remain compatible.
CLI operator configurations can opt into auto_improve for direct Issue development.
The flag is not a scheduler for requirement planning or external PR-review polling.

For a known completed malformed implementation response, feed back its exact bounded text
and request the original schema. For known failed checks, feed back the candidate and actual
collector results; for valid independent review failures, retain and replay the validated
review findings as untrusted context. Never interpret feedback as permission, command,
Harness modification or relaxed quality criteria. Every new candidate starts from the same
approved source revision/Harness, and runs every original check plus independent review.

Correction steps and rationale live in the original Issue's automation journal. No new
Factory Task entity, GitHub Issue, automatic merge or release is introduced. Harness
improvement proposals retain their separate explicit approval; this change automatically
repairs application code within the approved paths, not Factory policy or its own engine.
Stop on repeated semantic file content or repeated invalid output, exhausted budgets,
source/Harness drift, unavailable isolation, incomplete records or unknown inference.

Each attempt reserves its effects before inference. Persist the failed Run and correction
plan before advancing. A saved repair plan may resume; an interrupted attempt with unknown
outcomes cannot silently generate again. Reviewed delivery reconciles the same Run without
new inference. Budget reservations never reset on restart. Terminal reads preserve the
recorded reason. Switching only the repair checkbox reuses an existing completed counterpart
receipt instead of publishing another PR; both policies share the Issue controller lock.
Previously stopped executions are retained; enabling the new policy is a distinct explicitly
consented scope, not a mutation or reset of those records.

Public progress exposes attempt numbers, failed check IDs, review counts and decision codes.
Raw candidate code, provider responses, check stdout and review text stay in private records;
only the approved model invocation receives repair evidence. No automatic model calls occur
because a browser refreshes or reads history.

Validation includes real persistence, bounded successful repair, reviewer findings, malformed
responses, stagnation, shared model/deadline limits, worker loss before/after durable repair,
unknown PR reconciliation, authenticated policy propagation, completed-receipt reuse, real
Chromium controls and a mandatory real Docker failure→repair→checks→Draft scenario. Model/SCM
are simulated in those tests. Live PC Bedrock/Copilot plus GitHub delivery is still unverified.
