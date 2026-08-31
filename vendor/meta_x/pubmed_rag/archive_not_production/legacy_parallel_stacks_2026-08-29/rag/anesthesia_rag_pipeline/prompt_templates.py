"""
RAG Prompt Templates for Anesthesia Clinical Q&A
Best practices:
- Strict grounding with citations [PMID:xxx]
- Step-back / query transform for clinical questions
- Safety disclaimer, refusal when no evidence
- Anesthesia-specific context: ASA, dosing, contraindications, airway
- Structured output with citations, confidence, evidence tier
"""
from typing import List, Dict, Any

# --- System prompts ---

RAG_SYSTEM_PROMPT = """You are an expert anesthesiologist assistant powering a Retrieval-Augmented Generation system grounded in PubMed literature.

STRICT GROUNDING RULES:
1. Answer ONLY from the provided context passages. Each passage has a PMID and citation.
2. Cite every factual claim using [PMID:xxxxx] or [DOI:xx] format. Group citations at end of sentence.
3. If context does NOT contain answer, say: "No relevant evidence found in the provided PubMed corpus for this query." Do NOT hallucinate.
4. Do NOT provide dosage recommendations without citing source and include safety note: dosing must be verified per local protocol.
5. Distinguish evidence tiers: core anesthesia journals > RCTs > observational > case reports.
6. Flag contraindications, drug interactions, and ASA classification when relevant.
7. Never extrapolate beyond humans unless context is animal study (then state limitation).

OUTPUT FORMAT:
- Clinical Answer: concise, 2-5 sentences per point, with inline citations
- Evidence Summary: bullet list of top 3 supporting studies with citation
- Confidence: high/medium/low based on number and quality of sources
- Disclaimer: "This is for educational purposes and does not constitute medical advice. Verify with primary literature and institutional guidelines."

Context relevance: The query was classified via PubMed MeSH and anesthesia-specific filters (propofol, sevoflurane, regional anesthesia, airway management, etc). Consider both title and abstract sections.
"""

QUERY_TRANSFORM_PROMPT = """You are a query rewriting expert for anesthesia PubMed retrieval.

Original question: {question}

Rewrite into 3 optimized PubMed queries:
1. Primary: formal MeSH + keywords for PubMed search
   Format: (anesthesia terms[MeSH or TIAB]) AND (clinical concept) AND (humans)
2. Expanded: synonyms and related anesthetics (e.g., propofol = 2,6-diisopropylphenol, sevoflurane = fluoromethyl)
3. Step-back: broader perioperative question to capture context (e.g., "What are the principles of...")

Return JSON:
{{
  "primary": "...",
  "expanded": "...",
  "step_back": "...",
  "clinical_entities": ["..."],
  "intent": "drug_info|technique|complication|dosing|comparative|guideline"
}}

Use anesthesia vocabulary: general/regional/local anesthesia, induction, maintenance, emergence, ASA, MAC, BIS, neuromuscular blockade, airway.
"""

CLINICAL_QA_PROMPT_TEMPLATE = """Context: Below are PubMed abstracts retrieved for anesthesia question. Each starts with [PMID:xxx] identifier and metadata.

{context_str}

---
User Question: {question}
Patient Context (if any): {patient_context}
Question Intent: {intent}

Instructions:
- Provide answer grounded strictly in context above
- Use format:
  **Answer:** <grounded response with citations like [PMID:12345678]>
  **Evidence:** 
   - [PMID:12345678] Author et al, Journal Year: key finding
  **Confidence:** high/medium/low - explanation
  **Caveats:** limitations, contraindications, need for local verification
- If asked about dosing, include weight, renal/hepatic, age adjustments ONLY if in context
- For comparative questions (e.g., propofol vs sevoflurane), create table with pros/cons sourced from context
- Total answer length: {length_guidance}

{disclaimer}
"""

COT_CLINICAL_REASONING_PROMPT = """You are performing clinical reasoning for anesthesia.

Context passages:
{context_str}

Question: {question}

Think step-by-step internally (do not output chain-of-thought), then produce final answer:

Steps to consider internally:
1. What anesthesia sub-domain? (pharmacology, airway, regional, monitoring, complications, peds, OB)
2. Which passages are relevant? Score each 0-5
3. Is there consensus or conflicting evidence?
4. What is the level of evidence? (RCT, meta-analysis, observational, case series)
5. Any safety signals? (malignant hyperthermia, anaphylaxis, awareness)

Now produce final answer with citations.
"""

FACT_CHECK_PROMPT = """Given:

Answer claim: "{claim}"
Supporting passages:
{passages}

Is claim supported? Return JSON:
{{
  "supported": true/false,
  "faithfulness_score": 0.0-1.0,
  "supporting_pmids": [],
  "contradicting_pmids": [],
  "reason": ""
}}

Criteria:
- supported=true only if passage explicitly states claim or strong paraphrase
- faithfulness penalizes extrapolation beyond passage
"""

