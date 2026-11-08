# ADR 0048: Read-only Web preparation diagnostics

Accepted. Reuse the registered profile, repository binding/Harness checks, local
model configuration, pinned Docker daemon enforcement probe and SCM read adapter.
Local checks never invoke a model, resolve AWS credentials or contact a remote
SCM. A separate explicit button performs one bounded repository read; reported
push capability does not prove fine-grained Issue/PR/native hierarchy writes.
AWS/Copilot authentication and model access remain unknown without actual use.

Only authenticated same-origin operator requests can diagnose a registered
fingerprint. No path/command/credential input, raw subprocess/SDK errors, token
values, model IDs or credential paths in responses. Failures show fixed reasons
and next actions; can_attempt never means end-to-end authentication/quality passed.
No check changes resources, pulls images or grants execution authority. This
reduces PC trial ambiguity without pretending live acceptance has completed.
