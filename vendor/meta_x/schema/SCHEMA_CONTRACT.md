# Frontier Research Warehouse Contract v2.0

## Layer model

**Bronze** is immutable source truth: extraction runs, hashed artifacts, unique raw source payloads, run observations, quarantine, and provenance. A source payload can be observed in many runs without being duplicated or losing the observation history.

**Silver** is a versioned canonical parse of Bronze. Parser/schema upgrades create a new `canonical_record`; they never mutate a prior parse. ClinicalTrials.gov, PubMed, and preprint snapshots map certified runs to those canonical records. `latest` is a view over certified snapshots, not a destructive overwrite.

**Gold** contains analytical entities and derivatives: research-work associations, drug crosswalk entities, evidence links, model enrichments, and release snapshots. Gold links are evidence-bearing and reversible.

## Identity rules

| Source | Source identity | Version/content identity |
|---|---|---|
| ClinicalTrials.gov | `NCTId` | raw SHA-256 + registry observation/run |
| PubMed | `PMID` | raw PubMed XML SHA-256 + observation/run |
| bioRxiv/medRxiv | `(server, DOI)` | explicit preprint `version` + raw SHA-256 |
| DrugBank | primary DrugBank ID | source release/version + raw SHA-256 |
| RxNorm | RxCUI / resolver response identity | returned source payload hash + source manifest |
| LiverTox | NCBI Bookshelf/source URL identity | captured source record hash + source manifest |

A DOI, normalized title, drug name, or synonym is **linkage evidence**, not permission to delete a source record.

## Snapshot promotion

Only runs exposed by `frontier.promotable_run` may enter a certified release. A promotable run must be completed, `PASS`, source-complete, non-truncated, contain zero quarantined records, and have no source-version drift during the run.

`WARN`, `TRUNCATED`, and `FAIL` outputs are retained for audit but cannot silently become production snapshots.

## Historical semantics

Source state is append-only. Re-extracting an unchanged source payload adds another `source_observation` but reuses its content identity. A changed payload creates a different source record hash. A parser upgrade can create a new canonical representation from the same raw payload without another network fetch.

This is intentional: the warehouse must be able to answer both **“what is current?”** and **“what did the source say in the certified snapshot from date X?”**.

## Raw-data rule

Canonical convenience fields never replace raw preservation. ClinicalTrials stores all top-level protocol/results/annotation/document/derived sections. PubMed retains per-article raw XML. Preprints retain the original API record. Malformed source bytes are hashable and quarantineable rather than silently discarded.

## Enrichment rule

Classification, embeddings, reranking, entity linking, evidence grading, summarization, and RAG are downstream enrichments. Extraction records are model-agnostic. Every model derivative must record model/provider/revision where available, exact input/output hashes, configuration, and certification state.

## Release rule

A release is a manifest over certified source runs, schema version, transformation versions, and artifact hashes. Release creation is a separate promotion step; extraction completion alone does not mean a release is certified.


## Physical projection compatibility

The logical Bronze/Silver/Gold contract is not sufficient by itself. Every table and top-level column emitted by the certified warehouse projector MUST exist in both `frontier_postgres.sql` and `frontier_bigquery.sql`. `validate_physical_projection.py` constructs rich source-shaped offline runs, executes the actual projectors, and fails closed on any missing backend table or emitted column. `PHYSICAL_PROJECTION_CONTRACT.json` is generated proof and is included in the production manifest hash.

Convenience JSON projections may intentionally coexist with normalized child tables. They are non-authoritative query accelerators; immutable source identity, canonical versioning, and child rows remain separately addressable.
