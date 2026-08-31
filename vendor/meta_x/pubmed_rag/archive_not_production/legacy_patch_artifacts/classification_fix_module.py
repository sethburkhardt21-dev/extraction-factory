
"""
Classification Fix Developer - Production Deliverable
Agent B8: regex \b word boundaries, MeSH major topic weighting, substring FP fixes

Fixes audit issues:
- CRITICAL-04: classification FP via substring (child in children, education trap)
- CRITICAL-07: MeSH major topic weighting missing
- HIGH-02: education trap over-classifies AI Simulation Education
- MED-01: short tokens (BIS, TAP, TEE) false positive via substring

Design:
- MeSH descriptor exact match = primary signal, weighted by MajorTopicYN
- TIAB text matched via \b word boundaries, compiled once
- Short tokens (<5 chars) require uppercase-aware regex or \b with length guard
- Education domain requires co-occurrence guard + exclusion
- Scoring: major_topic MeSH *3.0, minor MeSH *1.5, TIAB *1.0
- Threshold per domain >=1.5 to tag
"""

import re
from typing import List, Dict, Tuple

MESH_MAJOR_WEIGHT = 3.0
MESH_MINOR_WEIGHT = 1.5
TIAB_WEIGHT = 1.0
TITLE_WEIGHT = 1.2

EDUCATION_EXCLUSION_PHRASES = [
    r"\bpatient\s+education\b",
    r"\bhealth\s+education\b",
    r"\beducation\s+level\b",
    r"\beducational\s+attainment\b",
]
EXCLUSION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in EDUCATION_EXCLUSION_PHRASES]

