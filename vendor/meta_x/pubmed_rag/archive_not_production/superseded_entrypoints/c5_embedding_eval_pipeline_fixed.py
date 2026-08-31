"""
Agent C5: Embedding Eval Developer - Production Fixed Pipeline v2
Full audit fixes + embedding evaluation integration

This is the C5 production deliverable that:
1. Fixes all audit issues (rate limits, dedup, classification FP, MedlineDate fallback, etc)
2. Implements evaluation metrics (recall@k, MRR, NDCG)
3. Integrates 50-query anesthesia benchmark
4. Provides production-ready extraction with enrichment

See also:
- embedding_eval_metrics.py (core metrics)
- anesthesia_embedding_evaluator.py (evaluator with benchmark loader)
- anesthesia_benchmark_queries.jsonl (50 queries)
"""

from __future__ import annotations
import json
import re
import time
import random
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from collections import defaultdict

# Re-use rate limiter, dedup, classification, date parsing from evaluator
from anesthesia_embedding_evaluator import (
    RateLimiter,
    fetch_with_retry,
    parse_medline_date,
    parse_pubmed_xml_fixed,
    deduplicate_records,
    classify_subdomains_precise,
    normalize_doi,
    normalize_title,
)

# Fallback if get_session not exported in evaluator (due to our naming)
try:
    from anesthesia_embedding_evaluator import get_session
except ImportError:
    def get_session():
        import requests
        s = requests.Session()
        s.headers.update({"User-Agent": "anethassist-c5/2.0 embedding-eval"})
        return s

from embedding_eval_metrics import evaluate_retrieval, ndcg_at_k, recall_at_k

JOURNAL_IF = {
    "Anesthesiology": 9.1,
    "British Journal of Anaesthesia": 9.166,
    "Anaesthesia": 6.995,
    "Anesthesia and Analgesia": 4.6,
    "European Journal of Anaesthesiology": 4.33,
    "Journal of Clinical Anesthesia": 5.1,
    "Regional Anesthesia and Pain Medicine": 3.5,
}

