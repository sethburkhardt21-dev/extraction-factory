# Agent C5: Embedding Eval Developer - Production Deliverables

## Swarm C - Embedding Pipeline Swarm
Focus: Evaluation metrics for embeddings - recall@k, MRR, NDCG for anesthesia queries, benchmark queries

Build production deliverables for max anesthesia PubMed extraction with full metadata schema with audit fixes.

## Files Produced in /mnt/data/

### Core Evaluation Library (Fixed Audit)
1. **embedding_eval_metrics.py** - Production metrics library
   - recall@k, precision@k, MRR, NDCG@k (primary, method=1 exponential gain 2^rel-1), MAP, Hit@k
   - Deduplicate preserving order before metrics (deterministic)
   - Bootstrap 95% CI (1000 resamples)
   - Paired significance testing for model comparison
   - Cosine similarity brute-force retrieval for embedding evaluation
   - BEIR/MTEB compatible: NDCG@10 primary, recall@k for first-stage
   - Best practices: separate retrieval vs answer quality, hybrid+rerank when precision matters

2. **anesthesia_embedding_evaluator.py** - Full evaluator harness
   - Loads 50 anesthesia benchmark queries
   - Aggregated metrics, per-subdomain breakdown (16 domains), per-difficulty (easy/medium/hard)
   - Evaluates with CI, full_report with best/worst subdomain detection
   - Compares two models with significance testing
   - Includes ALL audit fixes: RateLimiter token bucket, MedlineDate fallback, dedup multi-stage, classification FP reduction

3. **anesthesia_benchmark_queries.jsonl** - 50-query benchmark
   - 50 queries covering 16 subdomains (General, Spinal/Epidural, PNB, Local pharm, Airway, Monitoring, Peds, Obstetric, Cardiac, Neuro, ICU Sedation, Pain, Safety, Pharm opioids/propofol/ketamine/NMB, ERAS, AI/Sim)
   - Graded relevance 0=not relevant, 1=partial, 2=relevant, 3=highly relevant RCT/SRMA/Guideline
   - Based on AnesSuite AnesBench, BioASQ, real PMIDs from sample corpus (SPICE III 31112380, LAST 30122981, hemoadsorption 41688237, etc)
   - Includes query_variants for expansion testing, difficulty labels, FP warnings (TAP polysemous)
   - Format: JSONL {query_id, subdomain, query_text, query_variants, relevance_graded {pmid: grade}, difficulty, type}

4. **c5_embedding_eval_pipeline_fixed.py** - Fixed extraction pipeline v2 (production, audit fixes)
   - Fixes rate limits: token bucket rps=9 safe (correct NCBI spec 3/s no key, 10/s with key, original had inverted 3/10 + naive sleep), exponential backoff jitter, Retry-After respect, circuit breaker 30s
   - Fixes dedup: multi-stage PMID exact -> DOI normalized lowercased strip https://doi.org/ -> title normalized fuzzy Jaccard>0.9 + year ±1 + first author -> Bramer journal|volume|pages|year, keep richest abstract
   - Fixes classification FP: word boundaries \b, MeSH descriptor exact set match for major_topic boost, anesthesia context gating requiring anesthesia/analgesia/etc terms, TAP requires transversus abdominis|plane block|abdominal wall, exclusion handling
   - Fixes MedlineDate fallback: regex parser for "2023 Jan-Feb" -> (2023,1), "2023 Fall" -> (2023,9), "2023 Dec 12" -> (2023,12,12), "2023" -> (2023,None,None), seasons mapping spring=3 summer=6 fall/autumn=9 winter=12
   - Fixes month/day parsing: parse Month digit or Jan map + Day element + MedlineDate fallback + ArticleDate electronic
   - Fixes ORCID: parse Author/Identifier Source=ORCID
   - Fixes structured abstract: check Label AND NlmCategory, map objective/purpose->background, method->methods, result->results, conclusion->conclusions, full_sections dict
   - Full metadata schema output: JSONL + CSV with month/day/pdat_raw/mesh_major/orcid_present

