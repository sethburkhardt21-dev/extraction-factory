# HERMES Extraction Factory Advanced v1.1 — audit test run

**Audited pack (READ-ONLY):**
`C:\Users\sethb\.codex\.chatgpt-projects\g-p-6a22140cf3d08191bef2524866d4c6fe\extraction_factory\vendor\hermes_x\HERMES_EXTRACTION_FACTORY_ADVANCED_v1_1`

**Date:** 2026-08-31
**Interpreter:** `C:\Users\sethb\.local\python\project09d-cpython-3.12.13\python.exe` with `-B`, plus
`PYTHONDONTWRITEBYTECODE=1` exported so the pack's own `subprocess` re-invocations (which do **not**
pass `-B`) could not write bytecode either.
**Network:** none used.

---

## 0. Isolation — why nothing ran in place

Three of the pack's canonical entry points **write inside the pack root**:

| Entry point | Writes |
| --- | --- |
| `verify_factory.py` (`VERIFY.sh`) | `PREFLIGHT/PREFLIGHT.json`, `PREFLIGHT/PREFLIGHT.txt` (`verify_factory.py:58,68`) |
| `hermes_factory test` | `CURRENT/TEST_REPORT.json`, `CURRENT/TEST_REPORT.md` (`test_runner.py:24,26`) |
| `hermes_factory verify` | `CURRENT/CURRENT_BUILD_MANIFEST.json`, `CURRENT/PREFLIGHT.json`, `CURRENT/PREFLIGHT.txt` (`preflight.py:15,37,44`) |

Additionally `test_runner.py:12` and `preflight.py:23` spawn `sys.executable -m unittest` **without**
`-B`, which would have deposited `cpython-312` `.pyc` files throughout the vendor tree.

**Therefore every executable step below was run against a byte-identical copy**, not the vendor tree:

```
C:\Users\sethb\AppData\Local\Temp\claude\hermes_audit_tmp\PACK
```

Copy + byte-identity proof:

```
python -B -c "shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__')) ..."
production files compared: 36
byte-identical         : True []
copy root              : C:\Users\sethb\AppData\Local\Temp\claude\hermes_audit_tmp\PACK
```

The copy is additionally validated *by the pack's own certifier*: the preflight check
`MANIFEST_INTEGRITY` returns **PASS** in the copy, meaning the 36 production files still hash to the
immutable `CERTIFIED_BUILD_MANIFEST.json` digest. The copy is a faithful stand-in.

**Vendor tree confirmed untouched after all runs:**

```
$ find . -name "*cpython-312*" | head
(no output — none written)

$ find . -type f -newermt "2026-08-31" -printf "%T+ %p\n" | sort -r | head -12
(no output — nothing written today)

$ ls -la CURRENT/PREFLIGHT.json CURRENT/TEST_REPORT.json PREFLIGHT.json
-rw-r--r-- 1 sethb 197609 7567 Aug 30 20:27 CURRENT/PREFLIGHT.json
-rw-r--r-- 1 sethb 197609 7135 Aug 30 20:23 CURRENT/TEST_REPORT.json
-rw-r--r-- 1 sethb 197609 7567 Aug 30 20:26 PREFLIGHT.json
```

Only file written outside the temp dir: this report.

---

## 1. Canonical entry points

Read: `README.md`, `README_ADVANCED_v1_1.md`, `VERIFY.sh`, `RUN_FACTORY.sh`, `verify_factory.py`,
`hermes_factory/cli.py`.

There are **two independent, non-overlapping verification systems** in this pack. This matters a lot,
because they disagree.

| # | Entry point | Shell wrapper | Implementation | What it checks |
| --- | --- | --- | --- | --- |
| A | `verify_factory.py` | `VERIFY.sh` → `python verify_factory.py` | standalone script at pack root | Turn-10 legacy: JSON well-formedness of 6 docs, schema-coverage validator, Turn08/Turn10 mutation suites, 4 blind-capsule inspections, pilot boundary scope, freeze-claim boundary. **Does not touch `hermes_factory/`, the unittest suite, or the runtime lock.** |
| B | `python -m hermes_factory <cmd>` | `RUN_FACTORY.sh` → `exec python -m hermes_factory "$@"` | `hermes_factory/cli.py` | The v1.1 advanced runtime. |

