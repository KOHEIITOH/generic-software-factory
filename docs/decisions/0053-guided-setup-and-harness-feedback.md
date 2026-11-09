# 0053: Guided setup and bounded, evidence-linked Harness suggestions

Status: accepted, 2026-11-09

Expose a separately authenticated local setup capability in the operator screen. The user
selects an explicit clean Git root, sees its verified GitHub origin, proposed source file
scope, fixed image, checks, Harness selection/exclusions and generated rules. Nothing runs
before the displayed exact proposal is approved. Setup never imports repository code,
executes tests on the host, fetches dependencies or models, or modifies Git. Store the
approved config in private Factory storage and reuse OperatorProfiles, DevelopmentConfig,
Harness discovery/validation/composition and existing execution contracts.

This deliberately extends the former CLI-only configuration boundary: authenticated setup
accepts an explicit repository path and proposed test argv. Execution routes still accept
only registered identities and frozen scope. Test argv is approved configuration and runs
only in the existing offline Docker sandbox, never a shell command on the host. Credentials
stay in local standard SDK/CLI configuration. Invalid symlinks, origin, dirty source, stale
revision/Harness inventory and mismatched proposal fingerprints block registration.

If repository rules are absent, generate deterministic minimal ProjectHarness text; do not
write AGENTS.md or invent commands/permissions. The reserved repository-<identity hash>
Project name maps these generated repository-local rules to the existing default Project,
so adding rules after a failed Run preserves Issue association. Explicit shared Project
names retain the existing separate identity. Existing instructions/directory Harness are
reused; discovered profile YAML is explicitly excluded in this wizard, since checks are
separately reviewed, and the exclusion is displayed. No silent source conflict is ignored.

Statically suggest unittest or pytest when recognized. Presets require a nonempty actual
run without skips, expected failures or failures; ignore inherited pytest options, disable
cache writes and automatic plugin loading. The operator supplies a trusted image containing
required dependencies. Unknown languages/frameworks require explicit checks rather than
pretending a generic preset proves their behavior. Do not run package installation/setup.

After failed Web development, derive a deterministic text suggestion only from the exact
failed session/Run and received model/check/review evidence. Auth/transport/resource failure
without quality evidence is not learning. No free-form AI generation, new inference charges,
write-scope changes, weaker checks, automatic adoption or recursive retry. One suggestion per
Run, five improvement proposals per repository and 100 proposals per state root bound the
history. Approval registers a new immutable profile; the original configuration, terminal
Run and cumulative budget remain evidence. The next explicitly started run uses unchanged
checks and independent review. Simulated successful re-evaluation proves the connection,
not that a particular suggested rule causally improves model quality.

Config publication and profile installation are durable and replayable. Identical setup
requests reuse the proposal; retries after registry publication do not duplicate profiles
or revive revoked ones. Recheck a parent configuration and source/Harness baseline before
installing an improvement. Show pending setup/improvement records for recovery. Keep the
panel unmounted when closed so normal execution does not fetch setup state.

Validation: unit/integration security and replay cases, actual test preset subprocesses,
real Chromium guided registration, and mandatory real Docker no-Harness→setup→worker→
checks/review→Draft PR and failed-review→approved-improvement→Draft PR cases. External model and SCM are simulated; live paid Bedrock/GitHub
acceptance remains on the user's PC. AWS provisioning/deploy and automatic PR merge are absent.
