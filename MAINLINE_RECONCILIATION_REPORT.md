# MAINLINE RECONCILIATION REPORT

## Repository and scope

- Repository: `sethburkhardt21-dev/extraction-factory`
- Campaign date: `2026-09-10`
- Scope: **GitHub remote universe only**.
- Final Machine-A/Machine-B checkout/worktree/stash/reflog/unreachable-object reconciliation is deliberately deferred until the GitHub repositories are normalized.
- Canonical `master` is not moved here.
- Historical branches are preserved; no force-push or branch deletion is part of this reconciliation.

## Canonical source and candidate

- `master`: `c35ad38324029c7eef2ebe1e5b0f0086fbe3b73e`
- strongest pre-reconciliation runtime frontier: `chatgpt-v126-reconciled-20260902@4071c18e740339a72363ba9246311398c2d80904`
- v1.26 relationship to `master`: **13 ahead / 0 behind**
- reconciliation candidate: `reconcile/mainline-20260910`
- draft promotion/CI surface: PR **#29**

The candidate preserves the v1.26 runtime as its base, preserves one valuable historical owner-runbook blob, and contains one narrowly scoped runtime repair for an already-existing W3 source-risk policy bug found by the previous CI run.

## Remote branch census

The pre-campaign remote branch universe was exhaustively enumerated: **37 heads**. A second branch page was empty.

Most heads are literal ancestors of v1.26 and therefore contain no unique remote implementation requiring harvest. The materially relevant divergent heads were:

1. `chatgpt-09d-schema-hardening-v14-20260901@a80121b0add62585886b615e84e8acd483ca48f3`
2. `chatgpt-cold-audit-certification-v124-20260901@22209d496fb95c032e672df4217ec6c5c2daad24`
3. `chatgpt-cold-runtime-w4-v125-20260902@6766238ec34d9c0e8d7ffe43037d677a60bf7bc9`
4. `chatgpt-owner-validation-runbook-v111-20260901@6f65949ff48e4e140cd11eec8c691805b6d5fd50`
5. `chatgpt-owner-validation-runbook-v112-20260901@bcf9301e176b27503383f934de52d4f852c5ebb6`

## Divergent-ref adjudication

### v1.14 09D schema-hardening line

**Classification after second-pass audit: PARTIAL_ABSORPTION -> SELECTIVE_INTEGRATION.**

The first reconciliation incorrectly classified this branch as fully superseded. Direct content inspection showed that v1.26 retained the stronger overall architecture but had lost several v1.14 invariants. Those invariants were selectively integrated into the v1.26 control path at runtime commit `e97a6dccc06f07b24f091f8b3198997e2f75b281`:

- stable source-grounded witness and claim identities independent of run/model IDs;
- backward-compatible default-preserving deserialization for old artifacts;
- crash-safe atomic JSON/JSONL/TSV controller writes;
- semantic lease TTL derived to outlive provider timeout plus margin;
- sealed 09D identity/schema/witness verification before external semantic dispatch;
- robust terminal-JSON parsing in the appliance wrapper;
- fail-closed appliance status/exit code when a requested 09D post-stage fails.

The stale `controller_v14.py` path was deliberately NOT restored. Existing v1.26 09D comparison/projection/certification machinery remains authoritative; only missing invariants were harvested into that stronger architecture.

### v1.24 cold-audit certification line

**Classification: SUPERSEDED BY CURRENT DIMENSION-AWARE COLD-AUDIT CERTIFIER.**

The old branch's source-first positive/negative mutation scorer is represented in stronger current form by:

- `factory/benchmarks_ext/cold_audit_challenge_dimensions.py`
- `factory/benchmarks_ext/cold_audit_certifier.py`
- compatibility entrypoint `factory/benchmarks_ext/certify_cold_audit.py`

Current authority includes explicit semantic dimensions, per-dimension coverage, exact source/model/version binding, gold-family disjointness, lifecycle/reactivation checks, and provider-verified immutable-version requirements. The old scorer is not restored as a second authority.

### v1.25 cold-runtime W4 line

**Classification: SEMANTICALLY ABSORBED / CURRENT CERTIFIER STRONGER.**

Its unique `certify_cold_audit_dimensions.py` wrapper has been folded into the canonical current certifier. Restoring it would duplicate certification authority.

### owner-validation runbook v1.11

**Classification: SUPERSEDED BY v1.12.**

No runtime harvest.

### owner-validation runbook v1.12

**Classification: RUNTIME ALREADY ABSORBED; OPERATIONAL KNOWLEDGE WORTH PRESERVING HISTORICALLY.**

The exact runbook blob is preserved at:

`AUDIT/HISTORICAL/OWNER_REAL_VALIDATION_RUNBOOK_v112_20260901.md`

It is historical evidence/operator knowledge, not current version authority. The stale Kanban variant is deliberately not restored.

## Feature-loss audit

**Corrected remote GitHub feature-loss result: PASS AFTER SELECTIVE HARVEST; independent exact-head replay still required.**

