# Fable Audit Handoff — extraction-factory

## Read this first

This repository has already undergone GitHub-remote branch reconciliation plus an independent second-pass feature-loss audit. Fable should verify or challenge the supplied evidence, not repeat branch archaeology unless the remote frontier changes.

Candidate branch: `reconcile/mainline-20260910`
Source `master`: `c35ad38324029c7eef2ebe1e5b0f0086fbe3b73e`
Strongest pre-reconciliation runtime: `chatgpt-v126-reconciled-20260902@4071c18e740339a72363ba9246311398c2d80904`
Selective safety-harvest runtime commit: `e97a6dccc06f07b24f091f8b3198997e2f75b281`
Exact runtime candidate independently replayed on Machine B: `6d9358da22b2d76fd4dc765b7407a16391da918f`

## What the first reconciliation got wrong

The initial report correctly found v1.26 stronger overall, but overclaimed that the divergent v1.14 09D-hardening branch was fully semantically absorbed. Direct content inspection and regression reconstruction found several v1.14 invariants absent from v1.26.

The candidate was therefore repaired rather than promoted as-is.

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

- pre-harvest exact candidate: 250/250 tests PASS with 1 justified skip; governed reporter PASS; deterministic E2E PASS;
- post-harvest focused reconciliation regressions: 9/9 PASS;
- post-harvest full factory suite: 259/259 PASS with 1 justified skip;
- post-harvest E2E: PASS, including build certification, preflight, package verification/tamper rejection, ledger resume, provider wrapper smoke, read-only 09D comparison/projection, and fail-closed untrusted-target behavior;
- E2E receipts show `lease_ttl_seconds=1200` and populated `stable_witness_sha256` / `stable_claim_sha256` on produced candidates;
- targeted invalid-09D probe proves provider execution count remains zero when the sealed contract fails.

Machine B independent replay of exact candidate `6d9358da22b2d76fd4dc765b7407a16391da918f`:

- 9/9 reconciliation regressions PASS;
- 259/259 full factory tests PASS with 1 justified skip;
- deterministic E2E PASS with `overall=PASS` and `core_readiness_status=READY_FOR_PROVIDER`;
- first E2E attempt was setup-blocked only by missing `pypdf`; successful rerun used isolated disposable `.venv` with `pypdf 6.18.0`;
- no canonical local user checkout was changed.

See `CURRENT_VERIFICATION_20260910.json` and `MACHINE_B_EXACT_HEAD_VERIFICATION_20260910.json`.

GitHub Actions attempts on earlier candidate heads failed at startup with zero jobs. Treat those as setup/infrastructure failures, not test results.

## Other divergent branches

The v1.24/v1.25 cold-audit branches were inspected separately. Their old APIs/tests do not replay literally because the architecture evolved, but their substantive invariants are represented in the current split dimension-aware challenge/certification system plus runtime authority checks: required-dimension coverage, exact challenge/result semantic hashing, provider/version/source binding, W4 authority, fail-closed missing/tampered coverage, lifecycle freshness, and independence from gold-construction families.

The v1.11 runbook is superseded by v1.12. The exact v1.12 owner runbook remains preserved under `AUDIT/HISTORICAL/` as historical operator evidence, not current authority.

## What Fable should and should not spend reasoning on

Do not spend high-reasoning budget re-discovering which remote branch is strongest unless refs changed. The remote feature-loss question has already been reopened once, corrected, and mechanically exercised on two machines.

Focus Fable effort on:

- whether the selectively harvested invariants compose correctly with v1.26's authority model;
- whether any remaining cross-repo DLE/EI capability should be absorbed;
- whether the factory's operational/semantic claims are sufficient for its intended Estate role;
- whether the documented proof boundaries are adequate and honestly stated;
- any contradiction between this handoff, the code, and exact current tests.

A disagreement is welcome, but it should identify the exact invariant, carrier, test, or authority path being challenged.

## Promotion boundary

The verification-receipt and cold-start documentation commits after `6d9358d...` do not intentionally modify runtime code. Before promotion, mechanically verify that claim and replay the final documentation-complete candidate head on Machine B. Then perform independent promotion review.

Normalization is not semantic-quality certification, clinical correctness, or production acceptance. Final Machine-A/Machine-B canonical checkout reconciliation remains deferred until the GitHub normalization campaign is complete.
