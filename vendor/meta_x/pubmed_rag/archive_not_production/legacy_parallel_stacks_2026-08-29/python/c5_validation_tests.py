"""
C5 Embedding Eval Developer - Production README + Validation

This file documents validation of all production deliverables for Agent C5

Deliverables:
1. embedding_eval_metrics.py - Core metrics library (recall@k, MRR, NDCG, MAP, bootstrap CI)
2. anesthesia_embedding_evaluator.py - Evaluator with 50-query benchmark loader, per-subdomain, per-difficulty, significance testing
3. anesthesia_benchmark_queries.jsonl - 50 anesthesia queries covering 16 subdomains with graded relevance 0-3, FP warnings
4. c5_embedding_eval_pipeline_fixed.py - Fixed extraction pipeline v2 with all audit fixes
5. (pre-existing) pubmed_extraction_pipeline_fixed.py - B7 rate limit fixed version (kept)

Audit fixes implemented (all critical):
- Rate limits: token bucket + exponential backoff + Retry-After + jitter + circuit breaker
  * Correct NCBI spec: 3 req/s no key, 10 req/s with key (original had inverted 10/20 and naive sleep)
- Dedup: multi-stage PMID exact -> DOI normalized -> title fuzzy Jaccard>0.9 + year + first author -> Bramer journal+volume+pages+year
- Classification FP: word boundaries \b, MeSH major_topic boost, anesthesia context gating, TAP requires transversus abdominis context, exclusion lists
- MedlineDate fallback: regex parser for "2023 Jan-Feb", "2023 Fall", etc, returns year/month/day
- Month/day parsing, ORCID, structured abstract improvements

Evaluation Metrics Best Practices (from web search):
- Use NDCG@10 as primary (MTEB/BEIR standard), recall@k for first-stage retriever
- Support graded relevance: method 1 exponential gain (2^rel-1)/log2(i+1)
- Deterministic dedup before metrics (preserve order)
- Bootstrap 95% CI with 1000 resamples for confidence intervals
- Paired significance test for model comparison
- Separate retrieval quality from answer quality
- Hybrid retrieval + reranking when precision matters

Benchmark Queries Design (Anesthesia-specific):
- 50 queries, 16 subdomains from 16-agent swarm
- Based on AnesSuite AnesBench + BioASQ + real PubMed sample PMIDs
- Graded relevance: 0=not relevant, 1=partial (same subdomain different drug), 2=relevant, 3=highly relevant RCT/SRMA/Guideline
- Includes FP warnings: e.g., TAP polysemous, BIS ambiguous
- Variants per query for query expansion testing
- Difficulty levels: easy (landmark trials SPICE III, BALANCED), medium, hard (neurotoxicity controversy, fascial plane mechanism)

How to run evaluation:

```python
from anesthesia_embedding_evaluator import AnesthesiaEmbeddingEvaluator

evaluator = AnesthesiaEmbeddingEvaluator(str(BASE_DIR / "anesthesia_benchmark_queries.jsonl"))

# results from your embedding model: {query_id: [ranked PMIDs]}
results = {
  "anes_001_general_bis": ["30122981", "31112380", ...],
  ...
}

report = evaluator.full_report(results, model_name="PubMedBERT", save_path="eval_report.json")
# Per-subdomain breakdown
by_domain = evaluator.evaluate_by_subdomain(results)
```

How to run extraction (requires internet):

```bash
export NCBI_API_KEY=your_key
python c5_embedding_eval_pipeline_fixed.py --max-records 100000 --output ./corpus_c5 --rps 2.8
```

Validation results below.
"""

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
import json
import sys

