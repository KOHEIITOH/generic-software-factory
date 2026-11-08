# ADR 0047: Source-bound planning, independent interpretation, downstream continuity

Accepted. New requirement workflows select references from the existing verified
remote snapshot before inference. Explicit context_paths wins; empty/omitted
opts into conventions from ADR 0046. No document candidates retains Issue-only
input and still requires sufficiency review. Existing frozen plans are not
rescanned/migrated or replayed; old citation-free plan fingerprints remain valid.

Every derived requirement cites known source IDs (issue or an exact selected
path). Existing two model calls perform planning and independent review; there
is no additional unbounded discovery agent or automatic budget increase. Review
must classify every input as requirement/supporting/irrelevant, explain its
interpretation, cover all identified requirement sources, bind the source/plan
fingerprints, and explicitly report ready/insufficient/conflicting. A planner
may decline early. Insufficiency/conflict or malformed/missing evidence stops
before child Issue writes. Semantic judgment is model-based; schema checks do
not prove all contradictions can be detected.

The private journal records selected paths/reasons/revision/SHA256/size and full
bounded interpretation/review provenance. Requirement IDs map to citations and
child units. Native child bodies include source identity and revision; their
idempotency markers also bind the source fingerprint. Child implementation and
independent repair receive the same references with content hashes constrained
in existing DevelopmentConfig. Changed/missing references stop before new model
calls. Ordinary code revisions may advance; reference contents may not silently
drift. Interrupted unpublished planning rechecks changed remote tips before
reusing frozen model receipts.

Operator Web consent states automatic versus explicit reference selection. Its
progress view exposes only paths/hashes/selection and assessment categories plus
requirement-to-child links. Source text, free-text interpretation/concerns, raw
model responses and SDK exceptions remain private. Full reasons are inspectable
in the existing automation journal. Stop/retry/authority limits remain unchanged.

Judgment: use existing context_paths, Run snapshots, journals and adapters rather
than adding a second requirement/task system. Unsupported/oversized context is
reported, never truncated. No external links fetched, command execution, Harness
permission merging, parent-Issue creation, AWS resource or deployment changes.