AGENT_QUERIES = {
    1: '("Anesthesia, General"[MeSH] OR "general anesthesia"[tiab] OR "general anaesthesia"[tiab]) AND ("depth of anesthesia"[tiab] OR BIS[tiab] OR "bispectral index"[tiab] OR awareness[tiab] OR "intraoperative awareness"[tiab])',
    2: '(("Anesthesia, Conduction"[MeSH] OR "Anesthesia, Spinal"[MeSH] OR "Anesthesia, Epidural"[MeSH]) OR ("combined spinal epidural"[tiab] OR CSEA[tiab] OR "dural puncture epidural"[tiab] OR "neuraxial block"[tiab]))',
    3: '(("Nerve Block"[MeSH] OR "Brachial Plexus Block"[MeSH]) OR ("femoral nerve block"[tiab] OR "transversus abdominis plane"[tiab] OR TAP[tiab] OR ESPB[tiab] OR QLB[tiab] OR PENG[tiab] OR "fascial plane block"[tiab]) AND (ultrasound[tiab] OR "Ultrasonography, Interventional"[MeSH]))',
    4: '(("Anesthetics, Local"[MeSH] OR "Anesthetics, Local"[Pharmacological Action]) AND (Lidocaine[MeSH] OR Bupivacaine[MeSH] OR Ropivacaine[MeSH] OR levobupivacaine[tiab]) AND (pharmacology[sh] OR toxicity[sh] OR pharmacokinetics[sh] OR "systemic toxicity"[tiab] OR LAST[tiab]))',
    5: '(("Airway Management"[MeSH] OR "Intubation, Intratracheal"[MeSH] OR "Laryngoscopy"[MeSH] OR "Laryngeal Masks"[MeSH]) AND ("difficult airway"[tiab] OR videolaryngoscopy[tiab] OR videolaryngoscope[tiab] OR "supraglottic airway"[tiab]))',
    6: '(("Monitoring, Intraoperative"[MeSH] OR "Electroencephalography"[MeSH] OR "Capnography"[MeSH]) AND (BIS[tiab] OR entropy[tiab] OR "spectral edge"[tiab] OR capnography[tiab] OR hemodynamic[tiab]))',
    7: '(("Anesthesia, General"[MeSH] OR "Anesthesia, Inhalation"[MeSH]) AND ("Pediatrics"[MeSH] OR "Infant"[MeSH] OR "Child"[MeSH]) AND (neurotoxicity[tiab] OR "GAS trial"[tiab] OR "pediatric anesthesia"[tiab]))',
    8: '(("Anesthesia, Obstetrical"[MeSH] OR "Analgesia, Obstetrical"[MeSH] OR "Analgesia, Epidural"[MeSH]) AND ("Labor, Obstetric"[MeSH] OR "Cesarean Section"[MeSH]) AND (PIEB[tiab] OR PCEA[tiab] OR "intrathecal morphine"[tiab] OR ERAC[tiab]))',
    9: '(("Cardiac Surgical Procedures"[MeSH] AND "Anesthesia"[MeSH]) AND ("Cardiopulmonary Bypass"[MeSH] OR "Echocardiography, Transesophageal"[MeSH] OR TEE[tiab] OR CPB[tiab]))',
    10: '(("Neurosurgical Procedures"[MeSH] AND "Anesthesia"[MeSH]) AND (craniotomy[tiab] OR "awake craniotomy"[tiab] OR "cerebral protection"[tiab] OR neuroprotection[tiab]))',
    11: '(("Intensive Care Units"[MeSH] OR "Critical Care"[MeSH]) AND ("Dexmedetomidine"[MeSH] OR Propofol[MeSH] OR "Hypnotics and Sedatives"[MeSH]) AND (Delirium[MeSH] OR "mechanical ventilation"[tiab]))',
    12: '(("Pain, Postoperative"[MeSH] OR "Acute Pain"[MeSH] OR "Chronic Pain"[MeSH]) AND ("opioid sparing"[tiab] OR "opioid-free"[tiab] OR "multimodal analgesia"[tiab] OR ERAS[tiab]) AND ("Anesthesia"[MeSH] OR "Nerve Block"[MeSH]))',
    13: '(("Malignant Hyperthermia"[MeSH] OR "Postoperative Nausea and Vomiting"[MeSH] OR "Anaphylaxis"[MeSH] OR "Intraoperative Complications"[MeSH]) AND "Anesthesia"[MeSH])',
    14: '(("Propofol"[MeSH] OR "Ketamine"[MeSH] OR "Analgesics, Opioid"[MeSH] OR "Neuromuscular Blocking Agents"[MeSH] OR "Sugammadex"[MeSH]) AND ("Anesthesia, Intravenous"[MeSH] OR "Anesthesia, General"[MeSH]))',
    15: '(("Enhanced Recovery After Surgery"[tiab] OR "Perioperative Care"[MeSH] OR "Preoperative Care"[MeSH]) AND (prehabilitation[tiab] OR "blood management"[tiab] OR "tranexamic acid"[tiab] OR hypothermia[tiab]))',
    16: '(("Artificial Intelligence"[MeSH] OR "Machine Learning"[MeSH] OR "Deep Learning"[MeSH] OR "Simulation Training"[MeSH]) AND ("Anesthesiology"[MeSH] OR "Anesthesia"[MeSH] OR anesthes*[tiab]))',
}

