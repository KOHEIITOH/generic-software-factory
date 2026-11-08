# ADR 0046: Bounded requirement references from verified source

Accepted. Existing operator `context_paths` is authoritative when nonempty. An
empty/omitted list opts into deterministic convention discovery: root README,
root requirement/spec/design documents and recognized requirement-related text
under docs/doc/requirements/spec directories. Historic ADR/archive/test/vendor
and unrelated files are excluded. No link following, host scanning, code/tool
execution or new permissions. Read only the existing verified Git blob contract.

At most 12 documents, 24 KiB/file, 48 KiB total and the existing reference/context
budgets apply. Missing explicit paths, invalid/empty UTF-8 or exceeded budgets
stop rather than fall back or truncate. No documents means Issue-only input,
whose sufficiency still needs planning review; absence never invents requirements.

Record source repository, exact revision, mode, selected paths, byte counts,
SHA256 and selection reasons with a canonical fingerprint. Existing config
can freeze reference hashes for downstream implementation/review. Hashes can
only constrain context_paths, never add paths or capabilities. Omitted and empty
context_paths are equivalent, preserving existing config fingerprints.

Judgment: add no second requirement configuration/registry. Convention detection
identifies candidates, not authoritative policy or semantic completeness. The
workflow integration must independently review sufficiency/conflicts and preserve
citations, then propagate the frozen references to child execution and repair.
