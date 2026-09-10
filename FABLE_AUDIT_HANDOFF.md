# Fable Audit Handoff — extraction-factory

## Read this first

This repository has already undergone GitHub-remote branch reconciliation plus an independent second-pass feature-loss audit. Fable should verify or challenge the supplied evidence, not repeat branch archaeology unless the remote frontier changes.

Candidate branch: `reconcile/mainline-20260910`
Source `master`: `c35ad38324029c7eef2ebe1e5b0f0086fbe3b73e`
Strongest pre-reconciliation runtime: `chatgpt-v126-reconciled-20260902@4071c18e740339a72363ba9246311398c2d80904`
Selective safety-harvest runtime commit: `e97a6dccc06f07b24f091f8b3198997e2f75b281`
Machine-B independently replayed exact GitHub head: `4d82f0fc3e003b71c5c0b2df0a17a842762189f5`
Included Windows runtime hardening: `5221ada186bfedf9a0b9de7401cee874bc68a1d6`

## What the first reconciliation got wrong

The initial report correctly found v1.26 stronger overall, but overclaimed that the divergent v1.14 09D-hardening branch was fully semantically absorbed. Direct content inspection and regression reconstruction found several v1.14 invariants absent from v1.26. The candidate was repaired rather than promoted as-is.

## Stronger v1.14 invariants now harvested

- stable source-grounded witness and claim identities independent of run ID;
- default-preserving deserialization for older SourceUnit / AssertionCandidate artifacts;
- crash-safe atomic JSON/JSONL/TSV controller writers;
- semantic lease TTL derived to outlive provider timeout plus safety margin;
- sealed 09D identity/schema/witness verification before external provider dispatch;
- robust terminal JSON parsing when prior logs contain braces;
- requested 09D post-stage failure downgrades appliance status and returns nonzero.

The stale `controller_v14.py` control path was NOT resurrected. These invariants were selectively integrated into the stronger v1.26 architecture.

## Mechanical evidence already obtained

Machine A disposable checkout:

- 9/9 reconciliation regressions PASS;
- 259/259 full factory tests PASS with 1 justified skip;
- governed reporter PASS;
- deterministic E2E PASS;
- build certification, preflight, package integrity/tamper rejection, ledger resume, provider-wrapper smoke, read-only 09D comparison/projection, and fail-closed untrusted-target behavior PASS.

Machine B independently replayed exact GitHub head `4d82f0fc3e003b71c5c0b2df0a17a842762189f5` in a disposable extracted archive:

- archive SHA-256 `fea904ccc23f6ad4a97c6a5aae2379c2859b28fa5512da6dce9521268469db76`;
- 10/10 reconciliation regressions PASS;
- 260/260 full factory tests PASS with 1 justified skip;
- deterministic E2E PASS with `overall=PASS` and `core_readiness_status=READY_FOR_PROVIDER`;
- this exact head includes runtime hardening commit `5221ada...`;
- isolated `.verify-venv` with `pypdf 6.18.0` resolved the only setup blocker;
- no canonical local user checkout was changed.

See `CURRENT_VERIFICATION_20260910.json` and `MACHINE_B_EXACT_HEAD_VERIFICATION_20260910.json`.

## Verification frontier

The runtime/test frontier is independently mechanically verified through `4d82f0f...`. Finalization after that SHA must remain documentation/receipt-only; prove that delta before promotion.

GitHub Actions attempts on earlier candidate heads failed at startup with zero jobs. Treat those as setup/infrastructure failures, not test results.

## Other divergent branches

The v1.24/v1.25 cold-audit branches were inspected separately. Their old APIs/tests do not replay literally because the architecture evolved, but their substantive invariants are represented in the current split dimension-aware challenge/certification system plus runtime authority checks: required-dimension coverage, exact challenge/result semantic hashing, provider/version/source binding, W4 authority, fail-closed missing/tampered coverage, lifecycle freshness, and independence from gold-construction families.

The v1.11 runbook is superseded by v1.12. The exact v1.12 owner runbook remains preserved under `AUDIT/HISTORICAL/` as historical operator evidence, not current authority.

## What Fable should and should not spend reasoning on

Do not spend high-reasoning budget re-discovering which remote branch is strongest unless refs changed. The remote feature-loss question has already been reopened once, corrected, and mechanically exercised.

Focus Fable effort on:

- whether the selectively harvested invariants compose correctly with v1.26's authority model;
- whether the bounded Windows replace retry is semantically safe and sufficient;
- whether any remaining cross-repo DLE/EI capability should be absorbed;
- whether the factory's operational/semantic claims are sufficient for its intended Estate role;
- any contradiction between this handoff, the code, and exact current tests.

A disagreement is welcome, but it should identify the exact invariant, carrier, test, or authority path being challenged.

## Promotion boundary

The runtime/test tree through `4d82f0f...` has been independently replayed on Machine B. Prove all later finalization commits are documentation-only, then independently review the PR before moving `master`.

Normalization is not semantic-quality certification, clinical correctness, or production acceptance. Final Machine-A/Machine-B canonical checkout reconciliation remains deferred until the GitHub normalization campaign is complete.
