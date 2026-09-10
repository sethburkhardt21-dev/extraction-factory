# Integrated Frontier Extraction Factory

One governed extraction appliance reconciling the Meta semantic/literature design plane, Hermes durable execution/governance plane, and Project 09D as a read-only downstream authority.

## Cold-start truth - 2026-09-10

**Canonical GitHub truth is `master`. Mainline reconciliation PR #29 was independently reviewed and promoted.**

Promotion lineage:

- tested candidate head: `4d82f0fc3e003b71c5c0b2df0a17a842762189f5`
- merge commit: `1693a3cd444072b2bd9041ec2b6e345876f4a348`
- merge tree: `edcd82a5b5107160fa89d7d5488835cc8ffce859`
- the merge tree is the same tree that was independently replayed on Machine B

Read these first, in order:

1. `POST_PROMOTION_STATE_20260910.json`
2. `FABLE_AUDIT_HANDOFF.md`
3. `CURRENT_VERIFICATION_20260910.json`
4. `MACHINE_B_EXACT_HEAD_VERIFICATION_20260910.json`
5. `DIVERGENT_REF_AUDIT_20260910.md`
6. `MAINLINE_RECONCILIATION_REPORT.md`
7. `MAINLINE_RECONCILIATION_MANIFEST.json`

The promoted runtime uses v1.26 as the strongest base, includes the W3 equation-risk repair, selectively restores safety invariants lost from the divergent v1.14 line, and includes bounded Windows atomic-replace retry hardening. Historical controllers/certifiers remain evidence, not competing authority paths.

## Mechanical evidence

Machine A disposable checkout:

- 9/9 reconciliation regressions PASS
- 259/259 full factory tests PASS with 1 justified skip
- governed reporter PASS
- deterministic E2E PASS

Machine B independent exact-head replay of `4d82f0fc3e003b71c5c0b2df0a17a842762189f5`:

- 10/10 reconciliation regressions PASS
- 260/260 full factory tests PASS with 1 justified skip
- deterministic E2E PASS
- `overall=PASS`
- `core_readiness_status=READY_FOR_PROVIDER`
- archive SHA-256: `fea904ccc23f6ad4a97c6a5aae2379c2859b28fa5512da6dce9521268469db76`

The Machine-B replay used a disposable extracted archive and isolated `.venv`; the first E2E attempt exposed only a missing `pypdf` dependency, and the rerun with `pypdf 6.18.0` passed. No canonical local checkout was changed.

GitHub Actions on the exact final candidate again failed before jobs were created. That remains setup/infrastructure evidence only and is not treated as a code-test result.

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
- Controller JSON/JSONL/TSV writes use atomic replacement; Windows transient sharing-lock retries are bounded and re-raise on exhaustion.
- Requested 09D downstream-stage failure cannot be hidden behind a successful core run.

## Historical evidence

Older verification reports and donor branches remain useful provenance, but do not override canonical `master`, this README, the Fable handoff, reconciliation report/manifest, or the current code/tests. The preserved v1.12 owner-validation runbook under `AUDIT/HISTORICAL/` is historical operator evidence rather than current runtime authority.

## Boundary still deferred

This GitHub promotion does **not** authorize destructive local normalization. Final Machine-A/Machine-B canonical checkout/ref/reflog/stash/unreachable-object reconciliation remains deferred until the GitHub repository-normalization campaign is complete.

Normalization is not semantic-quality certification, clinical correctness, or production acceptance.
