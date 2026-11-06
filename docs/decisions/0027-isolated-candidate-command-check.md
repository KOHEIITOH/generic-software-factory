# ADR 0027: Candidate source is materialized only in verified isolation

Status: accepted as an execution primitive; not an enabled Issue execution endpoint.

Revalidate a Run-scoped change proposal, construct candidate bytes in memory, and
send a bounded base64/hash bundle plus controller-approved command through the
verified offline executor. The trusted isolated Python parent (-I) materializes
source in a fresh tmpfs, then executes untrusted repository/check code in a child.
No repository code is imported into the host or trusted parent; no host mounts,
credentials, network or fallback execution are added.

Capture bounded child output under a deadline, kill the command group, inspect
candidate file integrity, and emit one strict request-hash-bound report. Transport
failure, wrong request, unknown fields, contradictory success, changed source or
unconfirmed cleanup cannot be accepted as command success. The request hash includes
Run/source/Harness/proposal identity, not only file contents. Outer Docker teardown
remains mandatory even if child processes outlive their command group.

Command exit zero is not a test-count proof, approval, independent review or delivery
eligibility. The trusted controller must connect real collectors/provenance and
record evidence. File hashes detect observed mutation, not arbitrary adversarial
program semantics. This initial executor keeps the existing source/CPU/memory/time
budgets and rejects unsupported requests rather than running them on the host.

Hosted CI must actually execute eleven required Docker cases, including valid and
failing candidate tests, source mutation and timeout; required skips fail CI. The
fixture proposal is not a live model or real Issue-to-PR completion claim.
