# Integrated Frontier Extraction Factory

One governed extraction appliance reconciling the Meta semantic/literature design plane, Hermes durable execution/governance plane, and Project 09D as a read-only downstream authority.

## Cold-start truth - 2026-09-10

**Canonical GitHub target remains `master`. Do not treat `reconcile/mainline-20260910` as canonical until PR #29 passes independent review and is merged.**

Read these first, in order:

1. `FABLE_AUDIT_HANDOFF.md`
2. `CURRENT_VERIFICATION_20260910.json`
3. `MACHINE_B_EXACT_HEAD_VERIFICATION_20260910.json`
4. `DIVERGENT_REF_AUDIT_20260910.md`
5. `MAINLINE_RECONCILIATION_REPORT.md`
6. `MAINLINE_RECONCILIATION_MANIFEST.json`

The candidate uses v1.26 as the strongest runtime base, includes the existing W3 equation-risk repair, and selectively restores safety invariants lost from the divergent v1.14 line. Historical controllers/certifiers are evidence, not competing authority paths.

Current mechanical evidence:

- Machine A: 259/259 factory tests PASS with 1 justified skip, 9/9 reconciliation regressions PASS, governed reporter PASS, deterministic E2E PASS.
- Machine B: exact runtime candidate `6d9358da22b2d76fd4dc765b7407a16391da918f` independently replayed; 9/9 reconciliation regressions PASS, 259/259 full suite PASS with 1 justified skip, deterministic E2E PASS.
- GitHub Actions attempts on earlier candidate heads failed before jobs were created and are classified as setup/infrastructure failures, not test evidence.

The Machine-B replay used a disposable extracted archive and isolated `.venv`; the first E2E attempt exposed only a missing `pypdf` dependency, and the rerun with `pypdf 6.18.0` passed. No canonical local checkout was changed.

Because the verification receipts/documentation themselves move the candidate head, one final exact-head replay of the documentation-complete candidate remains before promotion review.

## Layout

| Path | Role |
| --- | --- |
| `factory/` | Production extraction runtime and canonical execution path |
| `factory/providers_ext/` | Provider adapters and model-version guards |
| `factory/stages_ext/` | Read-only 09D comparison/projection and downstream guards |
| `factory/benchmarks_ext/` | Source-first gold, scoring, certification, lifecycle and replay authority |
| `factory/run_appliance.py` | Canonical operator entrypoint |
| `AUDIT/` | Intake, historical evidence, capability and reconciliation records |
| `vendor/` | Preserved donor/source packs; do not treat as current runtime authority |
| `runs/` | Generated self-contained run outputs; gitignored |

## Canonical command shape

```bat
cd factory
<locked-python> -B run_appliance.py --profile SAFE_4 --pilot machines ^
    --primary claude:claude-opus-5 ^
    --blind   ollama:<local-model> ^
    --cold    ollama:deepseek-r1:14b
```

Provider specs are `backend:model`. Legacy `backend:model:FAMILY` input is accepted only as a checked compatibility form. Runtime family and independence authority comes from the governed model registry, not an operator-declared family label. Ollama tags may contain `:`.

The high-level chain is:

source identity/hash -> build + runtime-lock verification -> durable work registration and leases -> primary + allowlist-blind extraction -> deterministic union -> evidence families -> specialist/precision review -> risk routing -> independent cold audit -> fail-closed readiness -> read-only 09D comparison/projection -> verified offline review package.

Readiness is derived mechanically from gate objects; no caller-authored status is authoritative.

## Current safety/authority invariants

- Extraction outputs remain `SOURCE_ASSERTION_CANDIDATE / UNREVIEWED / NON_CANONICAL` until separately governed.
- 09D is read-only. Agreement does not prove truth and disagreement does not automatically refute it.
- External semantic dispatch against 09D is blocked unless the sealed target contract passes identity/schema/witness checks.
- Blindness is enforced by positive allowlisting; known contamination keys are rejected by regression tests.
- Model certification is source-, role-, provider-, version-, benchmark-, and authority-projection-bound.
- Cold-audit authority is dimension-complete and must remain independent from gold-construction groups.
- Stable witness/claim identities survive run-ID changes and are separate from ephemeral per-run candidate IDs.
- Semantic work leases must outlive provider timeout plus safety margin.
- Controller JSON/JSONL/TSV writes use atomic replacement; package integrity is independently re-hashed and tamper-tested.
- Requested 09D downstream-stage failure cannot be hidden behind a successful core run.

## Historical evidence

Older verification reports and donor branches remain useful provenance, but do not override this README, the Fable handoff, the reconciliation report/manifest, or the current code/tests. In particular, the preserved v1.12 owner-validation runbook under `AUDIT/HISTORICAL/` is historical operator evidence rather than current runtime authority.

## Promotion boundary

Normalization is not semantic-quality certification, clinical correctness, or production acceptance. The final user-canonical Machine-A/Machine-B checkout/ref/reflog/stash reconciliation is intentionally deferred until GitHub repository normalization is complete.

For the current decision frontier, start with `FABLE_AUDIT_HANDOFF.md`.