`README.md` (the older file) still advertises only `./VERIFY.sh`. `README_ADVANCED_v1_1.md` names
`./RUN_FACTORY.sh` as "Canonical entrypoint" and lists commands
`test`, `verify`, `certify-build`, `ingest-pdf`, `run`, `status`, `resume`, `package`, `verify-package`.

Sub-commands relevant to this audit (`cli.py:186-231`):

- **test runner** → `cmd_test` → `test_runner.run_tests()` → `python -m unittest discover -s tests -v`
- **preflight / verify** → `cmd_verify` → `preflight.run_preflight()` (4 checks; `--skip-tests` drops the 4th)
- There is **no** `preflight` sub-command; `verify` *is* the preflight. `run_preflight` is the only
  thing that writes `CURRENT/PREFLIGHT.{json,txt}`.

The suite is **unittest-based, not pytest** — plain `unittest.TestCase` classes with
`if __name__ == "__main__": unittest.main()`. No pytest is required and none is used. (Confirmed:
the locked interpreter has `pip` and `setuptools` but **no pytest and no wheel** — irrelevant here.)

---

## 2. Canonical verification — `verify_factory.py`

```
$ cd <TEMP>/PACK
$ PYTHONDONTWRITEBYTECODE=1 python -B verify_factory.py
```

```
HERMES FACTORY v1 PREFLIGHT: PASS
PASS: json:FREEZE/FACTORY_V1_FREEZE_MANIFEST.json
PASS: json:IMPLEMENTATION/IMPLEMENTATION_MATURITY_MATRIX_v0_1.json
PASS: json:CONTRACTS/EVIDENCE_SUBSTRATE_v0_1/EVIDENCE_SUBSTRATE_CONTRACT_v0_1.json
PASS: json:PILOTS/MACHINES_P0299_P0301_TURN09/SOURCE/source_identity.json
PASS: json:PILOTS/MACHINES_P0299_P0301_TURN09/SOURCE_UNITS/source_unit_manifest.json
PASS: json:RUNTIME_REFERENCE_v1/schemas/BUZZ_SIDECAR_REQUEST_SCHEMA.json
PASS: schema_coverage
PASS: turn08_mutations
PASS: turn10_runtime_tests
PASS: turn10_real_source_mutations
PASS: blindness:W2_PRIMARY
PASS: blindness:W2_BLIND_RECALL
PASS: blindness:W1_NUMERIC_LITERAL
PASS: blindness:W1_QUALIFIER_LITERAL
PASS: pilot_boundary_scope
PASS: freeze_claim_boundary
=== EXIT CODE: 0 ===
```

**Verdict: PASS, exit 0, 16/16 checks, clean on 3.12.13.**

This is the *legacy* verifier. It is green because it never exercises the two things that actually
break on this machine (the runtime lock and the staging code path). Do not read this exit 0 as
"the pack verifies on 3.12.13" — system B disagrees, below.

---

## 3. Full test suite on locked 3.12.13

Run exactly as `test_runner.py:12` constructs it:

```
$ cd <TEMP>/PACK
$ PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s <TEMP>/PACK/tests -v
```

Tail:

```
======================================================================
FAIL: test_complete_stage_verifies (test_ledger_staging.StagingTests.test_complete_stage_verifies)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\sethb\AppData\Local\Temp\claude\hermes_audit_tmp\PACK\tests\test_ledger_staging.py", line 131, in test_complete_stage_verifies
    self.assertTrue(verify_staged_artifact(Path(s["path"]))["ok"])
AssertionError: False is not true

----------------------------------------------------------------------
Ran 53 tests in 3.239s

FAILED (failures=1, skipped=1)
=== EXIT CODE: 1 ===
```

And via the pack's own runner:

```
$ PYTHONDONTWRITEBYTECODE=1 python -B -m hermes_factory test
{
  "overall": "FAIL",
  "duration_seconds": 3.227
}
=== EXIT CODE: 1 ===
```

### Reproducing the claimed 53/53?

