# Divergent Ref Audit — 2026-09-10

Remote GitHub universe was enumerated from a bare clone. At the current frontier there are 38 heads and 0 tags, including the reconciliation candidate. All but five historical heads are literal ancestors of the candidate.

## `chatgpt-09d-schema-hardening-v14-20260901`

**Final classification: PARTIAL_ABSORPTION; SELECTIVE HARVEST REQUIRED.**

The initial reconciliation called this branch semantically superseded. Independent content inspection overturned that conclusion. v1.26 was stronger overall, but had lost several v1.14 invariants:

- source-grounded stable witness/claim identity across run IDs;
- default-preserving deserialization of older artifacts;
- atomic/fsync controller artifact writes;
- lease TTL tied safely to provider timeout;
- exact sealed-09D identity/schema/witness predispatch gate;
- robust terminal-JSON parsing;
- fail-closed appliance status when requested 09D post-stages fail.

These were ported into v1.26 without reviving the stale `controller_v14.py` authority path. Regression tests were rewritten against current APIs rather than blindly copying obsolete test harnesses.
## `chatgpt-cold-audit-certification-v124-20260901`

**Final classification: SUPERSEDED_BY_STRONGER_CURRENT_SPLIT_ARCHITECTURE.**

The old branch bundled challenge mutation, case validation, execution, scoring and certificate construction. Current v1.26 separates those responsibilities across `cold_audit_challenge_dimensions.py`, `cold_audit_certifier.py`, runtime certificate policy, lifecycle/replay authority and source-bound certification.

Current tests cover the old positive/negative challenge intent plus stricter requirements: numeric/atomicity/negation, qualifier and relationship dimensions, required-dimension coverage, per-dimension failure, semantic freshness, gold-construction independence, provider/version authority, W4 keying, exact source/version/coverage binding and tamper invalidation. The old single-file scorer should not be restored as parallel authority.

## `chatgpt-cold-runtime-w4-v125-20260902`

**Final classification: SUPERSEDED_BY_STRONGER_CURRENT_RUNTIME_AUTHORITY.**

The old wrapper's dimension gate and W4 runtime checks are represented in the current dimension-aware certifier plus `cold_audit_certificate_policy.py` and `certification_authority.py`. Current authority additionally hashes coverage, rejects missing/tampered dimensions, binds candidate semantics, verifies current registry identity, and participates in lifecycle freshness/replay checks.

Old tests fail against the current tree largely because APIs and challenge cardinality became stricter; this was not treated as proof of feature loss. Their invariants were mapped to current code/tests instead.

## Owner-validation runbooks

v1.11 is superseded by v1.12. The exact v1.12 runbook blob is preserved under `AUDIT/HISTORICAL/OWNER_REAL_VALIDATION_RUNBOOK_v112_20260901.md`. It is historical operator evidence only.

## Feature-loss disposition

After the v1.14 selective harvest, no remaining known material GitHub-remote capability from the five divergent historical refs requires a second runtime authority path. Final local Machine-A/Machine-B ref/reflog/stash/unreachable-object reconciliation remains intentionally deferred.