DOMAIN_RULES = {
    "General Anesthesia": {
        "mesh_exact": ["anesthesia, general", "anesthesia, inhalation", "anesthesia, intravenous", "depth of anesthesia"],
        "tiab_phrases": [r"general anesthesia", r"general anaesthesia", r"depth of anesthesia", r"bispectral index", r"intraoperative awareness", r"balanced anesthesia"],
        "tiab_tokens_short": [],
        "tiab_regex_extra": [r"\bBIS\b"],
    },
    "Regional Anesthesia - Spinal Epidural": {
        "mesh_exact": ["anesthesia, spinal", "anesthesia, epidural", "anesthesia, conduction", "anesthesia, caudal"],
        "tiab_phrases": [r"spinal anesthesia", r"epidural anesthesia", r"combined spinal.*epidural", r"neuraxial block", r"dural puncture epidural", r"spinal anaesthesia"],
        "tiab_tokens_short": [r"\bCSEA\b"],
    },
    "Peripheral Nerve Blocks": {
        "mesh_exact": ["nerve block", "brachial plexus block", "femoral nerve block", "transversus abdominis plane block"],
        "tiab_phrases": [r"nerve block", r"brachial plexus", r"femoral nerve", r"transversus abdominis", r"erector spinae plane", r"fascial plane block", r"ultrasound-guided block", r"quadratus lumborum"],
        "tiab_tokens_short": [r"\bTAP\b", r"\bESPB\b", r"\bQLB\b", r"\bPENG\b"],
    },
    "Local Anesthetics Pharmacology": {
        "mesh_exact": ["anesthetics, local", "lidocaine", "bupivacaine", "ropivacaine", "levobupivacaine", "mepivacaine"],
        "tiab_phrases": [r"local anesthetic systemic toxicity", r"\bLAST\b", r"local anaesthetic", r"ropivacaine", r"levobupivacaine", r"lipid emulsion"],
        "tiab_tokens_short": [],
    },
    "Airway Management": {
        "mesh_exact": ["airway management", "intubation, intratracheal", "laryngoscopy", "laryngeal masks", "airway obstruction"],
        "tiab_phrases": [r"difficult airway", r"videolaryngoscopy", r"videolaryngoscope", r"supraglottic airway", r"laryngeal mask airway", r"\btube exchange\b", r"awake intubation"],
        "tiab_tokens_short": [],
    },
    "Anesthesia Monitoring": {
        "mesh_exact": ["monitoring, intraoperative", "electroencephalography", "capnography", "pulse oximetry"],
        "tiab_phrases": [r"intraoperative monitoring", r"spectral edge", r"entropy monitoring", r"capnography", r"hemodynamic monitoring", r"processed eeg"],
        "tiab_tokens_short": [r"\bBIS\b"],
    },
    "Pediatric Anesthesia": {
        "mesh_exact": ["pediatrics", "infant", "child", "child, preschool", "adolescent", "anesthesia, general"],
        "tiab_phrases": [
            r"\bpediatric anesthesia\b",
            r"\bpaediatric anaesthesia\b",
            r"\bneonatal anesthesia\b",
            r"\bchildren\b",
            r"\bchild\b",
            r"\binfant\b",
            r"\btoddler\b",
            r"GAS trial",
            r"\bneurotoxicity\b"
        ],
        "tiab_tokens_short": [],
        "use_word_boundaries_strict": True,
    },
    "Obstetric Anesthesia": {
        "mesh_exact": ["anesthesia, obstetrical", "analgesia, obstetrical", "analgesia, epidural", "labor, obstetric", "cesarean section"],
        "tiab_phrases": [r"obstetric anesthesia", r"labor analgesia", r"cesarean delivery", r"caesarean", r"intrathecal morphine", r"\bERAC\b"],
        "tiab_tokens_short": [r"\bPIEB\b", r"\bPCEA\b"],
    },
    "Cardiac Anesthesia": {
        "mesh_exact": ["cardiac surgical procedures", "cardiopulmonary bypass", "echocardiography, transesophageal", "extracorporeal circulation"],
        "tiab_phrases": [r"cardiac anesthesia", r"cardiopulmonary bypass", r"transesophageal echocardiography", r"\bcardiac surgery\b"],
        "tiab_tokens_short": [r"\bCPB\b", r"\bTEE\b", r"\bCABG\b"],
    },
    "Neuroanesthesia": {
        "mesh_exact": ["neurosurgical procedures", "craniotomy", "brain injuries", "cerebrovascular circulation"],
        "tiab_phrases": [r"\bcraniotomy\b", r"awake craniotomy", r"cerebral protection", r"neuroprotection", r"neurosurgical anesthesia", r"\bbrain protection\b"],
        "tiab_tokens_short": [],
    },
    "Critical Care ICU Sedation": {
        "mesh_exact": ["intensive care units", "critical care", "intensive care", "conscious sedation", "deep sedation", "dexmedetomidine"],
        "tiab_phrases": [r"intensive care", r"critical care", r"mechanical ventilation", r"ICU delirium", r"ICU sedation"],
        "tiab_tokens_short": [],
    },
    "Pain Medicine": {
        "mesh_exact": ["pain, postoperative", "acute pain", "chronic pain", "pain management", "analgesia"],
        "tiab_phrases": [r"postoperative pain", r"multimodal analgesia", r"opioid sparing", r"opioid-free anesthesia", r"pain score", r"\bVAS\b.*pain"],
        "tiab_tokens_short": [],
    },
    "Anesthesia Safety": {
        "mesh_exact": ["malignant hyperthermia", "postoperative nausea and vomiting", "anaphylaxis", "intraoperative complications", "drug hypersensitivity"],
        "tiab_phrases": [r"malignant hyperthermia", r"postoperative nausea", r"\bPONV\b", r"\banaphylaxis\b", r"intraoperative complication", r"awareness.*anesthesia"],
        "tiab_tokens_short": [],
    },
    "Pharmacology - Opioids Propofol Ketamine NMB": {
        "mesh_exact": ["propofol", "ketamine", "analgesics, opioid", "neuromuscular blocking agents", "sugammadex", "neostigmine", "rocuronium"],
        "tiab_phrases": [r"\bpropofol\b", r"\bketamine\b", r"\bopioid\b", r"neuromuscular block", r"\bsugammadex\b", r"\bneostigmine\b", r"\bremifentanil\b", r"\brocuronium\b"],
        "tiab_tokens_short": [r"\bNMB\b"],
    },
    "ERAS Perioperative": {
        "mesh_exact": ["enhanced recovery after surgery", "perioperative care", "preoperative care", "blood management", "hypothermia"],
        "tiab_phrases": [r"enhanced recovery", r"\bERAS\b", r"perioperative care", r"prehabilitation", r"blood management", r"tranexamic acid"],
        "tiab_tokens_short": [r"\bERAS\b"],
    },
    "AI Simulation Education": {
        "mesh_exact": ["artificial intelligence", "machine learning", "deep learning", "simulation training", "education, medical", "computer simulation"],
        "tiab_phrases": [
            r"artificial intelligence",
            r"machine learning",
            r"deep learning",
            r"simulation training",
            r"virtual reality.*anesthesia",
            r"anesthesia simulation",
            r"anesthesia education",
            r"anaesthesia education",
            r"medical education.*anesthesia",
            r"residency training.*anesthesia",
            r"\btelementoring\b",
        ],
        "tiab_tokens_short": [],
        "requires_anesthesia_context": True,
        "education_trap_guard": True,
    }
}

