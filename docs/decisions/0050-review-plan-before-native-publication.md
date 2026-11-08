# ADR 0050: Human review of the exact plan before child Issue publication

Accepted. New Web requirement workflows persist require_plan_approval before
planning. Existing planning/independent review produces a preview and waits,
without Issue/PR writes. The operator sees derived requirement interpretation,
requirement citations, child goals, acceptance, dependencies, allowed paths and
approved check IDs. Existing legacy CLI authorization and already-frozen plans
are preserved; a workflow requiring approval cannot be bypassed by changing its
caller option on resume.

A canonical approval digest binds the full plan, independent review, parent
snapshot, configuration/reviewer scope, source metadata/fingerprint/revision and
clean local baseline. The browser's confirmation is tied to that exact digest,
not an editable plan. Approval is authenticated, explicitly consented and durable
before any child creation. Unknown/stale/changed scope is rejected. Changed remote
or local baseline invalidates approval before unpublished children are created.
After all children exist, ordinary code advances retain existing reference-pin,
quality and merge rules. No merge/deploy authority or budget reset is added.

Approval-only runs use NoInference providers and do not initialize Bedrock/Copilot
or require inference consent. Native Issue mutations still require explicit run
consent and registered scope. Repeated submissions reuse the request identity;
crashes after approval retain the receipt, existing delivery intents reconcile
without duplicate children. Web step timers never approve or advance anything.

Privacy decision: authenticated preview for these new review-required workflows
exposes only a bounded derived interpretation/plan needed for human judgment.
Raw repository_context, source text, parent prompt, concern reports, credentials
and SDK errors remain private. Legacy progress retains its previous metadata-only
contract. This is an intentional narrow extension to ADR 0047 for operator review.
