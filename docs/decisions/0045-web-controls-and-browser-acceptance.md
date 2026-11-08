# ADR 0045: Explicit Web advancement and browser acceptance

Accepted. Keep `sf web --rebuild` as the normal launcher. One-time local profile
registration establishes scope; the browser displays that scope and requires
per-job consent, including Bedrock charges. Plan, advance and same-PR review use
existing controllers. Stop is cooperative and interrupted/terminal states remain
honest; the UI never implies unknown effects can be replayed or budgets reset.

Timers only read local progress while a worker is active, never fetch GitHub
or advance workflows. Unknown HTTP submission responses retain the same nonce.
No source/config path/prompt/credential is needed by the UI. Authentication is
cookie based after a one-time fragment exchange, including under React StrictMode.

Browser acceptance covers actual HTTP and durable records with simulated workflow
effects: explicit consents, capability removal, unknown-response idempotence,
child/PR links, progress and budgets, stop, reload/resume, mobile width, anonymous
access and logout. Separate required Docker CI exercises the real private worker
and actual workflow checks with simulated model/SCM. Neither is a claim of live
Bedrock/GitHub E2E; that remains the PC acceptance test.