**No.** The pack's `TEST_REPORT.md` claims `Overall: **PASS**`, `Return code: 0`, 53 tests.

| Metric | `TEST_REPORT.md` claim | Measured on locked 3.12.13 / Windows |
| --- | --- | --- |
| Tests collected | 53 | **53** (count reproduces exactly) |
| Passed | 53 | **51** |
| Failed | 0 | **1** |
| Skipped | 0 | **1** |
| Exit code | 0 | **1** |

So the *collection* count reproduces; the *result* does not. Two tests behave differently, and
**neither difference is caused by the 3.12-vs-3.13 version gap** — both are environment differences.

### Failure 1 (real defect) — `test_complete_stage_verifies`

A **Windows path-separator bug in the pack's own production code**, not a version issue and not a
test bug. Exact error, reproduced directly:

```
$ python -B -c "... stage_artifact(files={'a.txt':'abc','nested/b.json':{'x':1}}) ..."
ok      : False
errors  : [
  "declared_actual_file_set_mismatch:['nested/b.json', 'nested\\\\b.json']"
]

declared (from manifest, dict-key form): ['a.txt', 'nested/b.json']
actual   (from rglob + str(Path))      : ['a.txt', 'nested\\b.json']
symmetric difference                   : ['nested/b.json', 'nested\\b.json']

os.sep is '\\' -> str(PurePath) renders with backslash on Windows
```

Root cause, `hermes_factory/staging.py` — `stage_artifact` records the manifest path from the caller's
dict key (forward slash, line 38 `"path": rel`), but `verify_staged_artifact` recomputes the on-disk
set with `str(p.relative_to(path))`, which renders `os.sep`:

```python
    actual = {
        str(p.relative_to(path)) for p in path.rglob("*")
        if p.is_file() and p.name not in RESERVED
    }
```

`staging.py:84-87` — no separator normalization.

The pack **already knows this idiom** and applies it correctly one module over, in
`build_integrity.py:34`:

```python
"path": str(p.relative_to(root)).replace("\\", "/"),
```

`staging.py` simply omits it. Proof that this is the whole cause — applying the same normalization in
a monkeypatched copy (vendor file untouched) turns the test green:

```
unpatched ok: False
sep-normalized ok: True
```

This is **platform-conditional, not version-conditional**: `str(PurePath)` has rendered with `os.sep`
across all supported CPython versions, so this fails on *any* Python on Windows and passes on *any*
Python on POSIX. Installing 3.13.5 would not fix it.

**Blast radius is narrow.** The bug only fires when a staged artifact contains a **nested** path.
The production controller stages only flat filenames — `staging.py` is called once, at
`controller.py:110`, with `files={"candidates.jsonl": ..., "worker_receipt.json": ...}`. Both are
top-level, so no separator appears and the comparison succeeds. Confirmed empirically in §4b: the
full pipeline runs to exit 0 on this machine. So this is a **latent** defect that the test suite
correctly catches but the current pipeline does not trip. It becomes live the moment any capsule
stages a subdirectory.

### Failure 2 (not a defect) — `test_machines_three_page_ingestion_if_source_available`

```
test_machines_three_page_ingestion_if_source_available ... skipped 'Machines source not mounted'
```

`tests/test_ingest_network.py:20-21`:

```python
        src=Path('/mnt/data/Machines Textbook.pdf')
        if not src.exists(): self.skipTest('Machines source not mounted')
```

A hardcoded POSIX path for the **whole 2724-page book**, which is not in the pack and not on this
machine. Self-skipping by design. Note this test would *also* need `pypdf`, which is absent.

The pack's `TEST_REPORT.md` records this same test as `... ok`, which is direct evidence the claimed
53/53 was produced **on Linux with `/mnt/data` mounted and pypdf installed** — i.e. the environment
`RUNTIME_LOCK.json` pins. It was never a Windows result.

---

## 4a. Preflight

There is no `preflight` sub-command; `verify` is the preflight (`cli.py:197` → `run_preflight`).

