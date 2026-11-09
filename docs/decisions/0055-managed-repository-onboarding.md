# 0055: Select a GitHub repository and acquire an immutable managed baseline

Status: accepted, 2026-11-09

Manual clone and absolute-path input did not meet the requested Repository→Issue→execute
flow. The authenticated setup panel now loads a paginated GitHub catalog only when opened,
then acquires the selected repository's default revision through existing SCM read contracts.
Credentials stay in server configuration. Browser input cannot choose URLs, destinations,
branches or credentials. Existing local paths remain an optional advanced mode.

Keep GitHub catalog/URL/auth details in its adapter and integration composition. Shared
acquisition consumes RepositoryInfo, CollaborationSourceControl and RevisionSource. Reuse
verified source limits: 1,000 files, 1MiB/file, 8MiB total, regular modes only, no sensitive
or control paths, symlinks, submodules or truncated trees. Bound acquisition by requests and
deadlines. No remote writes, model calls, package installs or generated-code execution.

Do not run git clone/checkout or extract an archive. Materialize validated blob bytes into a
private staging workspace, construct the local index/commit directly with Git plumbing,
and configure a credential-free origin. No repository hooks/filters/templates execute.
Git subprocesses drop inherited GIT_* redirects and global/system config, disable protocols,
hooks and fsmonitor. Local mode still rejects repository-local executable filter config.
Preserve Git object/source bytes instead of applying host transforms.

Managed workspaces live in an operator-owned sibling directory outside the Factory's Git
checkout and private state root. Publication metadata is private and content addressed by
canonical repository and remote revision. Sync files/directories and record immutable intent
before publishing the workspace. Interrupted unpublished work may be reconstructed exactly;
existing modified or unjournaled workspaces are retained and rejected, never overwritten.
Limit history to 64 managed baselines per state root without automatic deletion.

A materialized local commit is not the original remote commit; record both honestly.
For execution, fetch the current remote source via the existing bounded transport and pass
it through existing remote-Harness verification, remote snapshot, checks/review and Draft
receipts. No manual pull is needed for ordinary code updates. Harness/manifest/CI drift
requires another configuration review before inference. Interrupted delivery resumes the
same recorded Run without rereading new source or regenerating a candidate.

Repository-local Project identity remains stable across managed baseline revisions. Adoption
of an existing local default Project preserves its association using the existing deterministic
Project identity; explicit shared Projects still require matching Project configuration.
Use separate Repository records for physical baselines, preserving old Run manifests. Harness
feedback verifies the managed local baseline separately from the failed Run's remote revision.

Validation: real Git acquisition→approval→Issue→Draft delivery; latest remote source, modified
workspace rejection, schema/origin/role boundaries, unsafe paths/modes, malicious inherited
Git config, interrupted publication recovery, stable Project membership and shared-Project
non-bypass; actual Chromium with no path input; mandatory actual Docker acquisition-to-Draft
case. External model/SCM are simulated in E2E; the read-only catalog GraphQL schema was also
checked against GitHub without displaying identities. Live paid AI delivery remains PC acceptance.
