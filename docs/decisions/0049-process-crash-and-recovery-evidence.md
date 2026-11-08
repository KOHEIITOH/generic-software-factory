# ADR 0049: Process-death and transport fault verification

Accepted. Add actual SIGKILL at durable reservation / simulated remote-effect /
pre-receipt boundaries, plus atomic rename interruption and localhost connection
loss. Model/SCM services are file-backed simulations; no paid model or GitHub
mutation is used. Parent processes reopen real journals and leases independently.

Verify OS-released worker locks yield interrupted status; pending model requests
are not called again and budgets do not reset. A lost commit receipt stops;
branch/PR side effects are adopted by authoritative readback, never written a
second time. Killing before/after atomic replace yields only a complete old/new
record. Staging files are not authoritative. These are process-death tests,
not a claim of hardware/power-loss durability or distributed storage semantics.

Judgment: exercise existing production boundaries rather than expose a fault
injection API or add automatic retries. Tests remain ordinary required Python CI.