```
$ PYTHONDONTWRITEBYTECODE=1 python -B -m hermes_factory verify --skip-tests
HERMES EXTRACTION FACTORY ADVANCED v1.1 PREFLIGHT
OVERALL: FAIL_BLOCKING

PASS: MANIFEST_INTEGRITY
FAIL_BLOCKING: RUNTIME_LOCK
  ["runtime_mismatch:python_version:expected=3.13.5:actual=3.12.13", "runtime_mismatch:external_python_dependencies:expected={'pypdf': '5.9.0'}:actual={'pypdf': 'NOT_INSTALLED'}"]
PASS: MODEL_CERTIFICATION_REGISTRY_PRESENT
  C:\Users\sethb\AppData\Local\Temp\claude\hermes_audit_tmp\PACK\CURRENT\MODEL_CERTIFICATION_REGISTRY.json

=== EXIT CODE: 1 ===
```

Full preflight (tests included):

```
$ PYTHONDONTWRITEBYTECODE=1 python -B -m hermes_factory verify
overall: FAIL_BLOCKING
  PASS           - MANIFEST_INTEGRITY
  FAIL_BLOCKING  - RUNTIME_LOCK
  PASS           - MODEL_CERTIFICATION_REGISTRY_PRESENT
  FAIL_BLOCKING  - ADVANCED_TEST_SUITE
=== EXIT CODE: 1 ===
```

**Preflight verdict: `FAIL_BLOCKING`, exit 1.** Two of four checks fail. `MANIFEST_INTEGRITY` passing
is the useful signal: the production code is bit-for-bit as certified. The failures are both
environmental/latent, not code-drift.

`README_ADVANCED_v1_1.md` claims "Canonical preflight: PASS". **That claim is stale on this machine.**

## 4b. End-to-end fixture pipeline (extra check, to size the staging bug)

```
$ PYTHONDONTWRITEBYTECODE=1 python -B -m hermes_factory run --pilot machines \
    --mode offline-fixture --output <TEMP>/OUT
...
  "source_unit_count": 8,
  "primary_candidate_count": 52,
  "blind_candidate_count": 36,
  "union_candidate_count": 88,
  "semantic_empirical": false,
  "semantic_quality_measured": false
=== EXIT CODE: 0 ===
```

Readiness gate result — `status: READY_FOR_PROVIDER`:

```
  PASS              - SOURCE_AUTHORITY (source_units=8)
  NOT_RUN           - SOURCE_HASH (Original source bytes and expected source hash were not both supplied)
  PASS              - BUILD_INTEGRITY (current build matches immutable certified manifest)
  FAIL_BLOCKING     - RUNTIME_LOCK (expected=3.13.5:actual=3.12.13; pypdf NOT_INSTALLED)
  PASS              - SCHEMA / PROVENANCE / EVIDENCE_SPANS / EVIDENCE_HASHES / LINEAGE
  PASS              - LEDGER_INTEGRITY / STATE_RECONCILIATION / CAS_CURRENT_STATE
  PASS              - BLINDNESS
  BLOCKED_EXTERNAL  - INDEPENDENCE (primary_family=FIXTURE;blind_family=FIXTURE)
  PASS              - PRIMARY_PASS (52) / BLIND_RECALL_PASS (36)
  BLOCKED_EXTERNAL  - SEMANTIC_PROVIDER_CERTIFICATION
  FAIL_REVIEW_REQUIRED - NUMERIC_CONTROL(3) QUALIFIER_CONTROL(2) RELATIONSHIP_CONTROL(1)
                         TABLE_VISUAL_CONTROL(9) CROSS_PAGE_CONTROL(2)
  PASS              - PRECISION_REVIEW / SEMANTIC_RECEIPTS(16) / PACKAGE_INTEGRITY
  BLOCKED_EXTERNAL  - COLD_AUDIT_POLICY
  NOT_APPLICABLE    - 09D_READONLY_BOUNDARY (No 09D database supplied)
```

The mechanical runtime — ledger, CAS commit, leases, blindness allowlist, staging, packaging — works
correctly on the locked 3.12.13 interpreter. `INDEPENDENCE` and
`SEMANTIC_PROVIDER_CERTIFICATION` are `BLOCKED_EXTERNAL` precisely because both roles are the fixture;
they are the gates a real Claude CLI provider would unblock.