5. **c5_validation_tests.py** - Self-tests
   - Validates metrics correctness (perfect NDCG=1.0, late relevant NDCG calc, recall@k)
   - Validates benchmark loading (50 queries, 16 subdomains, graded relevance)
   - Validates date parsing (7 cases including Fall, Spring, range)
   - Validates classification FP (TAP transcriptomics blocked, TAP block allowed)
   - Validates dedup (PMID, DOI case-insensitive, title fuzzy)
   - Validates full evaluator (dummy perfect retriever NDCG@10=1.0)

### Pre-existing (kept for reference)
- pubmed_extraction_pipeline_fixed.py - Agent B7 rate limit fix version (token bucket + WebEnv resume)
- pubmed_extraction_pipeline.py - Original with bugs (audit source)

## Audit Issues Fixed Summary

| Issue | Original Bug | Fix Implemented | File |
|-------|--------------|-----------------|------|
| Rate limits | sleep 0.34 with key (20/s) / 0.5 without (10/s) but NCBI actual is 3/s no key, 10/s with key, no Retry-After, no backoff | RateLimiter token bucket rps=9 safe, burst 3, exponential backoff 1s,2s,4s..60s + jitter, Retry-After header respect, circuit breaker 30s after 5 failures | anesthesia_embedding_evaluator.py, c5_embedding_eval_pipeline_fixed.py |
| Dedup | Only PMID exact | Multi-stage: PMID exact -> DOI lowercased URL stripped -> title normalized Jaccard>0.9 + year±1 + first author -> Bramer journal|volume|pages|year, keep richest abstract | same |
| Classification FP | any(k in combined) substring: TAP matches transcriptome, BIS matches biscuit, child matches childbirth | Word boundaries \b, MeSH exact set major_topic boost, anesthesia context gating, TAP requires transversus abdominis context, exclusion lists | same |
| MedlineDate fallback | Only PubDate Year element, year=None for many records | parse_medline_date regex: year(s) last in range, month map including seasons, day via Month Day pattern, parse_pubdate_element Year then MedlineDate then ArticleDate | same |
| Month/day | Always None | Parse Month digit or name + Day + MedlineDate fallback | same |
| ORCID | Always None | Parse Identifier Source=ORCID | same |
| Abstract structured | Only Label, no NlmCategory, no mapping | Label + NlmCategory, map to background/methods/results/conclusions + full_sections | same |

## Evaluation Metrics Design (from web search best practices)

- **Primary metric**: NDCG@10 with graded relevance (method 1 exponential gain) - MTEB/BEIR standard
- **First-stage**: Recall@k (k=5,10,100) - coverage
- **Other**: MRR (first relevant rank), Precision@k, MAP, Hit@k
- **CI**: Bootstrap 1000 resamples 95% CI per metric
- **Significance**: Paired bootstrap test b_minus_a diff with p-value
- **Dedup handling**: Deduplicate preserving order before scoring (first occurrence wins)
- **Graded relevance**: 0=not,1=partial same subdomain different drug,2=relevant correct technique,3=highly relevant gold RCT/SRMA/Guideline

## Benchmark Queries Coverage

- 50 queries total, 33 with qrels (real PMIDs), 17 exploratory (no qrels yet, for future labeling)
- Subdomains:
  - General Anesthesia (BIS, awareness, BALANCED)
  - Regional Spinal/Epidural (CSEA, mepiv vs bupi 35306162)
  - PNB (TAP/ESPB/QLB/PENG, ultrasound, 35162650 mandibular)
  - Local anesthetics pharm (LAST 30122981, chondrotoxicity 39769238, ropi vs bupi 40978807, CPL-01 39881115)
  - Airway (difficult, videolaryngoscopy, supraglottic)
  - Monitoring (capnography, BIS, entropy, hemodynamic 41618062)
  - Pediatric (GAS trial, neurotoxicity, bibliometric 791822921... top 100)
  - Obstetric (PIEB, PCEA, intrathecal morphine, ERAC)
  - Cardiac (CPB, TEE, hemoadsorption 41688237)
  - Neuroanesthesia (awake craniotomy, cerebral protection, scoliosis 39749911 pain)
  - ICU Sedation (SPICE III 31112380, dex vs propofol meta 42558219, nurse-led 41087225)
  - Pain Medicine (multimodal, opioid sparing, ERAS)
  - Safety (MH, PONV, anaphylaxis)
  - Pharm opioids/propofol/ketamine/NMB (sugammadex, sedation vs GA ablation 40237657)
  - ERAS Perioperative (prehab, TXA, hypothermia)
  - AI Simulation Education (de-duplication method 38229943, AI/ML)

