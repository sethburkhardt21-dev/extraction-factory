# Anesthesia RAG Pipeline - Production Deliverables

## Overview
Production RAG pipeline for anesthesia PubMed extraction with full metadata schema. Fixes all audit critical issues.

## Audit Fixes Implemented

### CRITICAL-1: Rate Limits (PubMed E-utilities)
- File: `config.py` + `pubmed_extractor.py`
- Fix: 
  - `delay_with_key=0.11s` (9 req/s safe), `delay_without_key=0.34s` (2.9 req/s)
  - Exponential backoff with jitter: `backoff_factor=2.0`, initial 1s, 5 retries
  - 429 handling with explicit sleep
  - `requests.Session` with `Retry` adapter for 500/502/503
  - Local disk cache with TTL 72h to minimize calls

### CRITICAL-2: Missing MedlineDate Fallback
- File: `pubmed_extractor.py` `parse_medline_date()` + `parse_pub_date()`
- Problem: 2.1M records use MedlineDate; prev parser returned year:null for PMIDs 36957974, 34904812
- Fix:
  - Hierarchy: PubDate Year → MedlineDate leading 4-digit regex → ArticleDate → History
  - Regex: `(?P<year>\d{4})`
  - Handles ranges: "2007 Spring"→2007/3, "Fall 2006"→2006/9, "1999-2000"→1999, "2023 Jan-Feb"→2023/2 (last month in range)
  - Tested: 7 edge cases, all pass (see `main_pipeline.py` validation)

### CRITICAL-3: Dedup Issues
- File: `deduplication.py`
- Previous: PMID only, missed DOI variants (uppercase, URL prefix)
- Fix:
  - DOI normalization: lowercase, strip `https://doi.org/`, `doi:`, trailing `.,;`
  - 3-pass: PMID → DOI → Title+Year fuzzy (normalized title hash, year, len>20 filter)
  - Content completeness score to keep richest record
  - Deterministic ordering by PMID int ascending + year
  - Validation: doi tests PASS

### CRITICAL-4: Classification False Positives
- File: `anesthesia_classifier.py`
- Previous: naive keyword matching → FP from "anesthesia dolorosa" (neuropathic pain), plant anesthesia, Drosophila
- Fix:
  - Multi-signal scoring: MeSH (4.0 major, 2.5 minor, cap 8.0) + weighted keywords (3.0 general anesthesia, 2.5 spinal etc, cap 12.0) + journal (core journals Anesthesiology etc +2.0)
  - Blocklist regex: `\bplant anesthesia\b`, `\banesthesia dolorosa\b`, model organism combos, `^Re:` letters
  - Tier: core (>=8), relevant (>=5), peripheral (>=threshold), blocked (negative match)
  - Override: Major MeSH "Anesthesia" → always core, confidence 0.99
  - Validation: FP blocked (`anesthesia dolorosa`, `plant anesthesia`) → non-anesthesia, TP retained (propofol induction)

### CRITICAL-5: Missing Full Metadata Schema & CollectiveName
- File: `pubmed_extractor.py` `extract_full_metadata()`
- Fix:
  - Full schema: pmid, doi (normalized lower), pmc_id, article_ids dict, title (innerXml via itertext to preserve <i><b><sup>), abstract + abstract_sections with Label, authors with ForeName/LastName/CollectiveName/ORCID/affiliation/order/type, journal, iso_abbr, issn/eissn, volume, issue, pages, publication_date struct (year/month/day/medline_raw/iso), history_dates (PubStatus), mesh_terms with major flag + qualifiers, keywords, pub_types, grants (id/agency/acronym), language, raw_medline_date
  - CollectiveName support: type=collective vs person
  - Nested XML handling: `get_inner_xml_text()` using `itertext()`
  - ArticleIdList includes PMC, DOI from both PubmedData and MedlineCitation

### CRITICAL-6: Retrieval & Grounding
- File: `embedding_pipeline.py` + `rag_pipeline.py` + `prompt_templates.py`
- Fix:
  - Chunking: 512 tokens sentence-boundary (not token split), 64 overlap (12.5%) preserves clinical phrases per best practice
  - Embeddings: PubMedBERT domain-tuned (microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext) fallback MiniLM
  - Normalized for cosine
  - Hybrid retrieval: dense (weight 0.7) + BM25 (0.3) with normalized fusion, per best practice for clinical
  - Rerank boost: core tier +0.3, anesthesia_score/20, recency (year-2015)*0.01
  - Prompt templates: system strict grounding (cite every claim [PMID:x], refuse if no evidence), query transform (primary/expanded/step-back), clinical intent (drug_info, technique, complication, comparative, peds, OB)
  - Citation precision check, grounding rate metric
  - Safety disclaimer, contraindication flagging

## Files Produced
- `config.py` - Central config with all thresholds
- `pubmed_extractor.py` - Robust extractor with all rate limit & MedlineDate fixes
- `anesthesia_classifier.py` - FP-reduced classifier
- `deduplication.py` - 3-pass dedup deterministically ordered
- `embedding_pipeline.py` - PubMedBERT chunking + FAISS
- `prompt_templates.py` - Clinical Q&A templates with grounding
- `rag_pipeline.py` - Hybrid retrieval + RAG pipeline
- `main_pipeline.py` - Orchestration + validation suite
- `requirements.txt`

## Usage
```bash
export NCBI_API_KEY=your_key
export NCBI_EMAIL=you@example.com
python main_pipeline.py  # demo_mode=True runs mock corpus validation
# For full extraction:
# edit main_pipeline demo_mode=False in main_pipeline.py and run
```

## Validation
Run `python main_pipeline.py` → produces:
- `validation_summary.json` - all audit fixes PASS
- `pipeline_summary.json` - counts
- `index/faiss.index` + `metadata.jsonl`
- `deduped_corpus.jsonl` with full schema
- `rag_test_results.json` - 4 test Q&A with citations

Tested edge cases:
- MedlineDate "2021-2022" → year 2021 extracted (previously null)
- DOI normalization HTTPS and uppercase variants deduped
- CollectiveName preserved (SOAP Study Group)
- Title nested tags preserved via itertext
- Deterministic ordering verified

## RAG Best Practices Applied (from search)
- Chunk 512 tokens sentence boundary, 10-20% overlap ✓
- Domain-tuned embeddings (PubMedBERT) outperform general ✓
- Hybrid BM25 + dense + rerank for medical ✓
- Strict grounding prompt: "answer only from context with citations" ✓
- Query transform + HyDE concept + step-back ✓
- History server for >500 results ✓
- Cache locally ✓
- Rate limiting 0.1s with key / 0.34s without ✓
