# Meta Extraction Estate — Repair Report v1

## Executive result

**Offline repair certification: PASS.**

The supplied Meta extraction archives were reconciled into four active production domains and a quarantined historical/archive area. The repaired tree passes 41 regression tests, compiles 70 active Python files, passes two PubMed validators, passes static safety checks, and imports as a package.

**This is not a live-source certification.** External API runs, licensed-source ingestion, real BigQuery/Postgres loads, real embedding-model execution, and LLM generation were not performed by the offline verification suite.

## Inputs reconciled

Six supplied archives were treated as one extraction estate:

| Archive | Files | Shadow-like files | SHA-256 |
|---|---:|---:|---|
| `canonical_8files_requested.zip` | 14 | 0 | `29a0f2fe1de8db0f5510d01c5b5d687c2d313678d5e87c65b322e49f6d2e05a4` |
| `canonical_clinicaltrials_14files_fixed (1).zip` | 14 | 0 | `b49e2e4b0016ae4b6098c90507299ca94bcc2798841f4b214dea3c0cdc445414` |
| `canonical_engine_only.zip` | 27 | 0 | `f7ba305e074e26dcf01c72977f6d7f9842ddd1dbcaafcad30d8a68f4d9f6b42f` |
| `extraction_engine_complete.zip` | 174 | 0 | `e2479544eed3fc710a3386d59bf21dfe3d5576970e491d81a88a6630ae8c19b0` |
| `medrxiv_biorxiv_mass_extraction_v4_clean.zip` | 145 | 100 | `4e5fa077103dbeef00ff9881b40e2bd1b3a0b7ec63b43559738cc3e032b6e38f` |
| `Complete_Meta_Extraction_bundle.zip` | 223 | 118 | `8ef0bf65cb2aa541ba0e2f673c09a6b894a3d0b50edb1ab3c1e7cc5b23da03db` |

The two 14-file ClinicalTrials archives have different ZIP byte hashes because of archive metadata but the same normalized content-tree digest: `98e976c11ce6aaf206bf2c682590b1867aba4b2eb6cfda5ad19ac7b280e393e8`.

## 1. ClinicalTrials.gov

### High-severity defects found

- Bulk mode downloaded the official archive but stopped at a TODO while still reporting completion.
- Checkpoint advancement could occur before output durability, allowing data loss after a hard crash.
- Ten-page checkpoint semantics could replay records and create duplicates after restart.
- Orphan page shards could survive a crash and conflict with the checkpoint authority.
- Query examples used a JSON-path-like `AREA[ConditionModule.Condition]` expression rather than the supported search field name.
- The reported NCT04368728 golden fixture lost a phase.
- `hasResults=false` could be semantically lost if truthiness was used instead of explicit boolean preservation.
- Source changes during a long run were not distinguished from successful snapshot completion.
- A capped run could be mistaken for complete output.

### Repairs

- Implemented actual bulk ZIP parsing and canonicalization; no false-success TODO path remains.
- Made the checkpoint the commit authority; page shards are durable before checkpoint advancement.
- Added orphan-shard cleanup/replay on resume.
- Bound checkpoints to query, filters, page size, cap, and extraction mode.
- Corrected search presets and retained `last_update_post_date` for public-registry synchronization.
- Preserved all phase values and explicit false booleans.
- Added start/end API/data-version provenance and source-drift status.
- Added per-record source hashes and parser/schema/run provenance.
- Added explicit `PASS`, `WARN`, and `TRUNCATED` semantics.
- Added archive SHA-256 and bulk-file completeness reconciliation.
- Updated DDLs for provenance fields.

### Offline proof

**10/10 tests pass.** Tests cover multi-phase parsing, false booleans, two-page completion, orphan-page replay, checkpoint identity, source timestamp drift, provenance, DDL provenance, capped-run truncation, and bulk archive parsing/hash/count certification.

## 2. medRxiv / bioRxiv

### High-severity defects found

- Pagination assumed a fixed 100-record page and could terminate early when an endpoint returned a shorter page.
- DOI alone was treated as unique, which destroys preprint version history.
- Multiple shadow copies (`_1`, `_1_1`, `_2`) obscured canonical lineage.
- Duplicate/conflicting versions could be resolved arbitrarily.
- Invalid records could contaminate canonical output.

### Repairs

- Cursor advances by the actual number of returned records and terminates only on an empty collection.
- Canonical raw/version identity is `(server, DOI, version)`.
- Latest-version projection is separate from immutable version history.
- Conflicting same-version records fail closed based on source-record hash.
- Invalid rows are quarantined instead of promoted.
- Atomic output/manifests include counts and SHA-256 hashes.
- Shadow variants were removed from the active tree.

### Offline proof

**7/7 tests pass**, including a deliberately short first page followed by a second page, conflicting-version fail-closed behavior, and quarantine behavior.

## 3. DrugBank / RxNorm / LiverTox

### High-severity defects found

- Meta generated RxCUIs from Python `hash()`, producing fabricated, process-dependent identifiers.
- Placeholder LiverTox likelihood/injury-pattern values were injected as though extracted.
- Ambiguous name resolution could be converted into a single link.
- DrugBank provenance hash did not cover the full source record.

### Repairs

- No fabricated RxCUI path remains; RxNorm identifiers come only from returned/prefetched source data.
- Ambiguous RxNorm matches remain explicitly ambiguous.
- LiverTox data requires source provenance and no placeholder clinical labels are generated.
- DrugBank uses streaming XML parsing.
- DrugBank source hash covers the complete record element.
- Primary names and synonyms can link conservatively, but only one distinct candidate is accepted.
- Pipeline manifests include input/output hashes and unresolved-link counts.

### Offline proof