def esearch_with_history(term: str, session, limiter: RateLimiter, api_key: str = None, retmax: int = 0):
    params = {
        "db": "pubmed",
        "term": term,
        "retmax": retmax,
        "retmode": "json",
        "usehistory": "y",
        "tool": "anethassist-c5-embedding-eval",
        "email": "anethassist@example.com"
    }
    if api_key:
        params["api_key"] = api_key
    r = fetch_with_retry(session, "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params, limiter)
    data = r.json()
    es = data["esearchresult"]
    return {"count": int(es["count"]), "webenv": es["webenv"], "query_key": es["querykey"], "idlist": es.get("idlist", [])}

def efetch_batch(webenv: str, query_key: str, retstart: int, retmax: int, session, limiter: RateLimiter, api_key: str = None) -> str:
    params = {
        "db": "pubmed",
        "WebEnv": webenv,
        "query_key": query_key,
        "retstart": retstart,
        "retmax": retmax,
        "retmode": "xml",
        "tool": "anethassist-c5-embedding-eval",
        "email": "anethassist@example.com"
    }
    if api_key:
        params["api_key"] = api_key
    r = fetch_with_retry(session, "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", params, limiter)
    return r.text

# ---------------------------------------------------------------------
# C5 Production Pipeline main
# ---------------------------------------------------------------------
def run_c5_pipeline(max_records_per_agent: int = 50000, output_dir: str = "./anesthesia_corpus_c5", api_key: str = None, rps: float = 2.8):
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # NCBI default contract: <=3 req/s without a key, <=10 req/s with a key.
    # Clamp caller input so a misconfigured CLI cannot exceed the default policy.
    actual_rps = min(rps, 9.5 if api_key else 2.8)
    limiter = RateLimiter(rps=actual_rps, burst=1)
    session = get_session()

    all_records = []
    seen_pmids = set()
    seen_dois = set()

    for agent_id in sorted(AGENT_QUERIES.keys()):
        query = AGENT_QUERIES[agent_id]
        print(f"\n[Agent {agent_id}] C5 fixed pipeline - query {query[:100]}...")
        try:
            search_res = esearch_with_history(query, session, limiter, api_key=api_key, retmax=0)
            count = search_res["count"]
            webenv = search_res["webenv"]
            qkey = search_res["query_key"]
            print(f"  Count: {count} | WebEnv: {webenv[:20]}... | rps={actual_rps}")
            fetch_n = min(count, max_records_per_agent)
            for start in range(0, fetch_n, 100):
                print(f"  Fetch batch {start}/{fetch_n}")
                xml = efetch_batch(webenv, qkey, start, 100, session, limiter, api_key=api_key)
                batch_recs = parse_pubmed_xml_fixed(xml)
                for rec in batch_recs:
                    pmid = rec.get("pmid", "")
                    doi_norm = normalize_doi(rec.get("doi", "") or "")
                    if pmid and pmid in seen_pmids:
                        rec["extraction_metadata"]["dedup_status"] = "duplicate_type_I"
                        continue
                    if doi_norm and doi_norm in seen_dois:
                        rec["extraction_metadata"]["dedup_status"] = "duplicate_type_I"
                        continue
                    # Precise classification fixing FP
                    rec["anesthesia_subdomains"] = classify_subdomains_precise(rec)
                    rec["extraction_metadata"]["query_used"] = query
                    rec["extraction_metadata"]["agent_id"] = agent_id
                    seen_pmids.add(pmid)
                    if doi_norm:
                        seen_dois.add(doi_norm)
                    all_records.append(rec)
        except Exception as e:
            print(f"Agent {agent_id} failed: {e}")
            import traceback
            traceback.print_exc()
            continue

    print(f"\nC5 pre-dedup: {len(all_records)} records")
    deduped, stats = deduplicate_records(all_records)
    print(f"C5 post-dedup: {len(deduped)} | stats {stats}")

    # Save JSONL
    with open(out_dir / "anesthesia_full_metadata_c5.jsonl", "w", encoding="utf-8") as f:
        for r in deduped:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Save CSV flattened with full schema fields including month/day (audit fix)
    import csv
    with open(out_dir / "anesthesia_full_metadata_c5.csv", "w", newline="", encoding="utf-8") as cf:
        writer = csv.DictWriter(cf, fieldnames=[
            "pmid","doi","pmcid","title","year","month","day","pdat_raw","journal_title","journal_if","volume","pages",
            "publication_types","mesh_terms_pipe","mesh_major_pipe","chemicals_pipe","subdomains_pipe","study_type",
            "authors_pipe","n_authors","orcid_present","abstract_first_500","query_used","agent_id","dedup_status"
        ])
        writer.writeheader()
        for r in deduped:
            writer.writerow({
                "pmid": r["pmid"],
                "doi": r["doi"],
                "pmcid": r["pmcid"],
                "title": r["title"],
                "year": r["publication_date"]["year"],
                "month": r["publication_date"]["month"],
                "day": r["publication_date"]["day"],
                "pdat_raw": r["publication_date"]["pdat"],
                "journal_title": r["journal"]["title"],
                "journal_if": r["journal"]["impact_factor"],
                "volume": r["journal"]["volume"],
                "pages": r["journal"]["pages"],
                "publication_types": "|".join(r["publication_types"]),
                "mesh_terms_pipe": "|".join([m["descriptor_name"] for m in r["mesh_terms"]][:15]),
                "mesh_major_pipe": "|".join([m["descriptor_name"] for m in r["mesh_terms"] if m.get("major_topic")][:10]),
                "chemicals_pipe": "|".join(r["anesthesia_specific"]["drugs"][:10]),
                "subdomains_pipe": "|".join(r["anesthesia_subdomains"]),
                "study_type": r["study_design"]["type"],
                "authors_pipe": "|".join([f"{a['last_name']} {a['initials']}" for a in r["authors"][:6]]),
                "n_authors": len(r["authors"]),
                "orcid_present": any(a.get("orcid") for a in r["authors"]),
                "abstract_first_500": (r["abstract"] or "")[:500].replace("\n"," "),
                "query_used": r["extraction_metadata"]["query_used"][:300],
                "agent_id": r["extraction_metadata"]["agent_id"],
                "dedup_status": r["extraction_metadata"]["dedup_status"]
            })

    # Save audit fix manifest
    manifest = {
        "agent": "C5 Embedding Eval Developer",
        "audit_fixes_applied": {
            "rate_limits": {
                "fixed": True,
                "previous_bug": "Sleep 0.34 with key (20 req/s) / 0.5 without (10 req/s) but no Retry-After, no exponential backoff, no jitter, no circuit breaker; also inverted per NCBI spec actual is 3/s no key, 10/s with key",
                "fix": "Token bucket clamped to NCBI default policy (2.8/s no key, <=9.5/s with key), burst 1, exponential backoff + Retry-After",
                "rps_used": actual_rps
            },
            "dedup": {
                "fixed": True,
                "previous_bug": "Only PMID exact",
                "fix": "Multi-stage: 1) PMID exact, 2) DOI lowercased stripped URL prefix, 3) Title normalized Jaccard>0.9 + year +-1 + first author, 4) Bramer: journal|volume|pages|year; keep richest abstract",
                "stats": stats
            },
            "classification_fp": {
                "fixed": True,
                "previous_bug": "any(k in combined for k in keywords) substring matching - TAP matches transcriptome, BIS matches biscuit, child matches childbirth, pain matches painting",
                "fix": "Word boundaries \\b, MeSH descriptor exact set match for major topics, phrase matching for multi-word, anesthesia context gating (require anesthesia/analgesia/etc for broad terms), TAP requires transversus abdominis|plane block|abdominal wall, exclusion lists",
                "examples": "TAP blocked unless transversus abdominis context"
            },
            "medline_date_fallback": {
                "fixed": True,
                "previous_bug": "Only looked at PubDate Year element, missing MedlineDate like '2023 Jan-Feb', '2023 Fall', '2023 Spring' causing year=None",
                "fix": "parse_medline_date regex extracts year(s) (last in range), month mapping including seasons spring=3 summer=6 fall/autumn=9 winter=12, day heuristic via Month Day pattern; parse_pubdate_element tries Year then MedlineDate fallback then ArticleDate",
                "test_cases": ["2023 Jan-Feb -> (2023,1,None)", "2023 Fall -> (2023,9,None)", "2023 Dec 12 -> (2023,12,12)"]
            },
            "month_day_parsing": {
                "fixed": True,
                "previous_bug": "month, day always None",
                "fix": "Parse Month element (digit or Jan/Feb map) and Day element, plus MedlineDate fallback"
            },
            "orcid_extraction": {
                "fixed": True,
                "previous_bug": "orcid always None",
                "fix": "Parse Author/Identifier where Source=ORCID"
            },
            "structured_abstract": {
                "fixed": True,
                "previous_bug": "Only label, not NlmCategory, no mapping to background/methods/results/conclusions, no full_sections",
                "fix": "Check Label and NlmCategory, map objective/purpose->background, method->methods, result->results, conclusion->conclusions, full_sections dict for others"
            },
            "embedding_eval": {
                "metrics_implemented": ["recall@k", "precision@k", "MRR", "NDCG@k (primary, method 1 exponential gain)", "MAP", "Hit@k", "bootstrap 95% CI", "paired significance test"],
                "benchmark": "50 anesthesia queries across 16 subdomains, graded relevance 0/1/2/3, AnesSuite-inspired, FP warnings for TAP/BIS",
                "k_values": [1,3,5,10,20,100],
                "primary_metric": "NDCG@10"
            }
        },
        "total_records": len(deduped),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    with open(out_dir / "c5_audit_fix_manifest.json", "w") as jf:
        json.dump(manifest, jf, indent=2)

    print(f"\n=== C5 Pipeline Complete ===")
    print(json.dumps(manifest["audit_fixes_applied"], indent=2))
    return out_dir, deduped, manifest

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-records", type=int, default=5000)
    parser.add_argument("--output", type=str, default="./anesthesia_corpus_c5")
    parser.add_argument("--api-key", type=str, default=None)
    parser.add_argument("--rps", type=float, default=2.8)
    args = parser.parse_args()
    run_c5_pipeline(max_records_per_agent=args.max_records, output_dir=args.output, api_key=args.api_key, rps=args.rps)
