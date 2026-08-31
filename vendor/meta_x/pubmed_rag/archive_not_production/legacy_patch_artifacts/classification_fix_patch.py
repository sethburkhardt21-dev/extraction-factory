
"""
Patch for pubmed_extraction_pipeline.py - replace classify_subdomains with fixed version
Usage: from classification_fix_patch import classify_subdomains_fixed
"""

import sys
sys.path.insert(0, '/mnt/data')
from classification_fix_module import classify_subdomains_fixed as _fixed

def classify_subdomains(record):
    # wrapper maintaining original signature but using fixed logic
    return _fixed(record)

# Also export scoring version for DB insert
def classify_with_scores(record):
    return _fixed(record, return_scores=True)
