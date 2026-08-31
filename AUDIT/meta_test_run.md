# META extraction frontier v11 — executable audit

**Audit date:** 2026-08-31
**Target (read-only):** `C:\Users\sethb\.codex\.chatgpt-projects\g-p-6a22140cf3d08191bef2524866d4c6fe\extraction_factory\vendor\meta_x`
**Interpreter used for every run:** `C:\Users\sethb\.local\python\project09d-cpython-3.12.13\python.exe` with `-B`
**Network:** none attempted, none made. No package was installed.

## Read-only compliance statement

`frontier_preflight.py` **writes into its own root** (`FRONTIER_PREFLIGHT.json`, `FRONTIER_PREFLIGHT.txt`),
and the `physical_projection_contract` gate it invokes rewrites `schema/PHYSICAL_PROJECTION_CONTRACT.json`.
The canonical command therefore cannot be run without mutating the vendor tree.

Per the audit constraint, the entire tree (614 files, 6.6 MB) was copied to
`C:\Users\sethb\AppData\Local\Temp\claude\meta_audit_tmp\meta_x` and **every execution was performed
there**. The vendor tree was verified byte-identical before and after:

```
$ cp -r .../vendor/meta_x C:/Users/sethb/AppData/Local/Temp/claude/meta_audit_tmp/meta_x
COPY OK ; 614 files

$ diff -rq .../vendor/meta_x C:/Users/sethb/AppData/Local/Temp/claude/meta_audit_tmp/meta_x   # after preflight
Files .../FRONTIER_PREFLIGHT.json and meta_x/FRONTIER_PREFLIGHT.json differ
Files .../FRONTIER_PREFLIGHT.txt and meta_x/FRONTIER_PREFLIGHT.txt differ
Files .../schema/PHYSICAL_PROJECTION_CONTRACT.json and meta_x/schema/PHYSICAL_PROJECTION_CONTRACT.json differ
```

All three differences are in the temp copy only. Nothing under
`Project_09D_Database_Structure_Implementation`, `releases\`, `deliverables\`, `checkpoint_work\`,
or `handoff_inbox\` was read or written.

---

## 1. Canonical entry points

Identified from `README.md`, `FRONTIER_READINESS.md`, `OFFLINE_VERIFICATION.txt`,
`run_offline_verification.sh`, `frontier_preflight.py`, `frontier_orchestrator.py`.

| Role | Canonical artifact | Status |
| --- | --- | --- |
| **Canonical preflight** | `frontier_preflight.py` (no args) | Current. Writes `FRONTIER_PREFLIGHT.json` + `.txt`. 62 gates. |
| **Canonical test suite** | The 16 subprocess gates *inside* `frontier_preflight.py` — `python -m pytest -q` against `clinicaltrials/`, `preprints/`, `drug_reference/`, `pubmed_rag/`, `warehouse/tests`, `frontier_tests`, and six explicitly-partitioned `bridge_09d/tests` groups | Current. 320 unique tests claimed and reproduced. |
| **Canonical start command** (mass extraction) | Three-stage chain in `FRONTIER_READINESS.md` §"Next executable sequence": `frontier_preflight.py` → `frontier_orchestrator.py --mode canary --execute --preflight FRONTIER_PREFLIGHT.json` → `--mode full ... --canary-cert ...` | Current. Dry-run by default. |
| **Legacy verification script** | `run_offline_verification.sh` | **STALE — see §3.4.** Kept in the tree but superseded by `frontier_preflight.py`. |
| **Legacy verification output** | `OFFLINE_VERIFICATION.txt` | **STALE.** Header reads `root=/mnt/data/Meta_Extraction_Repaired_v1`; claims "70 active Python files" and suite counts 10/7/6/18. Current tree compiles 90 files under that script's own definition and the suites are 19/9/16/21. |

`README.md` is internally inconsistent about which turn this is: the top section says "v10 — 09D Turn 5",
a later section says "Current v5 status", and a "Turn 6 update" section follows. `09D_FRONTIER_EXTRACTION_STATE.md`
(which `README.md` names as authoritative) says **Turn 6**, `PASS_OFFLINE_IDENTITY_AND_COMPARATOR_CONTRACT`.
`FRONTIER_READINESS.md` is titled "v3" and reports "Production Python files: **38**" and manifest hash
`080faf6a…`, both of which are stale — the current preflight reports 58 production Python files, an
83-entry code/contract manifest, and hash `d9a3c508…`.

---

## 2. Code inventory

### 2.1 Production vs. reports vs. dead

`frontier_core/readiness.py:20` (`production_python_files`) is the machine-readable definition of
production code. It takes **58** files from five package roots plus four named `pubmed_rag` files, four
`frontier_core` files, and four top-level scripts, then excludes anything under
`archive_not_production`, `experimental_enrichment_not_certified`, `tests`, `__pycache__`, `.pytest_cache`.

**Three incompatible definitions of "production code" coexist in the tree:**

| Source | Count | Definition |
| --- | --- | --- |
| `frontier_core/readiness.py` → preflight | **58** py (+25 contract files = 83-entry manifest) | explicit allow-list of roots |
| `run_offline_verification.sh` step [1/8] | **90** py | everything except `archive_not_production` / `__pycache__` |
| `FRONTIER_READINESS.md` line 20 | **38** py | stale, matches nothing in the tree |

#### Production code (executable, in the manifest)

| Domain | Directory | Files |
| --- | --- | --- |
| Control plane | `frontier_core/` | `contracts.py`, `gate.py`, `readiness.py`, `__init__.py` |
| Control plane | root | `frontier_preflight.py`, `frontier_orchestrator.py`, `frontier_external_canary.py`, `frontier_release.py` |
| ClinicalTrials.gov | `clinicaltrials/canonical/` | `run_extraction.py`, `config.py`, `clinicaltrials/{client,extractor,models,parser,storage}.py`, `utils/rate_limiter.py` |
| Preprints | `preprints/src/` | `pipeline.py`, `run_all.py`, `medrxiv_biorxiv/{client,parser,storage}.py` |
| Drug reference | `drug_reference/drugref/` | `common.py`, `drugbank.py`, `linker.py`, `livertox.py`, `pipeline.py`, `rxnorm.py` |
| PubMed | `pubmed_rag/` | `metadata_schema.py`, `pubmed_anesthesia_extraction.py`, `run_pubmed.py`, `__init__.py` *(only these four are production)* |
| Warehouse | `warehouse/` | `project.py`, `__init__.py` |
| 09D bridge | `bridge_09d/` | 19 modules (see §2.2) |
| Contracts (non-py, hashed) | `schema/`, `bridge_09d/contracts/`, root | 8 schema/contract files + 15 `*_CONTRACT.md` + `09D_READONLY_AUTHORITY.json` + `09D_EXTRACTION_BOUNDARY_CONTRACT.md` + both lock files |

#### Reports / evidence (not code)

24 top-level `TURN*`/`REPAIR_REPORT`/`FRONTIER_*`/`EMPIRICAL_*`/`09D_*` `.md`/`.json` files, plus
`evidence/` — 30+ subdirectories of frozen sample runs and fault-injection captures. Three Python files
live under `evidence/fault_injection/` (`run_local_http_certification.py`,
`run_native_path_local_certification.py`, `run_relational_smoke.py`); they import `requests`, are **not**
in the production manifest, and are **not** invoked by the preflight.

#### Explicitly dead material

Everything dead is under `pubmed_rag/`. Each directory carries its own `README.md` marker.

| Directory | Contents | What the marker says |
| --- | --- | --- |
| `archive_not_production/` (root) | `anesthesia_extraction_pipeline.py.disabled.txt`, `embedding_backfill.py.disabled.txt` | "retained as inert `.txt` lineage evidence only… not importable production code because they contained synthetic/placeholder data behavior" |
| `archive_not_production/superseded_entrypoints/` | `anesthesia_pubmed_extractor.py`, `anesthesia_schema.py`, `c5_embedding_eval_pipeline_fixed.py`, `pubmed_extraction_pipeline_fixed.py` | "**not production entrypoints**… would create multiple competing extraction surfaces if left active" |
| `archive_not_production/legacy_parallel_stacks_2026-08-29/` | 35 py across `python/`, `rag/anesthesia_rag_pipeline/`, `sql/` — includes `pubmed_client.py`, `pubmed_client_hardened.py`, `ingestion_pipeline.py`, `incremental_update_pipeline.py`, `production_pipeline.py`, `embedding_engine.py`, `vector_store.py`, `api_server.py`, `c5_validation_tests.py`, `validate_pipeline.py` | "competing extraction/storage/RAG implementations, capped/silent-partial extraction behavior, model-coupled source ingestion… **not** part of frontier extraction certification" |
| `archive_not_production/legacy_patch_artifacts/` | 5 py + 6 md | "retained for lineage/history only… not supported production entrypoints" |
| `archive_not_production/legacy_docs/` | 5 md | "stale paths, old rate-limit claims, synthetic/demo assumptions… Do not use it as operational guidance" |
| `archive_not_production/untrusted_generated_artifacts/` | demo corpora + `index/` | "**Forbidden use:** loading into a production corpus, clinical knowledge base, vector index, analytics table, or as evidence that PubMed extraction/embedding succeeded" |
| `experimental_enrichment_not_certified/` | `pubmedbert_embedding_pipeline.py` (imports `numpy`), `requirements.txt` | "deliberately outside the active extraction surface… retained here for lineage only" |

> **Defect — the archive marker contradicts the active validator.**
> `pubmed_rag/archive_not_production/superseded_entrypoints/README.md` ends by naming the canonical paths:
> *"Canonical full PubMed extraction: `../../production_pipeline.py` + `../../pubmed_anesthesia_extraction.py`.
> Canonical incremental PubMed path: `../../incremental_update_pipeline.py` + `../../pubmed_client_hardened.py`."*
> All three of `production_pipeline.py`, `incremental_update_pipeline.py`, `pubmed_client_hardened.py`
> are **absent** from `pubmed_rag/`, and `pubmed_rag/validate.py:12-19` lists all three in
> `FORBIDDEN_ACTIVE` — the active `pubmed_source_validator` gate **fails** if they exist. The archive
> README points at files the certification gate forbids.

### 2.2 Actual executable production path, by capability

| Capability | Executable path | Notes |
| --- | --- | --- |
| **Source acquisition — CTG** | `clinicaltrials/canonical/run_extraction.py` → `canonical/clinicaltrials/{client,extractor,parser,models,storage}.py` | Only source with a `--bulk` official-ZIP path. Orchestrated. |
| **Source acquisition — PubMed** | `pubmed_rag/run_pubmed.py` → `pubmed_rag/pubmed_anesthesia_extraction.py` (sole active E-utilities client) + `metadata_schema.py` (pydantic) | Orchestrated. Requires real `--email`. |
| **Source acquisition — preprints** | `preprints/src/pipeline.py` (single interval) and `preprints/src/run_all.py` (sharded) → `medrxiv_biorxiv/{client,parser,storage}.py` | Orchestrated. Requires real `--contact-email`. |
| **Source acquisition — drug reference** | `drug_reference/drugref/pipeline.py::main` | **Not orchestrated.** `frontier_orchestrator.py:127` restricts `--source` to `{ctg, pubmed, medrxiv, biorxiv}`. Drug reference consumes pre-fetched, hash-pinned sidecar inputs only. |
| **Source units / segmentation** | `bridge_09d/source_units.py` (573 lines) | Real JATS/XML segmenter. `segment_jats_xml`, `segment_pubmed_abstract`, `segment_structured_json`, `segment_monograph_text`, `segment_pubmed_evidence`, `segment_preprint_evidence`, `segment_clinicaltrials_evidence`, `segment_artifact_jats`. Also owns rights (`rights_decision`, `_license_code_from_jats`) and full-text acquisition (`acquire_http_fulltext`, `acquire_pmc_oai_fulltext`). |
| **Assertion engine** | `bridge_09d/assertion_engine.py` + persistence `bridge_09d/assertion_pipeline.py` | See §6.1. |
| **Blind recall** | `bridge_09d/blind_recall.py` + persistence `bridge_09d/blind_recall_pipeline.py` | See §6.2. |
| **Semantic capsules / factory** | `bridge_09d/semantic_capsules.py` (450 lines, the real logic) → `bridge_09d/verifier.py` → composed by `bridge_09d/semantic_factory.py::run_semantic_factory`, routed by `bridge_09d/semantic_router.py` | See §6.3. |
| **Verifier** | `bridge_09d/verifier.py` (canonical) + `bridge_09d/verifier_pipeline.py` (persistence). `bridge_09d/assertion_verifier.py` and `bridge_09d/verification_pipeline.py` are 6- and 8-line `from … import *` compatibility shims. | See §6.4. |
| **09D comparator** | `bridge_09d/comparator_09d.py` (309 lines) + `bridge_09d/identity_resolution.py` (211 lines), composed by `bridge_09d/turn6_factory.py::run_turn6_audit_prep` (41 lines) | Read-only SQLite via `mode=ro&immutable=1` + `PRAGMA query_only=ON`, hash-pinned. **Never executed against the real 09D database** — see §6.5. |
| **Warehouse projection** | `warehouse/project.py::project_run` → `project_ctg` / `project_pubmed` / `project_preprint` / `project_drug` | Invoked automatically by the orchestrator after a completed source run. |

---

## 3. Canonical test suite on the locked interpreter

### 3.1 Interpreter capability

```
$ "C:/Users/sethb/.local/python/project09d-cpython-3.12.13/python.exe" -B -c "import sys; print(sys.version)"
3.12.13 (main, May 10 2026, 19:35:37) [MSC v.1944 64 bit (AMD64)]