**6/6 tests pass**, including full-record provenance hash sensitivity and synonym linking without guessing.

## 4. PubMed / Embeddings / RAG

### High-severity defects found

- The flagship “max” extractor silently capped each ESearch query at 5,000–10,000 PMIDs.
- Failed ESearch and EFetch batches were swallowed with `continue`, allowing partial corpora to look successful.
- PubMed ESearch itself exposes only the first 10,000 UIDs for one query; naïve `retstart` pagination cannot certify larger PubMed queries.
- EFetch results were not reconciled against requested PMIDs.
- Source candidates were discarded before the classification projection.
- Title-based dedup could delete a distinct valid PMID merely because another article had the same normalized title.
- Synthetic corpus, embeddings, RAG outputs, and sample records were located in normal data paths and could be mistaken for production evidence.
- Some active entrypoints used fake contact emails or stale rate-limit claims.
- Embedding paths could manufacture deterministic fallback vectors.
- RAG answer generation could emit an ungrounded fallback answer.
- A naïve capitalization regex was labeled as clinical entity extraction.
- Multiple competing “production” scripts and stale readmes obscured the supported path.

### Repairs

- Complete PubMed runs use explicit date bounds and recursively partition oversized ESearch queries until every segment is <=10,000 UIDs.
- A single-day segment >10,000 fails closed and directs the operator to EDirect/FTP bulk data rather than accepting truncation.
- User caps are explicit and produce `TRUNCATED`, never `PASS`.
- ESearch/EFetch failures fail closed; EFetch requested and returned PMID sets must match exactly.
- PMID ordering is deterministic.
- Every source PMID is preserved; DOI/title heuristics may flag a possible duplicate but cannot delete the source record.
- Raw per-record XML and its SHA-256 are retained for deterministic provenance/reparse.
- Candidate records are saved before anesthesia-classification filtering; retained and excluded projections are separate.
- NCBI contact email is required for network access; fake production defaults were removed.
- Retry honors `Retry-After` and uses safe 3/s no-key / 10/s keyed margins.
- Embedding paths fail closed when a real model is unavailable.
- Synthetic/demo corpora, embeddings, and RAG outputs were moved under `archive_not_production/untrusted_generated_artifacts/`.
- RAG generation has no fake backend; unconfigured generation fails closed.
- Uncertified clinical NER returns no entities rather than pretending a capitalization heuristic is NER.
- Superseded Meta entrypoints and stale production docs were moved to `archive_not_production/`.
- Pydantic v2 deprecations and the inconsistent requirements contract were fixed.

### Offline proof

**18/18 tests pass**, including:

- >10,000 query partitioning with a simulated 12,000-PMID result;
- single-day >10,000 fail-closed behavior;
- explicit capped-run truncation;
- missing EFetch PMID fail-closed behavior;
- raw-XML provenance hashing;
- preservation of two distinct PMIDs with the same title;
- no untrusted corpus in production roots;
- no synthetic embedding fallback;
- no unconfigured RAG answer fallback;
- real-contact requirement;
- production-mode defaults.

Two additional validators also pass.

## Consolidated offline verification

`run_offline_verification.sh` produced `OFFLINE_VERIFICATION.txt` with:

- 70 active Python files compiled successfully;
- ClinicalTrials: 10 passed;
- preprints: 7 passed;
- drug reference: 6 passed;
- PubMed/RAG: 18 passed;
- PubMed file/static validator: PASS;
- PubMed import/date/dedup validator: PASS;
- static active-tree scan: PASS;
- package import: PASS.

**Total regression tests: 41 passed.**

## Remaining certification gates

These are intentionally **not** represented as complete:

1. Live ClinicalTrials.gov full/filtered network run and start/end dataset-version consistency.
2. Real Postgres and BigQuery DDL/load tests for each production schema.
3. Live bioRxiv and medRxiv pagination/retry run.
4. Licensed DrugBank XML ingestion with a real owner-provided source artifact.
5. Live RxNav resolution run.
6. Provenance-producing LiverTox structured acquisition; no synthetic substitute is permitted.
7. Live PubMed large-query extraction against NCBI and source-count reconciliation.
8. Real embedding-model load/inference and retrieval-quality evaluation.
9. RAG generation backend integration and grounded-answer/citation certification.
10. Long-duration soak/resume tests under real network failures and rate limiting.

Until those gates are executed, the correct status is:

> **OFFLINE REPAIR CERTIFIED — LIVE SOURCE / DATABASE / MODEL CERTIFICATION PENDING**

---

## Frontier hardening v3 — control plane and warehouse promotion

A later hardening pass added the production authorization boundary rather than merely adding parsers.

- Exact production-code preflight now hashes 38 active Python files.
- Network CLIs require that exact-code PASS preflight.
- Full extraction additionally requires a source-specific PASS canary bound to the same code hash.
- Canary runs must parse at least one real record before certification.
- Completed runs automatically project into the immutable warehouse model.
- Orchestration evidence hash-chains code, preflight, source manifest, and warehouse projection.
- Release promotion rejects canaries, WARN/FAIL/TRUNCATED runs, incomplete runs, quarantine, source drift, artifact hash mismatch, and duplicate promoted source runs.
- PubMed now emits a physically separate immutable raw XML record artifact.
- Aggregate preprint warehouse projection resolves root version artifacts plus per-shard provenance.
- Drug crosswalk source-artifact locators are portable relative paths.
- Unfiltered full ClinicalTrials extraction defaults to the official full JSON ZIP.

Current source/control regression suites: **69/69 passing**.

A native ClinicalTrials live canary was attempted only after the frozen preflight PASS. It was blocked by DNS resolution in the execution environment before source retrieval. The failed orchestration is retained as evidence; no canary certificate was emitted and mass extraction did not start.
