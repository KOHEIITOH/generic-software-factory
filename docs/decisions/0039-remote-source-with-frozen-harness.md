# ADR 0039: Remote candidate source without host checkout

Accepted. Review repairs and sequential child Issues need the exact remote PR
head or current default branch, even when the local operator baseline is older.
Reuse the existing approval, prepared Run, source snapshot, checks and review.

The remote adapter supplies bounded hash-verified Git blobs. The controller
compares the entire discovered Harness inventory, including new/removed sources,
manifest and CI conventions, against the clean local baseline. Profile reference
hashes must also match. Any change stops; remote instructions cannot expand the
operator's authority. Shared Project rules remain operator-owned and hash-bound.

Snapshots use the existing durable payload-before-registration publication and
full rehash on load. No git fetch/checkout, filters, model tools, repository code
execution on the host, or Docker security downgrade is added. Candidate-only
evaluation performs the same behavioral checks and independent review but makes
no SCM writes. A separate controller must authorize exact delivery with existing
local evidence guards and atomic branch CAS.

Judgment: stopping when manifests or Harness change is intentional scope safety;
ordinary code changes do not require local checkout. No new source/state storage
interface is introduced.
