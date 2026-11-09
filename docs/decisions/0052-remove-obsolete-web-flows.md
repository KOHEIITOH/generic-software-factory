# 0052: Remove obsolete Web entry points and load optional management on demand

Status: accepted, 2026-11-09

The normal workflow is select an external Issue and explicitly execute one registered
scope. Keeping old manual import/binding, demo PR, quick path inspection, preflight and
unavailable Runtime cards behind a disclosure still left conflicting workflows, mounted
state and background requests. Remove these controls, handlers and their unused state.
Remove the obsolete public HTTP adapters and demo orchestrator as well; no compatibility
aliases or automatic redirects execute old actions. Removed routes return 404, including
when the built dashboard is served.

Keep internal Issue snapshot/cache and repository verification, SCM adapters, actual
quality checks, durable Run evidence and authenticated operator jobs. Read-only Issue/Run
inspection APIs remain for audit; the dashboard uses one operator history. Preserve
Project/Repository metadata APIs and Project/Repository/directory Harness contracts.
Extract Project management into a lazy component mounted only while its optional panel
is open. Initial page loading performs local health and operator reads, not legacy
runtime/cache/history or optional Project fetches.

The user authorized removal of unnecessary functionality rather than compatibility work.
Update user-facing README/onboarding/HTML/API guides to the current execution route.
Historical architecture/ADR records remain history and do not authorize removed APIs.

Validate route absence through HTTP/OpenAPI, unchanged internal persistence/binding and
operator execution, real Chromium absence of legacy requests/controls, on-demand Project
create/reopen, and the full regression suite. Existing Docker isolation guards and actual
model/SCM E2E acceptance boundaries are unchanged.