$ ... -B -m pip list
Package    Version
---------- -------
pip        26.1.1
setuptools 83.0.0

$ ... -B -c "import pytest"
ModuleNotFoundError: No module named 'pytest'
```

**pytest is unavailable, so no canonical `python -m pytest` gate can run.** Every one of the 12
pytest-driven preflight gates fails with `No module named pytest` (verbatim output in §4).

### 3.2 unittest discovery: collects zero tests

The suites contain **no** `unittest.TestCase` subclasses:

```
$ grep -rn "unittest.TestCase" --include="*.py" .
(no matches)
```

All 296 test bodies are bare `def test_*()` functions; 15 files `import pytest`; the only pytest APIs
used are `pytest.raises` (53 call sites) and one `pytest.mark.parametrize`
(`bridge_09d/tests/test_semantic_verifier_gold.py:22`). There is no `conftest.py`, no `pytest.ini`,
no `pyproject.toml`, no `setup.cfg`. `unittest discover` therefore collects **0 tests** from this tree —
it cannot substitute for pytest here.

### 3.3 What could actually be executed — audit-only shim runner

To get real pass/fail data rather than "cannot run", a minimal pytest-compatible shim was written
**outside the vendor tree** at `C:\Users\sethb\AppData\Local\Temp\claude\meta_audit_tmp\shim\pytest.py`
and `…\shim_runner.py`. It implements exactly the surface this package uses — `pytest.raises`,
`pytest.mark.parametrize`, the `tmp_path` and `monkeypatch` fixtures — and mirrors `python -m pytest`
by placing the invocation directory on `sys.path[0]`.

**Fidelity check:** the `turn5_semantic_verification_suite` returns **86 passed**, matching the shipped
snapshot's `86 passed in 0.30s` exactly. Other suites reproduce their shipped counts wherever no
dependency blocks them.

Command form (one per canonical gate; suite groupings copied from `frontier_preflight.py:31-68`):

```
$ "C:/Users/sethb/.local/python/project09d-cpython-3.12.13/python.exe" -B \
    .../shim_runner.py --cwd <gate cwd> --label <gate name> <gate paths>
```

Results:

```
SUITE clinicaltrials_regression_suite              :: files=1 passed=0  failed=0  collect_errors=1 skipped=0
SUITE preprint_regression_suite                    :: files=1 passed=0  failed=0  collect_errors=1 skipped=0
SUITE drug_regression_suite                        :: files=1 passed=0  failed=0  collect_errors=1 skipped=0
SUITE pubmed_regression_suite                      :: files=2 passed=5  failed=16 collect_errors=0 skipped=0
SUITE warehouse_projection_suite                   :: files=1 passed=6  failed=3  collect_errors=0 skipped=0
SUITE 09d_bridge_core_suite                        :: files=5 passed=33 failed=0  collect_errors=1 skipped=0
SUITE evidence_substrate_adversarial_suite         :: files=2 passed=11 failed=0  collect_errors=1 skipped=0
SUITE gold_evidence_acceptance_suite               :: files=2 passed=0  failed=0  collect_errors=2 skipped=0
SUITE turn5_semantic_verification_suite            :: files=6 passed=86 failed=0  collect_errors=0 skipped=0
SUITE turn6_identity_readonly_comparator_suite     :: files=3 passed=0  failed=0  collect_errors=3 skipped=0
SUITE frontier_control_plane_suite                 :: files=1 passed=20 failed=2  collect_errors=0 skipped=0
```

**Totals: 161 passed, 21 failed, 10 collection errors, 0 skipped.** Shipped snapshot claims 320.

**Every single failure and collection error is a missing third-party module. Zero assertion failures,
zero logic errors.** Exhaustive cause breakdown:

```
$ grep -E "ModuleNotFoundError|ImportError:|AssertionError" shimrun_full.log | sort | uniq -c | sort -rn
     27 ModuleNotFoundError: No module named 'requests'
      3 ModuleNotFoundError: No module named 'pydantic'
      1 ModuleNotFoundError: No module named 'dateutil'
      1 ImportError: attempted relative import with no known parent package
