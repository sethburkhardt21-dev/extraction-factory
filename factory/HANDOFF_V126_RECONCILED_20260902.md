# Extraction Factory v1.26 Reconciliation Handoff — 2026-09-02

## Executive state

The two active v1.26 lines have now been reconciled into one integration branch without changing `master`.

Authoritative integration branch for further v1.26 work:

`chatgpt-v126-reconciled-20260902`

Current branch head after this handoff:

`7bd5ed2fcb42238c80533757e537df4fa01eb085`

Reconciliation merge commit:

`ce6f9e709b33d9265bc2e7e1074a9f17d00977da`

Canonical release branch remains:

`master @ c35ad38324029c7eef2ebe1e5b0f0086fbe3b73e`

Draft integration PR:

`#28 — v1.26: reconcile certification strata and W3 Tier-B routing`

At handoff time GitHub reported no workflow runs or combined status checks yet for the reconciled head. Treat verification as NOT YET PROVEN.

Do not advance `master` until the reconciled branch passes the repository's full required test/CI/E2E/certification gates.

## What was reconciled

Two branches independently started from the same v1.25 master commit:

1. `chatgpt-certification-strata-v126-20260902 @ 32b54ef40d8eea027406e1570c9a8e0d61527f0a`
   - one commit;
   - sole tree change: add `factory/hermes_factory/certification_strata.py`;
   - policy intent: only W2/S1 is automatically certifiable; W3 and S2/S3 material must remain on a bounded review surface.

2. `chatgpt-w3-tierb-v126-20260902 @ c79ea0c44a6a2bc507331827c573ee6763ca2247`
   - eight commits ahead of v1.25 master;
   - stamps governed source risk onto semantic candidates;
   - carries source-risk metadata into evidence families;
   - makes conflicting source-risk metadata a P0 integrity failure;
   - forces every family stamped `source_risk_work_class=W3` to `SPECIALIST_REVIEW_REQUIRED` with `W3_TIER_B_REVIEW_REQUIRED`;
   - adds regression tests;
   - bumps factory/runtime version to 1.26.0;
   - documents the source-risk authority boundary in ADR-126.

## Reconciliation decision

The reconciliation commit has both branch heads as parents, but intentionally retains the W3 Tier-B branch tree as the content resolution.

The standalone `certification_strata.py` file was NOT carried forward verbatim.

Reason: the file is unreferenced by the runtime and its `assess_higher_risk_routing()` helper expects route rows keyed by `source_unit_id`, while the v1.26 runtime router is evidence-family keyed and emits `family_id`. Blindly retaining that helper would create a second, incompatible policy surface rather than strengthen the active router.

Its policy intent is not discarded. The current governed classifier emits W2/S1 for ordinary text, W3/S1 for equations, and W3/S3 for complex representations/cross-page material; current S3 cases therefore inherit W3 review authority and cannot be locally closed. The living architecture already states that high source risk can upgrade the required reviewer.

Important future-proofing note: the current classifier does not emit S2. If S2 or any future non-W2/S1 class is introduced independently of W3, the router must gain an explicit regression proving that such material cannot reach local completion merely because its `work_class` is W2. Do not resurrect the discarded helper as a parallel authority; extend the canonical router/tests instead.

## v1.26 integration delta versus master

The reconciled branch contains these material tree changes relative to `master`:

- `factory/ADR/ADR-126_W3_TIER_B_ROUTING_IS_SOURCE_RISK_AUTHORITY.md` added
- `factory/VERSION` -> 1.26.0
- `factory/hermes_factory/__init__.py` -> 1.26.0
- `factory/hermes_factory/router.py` updated for source-risk routing authority and P0 metadata conflicts
- `factory/hermes_factory/semantic.py` stamps governed source-risk metadata on candidates
- `factory/hermes_factory/union.py` carries/validates source-risk metadata into evidence families
- `factory/hermes_factory/w3_policy.py` added
- `factory/tests/test_w3_tierb_routing.py` added
- `factory/HANDOFF_V126_RECONCILED_20260902.md` added

The reconciled branch is ahead of master and not behind it. `master` was not modified.

## Claim boundary

What v1.26 currently proves in code:

- source risk is carried through the candidate/family path;
- W3 families cannot be silently marked `LOCAL_PRECISION_COMPLETE`;
- conflicting source-risk stamps fail blocking;
- W3 material is routed to a bounded Tier-B/specialist review surface.

What v1.26 does NOT yet prove:

- that a Tier-B reviewer/model has been empirically certified;
- that a real W3 semantic review has passed;
- that W3 output is canonicalized;
- that this branch has passed the full required CI/E2E/certification matrix after reconciliation.

Do not convert routing authority into reviewer competence by assertion.

## Instructions for Claude / next operator

If you are already working in another checkout or branch, preserve any local edits first. Do not reset, force-push, or overwrite uncommitted work.

Then treat `chatgpt-v126-reconciled-20260902` as the sole v1.26 integration frontier. Fetch it, compare your current work against it, and rebase/cherry-pick only deliberate local work that is not already present.

First objective is verification, not new architecture:

1. Run the full repository test suite on the reconciled branch.
2. Run the required clean-checkout E2E path and all version/build/package/readiness/semantic freshness/09D gates used by the current repository.
3. Confirm the new W3 regression suite is green.
4. Confirm ordinary W2/S1 text still reaches local completion when no other hard flags exist.
5. Confirm W3/S1 and W3/S3 material cannot locally close.
6. Confirm conflicting source-risk metadata remains P0/fail-blocking.
7. Record exact commands, exit codes, environment/runtime versions, and commit SHA.
8. If any gate fails, fix the smallest canonical surface; do not weaken a gate or create a parallel router/certification authority.

Only after green verification should the next semantic milestone be attempted: empirical Tier-B reviewer qualification and then a real governed W3 extraction/review traversal.

## Branch hygiene

Keep these historical branch identities intact for provenance:

- `chatgpt-certification-strata-v126-20260902 @ 32b54ef40d8eea027406e1570c9a8e0d61527f0a`
- `chatgpt-w3-tierb-v126-20260902 @ c79ea0c44a6a2bc507331827c573ee6763ca2247`

Do not delete or force-move them during verification. They are now parents of the reconciliation history, not competing integration authorities.

A temporary branch named `tmp` was created during the reconciliation operation and then force-moved to exactly `master @ c35ad383...`. It carries no unique work and is safe to delete when convenient; do not treat it as an integration branch.

Older v1.x branches/PRs may remain visible but are not automatically evidence of missing current work. Compare them to current master before using anything from them.

## Short form

`master` = stable v1.25 release frontier.

`chatgpt-v126-reconciled-20260902` = current v1.26 integration frontier.

PR #28 = draft verification/merge surface.

W3 routing boundary = implemented candidate awaiting full green verification.

Tier-B reviewer competence = not yet proven.
