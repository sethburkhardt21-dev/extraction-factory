# MAINLINE RECONCILIATION REPORT

## Scope

Repository: `sethburkhardt21-dev/extraction-factory`

Campaign date: `2026-09-10`

Scope is the GitHub remote universe only. Final Machine-A/Machine-B checkout/worktree/stash/reflog/unreachable-object reconciliation is deliberately deferred until GitHub normalization is complete. `master` has not yet been moved by this reconciliation.

## Canonical source and candidate

- source `master`: `c35ad38324029c7eef2ebe1e5b0f0086fbe3b73e`
- strongest pre-reconciliation runtime: `chatgpt-v126-reconciled-20260902@4071c18e740339a72363ba9246311398c2d80904`
- v1.26 relation to source master: 13 ahead / 0 behind
- candidate: `reconcile/mainline-20260910`
- draft PR: #29

## Remote ref audit

The pre-campaign remote universe was exhaustively enumerated: 37 heads; second page empty. Most non-candidate heads are literal ancestors of the v1.26 line. Five materially divergent historical heads required semantic adjudication:

1. `chatgpt-09d-schema-hardening-v14-20260901@a80121b0add62585886b615e84e8acd483ca48f3`
2. `chatgpt-cold-audit-certification-v124-20260901@22209d496fb95c032e672df4217ec6c5c2daad24`
3. `chatgpt-cold-runtime-w4-v125-20260902@6766238ec34d9c0e8d7ffe43037d677a60bf7bc9`
4. `chatgpt-owner-validation-runbook-v111-20260901@6f65949ff48e4e140cd11eec8c691805b6d5fd50`
5. `chatgpt-owner-validation-runbook-v112-20260901@bcf9301e176b27503383f934de52d4f852c5ebb6`

## Adjudication

### v1.14 09D hardening

**PARTIAL_ABSORPTION -> SELECTIVE_INTEGRATION.**

The first reconciliation incorrectly called this line fully superseded. Direct content inspection found real invariants missing from v1.26. Commit `e97a6dccc06f07b24f091f8b3198997e2f75b281` selectively restored them into the stronger current control path:

- stable source-grounded witness and claim identity across run IDs;
- default-preserving deserialization of older artifacts;
- crash-safe atomic JSON/JSONL/TSV writes;
- lease TTL derived to outlive provider timeout plus safety margin;
- sealed 09D identity/schema/witness verification before external semantic dispatch;
- robust terminal JSON parsing;
- fail-closed status/exit behavior when requested 09D post-stages fail.

The stale `controller_v14.py` authority path was not resurrected.

### v1.24 cold-audit certification

**SUPERSEDED_BY_STRONGER_CURRENT_SPLIT_ARCHITECTURE.**

Its mutation/challenge/scoring/certification intent is represented by the current dimension-aware challenge builder/certifier plus runtime certification authority. Current code additionally binds required dimensions, source/model/version identity, gold-family disjointness, lifecycle freshness and provider-version authority.

### v1.25 cold-runtime W4

**SEMANTICALLY_ABSORBED_CURRENT_RUNTIME_AUTHORITY_STRONGER.**

Its dimension gate/W4 checks are represented by current certifier and runtime certificate-policy/authority code. Restoring the old wrapper would create duplicate authority.

### owner-validation v1.11/v1.12

v1.11 is superseded by v1.12. The exact v1.12 runbook is preserved at `AUDIT/HISTORICAL/OWNER_REAL_VALIDATION_RUNBOOK_v112_20260901.md` as historical operator evidence, not current runtime authority.

## W3 policy defect and repair

Historical v1.26 GitHub Actions run `33667868250` executed 250 tests and failed 2 tests because equation risk escalation checked `content_representation == "EQUATION"` but governed test/source shape used `unit_type == "EQUATION"` with text representation.

Commit `e562d8af372ede9c3b5a9df1a5d3f2aa9c9c5b11` repairs that declared policy by classifying source risk W3 when either field denotes an equation. Candidate-generation semantics remain W2; no new authority path was introduced.

## Mechanical verification

Machine A established the repaired/harvested baseline: 9/9 reconciliation regressions PASS, 259/259 full factory tests PASS with 1 justified skip, governed reporter PASS, deterministic E2E PASS.

Machine B independently replayed exact GitHub head `4d82f0fc3e003b71c5c0b2df0a17a842762189f5` from archive SHA-256 `fea904ccc23f6ad4a97c6a5aae2379c2859b28fa5512da6dce9521268469db76`. That exact head includes Windows runtime hardening commit `5221ada186bfedf9a0b9de7401cee874bc68a1d6`.

Machine-B result: 10/10 reconciliation regressions PASS; 260/260 full factory tests PASS with 1 justified skip; deterministic E2E PASS; `overall=PASS`; `core_readiness_status=READY_FOR_PROVIDER`. The system interpreter lacked `pypdf`, so the first E2E attempt was setup-blocked; a disposable `.verify-venv` with `pypdf 6.18.0` passed. No canonical local checkout was changed.

### Windows atomic-replace hardening

Commit `5221ada...` adds bounded retry/backoff around transient Windows `PermissionError` from `os.replace()` and a regression forcing first-attempt failure then successful retry. Exhausted retries still re-raise. Machine B's exact-head replay includes this commit, so the previous verification gap is closed.

## GitHub Actions status

Earlier PR-triggered runs failed at Actions startup with zero jobs created. These are `SETUP_ERROR` / infrastructure failures, not code-test passes or failures.

## Feature-loss result

**PASS AFTER SECOND-PASS SELECTIVE HARVEST AND INDEPENDENT MACHINE-B EXACT-HEAD REPLAY.**

No remaining material strongest-known GitHub-remote capability from the enumerated divergent refs is known to require a second authority path. This is a capability-preservation conclusion, not semantic-quality certification.

## Promotion posture

**READY FOR INDEPENDENT PROMOTION REVIEW AFTER DOCUMENTATION-ONLY FINALIZATION.**

Required next steps:

1. Commit only verification/cold-start documentation after verified head `4d82f0f...`.
2. Prove the delta from `4d82f0f...` to final PR head contains no runtime or test changes.
3. Independently inspect the complete PR diff and authority implications.
4. Only then promote `master`.

## Fable reasoning frontier

Fable should not repeat remote branch archaeology unless refs changed. It should instead verify or challenge the supplied evidence and spend reasoning on:

- whether the selectively restored v1.14 invariants compose correctly with v1.26;
- whether the Windows atomic-replace retry is safe and sufficient;
- whether any cross-repo DLE/EI capability remains worth absorbing;
- whether operational/semantic claims match actual authority paths and proof strength;
- any contradiction between the handoff, code, tests and receipts.

Normalization is not semantic-quality certification, clinical correctness, or production acceptance.

## Zero-context continuation

Read first:

1. `FABLE_AUDIT_HANDOFF.md`
2. `CURRENT_VERIFICATION_20260910.json`
3. `MACHINE_B_EXACT_HEAD_VERIFICATION_20260910.json`
4. `DIVERGENT_REF_AUDIT_20260910.md`
5. this report
6. `MAINLINE_RECONCILIATION_MANIFEST.json`

Do not move canonical local Machine-A/Machine-B checkouts until the GitHub normalization campaign is complete.