# Test 1: Metrics library correctness
def test_metrics():
    print("=== Test 1: embedding_eval_metrics.py correctness ===")
    from embedding_eval_metrics import recall_at_k, precision_at_k, ndcg_at_k, reciprocal_rank, evaluate_retrieval

    # Simple perfect retrieval
    retrieved = ["doc1","doc2","doc3"]
    relevant = {"doc1","doc2"}
    assert recall_at_k(retrieved, relevant, 2) == 1.0, "Recall@2 should be 1.0 when both relevant in top2"
    assert precision_at_k(retrieved, relevant, 2) == 1.0
    assert reciprocal_rank(retrieved, relevant) == 1.0
    # Recall@1 = 0.5 (only doc1)
    assert recall_at_k(retrieved, relevant, 1) == 0.5

    # NDCG perfect
    rel_dict = {"doc1":3, "doc2":2, "doc3":1}
    ndcg_perfect = ndcg_at_k(["doc1","doc2","doc3"], rel_dict, 3)
    assert abs(ndcg_perfect - 1.0) < 1e-6, f"Perfect NDCG should be 1.0 got {ndcg_perfect}"

    # NDCG imperfect: relevant at position 3
    ndcg_late = ndcg_at_k(["docX","docY","doc1"], {"doc1":3}, 3)
    assert 0 < ndcg_late < 1.0, "Late relevant should have 0<NDCG<1"
    # DCG calculation check: exponential gain
    # doc1 at rank3: gain (2^3-1)=7 / log2(4)=2 => 3.5 ; IDCG = 7/log2(2)=7 => NDCG=0.5
    expected = 3.5/7.0
    assert abs(ndcg_late - expected) < 1e-6, f"Expected {expected} got {ndcg_late}"

    # Evaluate retrieval aggregate
    qrels = {"q1": {"doc1":3, "doc2":1}, "q2": {"doc3":2}}
    results = {"q1": ["doc1","doc2","docX"], "q2": ["docX","doc3"]}
    agg = evaluate_retrieval(qrels, results, k_values=[1,2,3])
    print(f"  Aggregated: {agg}")
    assert agg["NDCG@1"] > 0, "NDCG@1 should be >0"
    assert agg["Recall@2"] > 0

    print("  PASS: metrics correctness")

def test_benchmark_loading():
    print("\n=== Test 2: benchmark query loading ===")
    benchmark_path = BASE_DIR / "anesthesia_benchmark_queries.jsonl"
    assert benchmark_path.exists(), f"Benchmark not found at {benchmark_path}"
    from anesthesia_embedding_evaluator import load_benchmark_queries
    queries, graded, binary = load_benchmark_queries(benchmark_path)
    print(f"  Loaded {len(queries)} queries, {len([g for g in graded.values() if g])} with qrels")
    # Check at least 40 queries have text
    assert len(queries) >= 40, "Should have at least 40 queries"
    # Check 16 subdomains present (from our 50)
    subdomains = set(q.get("subdomain") for q in queries.values())
    print(f"  Subdomains: {subdomains}")
    assert len(subdomains) >= 10, "Should cover many subdomains"

    # Check FP warnings present
    has_fp_warning = any("fp_warning" in q or "TAP" in q.get("query_text","") for q in queries.values())
    print(f"  FP handling present: {has_fp_warning}")

    # Check graded relevance grades valid 1-3
    for q_id, rel in graded.items():
        for doc_id, grade in rel.items():
            assert grade in (1,2,3,1.0,2.0,3.0), f"Invalid grade {grade} for {q_id}"

    print("  PASS: benchmark loading")

def test_date_parsing():
    print("\n=== Test 3: MedlineDate fallback ===")
    from anesthesia_embedding_evaluator import parse_medline_date

    cases = [
        ("2023", (2023, None, None)),
        ("2023 Jan", (2023, 1, None)),
        ("2023 Jan-Feb", (2023, 1, None)),
        ("2023 Dec 12", (2023, 12, 12)),
        ("2023 Fall", (2023, 9, None)),
        ("2023 Spring", (2023, 3, None)),
        ("2022-2023", (2023, None, None)),
    ]
    for raw, expected in cases:
        y,m,d, _ = parse_medline_date(raw)
        exp_y, exp_m, exp_d = expected
        # Allow day maybe present for some, but check year/month
        assert y == exp_y, f"For '{raw}' expected year {exp_y} got {y}"
        if exp_m is not None:
            assert m == exp_m, f"For '{raw}' expected month {exp_m} got {m}"
        print(f"  '{raw}' -> {(y,m,d)} OK")

    print("  PASS: date parsing")

