# Fable Audit Handoff — extraction-factory

## Read this first

This repository has already undergone GitHub-remote branch reconciliation plus an independent second-pass feature-loss audit. Fable should verify or challenge the supplied evidence, not repeat branch archaeology unless the remote frontier changes.

Candidate branch: `reconcile/mainline-20260910`
Source `master`: `c35ad38324029c7eef2ebe1e5b0f0086fbe3b73e`
Strongest pre-reconciliation runtime: `chatgpt-v126-reconciled-20260902@4071c18e740339a72363ba9246311398c2d80904`
Selective safety-harvest runtime commit: `e97a6dccc06f07b24f091f8b3198997e2f75b281`

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
## Independent mechanical evidence

Machine A disposable clean checkout was used; user canonical local worktrees were not touched.

- pre-harvest exact candidate: 250/250 tests PASS with 1 justified skip; governed reporter PASS; deterministic E2E PASS;
- post-harvest focused reconciliation regressions: 9/9 PASS;
- post-harvest full factory suite: 259/259 PASS with 1 justified skip;
- post-harvest E2E: PASS, including build certification, preflight, package verification/tamper rejection, ledger resume, provider wrapper smoke, read-only 09D comparison/projection, and fail-closed untrusted-target behavior;
- E2E receipts show `lease_ttl_seconds=1200` and populated `stable_witness_sha256` / `stable_claim_sha256` on produced candidates;
- targeted invalid-09D probe proves provider execution count remains zero when the sealed contract fails.

GitHub Actions attempts on earlier candidate heads failed at startup with zero jobs. Treat those as setup/infrastructure failures, not test results.

## Other divergent branches

The v1.24/v1.25 cold-audit branches were inspected separately. Their old APIs/tests do not replay literally because the architecture evolved, but their substantive invariants are represented in the current split dimension-aware challenge/certification system plus runtime authority checks: required-dimension coverage, exact challenge/result semantic hashing, provider/version/source binding, W4 authority, fail-closed missing/tampered coverage, lifecycle freshness, and independence from gold-construction families.

The v1.11 runbook is superseded by v1.12. The exact v1.12 owner runbook remains preserved under `AUDIT/HISTORICAL/` as historical operator evidence, not current authority.

## Reasoning frontier for Fable

Do not spend high-reasoning budget re-discovering which remote branch is strongest unless refs changed. Focus on whether the selectively harvested invariants compose correctly with v1.26, whether any remaining cross-repo DLE/EI capability should be absorbed, and whether the factory's operational/semantic claims are sufficient for its intended Estate role.

Normalization is not semantic-quality certification, clinical correctness, or production acceptance. Final Machine-A/Machine-B canonical checkout reconciliation remains deferred until the GitHub normalization campaign is complete.