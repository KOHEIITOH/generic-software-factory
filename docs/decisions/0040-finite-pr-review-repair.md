# ADR 0040: Finite repair on the same Factory PR

Accepted. `sf issue review --config /outside/repo/operator.json --run ORIGINAL_RUN
--confirm-run --confirm-bedrock` advances at most one feedback round, then saves
and exits. Repeat the same command after new review or merge events. This is not
a daemon and does not poll, merge, resolve human threads, or mark a PR ready.

Trust defaults to the authenticated operator identity; `--reviewer LOGIN` may
explicitly select up to 16 trusted reviewers/bots (including for installation
tokens without a `/user` identity). Untrusted feedback is ignored with recorded
IDs. Closed PR, changed external head/base, changed Harness, scope expansion,
quality failure, repeated file candidate, unknown commit preparation, exhausted
budget/deadline, and corrupt state terminate without replay or silent reset.

Each repair reuses the exact Factory delivery receipt and original marker, reads
the PR's bounded complete reviews/threads, uses exact remote head blobs, runs
approved isolated behavioral checks, obtains independent inference review, and
appends a commit via atomic expected-head CAS. Unknown branch writes are read
back only. Approval refers to a trusted current-head review; merge completion
requires the provider's merged state for the exact expected PR head.

Default limits persist across invocations: 3 feedback rounds, 8 model calls,
3,000,000 conservative reserved tokens, 2,500 SCM/API calls, 128 writes, 7 days.
Bedrock SDK retries are included in conservative token reservation. Waiting
consumes no inference. Limits are safety bounds, not a currency cost guarantee.
Each model and commit/branch action is durably reserved before the side effect.
Run/quality artifacts stay in existing storage; structured decisions live under
`automation-v1/<session>/state.json`. No standalone Task CRUD is restored.

Judgment: test/review failures stop rather than inventing successful evidence;
a changed scope needs a new operator configuration. Human approval and actual
merge are external events, so automation records waiting instead of asking a
question or running an unbounded loop.
