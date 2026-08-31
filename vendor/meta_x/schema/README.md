# Frontier Research Schema v2

The warehouse is explicitly **Bronze / Silver / Gold** and append-only by design.

- **Bronze**: `ingestion_run`, run artifacts, immutable source payload identities, observations, provenance, and quarantine.
- **Silver**: parser-versioned canonical records and source-specific normalized projections. A parser upgrade never destroys an earlier parse.
- **Gold**: reversible cross-source work/drug entities, evidence links, model enrichments, and certified release manifests.

PostgreSQL uses normalized child tables for high-value ClinicalTrials/PubMed analytics. BigQuery keeps more repeated structures nested/JSON for scan efficiency while preserving the same identity and lineage contract.

See `SCHEMA_CONTRACT.md` for promotion, identity, history, raw-data, and enrichment rules.

## Non-negotiable promotion rule

Only a completed source run with `certification_status=PASS`, exact source completeness, zero quarantine, no truncation, and no snapshot/source-version drift is promotable. All other outputs remain queryable audit artifacts but cannot silently become a certified release.
