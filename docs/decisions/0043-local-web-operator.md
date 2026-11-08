# ADR 0043: Local operator authority for Web execution

Accepted. The loopback dashboard remains one command. The launcher creates a
random per-server root capability in the URL fragment (not an HTTP query), and
the browser exchanges it for an eight-hour HttpOnly SameSite=Strict cookie. The
fragment is removed immediately. No secret in assets/localStorage/API output.
Same-origin, exact loopback host and a custom header are required for every
operator read/write. Sessions expire, logout revokes, restart invalidates all.
This is local single-OS-user authority, not remote or multi-user authentication.

Only a local CLI can register or revoke operator-owned configurations outside
the target repository. The configuration fingerprint and dashboard data root
must match on every execution. HTTP accepts only registered profile identities,
not filesystem paths, commands, credentials, arbitrary scopes or approvals.
Bedrock consent is explicit per submitted job. Registering a profile does not
invoke AI, execute repository code or grant merge/deployment authority.

Judgment: retain existing public read-only dashboard behavior and scope the new
capability to operator routes. No login/password database or network service is
needed. Existing workflow budgets and quality gates remain authoritative.
