"""
Agent B7: Fixed Extraction Pipeline - Drop-in Replacement
Integrates rate limit fix + WebEnv resume + error parsing
Save as pubmed_extraction_pipeline_fixed.py and run locally with internet

Usage:
  pip install requests biopython
  export NCBI_API_KEY=your_key  # optional, raises 3->10 req/s
  python pubmed_extraction_pipeline_fixed.py --max-records 100000 --output ./corpus

Fixes from audit:
- Rate limit: 3/s no key (0.34s), 10/s with key (0.11s) - was inverted 0.34 with key / 0.5 without and wrong 20/10 comment
- WebEnv: detects <ERROR>WebEnv not found</ERROR> in HTTP 200 body, re-runs ESearch, resumes at checkpoint
- Error parsing: handles 429, 5xx, XML ERROR, HTML error pages
- Checkpoint: saves retstart to disk per agent, resumes after crash/expiry
"""

import argparse
import time
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any
import re

# Import fixed module
from agent_b7_rate_limit_fix import (
    ProductionPubMedClient,
    NCBIRateLimiter,
    NCBIErrorParser,
    CheckpointManager,
    WebEnvExpiredError,
    POSTGRES_RATE_LIMIT_DDL,
    BIGQUERY_RATE_LIMIT_DDL,
    parse_pubmed_xml_safe
)

# Keep original AGENT_QUERIES from pipeline
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