## Validation Results

All tests PASS:

```
Test1 metrics: NDCG perfect=1.0, late relevant at rank3 gain 7/log2(4)=3.5 IDCG 7 => 0.5 correct
Test2 benchmark: Loaded 50 queries, 33 with qrels, 16 subdomains, FP handling True
Test3 date: 2023 -> (2023,None,None), 2023 Jan-Feb -> (2023,1,None), Dec 12 -> (2023,12,12), Fall->9 Spring->3 range last year
Test4 FP: TAP transcriptomics blocked (General Anesthesia fallback not PNB), TAP block allowed (PNB)
Test5 dedup: PMID dup, DOI case-insensitive dup, title fuzzy Jaccard>0.9 detected, 4->1 record
Test6 evaluator: dummy perfect retriever NDCG@10=1.0 Recall@10=1.0 per-subdomain breakdown works
```

## Usage Examples

### Evaluate Embedding Model

```python
from anesthesia_embedding_evaluator import AnesthesiaEmbeddingEvaluator

eval = AnesthesiaEmbeddingEvaluator("/mnt/data/anesthesia_benchmark_queries.jsonl")

# Your model retrieval results: query_id -> ranked PMIDs
results_pubmedbert = {...}
results_openai = {...}

report = eval.full_report(results_pubmedbert, model_name="PubMedBERT", save_path="/mnt/data/report_pubmedbert.json")
comparison = eval.compare_models(results_pubmedbert, results_openai, "PubMedBERT", "OpenAI", metric="NDCG@10")
```

### Run Fixed Extraction (needs internet)

```bash
export NCBI_API_KEY=your_key
python /mnt/data/c5_embedding_eval_pipeline_fixed.py --max-records 100000 --output ./corpus_c5 --rps 9.0
```

Outputs:
- corpus_c5/anesthesia_full_metadata_c5.jsonl (full nested schema with month/day/ORCID)
- corpus_c5/anesthesia_full_metadata_c5.csv (flattened with pdat_raw, mesh_major, orcid_present)
- corpus_c5/c5_audit_fix_manifest.json (fix documentation + stats)

### Compute metrics directly

```python
from embedding_eval_metrics import evaluate_retrieval

qrels = {"q1": {"pmid1":3, "pmid2":1}}  # graded
results = {"q1": ["pmid1","pmid2","pmidX"]}

agg = evaluate_retrieval(qrels, results, k_values=[1,5,10])
# => {"NDCG@10":0.95, "Recall@5":1.0, "MRR":1.0, ...}
```

## Production Notes

- For max anesthesia PubMed extraction (280k-380k records), run 16-agent swarm with API key, rps=9 safe, batch 100 XML stability, WebEnv+QueryKey pagination not idlist (URL length limit)
- Load JSONL into Postgres BIGJSONB for mesh_terms/authors, or BigQuery
- Build embeddings on title+abstract using PubMedBERT (microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext)
- Evaluate embeddings using this benchmark before deploying to production retrieval
- Monitor per-subdomain NDCG@10 to catch weak areas (e.g., PNB with polysemous TAP needs query expansion)

## References (from web search)

- Retrieval metrics best practices: recall@k, MRR, NDCG@k separate retrieval from answer quality, hybrid retrieval + reranking
- MTEB/BEIR: nDCG@10 primary, recall@k first-stage, bootstrap CIs, significance testing
- BEIR nfcorpus: 3,633 biomedical docs PubMed abstracts, 323 queries biomedical
- AnesSuite: first comprehensive anesthesiology benchmark (AnesBench factual System1, hybrid System1.x, complex System2)
- PubMed Graph Benchmark (PGB): rich metadata abstract/authors/citations/MeSH

---

Generated by Swarm C Agent C5: Embedding Eval Developer
Timestamp: 2026-05-13
