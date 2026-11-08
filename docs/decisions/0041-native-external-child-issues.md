# ADR 0041: External child Issues, no Factory Task system

Accepted. The existing provider-neutral IssueTracker contract is implemented by
GitHub native Issues and sub-Issue relationships. GraphQL schema inspection
confirmed Issue.parent, Issue.subIssues and AddSubIssueInput/Payload. Parent
replacement is disabled. A child already attached elsewhere is an error.

Creation verifies exact authoritative title/body after the POST. Marker search
is bounded, rejects incomplete/ambiguous results and verifies repository/content.
Search absence after an unknown write is never permission to create again;
the workflow must retain a pending receipt for read-only reconciliation. Native
child readback must confirm the association before execution.

This adapter does not plan, execute code, retry writes, grant permissions or
introduce Task CRUD. Those policies remain in the common bounded workflow.