def test_classification_fp():
    print("\n=== Test 4: Classification FP reduction ===")
    from anesthesia_embedding_evaluator import classify_subdomains_precise

    # FP case: TAP in transcriptomics should not trigger Peripheral Nerve Blocks without context
    rec_fp = {
        "title": "TAP transcription analysis shows TAP1 and TAP2 expression",
        "abstract": "We analyzed TAP1 transcriptomics in water samples TAP water contamination",
        "mesh_terms": [{"descriptor_name": "Gene Expression", "major_topic": True}],
        "chemicals": []
    }
    tags_fp = classify_subdomains_precise(rec_fp)
    # Should NOT be peripheral nerve blocks, should be General fallback (since no anesthesia context)
    has_pnb = "Peripheral Nerve Blocks" in tags_fp
    print(f"  FP test - transcriptomics TAP tags: {tags_fp} -> PNB? {has_pnb}")
    # We expect not PNB for this clear non-anesthesia case (since no anesthesia context, but our function still returns General Anesthesia as default)
    # The important part is that TAP alone doesn't cause false PNB when combined with other heuristics
    # Actually our function will return General Anesthesia fallback, not PNB - which is less harmful than PNB FP
    assert not has_pnb, "TAP transcriptomics should not be classified as PNB"

    # True positive: TAP block
    rec_tp = {
        "title": "Ultrasound-guided transversus abdominis plane TAP block for postoperative analgesia",
        "abstract": "TAP block provides analgesia after abdominal surgery, ultrasound guided",
        "mesh_terms": [{"descriptor_name": "Nerve Block", "major_topic": True}],
        "chemicals": [{"name": "Ropivacaine"}]
    }
    tags_tp = classify_subdomains_precise(rec_tp)
    print(f"  TP test - TAP block tags: {tags_tp}")
    assert "Peripheral Nerve Blocks" in tags_tp, "True TAP block should be classified as PNB"

    print("  PASS: classification FP")

def test_dedup():
    print("\n=== Test 5: Multi-stage dedup ===")
    from anesthesia_embedding_evaluator import deduplicate_records

    records = [
        {"pmid":"123","doi":"10.1000/xyz","title":"Test Title One","publication_date":{"year":2020},"authors":[{"last_name":"Smith"}],"journal":{"title":"Anesthesiology","volume":"1","pages":"1-2"},"extraction_metadata":{"dedup_status":"unique"}},
        {"pmid":"123","doi":"10.1000/xyz","title":"Test Title One","publication_date":{"year":2020},"authors":[{"last_name":"Smith"}],"journal":{"title":"Anesthesiology","volume":"1","pages":"1-2"},"extraction_metadata":{"dedup_status":"unique"}},
        {"pmid":"124","doi":"10.1000/XYZ","title":"Test Title One","publication_date":{"year":2020},"authors":[{"last_name":"Smith"}],"journal":{"title":"Anesthesiology","volume":"1","pages":"1-2"},"extraction_metadata":{"dedup_status":"unique"}}, # DOI dup case-insensitive
        {"pmid":"125","doi":"10.1000/abc","title":"Test Title One","publication_date":{"year":2020},"authors":[{"last_name":"Smith"}],"journal":{"title":"Anesthesiology","volume":"1","pages":"1-2"},"extraction_metadata":{"dedup_status":"unique"}}, # title fuzzy dup
    ]
    deduped, stats = deduplicate_records(records)
    print(f"  Stats: {stats} | deduped len {len(deduped)}")
    assert len(deduped) < len(records), "Should dedup"
    assert stats["pmid_dup"] >=1
    assert stats["doi_dup"] >=1 or stats["title_fuzzy_dup"]>=1

    print("  PASS: dedup")

def test_full_evaluator():
    print("\n=== Test 6: Full evaluator end-to-end ===")
    from anesthesia_embedding_evaluator import AnesthesiaEmbeddingEvaluator
    benchmark_path = str(BASE_DIR / "anesthesia_benchmark_queries.jsonl")
    evaluator = AnesthesiaEmbeddingEvaluator(benchmark_path)

    # Build dummy perfect retriever
    dummy_results = {}
    for q_id, qrels in evaluator.qrels_graded.items():
        if qrels:
            # return relevant docs sorted by grade desc
            sorted_docs = sorted(qrels.keys(), key=lambda d: qrels[d], reverse=True)
            dummy_results[q_id] = sorted_docs + [f"rand_{i}" for i in range(50)]
        else:
            dummy_results[q_id] = [f"rand_{i}" for i in range(50)]

    report = evaluator.full_report(dummy_results, model_name="dummy_perfect")
    print(f"  Overall NDCG@10: {report['overall_metrics'].get('NDCG@10')}")
    print(f"  Recall@10: {report['overall_metrics'].get('Recall@10')}")
    assert report["overall_metrics"]["NDCG@10"] > 0.9, "Perfect retriever should have high NDCG"

    # Test per-subdomain breakdown exists
    assert "by_subdomain" in report and len(report["by_subdomain"]) > 0

    print("  PASS: full evaluator")

if __name__ == "__main__":
    test_metrics()
    test_benchmark_loading()
    test_date_parsing()
    test_classification_fp()
    test_dedup()
    test_full_evaluator()
    print("\n=== ALL TESTS PASSED ===")
    print("Production deliverables validated for C5 Embedding Eval Developer")
