# ADR 0022: Minimal SourceControl for the existing Draft PR demo

Status: accepted.

The previous GitHub demo HTTP route owned provider API requests and orchestration.
Keep its endpoint and explicit same-origin boolean confirmation, but move REST URLs,
authentication, GitHub JSON, branch/repository parsing and domain record conversion
into GitHubSourceControl. Expose only operations actually needed by the existing
flow: describe repository, read branch revision, create branch, write a file and
create a Draft PR. Reuse RepositoryCapabilities. No merge operation is exposed.

The shared demo workflow consumes SourceControl and opaque IDs/revisions. It checks
write/PR capability before mutations, creates the same marker and stops on failure.
Core uses no GitHub payload, credentials, REST exception or provider normalization.
The HTTP adapter alone maps domain errors and GitHub's external PR number to HTTP.
Only GitHub is wired in integration_defaults; a fixture proves portability without
implementing another remote provider or a general plugin registry.

This preserves a confirmed demo, not production Issue-to-PR delivery. Multi-resource
branch/file/PR creation is not a distributed transaction. Failed/unknown operations
are not automatically retried or rolled back; reconciliation/idempotent production
delivery remains separate work. No model calls, extra startup command, schema or
new write permission is introduced.