def classify_subdomains_fixed(record: Dict) -> List[str]:
    """
    Fixed classifier - addresses FP via substring issue
    Original used: any(k in combined for k in keywords) -> "child" matches "childbirth" etc, "pain" matches "painting"
    Fixed: use word boundaries and MeSH exact matching where possible
    """
    import re
    text = (record["title"] + " " + (record["abstract"] or "")).lower()
    mesh_descriptors = [m["descriptor_name"].lower() for m in record["mesh_terms"]]
    mesh_str = " ".join(mesh_descriptors)
    mesh_set = set(mesh_descriptors)
    
    combined = text + " " + mesh_str
    tags = []
    
    # Define checks with regex word boundaries to avoid substring FP
    checks = {
        "General Anesthesia": {
            "mesh_exact": ["anesthesia, general"],
            "phrase": ["general anesthesia", "general anaesthesia", "depth of anesthesia", "bispectral", "intraoperative awareness"],
            "word": []
        },
        "Regional Anesthesia - Spinal Epidural": {
            "mesh_exact": ["anesthesia, spinal", "anesthesia, epidural", "anesthesia, conduction"],
            "phrase": ["spinal anesthesia", "epidural anesthesia", "combined spinal", "neuraxial block"],
            "word": []
        },
        "Peripheral Nerve Blocks": {
            "mesh_exact": ["nerve block", "brachial plexus block"],
            "phrase": ["femoral nerve block", "transversus abdominis", "erector spinae", "fascial plane block", "ultrasound-guided"],
            "word": []
        },
        "Local Anesthetics Pharmacology": {
            "mesh_exact": ["anesthetics, local", "lidocaine", "bupivacaine", "ropivacaine"],
            "phrase": ["local anesthetic systemic toxicity", "last toxicity"],
            "word": []
        },
        "Airway Management": {
            "mesh_exact": ["airway management", "intubation, intratracheal", "laryngoscopy", "laryngeal masks"],
            "phrase": ["difficult airway", "videolaryngoscopy", "supraglottic airway"],
            "word": []
        },
        "Anesthesia Monitoring": {
            "mesh_exact": ["monitoring, intraoperative", "electroencephalography", "capnography"],
            "phrase": ["spectral edge", "entropy monitoring"],
            "word": []
        },
        "Pediatric Anesthesia": {
            "mesh_exact": ["pediatrics", "infant", "child"],
            "phrase": ["pediatric anesthesia", "pediatric anaesthesia"],
            "word": [r"\bchild\b", r"\binfant\b", r"\bneonate\b"],  # word boundaries fix
        },
        "Obstetric Anesthesia": {
            "mesh_exact": ["anesthesia, obstetrical", "analgesia, obstetrical", "labor, obstetric", "cesarean section"],
            "phrase": ["obstetric anesthesia", "labor analgesia"],
            "word": []
        },
        "Cardiac Anesthesia": {
            "mesh_exact": ["cardiac surgical procedures", "cardiopulmonary bypass", "echocardiography, transesophageal"],
            "phrase": ["cardiac anesthesia", "cardiopulmonary bypass"],
            "word": []
        },
        "Neuroanesthesia": {
            "mesh_exact": ["neurosurgical procedures"],
            "phrase": ["awake craniotomy", "cerebral protection", "neuroprotection"],
            "word": []
        },
        "Critical Care ICU Sedation": {
            "mesh_exact": ["intensive care units", "critical care", "dexmedetomidine", "delirium"],
            "phrase": ["mechanical ventilation", "icu sedation"],
            "word": []
        },
        "Pain Medicine": {
            "mesh_exact": ["pain, postoperative", "acute pain", "chronic pain"],
            "phrase": ["opioid sparing", "opioid-free", "multimodal analgesia"],
            "word": []
        },
        "Anesthesia Safety": {
            "mesh_exact": ["malignant hyperthermia", "postoperative nausea and vomiting", "anaphylaxis", "intraoperative complications"],
            "phrase": ["malignant hyperthermia"],
            "word": []
        },
        "Pharmacology - Opioids Propofol Ketamine NMB": {
            "mesh_exact": ["propofol", "ketamine", "analgesics, opioid", "neuromuscular blocking agents", "sugammadex"],
            "phrase": ["neuromuscular blocking"],
            "word": []
        },
        "ERAS Perioperative": {
            "mesh_exact": ["perioperative care", "preoperative care"],
            "phrase": ["enhanced recovery after surgery", "enhanced recovery", "prehabilitation", "blood management", "tranexamic acid"],
            "word": []
        },
        "AI Simulation Education": {
            "mesh_exact": ["artificial intelligence", "machine learning", "deep learning", "simulation training"],
            "phrase": ["virtual reality", "simulation training"],
            "word": []
        }
    }
    
    for domain, rules in checks.items():
        matched = False
        
        # Exact MeSH descriptor matching - avoids substring FP
        for mesh_want in rules["mesh_exact"]:
            if mesh_want in mesh_set:
                matched = True
                break
        
        # Phrase matching (multi-word, substring OK for phrases)
        if not matched:
            for phrase in rules["phrase"]:
                if phrase in combined:
                    matched = True
                    break
        
        # Word boundary regex for short terms like "child" to avoid "childbirth" matching peds when it's obstetric
        if not matched:
            for pattern in rules["word"]:
                if re.search(pattern, combined):
                    # Additional guard: if term is child/infant but also has obstetric terms, prefer obstetric
                    if domain == "Pediatric Anesthesia" and any(o in combined for o in ["labor", "obstetric", "cesarean", "pregnancy"]):
                        # Check if truly pediatric vs obstetric neonate
                        if "pediatric anesthesia" in combined or "neonatal anesthesia" in combined:
                            matched = True
                        else:
                            # likely obstetric, skip pediatric
                            continue
                    else:
                        matched = True
                    break
        
        if matched:
            tags.append(domain)
    
    return tags or ["General Anesthesia"]

