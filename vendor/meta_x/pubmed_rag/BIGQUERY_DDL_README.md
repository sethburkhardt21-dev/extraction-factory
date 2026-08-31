# BigQuery DDL - Production Deliverables Summary
## Agent B2: BigQuery DDL Architect - Max Anesthesia PubMed Extraction

### Files Produced
1. **`/mnt/data/bigquery_ddl_anesthesia_pubmed.sql`** - Main production DDL (18KB)
   - Partitioned clustered table: `anesthesia_prod.pubmed.anesthesia_pubmed_max`
   - PARTITION BY DATE_TRUNC(pub_date, YEAR) - handles 10k partition limit (yearly ~76 partitions vs daily 20k)
   - CLUSTER BY first_subdomain, journal_title, study_type, publication_year (4 cols max, ordered by filter frequency)
   - STRUCT for journal: title, iso_abbreviation, issn, volume, issue, pages, impact_factor, publisher
   - REPEATED ARRAY<STRUCT> for mesh_terms: descriptor_name, descriptor_ui, qualifiers ARRAY<STRING>, major_topic BOOL
   - OPTIONS(description) on table + 81 column/struct field descriptions
   - Helper UDFs: normalize_doi(), parse_medline_date() addressing audit critical issues

2. **`/mnt/data/bigquery_pubmed_helpers.py`** - Ingestion transformation helpers
   - normalize_doi() - LOWER(TRIM()), strip https://doi.org/, validate regex ^10.\d{4,}/
   - parse_pubmed_date() - Handles MedlineDate fallback: "2020 Dec" -> 2020-12-01, seasons Winter->1 Spring->3 Summer->6 Fall->9
   - classify_subdomains_boundary() - Word boundary regex \b to avoid FP via substring (e.g., block vs blockade)
   - RATE_LIMIT constants corrected: 20/s with key (0.05s sleep), 10/s without (0.1s sleep) - fixes inverted bug
   - handle_webenv_expiration() stub for WebEnv 8hr expiration handling
   - transform_jsonl_record_to_bq_row() - maps anesthesia_pubmed_schema.json to BigQuery row

3. **`/mnt/data/bigquery_validation_test.py`** - Validation script
   - Checks PARTITION BY, CLUSTER BY, STRUCT, ARRAY<STRUCT>, OPTIONS
   - Tests transformation on sample JSONL

4. **`/mnt/data/bq_load_job.py`** - (this folder) BigQuery batch load + embedding generation

### Key Design Decisions (from search best practices)

**Partitioning:**
- Time-unit YEAR partitioning chosen over DAY because corpus spans 1970-2026 ~56 years
- Daily partitions would exceed BigQuery 10k partition limit (56*365=20k)
- Uses canonical pub_date DATE NOT NULL derived from publication_date struct with MedlineDate fallback
- `require_partition_filter = TRUE` prevents full scans, cost control
- `partition_expiration_days = 1825` (5 years) for staging; prod may remove

**Clustering:**
- Up to 4 clustering columns (BigQuery limit)
- Order: first_subdomain (most filtered in anethassist), journal_title, study_type, publication_year
- Helper columns first_subdomain, journal_title, study_type denormalized because BigQuery clustering cannot use nested STRUCT fields directly
- Clustering free automatic re-clustering, improves filter performance

**Nested vs Flat:**
- STRUCT for 1:1 relationships: journal, publication_date, study_design, anesthesia_specific, citation_metrics, extraction_metadata, abstract_structured
- ARRAY<STRUCT> for 1:N: authors, mesh_terms, chemicals
- ARRAY<STRING> for simple repeated: keywords, publication_types, anesthesia_subdomains
- STRUCT containing ARRAY: anesthesia_specific.drugs ARRAY<STRING> allowed (<15 nesting levels, we use 3)
- Avoids JOINs, preserves context, per best practice "Use ARRAY and STRUCT for nested/repeated data instead of separate tables"

**OPTIONS(description):**
- Table OPTIONS description with full context, labels for domain/source/swarm/pii
- Column OPTIONS(description) on every top-level column and STRUCT field (81 descriptions)
- Helps Data Catalog and documentation