# --- Anesthesia-specific prompt library ---

ANESTHESIA_PROMPT_LIBRARY = {
    "drug_info": {
        "template": CLINICAL_QA_PROMPT_TEMPLATE,
        "length_guidance": "concise 150-250 words, focus on mechanism, indication, contraindication, dosing class if cited",
        "required_entities": ["drug name", "indication", "contraindication"]
    },
    "technique": {
        "template": CLINICAL_QA_PROMPT_TEMPLATE,
        "length_guidance": "stepwise technique description with indications, contraindications, monitoring, citations",
        "required_entities": ["indication", "contraindication", "complications"]
    },
    "complication": {
        "template": COT_CLINICAL_REASONING_PROMPT,
        "length_guidance": "include incidence from literature, risk factors, management, prevention - all cited",
        "required_entities": ["incidence", "risk factors", "management"]
    },
    "comparative": {
        "template": CLINICAL_QA_PROMPT_TEMPLATE,
        "length_guidance": "comparison table: Drug A vs Drug B - efficacy, onset, duration, side effects, cost if mentioned, ASA considerations. Provide recommendation only if evidence strong.",
        "required_entities": ["comparators", "outcomes"]
    },
    "pediatric": {
        "template": CLINICAL_QA_PROMPT_TEMPLATE,
        "length_guidance": "pediatric dosing weight-based, age-specific considerations, include disclaimer for pediatric",
        "required_entities": ["age range", "weight-based dosing", "pediatric risks"]
    },
    "obstetric": {
        "template": CLINICAL_QA_PROMPT_TEMPLATE,
        "length_guidance": "consider fetal considerations, uteroplacental flow, teratogenicity, labor analgesia specifics",
        "required_entities": ["fetal safety", "maternal safety"]
    }
}

def build_context_string(retrieved_docs: List[Dict[str, Any]], max_chars: int = 12000) -> str:
    """
    Build context string with citations preserved.
    Each doc includes metadata for grounding.
    """
    context_parts = []
    total_chars = 0
    for idx, doc in enumerate(retrieved_docs):
        meta = doc.get('metadata') or doc.get('parent_article') or {}
        pmid = meta.get('pmid') or doc.get('metadata', {}).get('pmid') or "unknown"
        title = meta.get('title','')[:200]
        journal = meta.get('journal','')
        year = meta.get('year','')
        tier = meta.get('tier','')
        text = doc.get('text','') or doc.get('abstract','')
        
        entry = f"[{idx+1}] [PMID:{pmid}] {title} | {journal} {year} | Tier:{tier}\n{text}\n---\n"
        if total_chars + len(entry) > max_chars:
            break
        context_parts.append(entry)
        total_chars += len(entry)
    
    return "\n".join(context_parts)

def get_prompt_for_intent(intent: str, question: str, context_str: str, patient_context: str = "None provided") -> str:
    """
    Selects appropriate prompt template based on intent classification.
    """
    library_entry = ANESTHESIA_PROMPT_LIBRARY.get(intent, ANESTHESIA_PROMPT_LIBRARY["drug_info"])
    template = library_entry["template"]
    length_guidance = library_entry["length_guidance"]
    
    disclaimer = "Disclaimer: This is for educational purposes and does not constitute medical advice. Verify with primary literature and institutional guidelines."
    
    prompt = template.format(
        context_str=context_str,
        question=question,
        patient_context=patient_context,
        intent=intent,
        length_guidance=length_guidance,
        disclaimer=disclaimer
    )
    return prompt

# --- Few-shot examples for grounding ---

FEW_SHOT_EXAMPLES = [
    {
        "question": "What is the induction dose of propofol for adults?",
        "context": "[1] [PMID:12345678] Propofol induction characteristics... induction dose 2-2.5 mg/kg IV in healthy adults...",
        "good_answer": "In healthy adults, propofol induction dose is 2-2.5 mg/kg IV [PMID:12345678]. Dose should be reduced in elderly, hypovolemic, and ASA III-IV patients.",
        "bad_answer": "Propofol dose is 2 mg/kg always." # missing citation, overgeneralization
    },
    {
        "question": "Is sevoflurane safe in patients with malignant hyperthermia susceptibility?",
        "context": "[1] [PMID:87654321] Sevoflurane is a trigger for MH... contraindicated in susceptible patients...",
        "good_answer": "No, sevoflurane is a known trigger for malignant hyperthermia and is contraindicated in susceptible patients [PMID:87654321]. Use total intravenous anesthesia.",
        "bad_answer": "Yes, sevoflurane is safe." # contradicts context - hallucination
    }
]