def main_fixed():
    parser = argparse.ArgumentParser(description="Fixed PubMed extraction - rate limit + WebEnv resume")
    parser.add_argument("--max-records", type=int, default=50000)
    parser.add_argument("--output", type=str, default="./anesthesia_corpus_fixed")
    parser.add_argument("--api-key", type=str, default=None)
    parser.add_argument("--agents", type=str, default="all")
    parser.add_argument("--batch-size", type=int, default=100, help="100 for XML stability")
    parser.add_argument("--email", type=str, default="anethassist@example.com")
    parser.add_argument("--checkpoint-dir", type=str, default="./checkpoints")
    args = parser.parse_args()
    
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    agent_list = list(AGENT_QUERIES.keys()) if args.agents == "all" else [int(x) for x in args.agents.split(",")]
    
    # Production client with correct rate limiting
    client = ProductionPubMedClient(
        api_key=args.api_key,
        email=args.email,
        checkpoint_dir=Path(args.checkpoint_dir)
    )
    
    all_records = []
    seen_pmids = set()
    
    # Save DDL for reference
    with open(out_dir / "rate_limit_fix_ddl_postgres.sql", "w") as f:
        f.write(POSTGRES_RATE_LIMIT_DDL)
    with open(out_dir / "rate_limit_fix_ddl_bigquery.sql", "w") as f:
        f.write(BIGQUERY_RATE_LIMIT_DDL)
    
    for agent_id in agent_list:
        query = AGENT_QUERIES[agent_id]
        print(f"\n[Agent {agent_id}] Fixed client - query: {query[:120]}...")
        
        def batch_callback(batch_records, retstart):
            # Classify and dedup in callback
            for rec in batch_records:
                if rec["pmid"] in seen_pmids:
                    rec["extraction_metadata"]["dedup_status"] = "duplicate_type_I"
                    continue
                rec["anesthesia_subdomains"] = classify_subdomains_fixed(rec)
                rec["extraction_metadata"]["query_used"] = query
                rec["extraction_metadata"]["agent_id"] = agent_id
                rec["extraction_metadata"]["retrieval_date"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                seen_pmids.add(rec["pmid"])
                all_records.append(rec)
        
        try:
            # This handles WebEnv expiration automatically with re-esearch resume
            records = client.fetch_with_auto_resume(
                term=query,
                agent_id=agent_id,
                max_records=args.max_records,
                batch_size=args.batch_size,
                output_callback=batch_callback
            )
            print(f"Agent {agent_id} done: {len(all_records)} total unique so far")
            
        except Exception as e:
            print(f"Agent {agent_id} failed: {e}")
            # Checkpoint preserved for resume
            continue
    
    print(f"\nTotal unique: {len(all_records)}")
    print(f"Rate limiter stats: {client.rate_limiter.get_stats()}")
    
    # Save JSONL
    with open(out_dir / "anesthesia_full_metadata.jsonl", "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    
    # Save CSV
    import csv
    with open(out_dir / "anesthesia_full_metadata.csv", "w", newline="", encoding="utf-8") as cf:
        writer = csv.DictWriter(cf, fieldnames=[
            "pmid","doi","pmcid","title","year","journal_title","volume","pages",
            "publication_types","mesh_terms_pipe","subdomains_pipe","study_type",
            "authors_pipe","n_authors","abstract_first_500","query_used","agent_id","dedup_status"
        ])
        writer.writeheader()
        for r in all_records:
            writer.writerow({
                "pmid": r["pmid"],
                "doi": r["doi"],
                "pmcid": r["pmcid"],
                "title": r["title"],
                "year": r["publication_date"]["year"],
                "journal_title": r["journal"]["title"],
                "volume": r["journal"]["volume"],
                "pages": r["journal"]["pages"],
                "publication_types": "|".join(r["publication_types"]),
                "mesh_terms_pipe": "|".join([m["descriptor_name"] for m in r["mesh_terms"]][:15]),
                "subdomains_pipe": "|".join(r["anesthesia_subdomains"]),
                "study_type": r["study_design"]["type"],
                "authors_pipe": "|".join([f"{a['last_name']} {a['initials']}" for a in r["authors"][:6]]),
                "n_authors": len(r["authors"]),
                "abstract_first_500": (r["abstract"] or "")[:500].replace("\n"," "),
                "query_used": r["extraction_metadata"]["query_used"][:300],
                "agent_id": r["extraction_metadata"]["agent_id"],
                "dedup_status": r["extraction_metadata"]["dedup_status"]
            })
    
    print(f"Saved to {out_dir}")

if __name__ == "__main__":
    main_fixed()