The first pass was not sufficient: it missed real v1.14 safety invariants. After reopening that branch at content level, selectively harvesting the missing invariants, and separately adjudicating v1.24/v1.25, no remaining material strongest-known remote capability was identified as missing from the candidate after:

- exhaustive remote-head enumeration;
- literal-ancestor comparison for the non-divergent heads;
- individual semantic adjudication of the five divergent heads;
- preservation of the one unique operational document worth retaining;
- explicit refusal to resurrect stale duplicate controller/certifier authority surfaces.

This is a capability-preservation conclusion, not a test-pass conclusion.

## Previous v1.26 CI failure — exact root cause

GitHub Actions run `33667868250` on exact v1.26 head `4071c18e740339a72363ba9246311398c2d80904` ran **250 tests** and ended with **2 failures / 1 skip**. The clean-checkout E2E job was skipped because the unit-test matrix failed.

Both failures were in `test_w3_tierb_routing.py`:

1. `test_primary_request_remains_w2_candidate_generation_for_w3_equation_source`
   - expected candidate metadata `source_risk_work_class == W3`
   - observed `W2`
2. `test_w3_equation_family_cannot_be_locally_closed_without_any_specialist_flags`
   - expected `SPECIALIST_REVIEW_REQUIRED`
   - observed `LOCAL_PRECISION_COMPLETE`

The failure was traced mechanically to `classify_source_unit()` in `factory/hermes_factory/risk.py`: equation escalation checked `content_representation == "EQUATION"`, while the governed test/source shape used `unit_type == "EQUATION"` with `content_representation == "TEXT"`.

## Targeted repair

Candidate commit:

`e562d8af372ede9c3b5a9df1a5d3f2aa9c9c5b11`

Repair:

- preserve W2 candidate-generation request semantics;
- classify source risk as W3 when **either** `content_representation` or `unit_type` is `EQUATION`;
- reuse the existing regression tests; no new feature or parallel authority was introduced.

This is a minimal repair of already-declared v1.26 policy, not greenfield functionality.

## Fresh candidate CI status

PR #29 was opened as a **draft** specifically to provide an exact-candidate GitHub verification surface without moving `master`.

Two PR-triggered attempts observed so far failed at GitHub Actions startup before creating any jobs:

- run `34406883546` on `e562d8af...`: `startup_failure`, 0 jobs;
- run `34407014258` on the subsequent documentation commit: `startup_failure`, 0 jobs.

The first run also refused a failed-jobs retry with HTTP 403 (`workflow run cannot be retried`). These startup failures are **not code-test evidence** and are not relabeled as test failures or passes.

GitHub Actions still lacks a usable exact-head receipt because those runs failed before jobs were created. Machine-A disposable-checkout verification now supplies local mechanical evidence for the repaired candidate: 259/259 factory tests PASS with 1 justified skip, 9/9 new reconciliation regressions PASS, governed reporter PASS, and deterministic E2E PASS.

## Promotion posture

**NOT READY FOR PROMOTION — independent Machine-B exact-GitHub-head replay remains.**

Reason: the candidate now passes the maintained mechanical suite on Machine A, including new regressions for the harvested invariants, but the authoring/repair machine must not certify itself. `master` remains unchanged until:

1. the final candidate is pushed and resolved to an exact GitHub SHA;
2. Machine B replays the exact GitHub SHA in a disposable clean checkout;
3. full unit suite, reconciliation regressions, E2E, build/certification integrity and repository-required gates pass there;
4. independent promotion review confirms no feature loss or authority regression.

If GitHub Actions remains unable to start, verification can be completed during the owner-deferred final Machine-A/Machine-B local reconciliation, but that local phase should occur only after GitHub normalization across the repository universe is complete.

## Authority boundaries

- 09D remains read-only downstream authority; no write, canonicalization, or automatic identity merge is authorized.
- Extraction output remains non-canonical review material unless separately governed and promoted.
- Model certification remains exact provider/model/version/source/benchmark scoped.
- Historical runbooks remain historical evidence, not automatic current instructions.
- GitHub reconciliation is not clinical correctness or production acceptance.

## Zero-context continuation

1. Resolve `reconcile/mainline-20260910` to its live SHA.
2. Read this report and `MAINLINE_RECONCILIATION_MANIFEST.json` first.
3. Treat v1.26 as the pre-repair runtime base; `e562d8af...` is the W3 equation-classification repair and `e97a6dc...` is the selective v1.14 safety-invariant harvest.
4. Do not resurrect the old v1.14 controller or old cold-audit certifier wrappers as competing authorities; the missing v1.14 invariants were already integrated into the v1.26 path.
5. Do not treat the preserved v1.12 runbook as current runtime version authority.
6. Use PR #29 only as a candidate/verification surface; do not merge while verification is unresolved.
7. Once all GitHub repositories are normalized, perform the final local Machine-A/Machine-B reconciliation before moving local canonical checkouts.

## Final recommendation

**GITHUB REMOTE CONTENT RECONCILIATION COMPLETE AFTER SECOND-PASS CORRECTION; PROMOTION BLOCKED ON INDEPENDENT MACHINE-B REPLAY OF THE FINAL PUSHED SHA AND FINAL REVIEW.**
