# Meta Extraction Frontier v10 — 09D Turn 5

Current status: **PASS_OFFLINE_SEMANTIC_CONTRACT**.

Turn 5 adds an append-only independent semantic verifier, specialist numeric/qualifier/relationship checks, risk routing, a 24-case semantic gold matrix, and hash-bound verifier persistence. Project 09D remains read-only. Extractor assertions remain `NOT_VERIFIED`; verification is stored separately as non-authoritative `VERIF:` events.

Mass extraction remains **NOT AUTHORIZED**. The next semantic gate is blind source-only recall/reconciliation.

See `09D_FRONTIER_EXTRACTION_STATE.md` and `TURN5_SEMANTIC_VERIFIER_REPORT.md` for the authoritative current state.

---

# Current v5 status

**Read first:** `09D_FRONTIER_EXTRACTION_STATE.md`. Project 09D is read-only. v5 is a Turn 1 09D-boundary release candidate; assertions/comparison/conflict engines are not implemented and mass extraction is not authorized. Older v4 empirical reports are historical evidence only.

# Meta Extraction Estate — Repaired v1

This package consolidates and repairs the extraction code supplied across the Meta-generated archives.
It is intentionally split into four source domains:

- `clinicaltrials/` — ClinicalTrials.gov v2 snapshot / filtered extraction
- `preprints/` — medRxiv + bioRxiv version-preserving extraction
- `drug_reference/` — DrugBank + RxNorm + provenance-gated LiverTox normalization/linking
- `pubmed_rag/` — PubMed extraction, incremental ingestion, embeddings, retrieval, and RAG scaffolding

## Certification boundary

`OFFLINE_VERIFICATION.txt` is the machine-run proof for this artifact. Passing offline verification means syntax,
regression, failure-injection, provenance, and static safety checks passed against local fixtures/fakes. It does
**not** mean external source APIs, licensed DrugBank input, BigQuery/Postgres loads, embedding model downloads,
or an LLM generation backend were live-certified.

No source/domain may promote `TRUNCATED`, `WARN`, demo, synthetic, or unproven output to a certified complete dataset.
Historical Meta variants and untrusted generated artifacts are retained only beneath `archive_not_production/`.

## Turn 6 update

The estate now includes provisional assertion-mention candidate registration and a hash-bound, query-only Project 09D comparator contract. These surfaces are non-authoritative: candidates remain REGISTERED, canonical assignment is never performed, and the actual frozen 09D SQLite has not been compared because that database artifact is not present in this workspace. See `TURN6_IDENTITY_READONLY_COMPARATOR_REPORT.md`.