---

## 5. PDF hash check

```
$ sha256sum PILOTS/MACHINES_P0299_P0301_TURN09/SOURCE/Machines_P0299_P0301.pdf
4395d2ff6f0204ae2539d4e97a6901bc021346640a3ec26b78f408f878e7959e

$ python -B -c "hashlib.sha256(p.read_bytes()).hexdigest()"
bytes   : 164681
sha256  : 4395d2ff6f0204ae2539d4e97a6901bc021346640a3ec26b78f408f878e7959e
expected: 379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197
MATCH   : False
```

**Against `379a5d5c...`: MISMATCH — and this mismatch is correct and expected, not corruption.**

`PILOTS/MACHINES_P0299_P0301_TURN09/SOURCE/source_identity.json` records **both** hashes and
distinguishes them explicitly:

```json
  "source_id": "BOOK-DORSCH-5E",
  "source_title": "Understanding Anesthesia Equipment",
  "source_version_id": "BOOK-DORSCH-5E-SHA-379a5d5c7fdf",
  "source_path_original": "/mnt/data/Machines Textbook.pdf",
  "source_sha256": "379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197",
  "page_count": 2724,
  "pilot_scope_pdf_pages": [299, 300, 301],
  "pilot_derivative_sha256": "4395d2ff6f0204ae2539d4e97a6901bc021346640a3ec26b78f408f878e7959e",
```

### What each hash refers to

| Hash | Refers to | Present in pack? |
| --- | --- | --- |
| `379a5d5c...` | **The whole book** — *Understanding Anesthesia Equipment* (Dorsch 5e), **2724 pages**, originally at `/mnt/data/Machines Textbook.pdf` | **No** |
| `4395d2ff...` | **The 3-page slice** (PDF pages 299–301), 164,681 bytes — `pilot_derivative_sha256` | **Yes** — this is the file in `SOURCE/` |

So `Machines_P0299_P0301.pdf` is the **3-page derivative**, and it matches its own recorded
`pilot_derivative_sha256` **exactly**. The file is intact. The `379a5d5c...` hash you were asked to
compare against is the **whole-book** hash and was never supposed to match this file.

### Consequential finding

`379a5d5c...` is nonetheless what the *pipeline* treats as source authority:

- All 8 source units carry it:
  ```
  distinct source_sha256 in units: ['379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197']
  distinct source_version_id     : ['BOOK-DORSCH-5E-SHA-379a5d5c7fdf']
  ```
- `cli.py:84-85` hardcodes both the whole-book hash **and** a POSIX path:
  ```python
          source_pdf = Path(args.source_pdf) if args.source_pdf else Path("/mnt/data/Machines Textbook.pdf")
          source_sha = "379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197"
          if not source_pdf.exists():
              source_pdf = None
  ```

On Windows that path never exists, `source_pdf` silently becomes `None`, and the `SOURCE_HASH`
readiness gate degrades to `NOT_RUN` (seen in §4b) rather than failing. **The pilot's source-hash
authority gate cannot be satisfied on this machine without the 2724-page book**, and its silent
`NOT_RUN` degradation is easy to miss. Pointing `--source-pdf` at the 3-page derivative would *not*
help — it would hash to `4395d2ff...` and fail against the hardcoded whole-book expectation.

---

## 6. Runtime lock

`CURRENT/RUNTIME_LOCK.json` in full:

```json
{
  "external_python_dependencies": {
    "pypdf": "5.9.0"
  },
  "python_implementation": "CPython",
  "python_version": "3.13.5",
  "runtime_contract": "hermes-factory-1.1"
}
```

Measured on the locked interpreter:

```
$ python -B -c "import sys,platform,sqlite3; ..."
3.12.13 (main, May 10 2026, 19:35:37) [MSC v.1944 64 bit (AMD64)]
3.12.13 CPython
sqlite 3.50.4
pypdf NOT_INSTALLED PackageNotFoundError
pytest MISSING / pip FOUND / setuptools FOUND / wheel MISSING
```

