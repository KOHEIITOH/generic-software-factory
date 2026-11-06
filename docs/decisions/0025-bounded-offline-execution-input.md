# ADR 0025: Bounded stdin into the verified offline executor

Status: accepted as an executor transport prerequisite, not connected Issue execution.

Allow explicit immutable bytes up to 16 MiB as stdin to run_offline_command. Verify
OpenStdin in the created container, attach interactively only when requested, and
multiplex nonblocking writes with bounded stdout reads under one deadline. A blocked
input consumer cannot prevent timeout/cleanup. Incomplete transfer or nonzero Docker
CLI exit cannot become success solely from an exited-zero container inspection.

Keep digest pinning, enforced cgroup-v2 resource gate, no host mounts/socket, private
IPC, read-only root, dropped capabilities, no-new-privileges, proxy clearing and
forced container cleanup. No host fallback, network enablement or inherited credential
mount is introduced. Payload is not put in process argv or environment. Existing
no-stdin behavior remains available.

This transports controller-selected data only. It does not validate an entire source
bundle, authorize a repository/command, collect quality proof, run a model, or make
ImplementationPlan executable. Workspace preparation and artifact/subject binding
must be connected separately before enabling Issue execution.

Hosted isolation CI must actually run all seven required tests, including binary
input roundtrip, stdin backpressure timeout and command failure with input; skipped
required tests fail CI. Local unsupported daemons continue to refuse execution.
