
# Agent B8 - Classification Fix Developer - Production Deliverables

## Overview
Fixes critical classification false positives in PubMed anesthesia subdomain tagging.

### Audit Issues Addressed
- **CRITICAL-04**: Substring FP - `k in combined` matches child inside children, education inside patient education, tap inside water tap
- **CRITICAL-07**: MeSH major topic weighting missing - all terms equal
- **HIGH-02**: Education trap - "education" keyword tags ANY patient education as AI Simulation Education
- **MED-01**: Short token FP - BIS, TAP, TEE, CPB, ERAS matched via lowercased substring

## Files Generated

### 1. Python Module: classification_fix_module.py
- Location: /mnt/data/classification_fix_module.py
- Production-ready, O(160 regex/record), pre-compiled patterns
- Key fix: `re.compile(r"\bchild\b", IGNORECASE)` distinct from `\bchildren\b`
- MeSH weighting: major 3.0, minor 1.5, TIAB 1.0, title boost 1.2, threshold 1.5
- Education guard: requires anesthesia co-occurrence, excludes patient/health education
- Short token strict: `r"\bTAP\b"` case-sensitive + water tap negative
- Function: `classify_subdomains_fixed(record, threshold=1.5, return_scores=False)` drop-in replace for original `classify_subdomains`

### 2. Postgres DDL: classification_fix_postgres.sql
- Location: /mnt/data/classification_fix_postgres.sql
- Tables: anesthesia_pubmed (JSONB), anesthesia_classification_scores (scored per domain)
- Functions:
  - fn_has_word_boundary() using \m \M (Postgres word boundaries)
  - fn_is_pediatric_text() with \b child/children separation
  - fn_is_anesthesia_education() with trap guard
  - fn_has_strict_acronym() for TAP/BIS/TEE
  - fn_mesh_weight() major 3.0 minor 1.5
- Views: v_classification_scoring, v_anesthesia_final_tags

### 3. BigQuery DDL: classification_fix_bigquery.sql
- Location: /mnt/data/classification_fix_bigquery.sql
- Same logic in BigQuery Standard SQL
- REGEXP_CONTAINS with r'\bchild\b' vs r'\bchildren\b' distinct
- Strict uppercase TAP via r'\bTAP\b' (no (?i))
- Education trap: NOT REGEXP_CONTAINS patient education unless simulation/AI present
- Materialized table anesthesia_classification_scores clustered by domain

### 4. Patch Wrapper: classification_fix_patch.py
- Location: /mnt/data/classification_fix_patch.py
- Drop-in import for pubmed_extraction_pipeline.py: `from classification_fix_patch import classify_subdomains`

### 5. Validation Report: classification_fix_validation_report.md
- Location: /mnt/data/classification_fix_validation_report.md

## Validation Results (from python run)

Test1 children paper: tags Pediatric correctly via \bchildren\b - PASS
Test2 childhood obesity: does NOT FP to pediatric via \bchild\b boundary - PASS
Test3 patient education trap: NOT tagged AI Education - PASS
Test4 valid AI anesthesia education: tags AI Education - PASS
Test5 water tap: NOT tagged PNB - PASS (strict upper + water exclusion)
Test6 TAP valid block: tags PNB - PASS
Test7 MeSH major vs minor weighting visible (major 3.0)

## Integration Instructions

Replace in pubmed_extraction_pipeline.py line 285-312:

```python
# OLD (buggy):
def classify_subdomains(record):
    ...
    if any(k in combined for k in keywords): tags.append(domain)

# NEW:
from classification_fix_module import classify_subdomains_fixed as classify_subdomains
# or
import sys; sys.path.insert(0, '/mnt/data')
from classification_fix_module import classify_subdomains_fixed

# Then in main:
rec["anesthesia_subdomains"] = classify_subdomains_fixed(rec)
# For DB:
tags, scores, evidences = classify_subdomains_fixed(rec, return_scores=True)
```

Postgres migration note:
- Python \b -> Postgres \m \M
- Python re.IGNORECASE -> Postgres ~* operator
- Python case-sensitive TAP -> Postgres ~ operator

BigQuery migration note:
- Same \b regex, use r'\bTAP\b' for strict
- Use (?i) prefix for case-insensitive

## Performance
- Pre-compiled 160 regex once at import
- 300k PubMed records => ~48M regex checks => <2 min Python, <30s BigQuery materialized view
- No catastrophic backtracking (all patterns \b + literal)

## Next Steps for Swarm
- Agent B8 done; integrate with B1 (DOI normalization) and B3 (rate limit) for full pipeline
- Add embedding rerank for edge cases where TIAB ambiguous