| Locked field | Pinned | Actual | Verdict |
| --- | --- | --- | --- |
| `python_version` | `3.13.5` | `3.12.13` | **VIOLATES** |
| `python_implementation` | `CPython` | `CPython` | satisfies |
| `runtime_contract` | `hermes-factory-1.1` | `hermes-factory-1.1` | satisfies |
| `external_python_dependencies` | `{"pypdf":"5.9.0"}` | `{"pypdf":"NOT_INSTALLED"}` | **VIOLATES** |

**Verdict: the locked 3.12.13 interpreter VIOLATES `RUNTIME_LOCK.json` on two of four fields.**

`runtime_lock.py:36-38` compares all four keys by **exact equality** — no semver range, no
major.minor tolerance, no "or newer". So `3.12.13` vs `3.13.5` is a hard mismatch, and the pypdf
dependency dict is compared whole. Exact preflight output:

```
FAIL_BLOCKING: RUNTIME_LOCK
  ["runtime_mismatch:python_version:expected=3.13.5:actual=3.12.13",
   "runtime_mismatch:external_python_dependencies:expected={'pypdf': '5.9.0'}:actual={'pypdf': 'NOT_INSTALLED'}"]
```

This propagates: `RUNTIME_LOCK` is `FAIL_BLOCKING` in both the preflight (§4a) and the per-run
readiness vector (§4b).

### Reconciliation options (not applied — vendor tree is read-only)

The lock is **regenerable, not sacred**: `cli.py:198` exposes
`certify-build --refresh-runtime-lock`, which calls `write_runtime_lock()` to re-stamp the lock from
whatever interpreter is running. Three paths:

1. **Re-stamp the lock to 3.12.13 + install pypdf** — keeps the locked interpreter, requires
   installing `pypdf` (not present) and issuing a fresh certification. Note `certify-build` refuses
   unless tests pass, so the staging bug (§3) must be fixed first.
2. **Install CPython 3.13.5 + pypdf 5.9.0** — satisfies the lock as written, but conflicts with the
   Project 09D locked-interpreter rule and would *not* fix the staging failure (which is
   Windows-conditional, not version-conditional).
3. **Accept `RUNTIME_LOCK: FAIL_BLOCKING`** as a known, documented deviation for wiring work, on the
   grounds that `MANIFEST_INTEGRITY` passes and the pipeline runs to exit 0 (§4b).

The `pypdf` gap only bites PDF *ingestion* (`ingest-pdf`, and `run` without `--source-units`). The
machines pilot uses the pre-built `source_units.jsonl`, so §4b ran fine without pypdf.

---

## 7. Provider interface contract (for wiring a real Claude CLI provider)

Files: `hermes_factory/providers/{__init__,base,command,fixture}.py`, plus the actual wire contract in
`hermes_factory/semantic.py` and `hermes_factory/blindness.py`.

1. **Subclass `providers.base.SemanticProvider`** (ABC). Three abstract methods must be implemented:
   `identity()`, `capabilities()`, `execute(request)`. A fourth, `is_empirical_semantic_provider()`,
   is concrete and defaults to `True`; the fixture overrides it to `False` to force
   `SEMANTIC_PROVIDER_CERTIFICATION` to `BLOCKED_EXTERNAL`. A real Claude provider leaves it `True`.
2. **`identity() -> WorkerIdentity`** — a 6-field dataclass (`models.py:57-63`): `provider`,
   `model_alias`, `underlying_family`, `observed_version`, `role`, `certification_status`
   (default `"UNBENCHMARKED"`). `underlying_family` is load-bearing: `controller.py:254` grants the
   `INDEPENDENCE` gate **only** when primary and blind families differ, so two Claude models in the
   same family will stay `BLOCKED_EXTERNAL`.
3. **`capabilities() -> dict`** — must report `network_required`; `network_policy.py` raises
   `network_provider_forbidden_in_local_only_mode` if `True` under `--execution-mode LOCAL_ONLY`.
   A hosted Claude CLI is network-required → run `CLOUD_MODEL` or `HYBRID`, or pass `--local-provider`.
4. **`execute(request) -> dict`** — synchronous, one request in, one response out. Providers get **no**
   ledger or database authority; they return staged, noncanonical output only.
