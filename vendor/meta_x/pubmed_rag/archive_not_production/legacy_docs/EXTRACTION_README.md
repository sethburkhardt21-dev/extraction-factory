# Max Anesthesia PubMed Extraction - Full Metadata Schema Package

## What you have

This package implements the 16-agent swarm max-recall extraction with **full metadata for every record**.

### Files

1. **anesthesia_pubmed_schema.json** - JSON Schema Draft 07 defining 18 top-level fields, 60+ subfields for every PubMed record
2. **pubmed_extraction_pipeline.py** - Production Python pipeline using E-utilities esearch + efetch with WebEnv, batch 100, rate limiting 10 req/s (20 with API key), rule-based subdomain classification, deduplication
3. **anesthesia_full_metadata_SAMPLE.csv** - Flattened CSV with 30 columns, sample 16 real PMIDs from swarm (SPICE III, LAST toxicity, hemoadsorption, etc)
4. **anesthesia_full_metadata_SAMPLE.jsonl** - JSONL with full nested schema (5 records) - this is the canonical format
5. **max-anesthesia-pubmed-extraction.md** - Full 16-agent report with query bank, counts, journals, landmark trials

## Schema - Every Field Explained

### Core identifiers
- `pmid` (string, required): PubMed ID
- `doi`, `pmcid`: CrossRef DOI, PubMed Central ID
- `title`, `abstract`, `abstract_structured`: full abstract + sections Background/Methods/Results/Conclusions parsed from XML

### Authors[]
- last_name, fore_name, initials, affiliation (from AuthorList), orcid (future)

### Journal{}
- title, iso_abbreviation, issn, volume, issue, pages, impact_factor (mapped from BJA 9.166, Anesthesiology 9.1, Anaesthesia 6.995, A&A 4.6 etc), publisher

### Publication_date{}
- year (int), month, day, pub_type_date (epub/ppublish), pdat

### MeSH
- `mesh_terms[]`: descriptor_name, descriptor_ui (e.g., D009407 for Nerve Block), qualifiers[], major_topic boolean
- `keywords[]`: KeywordList
- `publication_types[]`: PT field - RCT, Systematic Review, Meta-Analysis, Guideline, Case Report, etc
- `chemicals[]`: NameOfSubstance + UI - drugs

### 16-Agent Classification
- `anesthesia_subdomains[]`: enum of 16 domains - multi-label, rule-based on MeSH + title/abstract lowercased matching
- `study_design{}`: type enum, is_landmark (GAS, BALANCED, SPICE III etc), n_patients (parsed via regex from abstract), n_studies_included (for SRMA), multicenter bool, blinding, registration (NCT, PROSPERO)
- `anesthesia_specific{}`: drugs[], techniques[], outcomes[] (PONV, awareness, delirium, mortality, pain score), population (adult/pediatric/obstetric/cardiac), asa_class

### Citation & Extraction Meta
- `citation_metrics{}`: openalex, semantic_scholar counts (enrichable), is_top_100_pediatric
- `extraction_metadata{}`: query_used, agent_id (1-16), retrieval_date ISO8601, dedup_status (unique/duplicate_type_I/duplicate_type_II/merged), duplicate_of_pmid

## How to Run Full Extraction (280k-380k records)

```bash
# 1. Install
pip install biopython pandas tqdm requests

# 2. Set API key (optional but recommended - doubles rate limit)
export NCBI_API_KEY=YOUR_NCBI_API_KEY
# Get key at https://www.ncbi.nlm.nih.gov/account/settings/

# 3. Run swarm - all 16 agents, max 100k each = ~500k before dedup
python pubmed_extraction_pipeline.py --max-records 100000 --output ./anesthesia_corpus --api-key $NCBI_API_KEY

# 4. Run single agent for testing
python pubmed_extraction_pipeline.py --agents 11 --max-records 1000 --output ./test_critical_care

# Outputs:
# ./anesthesia_corpus/anesthesia_full_metadata.jsonl - 1 JSON per line, full schema
# ./anesthesia_corpus/anesthesia_full_metadata.csv - flattened for Excel/BigQuery
# ./anesthesia_corpus/schema.json - copy of schema
```

### Rate Limits & Best Practices

- Without key: 10 req/s, use sleep 0.5 between efetch
- With key: 20 req/s, sleep 0.34
- E-utilities requires tool + email params for tracking
- Use WebEnv + QueryKey + retstart pagination, not idlist for >10k records (idlist URL length limit)
- retmax 100 for XML stability, 5000 max allowed but fails on large payloads
- Parse PMID first for dedup Type-I - same study across agents

### Deduplication Pipeline (per de-duplication review)

```python
# Pseudocode from PMC10789108
# 1. DOI lowercase exact -> merge keep richest abstract
# 2. PMID exact
# 3. Title fuzzy >90% + year + first author
# 4. Bramer method: pagination + volume + journal
# Tools: SRA-DM 84% sens 100% spec vs EndNote 42% less sensitive
```

## Sample Query Bank (from swarm)

See max-anesthesia-pubmed-extraction.md Section 5 for master inclusive query and 16 subdomain strings. Master:

```
(
 "Anesthesia"[MeSH] OR "Anesthesiology"[MeSH] OR "Anesthetics"[MeSH] OR 
 "Analgesia"[MeSH] OR "Anesthesia, General"[MeSH] OR "Anesthesia, Conduction"[MeSH] OR 
 "Nerve Block"[MeSH] OR "Airway Management"[MeSH] OR anesthes*[tiab] OR anaesthes*[tiab]
)
```

## Next Steps for anethassist

1. Run pipeline locally with your NCBI API key
2. Load JSONL into Postgres/BigQuery - schema maps directly to table with JSONB for mesh_terms/authors
3. Build embeddings on title+abstract for semantic search (use PubMedBERT)
4. For nclexhacks: filter publication_types = RCT|Systematic Review + year >=2020 + high IF journal for question stems

## Limitations in this sandbox

Container has no internet, so this package contains:
- Full schema definition
- Production code ready to run outside sandbox
- Sample CSV/JSONL with 16 real PMIDs validated from swarm searches (not full 280k)

To get full 280k corpus, run pubmed_extraction_pipeline.py on a machine with internet.

## Contact

Seth Burkhardt - anethassist project
Swarm: 16 agents, max recall, deduplicated, full metadata per record