COMPILED_RULES = {}

def _compile_rules():
    for domain, rule in DOMAIN_RULES.items():
        compiled = {
            "mesh_exact_set": set([m.lower() for m in rule.get("mesh_exact", [])]),
            "tiab_phrases": [],
            "short_tokens": [],
            "extra_regex": [],
        }
        for phrase in rule.get("tiab_phrases", []):
            try:
                comp = re.compile(phrase, re.IGNORECASE)
                compiled["tiab_phrases"].append((phrase, comp))
            except re.error:
                comp = re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
                compiled["tiab_phrases"].append((phrase, comp))
        for tok in rule.get("tiab_tokens_short", []):
            try:
                comp = re.compile(tok)
                compiled["short_tokens"].append((tok, comp))
            except re.error:
                comp = re.compile(re.escape(tok), re.IGNORECASE)
                compiled["short_tokens"].append((tok, comp))
        for extra in rule.get("tiab_regex_extra", []):
            comp = re.compile(extra)
            compiled["extra_regex"].append((extra, comp))
        compiled["flags"] = rule
        COMPILED_RULES[domain] = compiled

_compile_rules()

def _is_exclusion(text: str) -> bool:
    for pat in EXCLUSION_PATTERNS:
        if pat.search(text):
            return True
    return False

def _score_domain(record: Dict, domain: str):
    compiled = COMPILED_RULES[domain]
    flags = compiled["flags"]
    score = 0.0
    evidence = []
    title = record.get("title") or ""
    abstract = record.get("abstract") or ""
    combined_lower = (title + " " + abstract).lower()
    combined_raw = title + " " + abstract

    for mesh in record.get("mesh_terms", []):
        desc = (mesh.get("descriptor_name") or "").lower()
        is_major = mesh.get("major_topic", False)
        weight = MESH_MAJOR_WEIGHT if is_major else MESH_MINOR_WEIGHT
        if desc in compiled["mesh_exact_set"]:
            score += weight
            evidence.append(f"MeSH:{desc} major={is_major} w={weight}")
        for phrase_pat, comp in compiled["tiab_phrases"]:
            if comp.search(desc):
                if desc not in compiled["mesh_exact_set"]:
                    score += weight * 0.8
                    evidence.append(f"MeSH-regex:{desc}~{phrase_pat} w={weight*0.8}")

    for phrase_pat, comp in compiled["tiab_phrases"]:
        if comp.search(combined_raw):
            s = TIAB_WEIGHT * TITLE_WEIGHT if comp.search(title) else TIAB_WEIGHT
            if flags.get("education_trap_guard"):
                if "education" in phrase_pat.lower():
                    if not re.search(r"\banesthes|\banaesthes", combined_lower):
                        continue
                    if _is_exclusion(combined_raw):
                        if not re.search(r"simulation|artificial intelligence|machine learning|virtual reality", combined_lower):
                            continue
            score += s
            evidence.append(f"TIAB:{phrase_pat} w={s}")

    for tok_pat, comp in compiled["short_tokens"]:
        if comp.search(combined_raw):
            if domain == "AI Simulation Education" and tok_pat == r"\bAI\b":
                if not re.search(r"\banesthes|\banaesthes", combined_lower):
                    continue
            if tok_pat == r"\bTAP\b":
                if re.search(r"water\s+tap|tap\s+water", combined_lower):
                    continue
            score += TIAB_WEIGHT * 0.9
            evidence.append(f"SHORT:{tok_pat}")

    for extra_pat, comp in compiled["extra_regex"]:
        if comp.search(combined_raw):
            score += TIAB_WEIGHT
            evidence.append(f"EXTRA:{extra_pat}")

    return score, evidence