5. **Request shape** (`semantic.py:30-63`, `request_schema_version: "hermes-worker-request-1.1"`):
   `task_role` (`PRIMARY` | `BLIND_RECALL`), `work_class`, `source_class`, `capsule_id`, `run_id`,
   `source_unit`, `boundary_context`, `task_instructions`, `output_schema`, `provider_constraints`.
6. **Response shape** — must be a `dict` with an `assertions` **list**, else
   `provider_output_missing_assertions`. Each assertion must be an object with non-empty
   `proposition` and `evidence`. Optional: `subject`, `predicate`, `object_value`, `numeric_values`,
   `qualifiers`, `polarity`, `certainty`, `conditionality`, `temporality`, `comparison`,
   `relationship_direction`, `table_binding_state`, `visual_binding_state`, `uncertainty_flags`.
7. **The hard constraint: `evidence` must be an exact substring of `unit.content`.**
   `semantic.py:88-89` raises `evidence_not_exact_source_substring` otherwise, and one bad assertion
   aborts the whole work item. A Claude provider must be prompted to quote verbatim, and should
   ideally verify substring-containment itself before returning.
8. **Blindness is enforced on the request, by positive allowlist** (`blindness.py`): only the 11
   allowlisted top-level keys survive into a `BLIND_RECALL` request, and the packet is then scanned
   recursively against 18 `FORBIDDEN_DISCLOSURE_KEYS`. A blind provider must not be handed — or given
   any side channel to — primary output, or `blindness_leakage_detected` fires.
9. **Easiest wiring path: no Python subclass at all.** `JSONCommandProvider` already implements the
   contract as a subprocess bridge — it takes a command, writes one JSON request to **stdin**, reads
   one JSON response from **stdout** (non-zero rc → `provider_command_failed`; unparseable stdout →
   `provider_stdout_not_json`; stderr is captured into `provider_diagnostics`). Wire Claude as a shell
   script and pass it via `--mode external-command --primary-command "..." --blind-command "..."`
   plus `--primary-family` / `--blind-family` (set these to *different* families to earn
   `INDEPENDENCE`), `--primary-model`, `--primary-version`, and matching `--blind-*` flags.
10. **Certification is registry-controlled, not self-declared.** A provider claiming
    `certification_status` does not make it certified — `test_model_registry.py` asserts that only
    `CURRENT/MODEL_CERTIFICATION_REGISTRY.json` governs, and absent entries are `UNBENCHMARKED`.
    Default timeout is 600 s per unit.

---

## Summary of findings

| # | Finding | Severity |
| --- | --- | --- |
| 1 | `staging.py` `verify_staged_artifact` does not normalize `os.sep`; fails on any nested staged path on Windows, on every Python version. `build_integrity.py:34` has the correct idiom. | **Real defect** — latent; current pipeline stages only flat names |
| 2 | `RUNTIME_LOCK.json` pins CPython 3.13.5 + pypdf 5.9.0, compared by exact equality. Locked 3.12.13 violates on 2 of 4 fields. | **Blocking** for preflight; regenerable via `certify-build --refresh-runtime-lock` |
| 3 | `TEST_REPORT.md`'s 53/53 PASS and `README_ADVANCED_v1_1.md`'s "Canonical preflight: PASS" are **Linux-only results**, stale on Windows/3.12.13. | Documentation staleness |
| 4 | `cli.py:84` hardcodes `/mnt/data/Machines Textbook.pdf`; on Windows it silently becomes `None` and `SOURCE_HASH` degrades to `NOT_RUN` rather than failing loudly. | Silent gate degradation |
| 5 | The two verification systems disagree (`verify_factory.py` exit 0 vs `hermes_factory verify` exit 1) and `README.md` still advertises only the older one. | Confusing; prefer system B |
| 6 | Pack PDF is the 3-page derivative and matches `pilot_derivative_sha256` exactly. Not corrupted. | Clean |
| 7 | Mechanical runtime (ledger/CAS/leases/blindness/staging/packaging) fully works on 3.12.13; pipeline exit 0, `READY_FOR_PROVIDER`. | Positive |
