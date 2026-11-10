# 0056: Guided Node checks and approved npm dependency images

Accepted: 2026-11-10

The existing Python-only setup selected a Python image and left checks empty for a
TypeScript/React repository. Reuse DevelopmentConfig, BehavioralCheck, offline Docker,
verified source snapshots and explicit Harness approval; do not introduce a parallel workflow.

Read package.json and npm lock v2/v3 statically. Propose recognized Vitest/Jest,
TypeScript noEmit and ESLint scripts, retaining their declared commands for operator review.
Do not substitute type/lint-only checks for an unsupported declared test script. If no test
exists, disclose that type/lint is not unit-test coverage. Unknown package managers,
workspace/file/git/private-registry dependencies require explicit manual configuration.

Install dependencies only after an operator-authenticated exact-plan approval. Use a
controller-owned Dockerfile, pinned multiarchitecture Node22/Python images, manifest/lock
bytes only, public npm registry HTTPS tarballs with integrity, no lifecycle scripts,
no repository .npmrc, host mounts, build secrets containing credentials, or source code.
The platform's public proxy CA may be a BuildKit secret mount; TLS stays enabled.
Bound build client/process-group lifetime to ten minutes, keep output private, and publish a
cache receipt only after exact manifest revalidation. Reuse receipts only for the same recipe
and an existing content-addressed local image. Never push images or silently migrate configs.

Accept immutable local sha256 image IDs alongside existing registry@digest references.
Mutable tags remain rejected. This enables local Docker builds without pretending that a
local config ID is a registry manifest digest. Existing container inspection verifies the
exact requested image and all isolation settings.

Runtime checks use the same unprivileged offline container and limits. Copy source into a
private tmpfs directory, link image-owned dependencies, and place generated caches/reports
there. Preserve original candidate bytes and provenance. Manifest and lock hashes are frozen
as read-only approved references, checked before inference and by the runtime wrapper.
Use bounded `source_hashes` for these integrity-only files; they are not requirement
documents or implicit model context. Existing `context_hashes` retain their document
meaning and limits. Planning validates source pins and child scopes preserve them.
Vitest/Jest reports must contain a positive number of executed, passed assertions and no
skips/todos/failures. Lint/type checks are separately named. No installs/network during tests.

Validation: static unsafe-dependency rejection, authentication/approval/schema boundaries,
manifest freezing, Chromium dependency-preparation consent and successful profile registration,
and mandatory real Docker dependency preparation→TypeScript fix→checks→Draft delivery with
simulated model/SCM. Actual PC Bedrock/GitHub acceptance remains a separate real-service check.