```

The single `ImportError` is a fallback path inside `pubmed_rag/run_pubmed.py:25` that immediately
re-raises as the `requests` failure at line 31 — it is not an independent defect.

Representative verbatim failures:

```
FAILURE: COLLECT-ERROR test_offline.py
  File ".../clinicaltrials/tests/test_offline.py", line 7, in <module>
    from canonical.clinicaltrials.extractor import ExtractionConfig, MassExtractor
  File ".../clinicaltrials/canonical/clinicaltrials/client.py", line 13, in <module>
    import requests
ModuleNotFoundError: No module named 'requests'

FAILURE: COLLECT-ERROR test_source_unit_segmenter.py
  File ".../bridge_09d/tests/test_source_unit_segmenter.py", line 8, in <module>
    from bridge_09d.source_units import (
  File ".../bridge_09d/source_units.py", line 12, in <module>
    import requests
ModuleNotFoundError: No module named 'requests'

FAILURE: test_project.py::test_preprint_projection_version_identity
  File ".../preprints/src/pipeline.py", line 20, in <module>
    from dateutil.parser import isoparse
ModuleNotFoundError: No module named 'dateutil'

FAILURE: test_project.py::test_pubmed_projection_from_fake_certified_run
  File ".../pubmed_rag/metadata_schema.py", line 10, in <module>
    from pydantic import BaseModel, Field, field_validator, ConfigDict
ModuleNotFoundError: No module named 'pydantic'
```

**Blast radius of a single unguarded import.** `bridge_09d/source_units.py:12` does an
unconditional module-level `import requests` purely to type-annotate optional
`Optional[requests.Session]` parameters on three network functions. Because
`bridge_09d/package.py:13` imports `source_units`, that one line blocks **six** otherwise
pure-stdlib test files (`test_09d_contract.py`, `test_source_unit_segmenter.py`,
`test_gold_evidence_corpus.py`, `test_gold_fixture_bundle.py`, `test_identity_resolution.py`,
`test_09d_comparator.py`, `test_turn6_factory.py`) and the `09d_alignment_contract` and
`schema_coverage_contract` validator gates. The entire Turn-6 identity/comparator suite — the
newest capability in the pack — is unrunnable offline for this reason alone.

### 3.4 `run_offline_verification.sh` — stale, fails even with dependencies

Run with the locked interpreter on PATH (a `bin/python` wrapper pointing at it; note the system PATH
carries an unrelated CPython 3.12.10 *with* pytest, deliberately bypassed):

```
$ cd .../meta_audit_tmp/meta_x
$ export PATH="/c/Users/sethb/AppData/Local/Temp/claude/meta_audit_tmp/bin:$PATH"
$ python -c "import sys;print(sys.executable, sys.version)"
C:\Users\sethb\.local\python\project09d-cpython-3.12.13\python.exe 3.12.13 ...
$ bash ./run_offline_verification.sh
Meta Extraction Repaired v1 — offline verification
root=/tmp/claude/meta_audit_tmp/meta_x

[1/8] Production Python compile
PASS: 90 active Python files compiled
[2/8] ClinicalTrials regression
C:\Users\sethb\.local\python\project09d-cpython-3.12.13\python.exe: No module named pytest
EXIT_CODE=1
```

Only step [1/8] passes. Beyond the pytest blocker, the script is **stale against its own tree** and
would fail on a fully-provisioned runtime too:

```
$ for f in ...; do [ -f "$f" ] && echo "EXISTS  $f" || echo "MISSING $f"; done
MISSING pubmed_rag/c5_validation_tests.py      # required by step [5/8]
EXISTS  pubmed_rag/bigquery_validation_test.py
EXISTS  pubmed_rag/tests/test_repaired_invariants.py
EXISTS  pubmed_rag/validate.py
MISSING pubmed_rag/validate_pipeline.py         # required by step [6/8]
MISSING pubmed_rag/production_pipeline.py
EXISTS  pubmed_rag/requirements.txt
MISSING pubmed_rag/pubmedbert_embedding_pipeline.py

$ (cd pubmed_rag && python validate.py); echo "exit=$?"
PASS canonical PubMed source-path validation
exit=0

$ (cd pubmed_rag && python validate_pipeline.py); echo "exit=$?"
can't open file '...\pubmed_rag\validate_pipeline.py': [Errno 2] No such file or directory
exit=2
```

Both missing files now live only under `archive_not_production/legacy_parallel_stacks_2026-08-29/python/`.

**Step [7/8] of the legacy script now fails outright on the current tree.** Re-running its inlined
static-safety block verbatim:

```
$ python - "$PWD" <<'PY'   # exact block from run_offline_verification.sh lines 39-63
...
frontier_core\readiness.py: /mnt/data hard-code
```

`frontier_core/readiness.py:157` contains `re.compile(r"/mnt/data")` as a *rule definition*. The newer
`frontier_preflight.py` handles this by self-exempting the scanner
(`readiness.py:155  scan_files=[p for p in files if p != root/"frontier_core/readiness.py"]`), but the
legacy script has no such exemption and flags it. The two verification surfaces disagree about whether
the tree is safe.

---

## 4. `frontier_preflight.py` — fresh run vs. shipped snapshot

### 4.1 Fresh run

```
$ cd .../meta_audit_tmp/meta_x
$ "C:/Users/sethb/.local/python/project09d-cpython-3.12.13/python.exe" -B frontier_preflight.py
FRONTIER PREFLIGHT: FAIL
NETWORK EXTRACTION PERFORMED: FALSE
LIVE SOURCE CERTIFICATION: PENDING
DATABASE EXECUTION CERTIFICATION: PENDING
PRODUCTION MANIFEST FILES: 83
PRODUCTION CODE/CONTRACT MANIFEST SHA256: 6f2adf3b4683fb0b96c09ff289d18da975101600a9742342c92506acaac701b1
VERIFICATION MANIFEST FILES: 40
EXIT_CODE=1
```

**Verdict: FAIL. Exit code 1.** 62 gates: 47 passed, 15 failed.

Shipped snapshot: **PASS**, same 62 gates, all passed, manifest
`d9a3c5087f55913b57d00f5029f71aafd809312f0dc7979b04279ef0d36f4900`.

### 4.2 The 15 fresh failures, verbatim

```
FAIL | source_runtime_lock | python 3.12.13 != 3.13.5; annotated-types missing; certifi missing;
       charset-normalizer missing; idna missing; pydantic missing; pydantic-core missing;
       python-dateutil missing; requests missing; six missing; typing-extensions missing;
       typing-inspection missing; urllib3 missing
FAIL | single_active_pubmed_eutils_client | pubmed_rag\pubmed_anesthesia_extraction.py
FAIL | clinicaltrials_regression_suite | ...python.exe: No module named pytest
FAIL | preprint_regression_suite       | ...python.exe: No module named pytest
FAIL | drug_regression_suite           | ...python.exe: No module named pytest
FAIL | pubmed_regression_suite         | ...python.exe: No module named pytest
FAIL | warehouse_projection_suite      | ...python.exe: No module named pytest
FAIL | schema_coverage_contract | Traceback (most recent call last):
  File "...\schema\validate_coverage.py", line 17, in <module>
    from pubmed_rag.metadata_schema import PubMedRecordFull
  File "...\pubmed_rag\metadata_schema.py", line 10, in <module>
    from pydantic import BaseModel, Field, field_validator, ConfigDict
ModuleNotFoundError: No module named 'pydantic'
FAIL | 09d_alignment_contract | Traceback (most recent call last):
  File "...\bridge_09d\validate_alignment.py", line 7, in <module>
    from bridge_09d.package import source_identity_sha256,candidate_id
  File "...\bridge_09d\source_units.py", line 12, in <module>
    import requests
ModuleNotFoundError: No module named 'requests'
FAIL | 09d_bridge_core_suite                    | ...python.exe: No module named pytest
FAIL | evidence_substrate_adversarial_suite     | ...python.exe: No module named pytest
FAIL | gold_evidence_acceptance_suite           | ...python.exe: No module named pytest
FAIL | turn5_semantic_verification_suite        | ...python.exe: No module named pytest
FAIL | turn6_identity_readonly_comparator_suite | ...python.exe: No module named pytest
FAIL | frontier_control_plane_suite             | ...python.exe: No module named pytest
```

Twelve failures are the pytest blocker. Two are dependency imports. Two are genuine
platform/environment findings, below.

### 4.3 `single_active_pubmed_eutils_client` — a Windows-only false negative

`readiness.py:194-198`:

```python
eutils=[]
for p in scan_files:
    if "eutils.ncbi.nlm.nih.gov" in p.read_text(encoding="utf-8",errors="replace"):
        eutils.append(str(p.relative_to(root)))
results.append(GateResult("single_active_pubmed_eutils_client",
                          eutils==["pubmed_rag/pubmed_anesthesia_extraction.py"], ...))
```

The gate compares against a **hard-coded POSIX path string**. On Windows `str(p.relative_to(root))`
yields `pubmed_rag\pubmed_anesthesia_extraction.py`, so the equality fails even though the tree is
correct — the detail line even prints the single correct file it found. This gate can never pass on
Windows.

### 4.4 The shipped manifest hash cannot be reproduced off POSIX — three independent causes

**Nothing has drifted.** Per-file comparison of all 83 code/contract entries and all 40 verification
entries in the shipped `FRONTIER_PREFLIGHT.json` against the actual bytes:

```
== production_code_manifest: shipped count=83 shipped sha=d9a3c5087f55913b57d00f5029f71aafd809312f0dc7979b04279ef0d36f4900
   missing files: []
   drifted files: 0
== verification_manifest: shipped count=40 shipped sha=eecc2e1039973428be780f49a353f92fe1ddec0ab66282ac0db43056e396b9b8
   missing files: []
   drifted files: 0
```

Yet the aggregate hash differs. Reconstructing the manifest under different platform conventions
isolates the cause exactly:

```
windows-Path-order + posix strings : 0eba2221f030095ec0476a1d1c7f3fba6c93e2d8abded235074dc941a586a4d1
sorted-by-posix-string             : d9a3c5087f55913b57d00f5029f71aafd809312f0dc7979b04279ef0d36f4900  <-- MATCH
windows-Path-order + native strings: 07edd7258932854265fdaecf453fb9218f7750843a73e6eeca0296579d27f841
TARGET (shipped)                   : d9a3c5087f55913b57d00f5029f71aafd809312f0dc7979b04279ef0d36f4900
first order divergence at index 74  windows: schema/frontier_bigquery.sql | posix-sorted: schema/PHYSICAL_PROJECTION_CONTRACT.json
```

The shipped hash reproduces **only** under POSIX conventions. Three independent platform dependencies
in `readiness.py:131-134` (`code_manifest`) break it:

1. **Path separator.** `str(p.relative_to(root))` emits `\` on Windows, `/` on POSIX. The hashed JSON
   payload differs.
2. **Sort collation.** `production_manifest_files` returns `sorted(set(files))` over `Path` objects.
   `PureWindowsPath.__lt__` compares case-folded; `PurePosixPath.__lt__` is case-sensitive. The
   entry *order* differs — first divergence at index 74, where POSIX sorts
   `PHYSICAL_PROJECTION_CONTRACT.json` before `frontier_bigquery.sql` and Windows does not.
   `json.dumps(..., sort_keys=True)` sorts dict keys, not list order, so this changes the hash.
3. **Line endings written by the preflight itself.** The `physical_projection_contract` gate
   (`schema/validate_physical_projection.py`) rewrites `schema/PHYSICAL_PROJECTION_CONTRACT.json`
   with `path.write_text(...)` in text mode. On Windows that translates `\n`→`\r\n`:

   ```
   $ od -c <vendor>/schema/PHYSICAL_PROJECTION_CONTRACT.json | head -1
   0000000   {  \n     "  b  a  c  k  e  n  d  s  " ...            44972 bytes
   $ od -c <temp-after-preflight>/schema/PHYSICAL_PROJECTION_CONTRACT.json | head -1
   0000000   {  \r  \n     "  b  a  c  k  e  n  d  s  " ...        46795 bytes
   $ tr -d '\r' < <each> | sha256sum
   4aae19cbb5aa438e93e2ed56be0c9e3000be259599ebc71c303405809cb2febd   (identical content)
   ```

   This file **is** in the 83-entry production manifest and the gates run *before*
   `code_manifest()` is computed (`frontier_preflight.py:30-70`). So on Windows, merely running the
   canonical preflight permanently changes the SHA-256 of a manifest member.

**Consequence.** `frontier_core/gate.py:14-17` (`require_frontier_preflight`) hard-fails unless the
recomputed manifest hash equals the one in the preflight report. A PASS preflight produced on the
POSIX build box can therefore **never** authorize execution on Windows, and a Windows-generated
preflight is invalidated by its own first run. The code-bound authorization chain — the pack's central
safety claim — is not portable.

### 4.5 Network interlock behavior (verified)

No network access was attempted by anything run in this audit. Observed:

```
$ python -B frontier_orchestrator.py --source ctg --mode canary --output-root <tmp>
{
  "mode": "canary",
  "network_extraction_performed": false,
  "note": "No HTTP performed. Re-run with --execute after PASS preflight.",
  "source": "ctg",
  "status": "dry_run"
}

$ python -B frontier_orchestrator.py --source ctg --mode canary --output-root <tmp> --execute
  File ".../frontier_orchestrator.py", line 78, in run_orchestration
    if not a.preflight: raise RuntimeError('--preflight required with --execute')
RuntimeError: --preflight required with --execute
```

Dry-run default and preflight requirement both work. The source CLIs' `--network` interlock could
**not** be exercised: they die at `import requests` before `argparse` runs.

```
$ python -B clinicaltrials/canonical/run_extraction.py --output <tmp>
  File ".../clinicaltrials/canonical/clinicaltrials/client.py", line 13, in <module>
    import requests
ModuleNotFoundError: No module named 'requests'
```

Reading the source, the interlocks are genuine behavioral gates, not decoration:
`clinicaltrials/canonical/run_extraction.py:38` (`p.error("network extraction is locked; pass --network
only after frontier preflight PASS")`), `pubmed_rag/run_pubmed.py:120`, `preprints/src/pipeline.py:92`,
`preprints/src/run_all.py:55`, and `bridge_09d/source_units.py:281`
(`if not allow_network: raise RuntimeError("full-text HTTP acquisition is locked…")`) plus a host
allowlist `APPROVED_FULLTEXT_HOSTS = {pmc.ncbi.nlm.nih.gov, www.biorxiv.org, www.medrxiv.org}`
at `source_units.py:21-25`. **The preflight does not check any of that behavior — see §5.**

---

## 5. String-presence gates

`frontier_preflight.py` runs **62 gates: 16 subprocess/command gates + 46 static gates**. Of the 46
static gates, **41 are string-presence gates** — they read a file as text and test for the presence or
absence of literal substrings or regexes. They never import, execute, or parse the file.

The mechanism is `frontier_core/readiness.py:145-148`:

```python
def _contains(path: Path, needles: Iterable[str]) -> bool:
    if not path.exists(): return False
    text=path.read_text(encoding="utf-8",errors="replace")
    return all(n in text for n in needles)
```

and `readiness.py:137-142`:

```python
def _scan(files, root, name, pattern) -> GateResult:
    hits=[]
    for p in files:
        text=p.read_text(encoding="utf-8",errors="replace")
        if pattern.search(text): hits.append(str(p.relative_to(root)))
    return GateResult(name,not hits, ...)
```

### 5.1 Full enumeration — all 41

**A. Positive substring presence (`_contains`) — 33 gates**

| # | Gate | file:line | Literally checks |
| --- | --- | --- | --- |
| 1 | `clinicaltrials_network_interlock_symbols_present` | `frontier_core/readiness.py:174` | `"--network"`, `"--preflight"`, `"require_frontier_preflight"` appear anywhere in `clinicaltrials/canonical/run_extraction.py` |
| 2 | `preprint_network_interlock_symbols_present` | `readiness.py:174` | same three tokens in `preprints/src/pipeline.py` |
| 3 | `preprint_sharded_network_interlock_symbols_present` | `readiness.py:174` | same three tokens in `preprints/src/run_all.py` |
| 4 | `pubmed_network_interlock_symbols_present` | `readiness.py:174` | same three tokens in `pubmed_rag/run_pubmed.py` |
| 5 | `clinicaltrials_exact_transport_capture_symbols_present` | `readiness.py:191` | `PASS_EXACT_HTTP_RESPONSES`, `transport_raw_locator`, `transport_index_sha256` in `clinicaltrials/canonical/clinicaltrials/extractor.py` |
| 6 | `preprint_exact_transport_capture_symbols_present` | `readiness.py:191` | same three in `preprints/src/pipeline.py` |
| 7 | `pubmed_exact_transport_capture_symbols_present` | `readiness.py:191` | `PASS_EXACT_HTTP_RESPONSES`, `transport_raw_locators`, `transport_index_sha256` in `pubmed_rag/run_pubmed.py` |
| 8 | `postgres_promotion_view` | `readiness.py:206` | `frontier.promotable_run`, `certification_status = 'PASS'`, `truncated = FALSE`, `quarantined_records = 0` in `schema/frontier_postgres.sql` |
| 9 | `immutable_schema_contract` | `readiness.py:207` | `append-only`, `` latest` is a view ``, `DOI`, `linkage evidence` in `schema/SCHEMA_CONTRACT.md` — a **prose Markdown file** |
| 10 | `frontier_orchestrator_control_plane` | `readiness.py:209` | 7 tokens in `frontier_orchestrator.py` |
| 11 | `external_canary_never_unlocks_mass` | `readiness.py:210` | `PASS_EXTERNAL_TRANSPORT`, `mass_unlock_eligible`, **`"False"`**, `strict=True` in `frontier_external_canary.py`. Note the bare token `False` — satisfied by any occurrence of the word anywhere in the file |
| 12 | `frontier_release_promotion_gate` | `readiness.py:211` | 6 tokens in `frontier_release.py` |
| 13 | `09d_readonly_boundary` | `readiness.py:212` | 4 phrases in `09D_EXTRACTION_BOUNDARY_CONTRACT.md` — a **prose Markdown file** |
| 14 | `09d_external_audit_bridge` | `readiness.py:213` | 5 tokens in `bridge_09d/package.py` |
| 15 | `09d_source_unit_assertion_contract` | `readiness.py:214` | `UNIT:`, `ASSERT:`, `INTERP:`, `NOT_VERIFIED`, `canonical_authority`, `frontier-source-unit-1.2` in `bridge_09d/assertions.py` |
| 16 | `09d_fulltext_source_unit_segmenter` | `readiness.py:215` | 6 tokens in `bridge_09d/source_units.py` |
| 17 | `09d_fulltext_rights_separation` | `readiness.py:216` | 3 tokens in `bridge_09d/package.py` |
| 18 | `09d_assertion_extraction_engine` | `readiness.py:217` | 6 tokens in `bridge_09d/assertion_engine.py` |
| 19 | `09d_assertion_pipeline_persistence` | `readiness.py:218` | 5 tokens in `bridge_09d/assertion_pipeline.py` |
| 20 | `09d_independent_semantic_verifier` | `readiness.py:219` | `VERIF:`, `blind_independent_review`, `specialist_capsules`, `downstream_semantic_ready`, `FRONTIER_ADJUDICATION`, `PROVENANCE_INCOMPLETE` in `bridge_09d/verifier.py` |
| 21 | `09d_semantic_specialist_capsules` | `readiness.py:220` | 9 capsule-name tokens in `bridge_09d/semantic_capsules.py` |
| 22 | `09d_blind_recall_lane` | `readiness.py:221` | 4 tokens in `bridge_09d/blind_recall.py` |
| 23 | `09d_blind_recall_pipeline` | `readiness.py:222` | 5 tokens in `bridge_09d/blind_recall_pipeline.py` |
| 24 | `09d_semantic_review_router` | `readiness.py:223` | 5 tokens in `bridge_09d/semantic_router.py` |
| 25 | `09d_semantic_factory` | `readiness.py:224` | 6 tokens in `bridge_09d/semantic_factory.py` |
| 26 | `09d_provisional_identity_resolution` | `readiness.py:225` | 4 tokens in `bridge_09d/identity_resolution.py` |
| 27 | `09d_readonly_comparator` | `readiness.py:226` | `mode=ro&immutable=1`, `PRAGMA query_only=ON`, `CONTRADICTORY`, `CONTEXT_DIFFERENT`, `09d_mutation_performed` in `bridge_09d/comparator_09d.py` |
| 28 | `09d_turn6_audit_prep_factory` | `readiness.py:227` | 4 tokens in `bridge_09d/turn6_factory.py` |
| 29 | `09d_single_verifier_authority` | `readiness.py:228` | two `_contains` ANDed: `"Compatibility import surface"` + `"from .verifier import *"` in `assertion_verifier.py`, and `"Compatibility shim"` + `"from .verifier_pipeline import *"` in `verification_pipeline.py`. **The first needle of each pair is a docstring phrase.** |
| 30 | `09d_verifier_pipeline_persistence` | `readiness.py:229` | 4 tokens in `bridge_09d/verifier_pipeline.py` |
| 31 | `09d_semantic_verifier_gold_contract` | `readiness.py:230` | `semantic-verifier-gold-1.0`, `certainty`, `conditionality`, `production model backend` in `contracts/SEMANTIC_VERIFIER_GOLD_CONTRACT.md` — **prose** |
| 32 | `09d_semantic_gold_gate_contract` | `readiness.py:231` | `hand-authored`, `deterministic hard contradiction`, `Production model benchmarking` in `contracts/SEMANTIC_GOLD_GATE_CONTRACT.md` — **prose** |
| 33 | `09d_gold_evidence_gate_contract` | `readiness.py:232` | `Generated output is evidence under test`, `PINNED_PHYSICAL_FIXTURE`, `mass_extraction_authorized = true` in `contracts/GOLD_EVIDENCE_GATE_CONTRACT.md` — **prose** |

**B. Negative token/regex absence — 5 gates**

| # | Gate | file:line | Literally checks |
| --- | --- | --- | --- |
| 34 | `no_hardcoded_container_paths` | `readiness.py:157` | regex `/mnt/data` absent from 57 production files (`readiness.py` itself is exempted at line 155) |
| 35 | `no_python_hash_identifiers` | `readiness.py:158` | regex `(?<![A-Za-z_])hash\s*\(` absent. **Text scan, not AST** — trips on the token in a comment or docstring; evaded by `builtins.hash(x)`, `h=hash` then `h(x)`, or `getattr(builtins,'hash')` |
| 36 | `no_fake_identifier_or_model_fallbacks` | `readiness.py:159` | regex `(?:fake\|placeholder\|synthetic)[ _-]?(?:id\|identifier\|rxcui\|likelihood\|answer\|embedding\|vector)` absent. Checks that the *word* "fake" is absent, not that behavior is real |
| 37 | `pubmed_source_model_agnostic` | `readiness.py:181-183` | tokens `sentence_transformers`, `SentenceTransformer(`, `torch.cuda`, `FAISS` absent from three named PubMed files |
| 38 | `no_premature_drug_canonical_authority` | `readiness.py:233` | string literals `"drug_entity"`, `"drug_alias"`, `"drug_linkage_evidence"` absent from `warehouse/project.py` |

**C. Substring-in-DDL — 2 gates**

| # | Gate | file:line | Literally checks |
| --- | --- | --- | --- |
| 39 | `postgres_frontier_schema_tables` | `readiness.py:200-205` | the literal `frontier.<name>` appears in `schema/frontier_postgres.sql` for each of 35 table names. No SQL parsing — a comment mentioning the name satisfies it |
| 40 | `bigquery_frontier_schema_tables` | `readiness.py:200-205` | same 35 names against `schema/frontier_bigquery.sql` |

**D. Hard-coded path-string comparison — 1 gate**

| # | Gate | file:line | Literally checks |
| --- | --- | --- | --- |
| 41 | `single_active_pubmed_eutils_client` | `readiness.py:194-198` | files containing `eutils.ncbi.nlm.nih.gov` must equal exactly `["pubmed_rag/pubmed_anesthesia_extraction.py"]` — POSIX-only literal; see §4.3 |

**The 5 static gates that are NOT string-presence:** `production_python_compile` (real `py_compile`),
`no_active_shadow_python_variants` (regex on *filenames*, not content),
`production_python_files_present` (count > 0), `source_runtime_lock` (real
`importlib.metadata.version()` comparison), `warehouse_projection_layer` (`Path.exists()`).

**Two further string-presence checks outside the preflight's static block:**
`pubmed_rag/validate.py` (the `pubmed_source_validator` gate) is *entirely* string-presence —
file existence plus `if token not in extractor` for `esearch_all`, `one day still exceeds`,
`EFetch reconciliation failed`, `source_record_sha256`, and two schema tokens, plus four forbidden
filenames (`validate.py:29-39`). `pubmed_rag/bigquery_validation_test.py` (the
`bigquery_schema_validator` gate) is a regex-over-DDL check plus four `assert "…" in text`
(`bigquery_validation_test.py:17,24-27`). Both PASS on the locked interpreter — they need no
dependencies precisely because they never execute anything.

### 5.2 Proof that the criticism bites

A gate that reads text cannot distinguish an implementation from a comment. Demonstrated on stub files
written **outside the vendor tree**, using the pack's own `_contains`:

```
$ cat poc/fake_run_extraction.py
# This file has NO executable interlock at all. It only mentions the tokens:
#   --network   --preflight   require_frontier_preflight

$ cat poc/fake_comparator_09d.py
"""Docstring only. Mentions: mode=ro&immutable=1 PRAGMA query_only=ON
CONTRADICTORY CONTEXT_DIFFERENT 09d_mutation_performed"""

$ python -B poc/proof.py     # imports _contains from the vendor's own readiness.py
clinicaltrials_network_interlock_symbols_present on a comment-only stub: True
09d_readonly_comparator on a docstring-only stub                      : True

stub file sizes: 134 128 bytes
```

A **134-byte comment** satisfies the ClinicalTrials network interlock gate. A **128-byte docstring**
satisfies the 09D read-only comparator gate — the gate asserting that the pack cannot mutate Project 09D.

**Fair reading of the design.** The pack is not hiding this. 20 of the 33 `_contains` gates carry a
detail string that says so verbatim — `"structural presence only"`, `"structural … markers present;
behavioral bridge tests run separately"`. The design intent is a two-layer scheme: cheap structural
markers plus behavioral pytest suites. The problem is the **failure mode**, not the honesty: the
structural layer is dependency-free and always passes, while the behavioral layer needs pytest +
requests + pydantic + dateutil + Python 3.13.5. On the locked interpreter the layer that actually
proves behavior is 100% dark, and 41 of 47 passing gates are text matches. A reader glancing at
"47 gates passed" gets a materially wrong impression of what was verified.

---

## 6. Semantic extraction implementation maturity

Verdict per component. The pack's own `09D_FRONTIER_EXTRACTION_STATE.md` describes all of these as
"implemented"; that is defensible for the *plumbing* and misleading for the *extraction*.

### 6.1 Assertion engine — real validator, near-absent extractor

`bridge_09d/assertion_engine.py` (302 lines) is genuinely substantial and genuinely executable, but it
is an **evidence-binder and authority-enforcer, not an extractor**:

- `validate_proposal` (`:160`) — allow-list/deny-list, atomic-sentence check via `_single_sentence` (`:105`), length cap
- `_text_span` (`:113`) — verifies `evidence_text` is an **exact** substring of the unit, computes char and UTF-8 byte offsets, rejects ambiguous multi-occurrence spans
- `_structured_path` (`:138`) — requires exact equality with the unit's `json_path`
- `_nested_forbidden_keys` (`:147`) — recursive scan preventing a provider from injecting identity/authority fields
- `proposal_to_assertion` (`:183`) — ends with a hard runtime invariant (`:213-214`): any emitted assertion must be `NOT_VERIFIED` with null candidate IDs or `RuntimeError`
- `extract_assertions` (`:223`) — deterministic ordering, exact-interpretation dedup, quarantine-not-drop for every provider failure

**But the actual proposition-generating step is `ProposalProvider` (`:35`), an injected callable.** The
sole in-package implementation is `structured_clinicaltrials_provider` (`:275-298`): **five hard-coded
`if path.endswith(...)` rules** over ClinicalTrials JSON — enrollment count, phase, overall status,
condition, `hasResults` — emitting f-string templates such as
`f"The study enrollment was {value} participants."`. Everything else returns `[]`, including all of
`.resultsSection.` (`:296-297`, comment: *"Turn 4 avoids generic result semantics until type-specific
mappings exist"*).

**There is no natural-language assertion extractor in this pack.** `build_model_request` (`:72`) builds
the prompt payload for one; no model backend exists.

### 6.2 Blind recall — scaffolding plus one real reconciler

`bridge_09d/blind_recall.py` is **76 lines total**.

- `build_blind_recall_request` (`:19`) — decorates `build_model_request` with a `recall_task` block and asserts the packet leaks no primary-extractor state (`:29-30`). Real, but a wrapper.
- `run_blind_recall` (`:34`) — delegates straight to `extract_assertions` with the caller's provider. **No recall logic of its own.**
- `reconcile_primary_recall` (`:53-76`) — the one piece of real algorithm: keys assertions by `(source_unit_id, assertion_type, evidence-span-sha or json_path)` via `_evidence_key` (`:46`) and classifies into `PRIMARY_AND_RECALL_EXACT`, `SAME_EVIDENCE_SEMANTIC_DISAGREEMENT`, `PRIMARY_ONLY`, `RECALL_ONLY_CANDIDATE`, with `automatic_repair_allowed: False` throughout.

**Verdict: scaffolding.** The recall lane has no recaller. `bridge_09d/blind_recall_pipeline.py`
(185 lines) adds hash-bound persistence around it. Grep confirms the only `provider=` argument bound
anywhere in non-test production code is `structured_clinicaltrials_provider`
(`assertion_pipeline.py:72`); every recall/reviewer provider in the tree is a test stub
(`bridge_09d/tests/test_blind_recall_pipeline.py:39`, `test_independent_verifier.py:99`, etc.).

### 6.3 Semantic capsules — the most mature component, real rule-based NLP

`bridge_09d/semantic_capsules.py` (450 lines) is the genuine article — deterministic, executable,
dependency-free, and it **passed 86/86 in the Turn-5 suite on the locked interpreter**:

- Compiled lexicon regexes at `:52-58` — `_NEGATION_RE`, `_UNCERTAINTY_RE`, `_CAUSAL_RE`, `_ASSOCIATION_RE`, `_DIRECTION_UP_RE`, `_DIRECTION_DOWN_RE`, `_NO_EFFECT_RE`
- Text canonicalization `canonical_semantic_text` (`:67`) with Unicode superscript/subscript maps (`:32-36`) and a vulgar-fraction table (`:37`)
- `_numeric_candidates` (`:106-111`) — a real numeric tokenizer handling `3.5 x 10^6`, `2e-3`, `1/2`, decimals
- `numeric_binding_check` (`:158`) with `_canonical_unit` (`:139`) and `_unit_variants` (`:151`)
- `_ROUTE_SYNONYMS` (`:39`) + `_route_mentions` (`:200`) / `_detected_routes` (`:212`)
- Nine capsules: `numeric_binding_check`, `negation_preservation_check` (`:220`), `certainty_modality_check` (`:235`), `conditionality_check` (`:247`), `qualifier_scope_check` (`:262`), `table_binding_check` (`:302`), `visual_binding_check` (`:331`), `relationship_semantics_check` (`:354`), `atomicity_check` (`:374`), plus `provenance_check` (`:383`)
- `risk_route` (`:394`) — computes risk level, required specialists, and `frontier_adjudication_required`

**Verdict: real executable logic.** This is rule-based/lexicon NLP, not a model, and it is honest about
being deterministic.

`bridge_09d/semantic_factory.py` (105 lines) is pure composition: `verify_assertions` →
optional `run_blind_recall` → `reconcile_primary_recall` → `route_semantic_review`, with a code-hash
binding check (`:47-48`) and metrics. Both `reviewer` and `recall_provider` are optional injected
callables with **no in-package implementation**.

### 6.4 Verifier — real reconciliation state machine, no semantic judge

`bridge_09d/verifier.py` (385 lines). Real logic:

- `build_blind_verifier_request` (`:82`) — constructs the reviewer packet and **actively enforces blindness** by re-serializing and refusing on leak (`:126-129`: `raise RuntimeError(f"blind verifier request leaked {token}")` for `extractor_provenance`, `interpretation_id`, `subject_candidate_id`, `object_candidate_id`)
- `validate_reviewer_response` (`:150`) + `_nested_forbidden` (`:138`) — reviewers cannot inject authority
- `_structured_deterministic_verdict` (`:191`) — **independent re-derivation**: re-runs `structured_clinicaltrials_provider` on the source unit and compares against the assertion, returning `NOT_ENTAILED` on mismatch. This is a genuine independent check.
- `_reconcile` (`:212-262`) — a real precedence state machine: provenance block → hard specialist FAIL → structured-rederivation mismatch → reviewer error → structured entailment → literal equality → reviewer verdict, with warning-driven `ENTAILED`→`PARTIAL` downgrade (`:250-251`)
- `verify_assertions` (`:355`) — batching, dedup, quarantine, verdict/risk/review-state metrics
- `validate_verification_event` (`:331`) — asserts all eight authority flags are `False`

**The semantic entailment judgment itself is `ReviewerProvider` (`:40`), injected and unimplemented.**
With `reviewer=None` — the only configuration available in this pack — the verifier can reach
`ENTAILED` by exactly two routes:

1. `DETERMINISTIC_REDERIVATION` — only for the five CTG structured rules (`:228-231`)
2. `DETERMINISTIC_LITERAL_EQUALITY` — `:236-242`, casefolded, period-stripped **exact string equality**
   between the normalized proposition and the evidence text; and even then
   `downstream_semantic_ready` is forced `False` (`:242`)

Any free-text assertion that is not byte-identical to its evidence returns
`AMBIGUOUS / NO_INDEPENDENT_SEMANTIC_REVIEW` (`:243`). The pack's own test name says it:
`test_paraphrase_without_independent_semantic_provider_is_ambiguous`
(`bridge_09d/tests/test_independent_verifier.py:34`).

`bridge_09d/assertion_verifier.py` (6 lines) and `bridge_09d/verification_pipeline.py` (8 lines) are
`from … import *` shims, correctly labelled.

**Verdict: mature harness, zero semantic capability without an external model that this pack does not
contain and has never certified.** `09D_FRONTIER_EXTRACTION_STATE.md:66` lists
"production general-text/reviewer/recall model certifications" as an open blocker, and
`SEMANTIC_VERIFIER_GOLD_CONTRACT.md` is gated on the phrase `production model backend`.

### 6.5 09D comparator — real read-only adapter, never run against real data

`bridge_09d/comparator_09d.py` (309 lines) is real: `build_snapshot_from_sqlite` (`:68`) opens the DB
with `mode=ro&immutable=1` plus `PRAGMA query_only=ON`, introspects columns via `_table_columns` (`:53`),
requires a SHA-256 match against `expected_sha256`, and `compare_assertion` (`:215`) classifies into
`EXACT_EXISTING` / `CONTRADICTORY` / `CONTEXT_DIFFERENT` / `IDENTITY_NOT_FOUND` using
`normalize_compare_text` (`:47`), `_context_key` (`:196`), `_numeric_equal` (`:209`).

But `TURN6_IDENTITY_READONLY_COMPARATOR_REPORT.json` states plainly:

```
"actual_09d_database_present": false,
"09d_comparator_status": "IMPLEMENTED_OFFLINE_CERTIFIED_REAL_DATABASE_PENDING",
"snapshot_source_kind": "SYNTHETIC_CONTRACT_FIXTURE",
"actual_09d_database_expected_sha256": "11f9e3150e5775f452cd90be7aa33dcb6c3a8df4fc9c3810f41b45248f6d4aee"
```

**Verdict: real adapter, unexercised against real data.** Also note that on the locked interpreter the
entire Turn-6 suite is unrunnable (0 passed, 3 collection errors) because of the transitive `requests`
import — this is the *least* verified component in the pack, not the most.

### 6.6 Scale of demonstrated evidence

The whole semantic plane has only ever been exercised on hand-built micro-fixtures. Largest artifacts
anywhere under `evidence/`:

```
    13  evidence/09d_turn3_segmentation_sample/audit_package/source_units/source_units.jsonl
    13  evidence/09d_turn4_assertion_sample/source_units.jsonl
     7  evidence/turn5_semantic_factory/assertions.jsonl
     7  evidence/turn5_semantic_factory/verification_events.jsonl
     6  evidence/turn5_semantic_verifier/assertions.jsonl
     4  evidence/turn6_identity_comparator/audit_package/09d_comparisons/comparisons.jsonl
     4  evidence/turn6_identity_comparator/audit_package/candidates/candidates.jsonl
```

Maximum: **13 source units, 7 assertions, 4 comparisons.** `09D_FRONTIER_EXTRACTION_STATE.md:50-58`
describes exactly this as the "Demonstration": 4 primary assertions → 4 ENTAILED, 2 downstream-ready,
4 candidates → 0 canonical assignments, one comparison of each classification. All against a
`SYNTHETIC_CONTRACT_FIXTURE`.

### 6.7 Summary

| Component | Verdict | Basis |
| --- | --- | --- |
| Source-unit segmentation (`source_units.py`) | **Real, mature** | 573-line JATS/XML parser, math rendering, section paths, license extraction, atomic writes, host allowlist |
| Semantic specialist capsules (`semantic_capsules.py`) | **Real, mature** | 450 lines of lexicon/regex NLP; 86/86 tests pass on the locked interpreter |
| Verifier reconciliation (`verifier.py`) | **Real harness, no judge** | Genuine state machine + blindness enforcement + structured re-derivation; entailment provider unimplemented |
| 09D comparator (`comparator_09d.py`) | **Real adapter, unexercised** | Correct read-only SQLite; never run against the real DB; suite unrunnable offline |
| Assertion engine (`assertion_engine.py`) | **Real binder, 5-rule extractor** | Strong validation/authority enforcement; the only extractor is 5 CTG field templates |
| Blind recall (`blind_recall.py`) | **Scaffolding + one reconciler** | 76 lines; no recaller; `reconcile_primary_recall` is the only algorithm |
| Warehouse projection (`warehouse/project.py`) | **Real** | 4 projectors; `validate_physical_projection.py` runs them on fixtures and unions emitted columns against both DDLs — a genuine behavioral contract test that passes offline |

---

## 7. Dependencies: required vs. provided

### 7.1 What Meta declares

`requirements-source.lock.txt`:

```
# Exact source-extraction runtime tested by Frontier v4 preflight.
# Regenerate + rerun preflight before changing any version.
requests==2.32.5
certifi==2026.5.20
charset-normalizer==3.4.7
idna==3.17
urllib3==2.7.0
python-dateutil==2.9.0.post0
six==1.17.0
pydantic==2.13.4
pydantic-core==2.46.4
annotated-types==0.7.0
typing-extensions==4.16.0
typing-inspection==0.4.2
```

`source-runtime.lock.json`:

```json
{ "runtime_contract_version": "frontier-source-runtime-1.0",
  "python": "3.13.5",
  "packages": { "annotated-types": "0.7.0", "certifi": "2026.5.20", "charset-normalizer": "3.4.7",
    "idna": "3.17", "pydantic": "2.13.4", "pydantic-core": "2.46.4", "python-dateutil": "2.9.0.post0",
    "requests": "2.32.5", "six": "1.17.0", "typing-extensions": "4.16.0",
    "typing-inspection": "0.4.2", "urllib3": "2.7.0" } }
```

`readiness.py:105-121` (`runtime_contract_gate`) enforces **exact equality** on both the Python version
and every package version.

**Undeclared but required:** `pytest` is needed by 12 of 16 subprocess gates and appears in **neither**
lock file. `numpy` is imported by `experimental_enrichment_not_certified/pubmedbert_embedding_pipeline.py`
(quarantined, with its own `requirements.txt`, not in the production manifest).

### 7.2 What the locked interpreter provides

```
Python 3.12.13 ; pip 26.1.1 ; setuptools 83.0.0 — nothing else.
```

### 7.3 Gap

| Requirement | Locked interpreter | Gap |
| --- | --- | --- |
| Python **3.13.5** exactly | 3.12.13 | **Version mismatch.** Not a syntax problem — all 58 production files compile cleanly under 3.12.13 (`production_python_compile | 58 files` PASSES). It is purely the exact-match assertion in `runtime_contract_gate`. |
| requests 2.32.5 | absent | **Blocks 27 tests + 2 validator gates.** Where imported: `clinicaltrials/canonical/clinicaltrials/client.py:13`, `preprints/src/medrxiv_biorxiv/client.py:20`, `drug_reference/drugref/rxnorm.py:8`, `pubmed_rag/pubmed_anesthesia_extraction.py:17`, `bridge_09d/source_units.py:12`, and (non-production) `evidence/fault_injection/run_local_http_certification.py:14`, `run_native_path_local_certification.py:13` |
| pydantic 2.13.4 (+ pydantic-core, annotated-types, typing-inspection) | absent | **Blocks 3 tests + `schema_coverage_contract`.** Imported at `pubmed_rag/metadata_schema.py:10`, re-exported by `pubmed_rag/__init__.py:5` |
| python-dateutil 2.9.0.post0 (+ six) | absent | **Blocks 1 test.** `preprints/src/medrxiv_biorxiv/client.py:21`, `preprints/src/pipeline.py:20` |
| certifi / charset-normalizer / idna / urllib3 / typing-extensions | absent | transitive deps of the above |
| **pytest** (undeclared) | absent | **Blocks 12 of 16 subprocess gates and 159 of 320 tests.** No `unittest.TestCase` fallback exists |
| numpy (quarantined path only) | absent | no production impact |

**Net:** the pack needs Python 3.13.5 plus 12 pinned packages plus an undeclared pytest. The locked
interpreter supplies none of them. Nothing was installed; per the audit constraint this is recorded
rather than remediated.

---

## 8. Consolidated findings

| # | Severity | Finding |
| --- | --- | --- |
| F1 | **High** | The code-bound manifest hash is **platform-dependent in three independent ways** — path separator, `Path` sort collation, and CRLF rewrite of a manifest member by the preflight's own `physical_projection_contract` gate. The shipped `d9a3c508…` reproduces only under POSIX conventions. `require_frontier_preflight` (`gate.py:16-17`) hard-fails on any mismatch, so a POSIX-issued PASS preflight can never authorize execution on Windows. The pack's central safety mechanism is not portable. |
| F2 | **High** | **41 of 46 static preflight gates are string-presence checks.** A 134-byte comment-only file satisfies the ClinicalTrials network interlock gate; a 128-byte docstring satisfies the 09D read-only comparator gate (proved with the pack's own `_contains`). On a runtime without pytest, 41 of the 47 passing gates are text matches and the behavioral layer is entirely dark. |
| F3 | **High** | `frontier_preflight.py` **mutates its own root** — `FRONTIER_PREFLIGHT.json`, `FRONTIER_PREFLIGHT.txt`, and `schema/PHYSICAL_PROJECTION_CONTRACT.json`, the last of which is inside the hash it certifies. A "frozen" pack cannot be verified in place without changing. |
| F4 | **High** | **Fresh preflight verdict is FAIL / exit 1** (47 pass, 15 fail) against a shipped snapshot of PASS. Thirteen failures are environmental (pytest + deps). Two are real defects: `single_active_pubmed_eutils_client` (F5) and `source_runtime_lock`. Per-file hashes prove **zero content drift** in all 123 manifest entries — the pack is intact; only the certification is unreproducible. |
| F5 | **Medium** | `single_active_pubmed_eutils_client` (`readiness.py:198`) compares against the hard-coded POSIX literal `"pubmed_rag/pubmed_anesthesia_extraction.py"`. **Can never pass on Windows**, even when the tree is correct — its own detail line prints the single correct file it found. |
| F6 | **Medium** | Unconditional `import requests` at `bridge_09d/source_units.py:12`, used only for `Optional[requests.Session]` type hints, transitively blocks 7 pure-stdlib bridge test files plus the `09d_alignment_contract` and `schema_coverage_contract` gates. Guarding it (`TYPE_CHECKING` / lazy import) would make the entire Turn-6 identity/comparator suite runnable offline. |
| F7 | **Medium** | `run_offline_verification.sh` is stale: references three files that exist only under `archive_not_production/` (`c5_validation_tests.py`, `validate_pipeline.py`), and its step [7/8] static check **now fails on the current tree** (`frontier_core\readiness.py: /mnt/data hard-code`) because it lacks the self-exemption the newer preflight added. Its recorded output `OFFLINE_VERIFICATION.txt` is from a different machine (`root=/mnt/data/…`) with obsolete counts (70 files, 10/7/6/18 tests vs. current 90 files, 19/9/16/21). |
| F8 | **Medium** | Three mutually incompatible definitions of "production code": 58 (preflight), 90 (`run_offline_verification.sh`), 38 (`FRONTIER_READINESS.md`). `FRONTIER_READINESS.md` also carries a stale manifest hash `080faf6a…`. |
| F9 | **Medium** | **No natural-language assertion extractor exists.** The only in-package `ProposalProvider` is `structured_clinicaltrials_provider` — five `if path.endswith(...)` rules over CTG JSON emitting f-string templates. `.resultsSection.` returns `[]` by design. |
| F10 | **Medium** | **No semantic entailment judge exists.** Both `ReviewerProvider` and `RecallProposalProvider` are injected callables with test stubs only. Without one, the verifier reaches `ENTAILED` solely by re-deriving the 5 CTG rules or by casefolded exact string equality; anything else is `AMBIGUOUS / NO_INDEPENDENT_SEMANTIC_REVIEW`. |
| F11 | **Low** | `pubmed_rag/archive_not_production/superseded_entrypoints/README.md` names `production_pipeline.py`, `incremental_update_pipeline.py`, `pubmed_client_hardened.py` as the canonical paths. All three are absent, and `pubmed_rag/validate.py:12-19` lists all three in `FORBIDDEN_ACTIVE` — the active gate fails if they exist. |
| F12 | **Low** | `README.md` self-contradicts on version: "v10 — 09D Turn 5", then "Current v5 status", then "Turn 6 update". The state doc it names as authoritative says Turn 6. |
| F13 | **Low** | `no_python_hash_identifiers` (`readiness.py:158`) is a text regex, not AST analysis: false-positives on the token in a comment, and is evaded by `builtins.hash(x)` or an aliased binding. |
| F14 | **Low** | The `external_canary_never_unlocks_mass` gate (`readiness.py:210`) includes the bare needle `"False"` — satisfied by any occurrence of that word anywhere in the file. |
| F15 | **Info** | Total demonstrated semantic evidence: **13 source units, 7 assertions, 4 comparisons**, against a `SYNTHETIC_CONTRACT_FIXTURE`. `actual_09d_database_present: false`. |
| F16 | **Info** | **Network interlock behaves correctly.** Orchestrator dry-runs by default and refuses `--execute` without `--preflight` (verified by execution). Source-CLI `--network` gates and the `APPROVED_FULLTEXT_HOSTS` allowlist are real behavioral `raise` statements (verified by reading; unreachable on the locked interpreter because `import requests` fails first). **No network access was attempted or made during this audit.** |

### What is genuinely good

`source_units.py` is a real, careful JATS segmenter. `semantic_capsules.py` is 450 lines of honest
deterministic NLP that passes 86/86 on a bare interpreter. `verifier.py` enforces reviewer blindness by
re-serializing its own request and refusing on leak — a real mechanism, not a marker.
`assertion_engine.py` quarantines rather than drops, and its authority invariants are runtime-enforced
`RuntimeError`s. `validate_physical_projection.py` runs the actual projectors and unions emitted
columns against both DDLs — a genuine behavioral contract test that needs no dependencies and passes.
The `NOT_VERIFIED` / `canonical_authority: False` discipline is consistent across all 19 bridge modules.
And every failure the shim runner produced was a missing dependency — **not one assertion failed** — so
where the code can run, it works.

---

## Appendix: audit workspace

| Path | Contents |
| --- | --- |
| `C:\Users\sethb\AppData\Local\Temp\claude\meta_audit_tmp\meta_x\` | Byte-identical working copy of the vendor tree (restored to pristine after the preflight run) |
| `…\shim\pytest.py`, `…\shim_runner.py` | Audit-only pytest shim + collector (see §3.3) |
| `…\shimrun_full.log` | Full verbatim output of all 11 shim suite runs |
| `…\fresh_FRONTIER_PREFLIGHT.json`, `…\fresh_FRONTIER_PREFLIGHT.txt` | Fresh preflight output preserved for comparison |
| `…\bin\python` | PATH wrapper forcing `run_offline_verification.sh` onto the locked interpreter |
| `…\manifest_variants.py`, `…\compare_shipped.py`, `…\count_gates.py` | Manifest-hash reproduction, per-file drift check, gate census |
| `…\poc\fake_run_extraction.py`, `…\poc\fake_comparator_09d.py`, `…\poc\proof.py` | String-presence-gate proof of concept (§5.2) |
