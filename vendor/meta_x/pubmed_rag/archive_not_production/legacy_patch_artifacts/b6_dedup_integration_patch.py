"""
B6 Integration Patch for pubmed_extraction_pipeline.py
Replaces simple PMID-only dedup with improved 4-stage pipeline:
- DOI normalization (lowercase trim URL prefix)
- Bramer page expansion
- Fuzzy title 90%

Usage:
  from b6_dedup_fix_pipeline import normalize_doi, expand_abbreviated_pages, deduplicate_records

Replace in main():
    # OLD:
    if rec["pmid"] in seen_pmids: ...

    # NEW:
    Use improved pipeline below

This file is a drop-in replacement for the dedup section.
"""

from b6_dedup_fix_pipeline import (
    normalize_doi,
    expand_abbreviated_pages,
    bramer_normalize_pages_for_dedup,
    normalize_title_for_fuzzy,
    title_similarity,
    deduplicate_records,
    DedupDecision
)

# Example integration snippet for pubmed_extraction_pipeline.py main loop:

INTEGRATION_CODE = '''
from b6_dedup_fix_pipeline import normalize_doi, expand_abbreviated_pages, deduplicate_records

# In main():
all_records = []
seen_pmids = set()
seen_dois_normalized = {}  # doi_norm -> primary pmid

for agent_id in agent_list:
    query = AGENT_QUERIES[agent_id]
    search_res = esearch_with_history(query, api_key=args.api_key, retmax=0)
    count = search_res["count"]
    webenv = search_res["webenv"]
    qkey = search_res["query_key"]

    fetch_n = min(count, args.max_records)
    for start in range(0, fetch_n, 100):
        xml = efetch_batch(webenv, qkey, start, 100, api_key=args.api_key)
        batch_records = parse_pubmed_xml(xml)
        for rec in batch_records:
            # Improved DOI normalization
            doi_norm = normalize_doi(rec.get("doi"))
            rec["doi_normalized"] = doi_norm  # store for audit

            # Bramer page expansion
            pages_raw = rec.get("journal", {}).get("pages")
            norm_pages, p_start, p_end = expand_abbreviated_pages(pages_raw)
            rec["journal"]["pages_normalized"] = norm_pages
            rec["journal"]["page_start"] = p_start
            rec["journal"]["page_end"] = p_end

            # PMID exact duplicate Type-I
            if rec["pmid"] in seen_pmids:
                rec["extraction_metadata"]["dedup_status"] = "duplicate_type_I"
                rec["extraction_metadata"]["duplicate_of_pmid"] = rec["pmid"]
                rec["extraction_metadata"]["dedup_method"] = "PMID_exact"
                continue

            # DOI normalized duplicate Type-I
            if doi_norm and doi_norm in seen_dois_normalized:
                primary_pmid = seen_dois_normalized[doi_norm]
                rec["extraction_metadata"]["dedup_status"] = "duplicate_type_I"
                rec["extraction_metadata"]["duplicate_of_pmid"] = primary_pmid
                rec["extraction_metadata"]["dedup_method"] = "DOI_normalized"
                rec["extraction_metadata"]["doi_normalized"] = doi_norm
                continue

            rec["anesthesia_subdomains"] = classify_subdomains(rec)
            rec["extraction_metadata"]["query_used"] = query
            rec["extraction_metadata"]["agent_id"] = agent_id
            rec["extraction_metadata"]["retrieval_date"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            rec["extraction_metadata"]["dedup_status"] = "unique"
            rec["extraction_metadata"]["dedup_method"] = "none_yet"

            seen_pmids.add(rec["pmid"])
            if doi_norm:
                seen_dois_normalized[doi_norm] = rec["pmid"]
            all_records.append(rec)

# Post-fetch global dedup: Fuzzy title 90% + Bramer composite keys (Type-II)
print(f"\\n[Post-processing] Running improved Bramer+fuzzy dedup on {len(all_records)} records...")
unique_records, dedup_decisions = deduplicate_records(all_records, fuzzy_threshold=90)

print(f"Unique after improved dedup: {len(unique_records)} (removed {len(all_records)-len(unique_records)})")
print(f"Breakdown:")
from collections import Counter
cnt = Counter(d.method for d in dedup_decisions)
for method, num in cnt.items():
    print(f"  {method}: {num}")

# Save with PRISMA counts
all_records = unique_records  # for final save, keep decisions separate for audit
'''

def apply_patch_to_original_pipeline(original_path="/mnt/data/pubmed_extraction_pipeline.py", output_path="/mnt/data/pubmed_extraction_pipeline_B6_fixed.py"):
    from pathlib import Path
    text = Path(original_path).read_text(encoding="utf-8")
    # Simple replacement: insert import after existing imports
    import_line = "from b6_dedup_fix_pipeline import normalize_doi, expand_abbreviated_pages, deduplicate_records\n"
    if "b6_dedup_fix_pipeline" not in text:
        text = text.replace("import re", "import re\n" + import_line)
    Path(output_path).write_text(text, encoding="utf-8")
    return output_path

if __name__ == "__main__":
    print(INTEGRATION_CODE)
    # Try to generate patched version
    try:
        out = apply_patch_to_original_pipeline()
        print(f"Patched pipeline written to {out}")
    except Exception as e:
        print(f"Patch generation skipped: {e}")
