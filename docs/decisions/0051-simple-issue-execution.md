# 0051: Select an external Issue and execute one bounded Draft PR job

Status: accepted, 2026-11-08

The operator requested an Issue selector and one execution action. The default screen
therefore exposes registered repository profiles, a read-only paginated Issue selector,
an explicit execute-and-consent button (including visible Bedrock charge disclosure), execution progress and Draft PR links. Import, binding, project registration,
diagnostics, demo PR and requirement decomposition are auxiliary/advanced controls.
The external Issue remains the requirement; no independent Factory Task is introduced.

Only the Issue identifier can vary within the registered repository. The original profile
fingerprint remains the revocation/configuration guard; the effective config fingerprint,
selected Issue and reviewers determine the durable automation session. Web payloads cannot
supply repositories, paths, commands, models, credentials or widened write scopes.
GitHub remains the initial composition choice in integration_defaults; shared execution
uses existing TaskSourceAdapter and ChangeSourceControl contracts.

A direct Issue does not create a child plan or child Issues. One existing develop_issue
invocation performs candidate generation, strict offline checks, independent review and
Draft PR delivery. Reference discovery reuses the existing bounded document rules; frozen
snapshot references remain read-only. Larger requirements retain the separate reviewed-plan
approval before child publication, with the configured parent Issue shown in the details.

Reserve a finite invocation round before checking prerequisites. When a candidate Run is
prepared, reserve its logical execution and freeze its identity before any inference.
A failure before this boundary may retry after fixing prerequisites, within the same
three-round/deadline budget; a crash before this boundary can only orphan local preparation
evidence, never an inference or remote write.
BudgetedModel and SCM transport guards persist finite call/token/API limits. Repeated clicks
reuse the same session; completed receipts are returned without additional inference or
writes. An unknown candidate outcome stops permanently. A reviewed delivery may only
reconcile the same Run using existing delivery receipts, never regenerate a candidate.
No polling timer starts work, no automatic merge or release is added.

Validation: real File/Git/evidence state with simulated external model/SCM; actual Chromium
and operator HTTP; mandatory hosted Docker case exercises the selected-Issue private worker
and real isolated behavioral tests. Paid Bedrock/GitHub E2E remains a user-PC acceptance check.
