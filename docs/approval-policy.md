# Approval policy: autonomy by risk

The Software Factory must not request human approval for every routine action.
Approval decisions belong at the execution boundary, not inside the AI model.

| Operation | Default policy |
| --- | --- |
| Read approved repository files and analyze | Automatic |
| Edit files in isolated, disposable workspaces | Automatic within scope |
| Run allowlisted tests, lint, and static checks in a sandbox | Automatic |
| Create commits and pull requests on task branches | Automatic within scope |
| Merge a pull request | Human approval initially |
| Deploy to production | Human approval |
| Modify secrets, credentials, permissions or production data | Explicit human approval |
| Execute unknown commands or operate outside the sandbox | Deny until separately reviewed |

## Execution prerequisites

- An action must be evaluated using its exact target, environment, scope and
  capabilities. A human-readable summary is **not** a secure action identifier.
- Automatic operations require a configured policy, sandbox isolation,
  scoped permissions and audit logging.
- Approval is bound to the immutable action payload, identity and environment,
  and should expire; a changed action needs a new approval.
- An AI-generated or caller-constructed `ApprovalDecision` is **not**
  proof of a human decision. The MVP gate is a pure validation primitive only.
- No command or file-write executor is wired to this gate yet. Integration
  must fail closed for sensitive actions and must not let the agent mint its
  own approvals.
- CI success is a quality signal, not authorization to merge or release.

## Next implementation

Introduce a typed policy decision (`auto`, `require_approval`, `deny`),
a trusted approval authority, and a capability-limited execution adapter.
Test policy bypasses and action mutation before enabling real side effects.
