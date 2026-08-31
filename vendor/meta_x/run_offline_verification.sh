#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Meta Extraction Repaired v1 — offline verification"
echo "root=$ROOT"
echo

echo "[1/8] Production Python compile"
python - "$ROOT" <<'PY'
from pathlib import Path
import py_compile, sys
root=Path(sys.argv[1])
files=[]
for p in root.rglob('*.py'):
    if 'archive_not_production' in p.parts or '__pycache__' in p.parts:
        continue
    files.append(p)
    py_compile.compile(str(p), doraise=True)
print(f"PASS: {len(files)} active Python files compiled")
PY

echo "[2/8] ClinicalTrials regression"
(cd "$ROOT/clinicaltrials" && python -m pytest -q tests/test_offline.py)

echo "[3/8] medRxiv/bioRxiv regression"
(cd "$ROOT/preprints" && python -m pytest -q tests/test_offline.py)

echo "[4/8] Drug reference regression"
(cd "$ROOT/drug_reference" && python -m pytest -q tests/test_offline.py)

echo "[5/8] PubMed/RAG regression"
(cd "$ROOT/pubmed_rag" && python -m pytest -q c5_validation_tests.py bigquery_validation_test.py tests/test_repaired_invariants.py)

echo "[6/8] PubMed validators"
(cd "$ROOT/pubmed_rag" && python validate.py && python validate_pipeline.py)

echo "[7/8] Static production safety checks"
python - "$ROOT" <<'PY'
from pathlib import Path
import re, sys
root=Path(sys.argv[1])
errors=[]
for p in root.rglob('*.py'):
    if 'archive_not_production' in p.parts or 'tests' in p.parts or '__pycache__' in p.parts:
        continue
    text=p.read_text(errors='replace')
    checks={
        '/mnt/data hard-code': r'/mnt/data',
        'fake contact': r'(?:research@example\.edu|anesthesia\.pipeline@example\.com|ragpipeline@example\.com|anethassist@example\.com|anesthesia-pipeline@example\.com)',
        'unsafe Python hash ID': r'\brxcu[iI]\w*\s*=\s*(?:str\()?hash\(',
    }
    for label, pat in checks.items():
        if re.search(pat,text): errors.append(f"{p.relative_to(root)}: {label}")
shadow=[]
for p in root.rglob('*.py'):
    if 'archive_not_production' in p.parts: continue
    if re.search(r'_(?:1|2|1_1)\.py$',p.name): shadow.append(str(p.relative_to(root)))
if shadow: errors.extend(f"shadow active: {x}" for x in shadow)
if errors:
    print('\n'.join(errors)); raise SystemExit(1)
print('PASS: no banned active paths/fake contacts/fabricated RxNorm hash IDs/shadow Python variants')
PY

echo "[8/8] Canonical package import"
(cd "$(dirname "$ROOT")" && python - <<'PY'
import sys
sys.path.insert(0,'.')
import Meta_Extraction_Repaired_v1.pubmed_rag as pkg
print('PASS: PubMed/RAG package import')
PY
) || (
  cd "$ROOT/.." && python - <<'PY'
import sys
sys.path.insert(0,'.')
import importlib.util
# Directory name is not intended as a Python package; validate pubmed_rag directly.
sys.path.insert(0,'Meta_Extraction_Repaired_v1')
import pubmed_rag
print('PASS: PubMed/RAG package import')
PY
)

echo
echo "OFFLINE REPAIR CERTIFICATION: PASS"
echo "External network/source/database/model certification: NOT RUN by this script"
