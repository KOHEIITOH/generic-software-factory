# 0054: Recover an expired local operator session without losing the dashboard

Status: accepted, 2026-11-09

The public API health indicator does not establish operator authority. Previously an
expired/logged-out browser only displayed an instruction and the module cached its
initial exchange forever. Opening a new fragment in the same tab did not reauthenticate.

Show operator authority separately and provide a masked input for the launcher's existing
same-origin capability link, plus a read-only session recheck. Handle hashchange so the
terminal link works in the same SPA. Deduplicate only in-flight exchanges, serialize
rotations, and discard the capability afterwards. A failed login must not poison retries.
On window focus, recheck the cookie; 401s from operator/setup requests lock the controls
and clear prior consent. Reauthentication fetches status only, never replays a job or
changes request IDs/budgets. Keep unknown-submission recovery explicit and idempotent.

The server remains unchanged: exact loopback origin and custom header, root proof,
HttpOnly/SameSite cookie, eight-hour expiry, logout/restart revocation and rate/session
limits. No anonymous token issuer, persistent browser capability, refresh-token bypass,
automatic browser permission grant or host command execution is introduced. Restarting
the server requires its new terminal link. Remove URL fragments immediately, do not send
links to other origins, clear submitted input and never echo tokens in errors.

Validation: real Chromium logout/reconnect, bad-token retry, wrong-origin link rejection,
same-tab fragment exchange, expired/missing-cookie lock and recovery, initial failed-login
recovery, and no job submissions or browser storage writes during reconnection. Existing
server expiry/revocation/security and job idempotency tests remain in force.
