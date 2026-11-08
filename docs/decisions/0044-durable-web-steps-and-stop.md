# ADR 0044: Durable single-worker Web steps and cooperative stop

Accepted. HTTP enqueues only a registered plan/advance/review operation, persisting
scope, consent, idempotency identity and events before starting a private Python
worker. It uses the same local controller entry as CLI, never shell commands or
repository executables. One Web step per data root may be active. Repeated HTTP
requests return the same job and never launch another worker. Completed jobs are
never automatically replayed. History is bounded to 500 jobs, retaining evidence.

Worker ownership uses POSIX locks, not PID/liveness guesses. A worker can outlive
a dashboard restart; lost leases become interrupted after a short startup grace.
There is no startup auto-run. An explicit next step re-enters existing durable
workflow journals: unknown inference/commit results stop, unknown delivery is
read back, existing budgets never reset. Interrupted does not imply retry-safe.

Stop is cooperative at the next model/action/API/container-start boundary; an
in-flight model/request/check may finish so its result/cleanup can be recorded.
Revocation and config changes are checked at those same boundaries. Stop never
force-kills a Docker container or PID selected from HTTP. A worker has a one-hour
alarm; existing per-request/check timeouts and cleanup still apply. A stopped
attempt may be terminal under existing safety rules; waiting progress can be
advanced explicitly. No permission to replay unknown side effects is added.

HTTP progress exposes only statuses, identifiers, external links, budget counters,
expiration and structured decision codes. Raw source, prompts, SDK errors,
stdout, tokens, credentials and config paths are not exposed. Jobs use existing
private POSIX atomic documents. Database and distributed worker services remain
optional/future scope. Runtime controls are transport-neutral optional callbacks.
