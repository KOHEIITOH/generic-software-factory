# ADR 0026: Model changes are bounded data, not host tool authority

Status: accepted as a disconnected implementation primitive.

Use the existing text-only ModelProvider contract to request a strict JSON change
proposal, bound to exact Run, approved source revision/fingerprint, Harness bundle
and operator-selected allowed paths. Validate unique fields/paths, old-file hashes,
text/response/context budgets and nonempty actual changes. Reject commands, test
outcome claims, permission claims, deletion, binary writes, path conflicts and
control/secret/dependency/Harness edits in the initial profile.

Construct candidate file bytes in memory and revalidate before use. Never write
model output into the user's checkout or execute it on the controller. This scope
is descriptive, not an approval token. Only a trusted controller after appropriate
inference/context approval may invoke the provider. Do not wrap a tool-capable host
AgentRuntime and pretend prompt instructions remove its tools.

Proposal fingerprint is a canonical data identifier, not a checked Git diff, commit,
quality result or permission to ship. Actual source materialization in verified
isolation, collectors, review, Run persistence and Draft PR delivery remain separate
connections. Fixture-provider tests are not a live AI end-to-end completion claim.