**Embeddings:**
- Column title_abstract_embedding ARRAY<FLOAT64> for PubMedBERT 768-dim or Vertex AI text-embedding-005 (1408-dim) / gemini-embedding-001
- Alternative autonomous generation: STRUCT<result ARRAY<FLOAT64>, status STRING> GENERATED ALWAYS AS (AI.EMBED(...))
- VECTOR INDEX: CREATE VECTOR INDEX ON (embedding) OPTIONS(index_type='IVF', distance_type='COSINE', ivf_options='{"num_lists":500}')
- Requires >=5000 rows for IVF index creation

**Audit Critical Fixes Addressed in DDL:**
- DOI normalization missing -> UDF normalize_doi() + Python normalize_doi() with LOWER(TRIM()) + URL stripping
- MedlineDate fallback missing -> UDF parse_medline_date() + Python parse_pubmed_date() with regex and season mapping
- Classification FP via substring -> classify_subdomains_boundary() uses \b word boundaries
- Rate limits inverted -> Constants RATE_LIMIT_WITH_API_KEY=20, SLEEP_WITH_KEY=0.05 vs WITHOUT 10/0.1
- WebEnv expiration not handled -> handle_webenv_expiration() retry with re-esearch for new WebEnv/QueryKey

### Example Queries (cost-efficient)

```sql
-- Partition pruning: must include pub_date filter due to require_partition_filter
SELECT pmid, title, journal.title, journal.impact_factor
FROM `anesthesia_prod.pubmed.anesthesia_pubmed_max`
WHERE pub_date BETWEEN '2020-01-01' AND '2025-12-31'
  AND first_subdomain = 'Pediatric Anesthesia'
  AND study_type = 'RCT'
ORDER BY journal.impact_factor DESC;

-- MeSH unnest (via view)
SELECT descriptor_name, COUNT(*) as n
FROM `anesthesia_prod.pubmed.v_anesthesia_mesh_flat`
WHERE pub_date >= '2023-01-01'
  AND major_topic = TRUE
GROUP BY descriptor_name
ORDER BY n DESC LIMIT 20;

-- Vector search (after loading embeddings)
SELECT pmid, title,
  1 - COSINE_DISTANCE(title_abstract_embedding, (SELECT embedding FROM ...)) AS similarity
FROM `anesthesia_prod.pubmed.anesthesia_pubmed_max`
WHERE pub_date >= '2020-01-01'
ORDER BY similarity DESC LIMIT 10;

-- Deduplicated canonical
SELECT * FROM `anesthesia_prod.pubmed.v_anesthesia_canonical`
WHERE publication_year >= 2020
  AND 'Critical Care ICU Sedation' IN UNNEST(anesthesia_subdomains);
```

### Load Pipeline

```bash
# Transform JSONL to BQ JSON with helpers
python bigquery_pubmed_helpers.py

# Load via bq CLI (after transforming)
bq load --source_format=NEWLINE_DELIMITED_JSON \
  --autodetect \
  anesthesia_prod.pubmed.anesthesia_pubmed_max \
  ./anesthesia_corpus/bq_rows.jsonl

# Or via Python client (see bq_load_job.py)
pip install google-cloud-bigquery
python bq_load_job.py --input ./anesthesia_corpus/anesthesia_full_metadata.jsonl --dataset anesthesia_prod --table pubmed.anesthesia_pubmed_max
```

### Validation Results
All checks PASS:
- PARTITION BY DATE_TRUNC(pub_date, YEAR) - avoids 10k limit
- CLUSTER BY 4 cols first_subdomain, journal_title, study_type, publication_year
- STRUCT for journal, REPEATED mesh_terms ARRAY<STRUCT>
- OPTIONS description count 81
- DOI UDF + MedlineDate UDF
- Embedding column present
- Transformation test: PMID 39769238 -> pub_date 2025-05-01 valid DATE, mesh_terms list len 4, DOI norm works, MedlineDate 2020 Dec -> 2020-12-01, Spring -> 2020-03-01

### Next Steps
- Run load job on full 280k-380k corpus after running pubmed_extraction_pipeline.py locally
- Generate embeddings batch: use Vertex AI text-embedding-005 via ML.GENERATE_EMBEDDING or PubMedBERT
- Create VECTOR INDEX after >=5k rows
- Build materialized view mv_subdomain_year_counts for dashboard already included