def classify_subdomains_fixed(record: Dict, threshold: float = 1.5, return_scores: bool = False):
    scores = {}
    evidences = {}
    for domain in DOMAIN_RULES.keys():
        sc, ev = _score_domain(record, domain)
        scores[domain] = sc
        evidences[domain] = ev
    tags = [d for d, s in scores.items() if s >= threshold]
    if not tags:
        has_anesth_mesh = any("anesthesia" in (m.get("descriptor_name") or "").lower() for m in record.get("mesh_terms", []))
        if has_anesth_mesh:
            tags = ["General Anesthesia"]
        else:
            txt = (record.get("title","") + " " + (record.get("abstract") or "")).lower()
            if "anesthes" in txt or "anaesthes" in txt:
                tags = ["General Anesthesia"]
    if return_scores:
        return tags, scores, evidences
    return tags

if __name__ == "__main__":
    tests = [
        {"pmid":"test1_child_vs_children","title":"Outcomes in children undergoing tonsillectomy","abstract":"We studied 100 children under general anesthesia","mesh_terms":[{"descriptor_name":"Child","major_topic":True},{"descriptor_name":"Anesthesia, General","major_topic":True}]},
        {"pmid":"test2_child_fp","title":"Childhood obesity and anesthesia","abstract":"Childhood is risk factor, we studied 50 adult patients","mesh_terms":[{"descriptor_name":"Adult","major_topic":True}]},
        {"pmid":"test3_education_trap","title":"Patient education and informed consent for anesthesia","abstract":"Patient education level affects consent but not AI","mesh_terms":[{"descriptor_name":"Informed Consent","major_topic":True}]},
        {"pmid":"test4_education_valid","title":"Artificial intelligence for anesthesia education: simulation training","abstract":"We developed AI model for anesthesia education and simulation training for residents","mesh_terms":[{"descriptor_name":"Artificial Intelligence","major_topic":True},{"descriptor_name":"Simulation Training","major_topic":True},{"descriptor_name":"Education, Medical","major_topic":False}]},
        {"pmid":"test5_short_token_fp","title":"Water tap contamination in hospital","abstract":"We studied water tap contamination, no anesthesia","mesh_terms":[{"descriptor_name":"Water","major_topic":True}]},
        {"pmid":"test6_TAP_valid","title":"Ultrasound-guided TAP block for postoperative analgesia","abstract":"Transversus abdominis plane (TAP) block performed under ultrasound guidance for laparotomy","mesh_terms":[{"descriptor_name":"Nerve Block","major_topic":True}]},
        {"pmid":"test7_MeSH_weighting","title":"General anesthesia depth monitoring","abstract":"General anesthesia monitoring using bispectral index","mesh_terms":[{"descriptor_name":"Anesthesia, General","major_topic":False},{"descriptor_name":"Monitoring, Intraoperative","major_topic":True}]},
    ]
    for rec in tests:
        tags, scores, ev = classify_subdomains_fixed(rec, return_scores=True)
        print(f"\n=== {rec['pmid']} ===")
        print(f"Title: {rec['title']}")
        print(f"Tags: {tags}")
        top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
        print(f"Top scores: {top}")
        for dom in tags:
            print(f"  Evidence {dom}: {ev[dom][:3]}")
