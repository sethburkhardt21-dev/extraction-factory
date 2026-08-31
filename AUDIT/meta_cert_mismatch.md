# META v11 — Independent verification of the certification/build mismatch

**Audit date:** 2026-08-31
**Auditor lane:** independent recomputation (claim treated as unverified on entry)
**Subject tree (read-only):**
`C:\Users\sethb\.codex\.chatgpt-projects\g-p-6a22140cf3d08191bef2524866d4c6fe\extraction_factory\vendor\meta_x`
**Context overlay (not source of truth):**
`...\extraction_factory\vendor\v12_overlay\META_EXTRACTION_FRONTIER_ADVANCED_v12`
**Interpreter:** `C:\Users\sethb\.local\python\project09d-cpython-3.12.13\python.exe -B` (no network, no installs)
**Scratch (all scripts written here, never in the vendor tree):**
`C:\Users\sethb\AppData\Local\Temp\claude\meta_cert_tmp`

**Bottom line up front:** the claim is **CONFIRMED**. The shipped tree hashes to
`d9a3c5087f55913b57d00f5029f71aafd809312f0dc7979b04279ef0d36f4900`. It does **not** hash to the
value the certification pins. The certification evidence is attached to an earlier, no-longer-present
build.

---

## 1. What EMPIRICAL_CERTIFICATION_PHASE pins, over what, by what algorithm

### 1.1 The pinned value

`vendor\meta_x\EMPIRICAL_CERTIFICATION_PHASE.json:30`

```json
"production_code_manifest_sha256": "afbcb997f8f3454c890fa01661c7a1a0ec16b00379b43266a31993e96b39824f",
"regression_tests_passed": 93,
"status": "PASS_WITH_EXTERNAL_BLOCKERS"
```

The prose companion `EMPIRICAL_CERTIFICATION_PHASE.md:9-18` states the same hash and adds the two
numbers that make the mismatch legible without any hashing at all:

> - Production manifest files: **47**
> - Production manifest SHA-256: `afbcb997f8f3454c890fa01661c7a1a0ec16b00379b43266a31993e96b39824f`
> - Regression tests: **93/93 PASS**

Its closing paragraph (`EMPIRICAL_CERTIFICATION_PHASE.md:122`) makes that hash load-bearing rather
than decorative:

> The next allowed transition is **public-host native canary certification on a network-capable
> runtime using the exact frozen production code hash**. Only a `PASS` certificate with
> `transport=native_http`, `mass_unlock_eligible=true`, and the same production-code hash can
> authorize a full extraction.

So `afbcb997…` is the identity that gates the single most consequential state transition in the
system — the mass-extraction unlock.

### 1.2 The file set

Defined by `frontier_core/readiness.py:80-81`:

```python
def production_manifest_files(root: Path) -> List[Path]:
    return sorted(set(production_python_files(root) + production_contract_files(root)))
```

- `production_python_files` (`readiness.py:20-45`) globs `clinicaltrials/canonical`, `preprints/src`,
  `drug_reference/drugref`, `warehouse`, `bridge_09d` recursively for `*.py`, plus four named files
  each from `pubmed_rag/` and `frontier_core/`, plus the four top-level `frontier_*.py` entrypoints.
  It then drops anything whose path parts include `archive_not_production`,
  `experimental_enrichment_not_certified`, `tests`, `__pycache__`, `.pytest_cache`.
- `production_contract_files` (`readiness.py:48-77`) is a hand-listed allowlist of 26 candidate
  contract paths (SQL schemas, `SCHEMA_CONTRACT.md`, the 15 `bridge_09d/contracts/*.md`, the two
  lock files, the two `09D_*` boundary/authority files), filtered to those that exist.

### 1.3 The algorithm (quoted verbatim)

`frontier_core/readiness.py:124-134`:

```python
def file_sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()


def code_manifest(root: Path) -> Dict[str, Any]:
    entries=[{"path":str(p.relative_to(root)),"sha256":file_sha256(p)} for p in production_manifest_files(root)]
    payload=json.dumps(entries,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return {"files":entries,"sha256":hashlib.sha256(payload).hexdigest(),"count":len(entries)}
```

Read precisely: SHA-256 of raw bytes per file; entries are `{path, sha256}` dicts in
`production_manifest_files` order; the payload is compact JSON (`separators=(",",":")`,
`ensure_ascii=False`, `sort_keys=True` — which sorts *dict keys*, **not** list order); the aggregate
is SHA-256 of that payload.

The call site that produces the pinned artifact is `frontier_preflight.py:70` (`cm=code_manifest(ROOT)`),
written to disk at `frontier_preflight.py:83-86`.

### 1.4 One portability defect worth flagging before recomputing

`str(p.relative_to(root))` renders with `os.sep`, and the ordering comes from `sorted()` over `Path`
objects. `WindowsPath` compares case-insensitively; `PosixPath` compares case-sensitively. The digest
is therefore **platform-dependent for byte-identical trees**. This matters for the recompute method
(§2) and is a real defect in its own right (§5.3).

---

## 2. Recomputation over the shipped tree

Two scripts, both in `C:\Users\sethb\AppData\Local\Temp\claude\meta_cert_tmp`:

- `recompute_manifest.py` — reimplements `production_python_files` / `production_contract_files` /
  `code_manifest` verbatim, **and** side-loads the vendored `frontier_core/readiness.py` itself
  (`sys.dont_write_bytecode = True`, run under `-B`) to confirm the reimplementation is faithful.
- `recompute_posix.py` — the platform-faithful recompute: every file hashed from raw bytes, entries
  ordered the way `PosixPath` (the build platform) orders them, then the exact payload/digest step.

### 2.1 Result

```
files hashed          : 83
RECOMPUTED sha256     : d9a3c5087f55913b57d00f5029f71aafd809312f0dc7979b04279ef0d36f4900
claim A (certification): afbcb997f8f3454c890fa01661c7a1a0ec16b00379b43266a31993e96b39824f
claim B (preflight)    : d9a3c5087f55913b57d00f5029f71aafd809312f0dc7979b04279ef0d36f4900
matches claim A       : False
matches claim B       : True
```

**Recomputed manifest hash of the shipped tree:**
`d9a3c5087f55913b57d00f5029f71aafd809312f0dc7979b04279ef0d36f4900` over **83 files**.

### 2.2 Why the POSIX ordering is the correct recompute, not a thumb on the scale

Run natively on Windows the same code yields `07edd7258932854265fdaecf453fb9218f7750843a73e6eeca0296579d27f841`
(and the side-loaded vendored module agrees with my reimplementation exactly, so the reimplementation
is faithful). That divergence is entirely a sort-order artifact, and it is provable rather than
assumed. `order_probe.py` re-hashes the manifest entries recorded inside `FRONTIER_PREFLIGHT.json`
under several orderings:

| Probe | Ordering | Digest |
|---|---|---|
| A | as recorded in the file | `d9a3c508…` |
| B | `PurePosixPath.parts` order | `d9a3c508…` |
| C | plain string order | `d9a3c508…` |
| D | casefolded string order (Windows) | `0eba2221…` |
| E | casefolded parts order (Windows) | `0eba2221…` |
| F | backslash paths, recorded order | `d182f9c4…` |

The recorded order is identical to both POSIX orderings and diverges from the Windows ordering first
at index 74 (`schema/PHYSICAL_PROJECTION_CONTRACT.json` vs `schema/frontier_bigquery.sql`).

Independently, `recompute_manifest.py` compares my freshly-computed per-file digests against the 83
entries recorded in `FRONTIER_PREFLIGHT.json`:

```
in recorded only: []
in current only : []
content differs : []
byte-identical file set: True
```

Every one of the 83 files is byte-identical to what the recorded manifest describes. So
`d9a3c508…` is not merely "the number written in a file I chose to trust" — it is what the shipped
bytes produce under the build platform's own ordering, and I verified the bytes independently.

---

## 3. Comparison against both claimed values

| Value | Where it appears | Files | Matches shipped tree? |
|---|---|---|---|
| `afbcb997f8f3454c890fa01661c7a1a0ec16b00379b43266a31993e96b39824f` | `EMPIRICAL_CERTIFICATION_PHASE.json:30`, `.md:11`, and all 6 empirical evidence artifacts | 47 | **NO** |
| `d9a3c5087f55913b57d00f5029f71aafd809312f0dc7979b04279ef0d36f4900` | `FRONTIER_PREFLIGHT.json`, `FRONTIER_PREFLIGHT.txt`, `09D_FRONTIER_EXTRACTION_STATE.md:13` | 83 | **YES** |

**The shipped tree matches `d9a3c508…`. The certification evidence is attached to `afbcb997…`, a
build that is not present in this package.** The mismatch is real, not a documentation typo: the
file *count* differs by 36 (47 → 83) and the regression *count* differs by 227 (93 → 320), so the two
identities describe materially different software, not two spellings of one build.

### 3.1 Which artifacts are stranded on the old identity

Every empirical artifact `EMPIRICAL_CERTIFICATION_PHASE.json` lists as `evidence[]` — the runs that
constitute the actual certification — carries `production_code_manifest_sha256: afbcb997…`:

- `evidence/fault_injection/NATIVE_PATH_LOCAL_HTTP_CERTIFICATION.json` (`status: PASS`)
- `evidence/fault_injection/LOCAL_HTTP_CERTIFICATION.json` (`status: PASS`)
- `evidence/native_canary_current/CTG_NATIVE_CANARY_ATTEMPT.json` (`status: BLOCKED_ENVIRONMENT_DNS`)
- `evidence/current_code_external_canary/{ctg,medrxiv,biorxiv}.json`
  (`status: PASS_LIVE_SCHEMA_CONFORMANCE`, `certified_at: 2026-08-30T02:04:03Z`)
- plus `evidence/native_canary_v4/ctg/91d15be0-….orchestration.json`

These are the exact-transport HTTP proofs, the retry/resume proofs, and the schema-conformance
proofs. **All of them certify code that is not what ships.** Note the irony in the directory name:
`evidence/current_code_external_canary/` is no longer current code.

### 3.2 The chronology, from filesystem mtimes

| Time (2026-08-30) | Event |
|---|---|
| 18:30:00 | `EMPIRICAL_CERTIFICATION_PHASE.json` / `.md` frozen at `afbcb997…`, 47 files, 93 tests |
| 18:32:04 | `bridge_09d/turn6_factory.py` written |
| 18:32:58 | `bridge_09d/comparator_09d.py`, `bridge_09d/identity_resolution.py` written |
| 18:34:48 | `frontier_core/readiness.py` **and** `frontier_preflight.py` edited |
| 18:37:38 | `FRONTIER_PREFLIGHT.json` / `.txt` **overwritten** — now `d9a3c508…`, 83 files |
| 18:38:04 | `09D_FRONTIER_EXTRACTION_STATE.md` written, correctly naming `d9a3c508…` and 320/320 |

The certification was frozen, then Turn-6 code landed, then the manifest *definition* itself was
edited (`readiness.py` is inside its own hashed set, so editing it changes the hash by construction),
then the preflight was re-run and silently re-pinned the identity. The certification file was never
touched again. The manifest confirms the shape of the change: 34 of the 83 entries are `bridge_09d/`
(19 Python, 15 contracts), including six Turn-6-era files —
`comparator_09d.py`, `identity_resolution.py`, `turn6_factory.py`, and the
`09D_READONLY_COMPARATOR` / `IDENTITY_RESOLUTION` / `TURN6_AUDIT_PREP` contracts. **The certified
47-file build predates the entire Turn-6 identity/comparator plane.**

### 3.3 The self-invalidating evidence pointer

`EMPIRICAL_CERTIFICATION_PHASE.json:3` lists `"FRONTIER_PREFLIGHT.json"` as its *first* evidence
item. That file was overwritten at 18:37:38 and now describes a different build. The certification's
own primary citation has been mutated out from under it, and nothing detected that — because
(verified by grep across all `*.py`) **no code path anywhere in the tree reads
`EMPIRICAL_CERTIFICATION_PHASE.json`.** The certification record has exactly zero machine enforcement.

---

## 4. What the interrupted v12 advancement pass concluded

The overlay is **documentation only** — five markdown files, no code. One of them
(`README.md`) is byte-identical to `vendor\meta_x\README.md`
(`e65035ebaee3d45dd88173bceb4c74b1a511cbd4b39dd7e2036312a9a9048a4a`), i.e. a carried-over v11 README
still titled "Meta Extraction Frontier v10 — 09D Turn 5"; it contributes nothing to the
reconciliation and should not be read as a v12 statement.

**`META_V11_BASELINE_AUDIT.md`** — states the mismatch plainly:

> `EMPIRICAL_CERTIFICATION_PHASE.json` pins production hash `afbcb997...`, while the shipped v11 tree
> computes `d9a3c508...`. Historical evidence is preserved; it is not silently rebound.

and diagnoses the root cause correctly: "Preflight computed current hashes but had no separate
immutable certified-build artifact to compare against." It also flags that many v11 static checks are
structural-presence only, and that `run_offline_verification.sh` is stale (stops at a missing
`pubmed_rag/c5_validation_tests.py`).

**`CERTIFICATION_RECONCILIATION.md`** — states the remedy and, critically, declines to fake agreement:

> The original v11 `EMPIRICAL_CERTIFICATION_PHASE.json` is retained as historical evidence. It pins
> production manifest `afbcb997...`, while the actual v11 shipped tree computed `d9a3c508...`; v12
> does not rewrite that record.

It then specifies a four-part mechanism: `CURRENT_BUILD_MANIFEST.json` (recomputed state),
`CERTIFIED_BUILD_MANIFEST.json` (active certification pointer), immutable `certifications/CERT-*.json`
receipts, verify-compares-and-fails, and "only the explicit `certify-build` operation can establish a
new certification" — closing "the previous ambiguity between 'hash observed during preflight' and
'build certified by prior evidence.'"

**`META_IMPLEMENTATION_DELTA.md`** — lists "immutable certified/current build distinction" and
"explicit `certify-build` operation" as the first two v12 additions, alongside a SQLite/WAL job
ledger, leases, hash-chained events, CAS commits, and behavioral tests for "preflight/build binding".
It ends with an honest scope limit: "No cloud model was run. No real semantic precision/recall
certification is claimed."

**`REMAINING_BLOCKERS.md`** — does not mention the hash mismatch, treating it as addressed by the
mechanism above. Its open items are empirical/external (model certifications, real-source
precision/recall benchmark, public native canaries, 09D SQLite comparison, Postgres/BigQuery
execution) plus scale proofs. Closing line: "Offline fixture success does not satisfy these empirical
gates."

### 4.1 Does my recomputation agree with the overlay's account?

**Yes — fully, on the substance, and I confirmed two of its independently checkable numbers.**

- The overlay's central factual claim (`afbcb997` pinned, `d9a3c508` computed by the shipped tree) is
  exactly what I derived from the bytes without relying on the overlay.
- Its baseline metrics reproduce: I count **134** `.py` files and **28,290** LOC in `meta_x`, matching
  `META_V11_BASELINE_AUDIT.md:4-5` precisely.
- Its diagnosis — preflight had no immutable certified artifact to compare against — is confirmed at
  the code level in §5.

**Two corrections/extensions the overlay does not state:**

1. The overlay frames the mismatch as v11 pinning one hash while the tree "computed" another. My
   evidence shows the sharper mechanism: the preflight **overwrote its own evidence file in place**
   at 18:37:38, four minutes after `readiness.py` — a file inside its own hashed set — was edited.
   The mismatch was not a drift that went unnoticed; it was *manufactured by running the verifier*.
2. The overlay does not note that `EMPIRICAL_CERTIFICATION_PHASE.json` cites the very file that was
   overwritten as its first evidence item, nor that nothing in the codebase reads the certification
   file at all. Both sharpen the severity.

**One caution:** `CERTIFICATION_RECONCILIATION.md` and `META_IMPLEMENTATION_DELTA.md` are written in
the present tense ("v12 introduces", "Added a durable local execution layer"), but **none of the
described mechanism exists in this overlay or in `meta_x`.** A filesystem search for
`CERTIFIED_BUILD_MANIFEST.json`, `CURRENT_BUILD_MANIFEST.json`, `CERT-*.json`, and
`RUN_META_FACTORY.sh` finds them **only** under the sibling Hermes package
(`vendor\hermes_x\HERMES_EXTRACTION_FACTORY_ADVANCED_v1_1\`) and `vendor\hermes_reports\` — never
under Meta. Consistent with "interrupted advancement pass": the design was written down, the port was
not performed. **Read those two files as a specification, not as a description of shipped state.**

---

## 5. VERIFY vs CERTIFY separation in Meta

### 5.1 Meta has no such separation. The verification entrypoint rewrites the certified identity.

**The rewrite: `frontier_preflight.py:83`**

```python
(ROOT/"FRONTIER_PREFLIGHT.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
```

with `report["production_code_manifest"] = cm` from `frontier_preflight.py:70,74` and the human-readable
twin written at `frontier_preflight.py:86`. This is unconditional: no existence check, no
`FileExistsError` guard, no versioning, no comparison against a prior pin, no separate operator
gesture. Running the verifier **is** the re-certification. That single line is what produced the
18:37:38 overwrite.

**The compare: `frontier_core/gate.py:14-17`**

```python
    expected=(report.get("production_code_manifest") or {}).get("sha256")
    current=code_manifest(root)["sha256"]
    if not expected or expected!=current:
        raise RuntimeError(f"active production code changed since preflight: expected={expected} current={current}")
```

This half is correct in isolation — pure read-compare-and-raise, writes nothing, and it is what every
network-capable CLI calls (`clinicaltrials/canonical/run_extraction.py:41`,
`preprints/src/pipeline.py:269`, `preprints/src/run_all.py:197`, `pubmed_rag/run_pubmed.py:255`,
`frontier_orchestrator.py:79`, `frontier_external_canary.py:83`).

**But the pin it enforces is self-refreshing.** `require_frontier_preflight` reads `expected` out of
whatever `FRONTIER_PREFLIGHT.json` currently says, and `frontier_preflight.py:83` can rewrite that
file at will. The gate therefore enforces "the code matches the last time someone ran the preflight",
never "the code matches the build the evidence certifies". Any mismatch is dissolved by re-running
the verifier — which is precisely what happened.

The consequence propagates into the unlock chain. `frontier_orchestrator.py:79` takes
`code_sha=pre['production_code_manifest']['sha256']` and stamps it into the canary certificate it
issues (`frontier_orchestrator.py:120`); `frontier_orchestrator.py:34` then refuses full extraction if
a canary certificate disagrees with it. That interlock is sound *given* a trustworthy pin — and the
pin is the rewritable file.

### 5.2 How the certified/current split is supposed to work — the sibling package does it correctly

`vendor\hermes_x\HERMES_EXTRACTION_FACTORY_ADVANCED_v1_1\hermes_factory\build_integrity.py` implements
the discipline the v12 overlay describes, and the contrast is line-for-line instructive:

| Concern | Hermes | Meta |
|---|---|---|
| Observed state | `write_current_manifest` → `CURRENT_BUILD_MANIFEST.json` (`build_integrity.py:49-54`), freely rewritable | conflated — `FRONTIER_PREFLIGHT.json` is both observed state and the pin |
| Establishing certification | `certify_build` only (`build_integrity.py:57`), an explicit CLI verb (`cli.py:198`) | none — implicit side effect of `frontier_preflight.py:83` |
| Overwrite protection | `build_integrity.py:85-86` raises `FileExistsError("certificate_already_exists; create a new versioned certificate instead of overwriting")`; `cli.py:68-70` allocates `CERTIFIED_BUILD_MANIFEST_0001.json`, `_0002.json`, … | none |
| Evidence precondition | `build_integrity.py:59-66` refuses without a test report whose `overall == "PASS"`, and binds `test_report_sha256` into the certificate (`:81`) | none |
| Verification | `verify_build` (`build_integrity.py:92-111`) is pure read-compare; returns `FAIL_BLOCKING` with `missing` / `added` / `changed` file lists; **writes nothing** | `require_frontier_preflight` compares, but against a rewritable pin |
| Claim boundary | recorded in the certificate itself (`build_integrity.py:73-74,82`): `certification_scope: "OFFLINE_MECHANICAL_BUILD"`, `semantic_model_certification_included: False` | asserted in prose only |

The decisive structural difference: in Hermes, `verify_build` **cannot** become `certify_build`. In
Meta, the only verification entrypoint *is* the certification path.

### 5.3 A second, latent defect: the digest is not portable

`readiness.py:132` uses `str(p.relative_to(root))` and orders by `sorted()` over `Path`. Hermes
normalizes at `build_integrity.py:34`:

```python
"path": str(p.relative_to(root)).replace("\\", "/"),
```

and sorts by that normalized string (`build_integrity.py:26`). Meta does neither. As measured in
§2.2, byte-identical trees yield `d9a3c508…` on POSIX and `0eba2221…` on Windows. Any future
verification run on a different OS would report `production code changed since preflight` against a
tree that had not changed by a single byte — and under current practice the natural "fix" is to
re-run the preflight, which silently re-pins. This defect and the missing verify/certify separation
compound each other.

---

## 6. Verdict

**The mismatch is real.** The certified build is `afbcb997f8f3454c890fa01661c7a1a0ec16b00379b43266a31993e96b39824f`
— a 47-file production manifest with 93 passing regression tests, frozen 2026-08-30 18:30:00, and the
build against which every empirical artifact in `evidence/` was actually run: the native-path exact
HTTP transport certification, the localhost fault-injection and retry/resume proofs, the CTG native
canary attempt, and the three external schema-conformance canaries. The shipped build is
`d9a3c5087f55913b57d00f5029f71aafd809312f0dc7979b04279ef0d36f4900` — an 83-file manifest with 320
passing regressions, which I recomputed independently from raw bytes using the tree's own
`code_manifest` algorithm under the build platform's ordering, and cross-checked entry-by-entry
against the recorded manifest (83/83 byte-identical, zero added, zero removed, zero differing). The
36 added files include the entire Turn-6 identity/comparator plane — `identity_resolution.py`,
`comparator_09d.py`, `turn6_factory.py` and their three contracts — none of which existed when the
empirical certification was frozen. This is not a stale label on unchanged code; the certified build
and the shipped build are materially different software. The mechanism is documented by the
filesystem: `readiness.py` (a file inside its own hashed set) was edited at 18:34:48, and the
preflight was re-run at 18:37:38, overwriting `FRONTIER_PREFLIGHT.json` — which
`EMPIRICAL_CERTIFICATION_PHASE.json:3` names as its own first piece of evidence — with the new
identity. Nothing objected, because no code path in the tree reads the certification file at all, and
because Meta's only verification entrypoint (`frontier_preflight.py:83`) rewrites the pin rather than
checking it.

**The honest remediation, in dependency order.** (1) **Leave `afbcb997…` exactly as written.** The
certification and all six evidence artifacts are a truthful record of a real build; editing them to
say `d9a3c508…` would attach passing HTTP-transport and canary evidence to code that never ran those
tests, converting a visible inconsistency into an invisible forgery. This is the whole principle:
certification evidence stays attached to the code that generated it, and the two are never made to
agree by moving the label. (2) **Mark `afbcb997…` superseded** by adding a *new* sibling record — a
build-lineage note stating that `afbcb997…` (47 files, 93 tests) was certified 2026-08-30 18:30 and
superseded by `d9a3c508…` (83 files, 320 tests) at 18:37 without re-certification, and that
`EMPIRICAL_CERTIFICATION_PHASE.json`'s evidence pointer to `FRONTIER_PREFLIGHT.json` is dangling
because that file was overwritten. Never add this by editing the certification. (3) **Treat the
shipped tree as UNCERTIFIED for empirical HTTP/transport/canary purposes** until those runs are
re-executed against `d9a3c508…`. Specifically, the `frontier_orchestrator.py:122` unlock path must
not accept `afbcb997…`-era evidence — and it currently would not, since
`frontier_orchestrator.py:34` compares against the live preflight; the exposure is that the preflight
is trivially re-pinned, not that the comparison is absent. (4) **Port the Hermes discipline into
Meta before any re-certification**, so the repair is not undone the next time someone runs the
verifier: split `write_current_manifest` from an explicit, test-report-gated, overwrite-refusing
`certify_build`; make preflight/verify pure read-compare that fails closed; and normalize path
separators and sort order (`replace("\\","/")` per `build_integrity.py:34`) so the digest stops
depending on the operating system. Until step 4 lands, any hash agreement Meta reports is an
agreement it is free to manufacture, and should be read as such.

---

## Appendix — reproduction

```bash
# from the scratch dir; vendor tree is never written to
cd C:/Users/sethb/AppData/Local/Temp/claude/meta_cert_tmp

# faithful recompute + entry-by-entry diff vs the recorded manifest
C:/Users/sethb/.local/python/project09d-cpython-3.12.13/python.exe -B recompute_manifest.py \
  <meta_x> C:/Users/sethb/AppData/Local/Temp/claude/meta_cert_tmp

# platform-faithful (POSIX-ordered) digest — the authoritative number
C:/Users/sethb/.local/python/project09d-cpython-3.12.13/python.exe -B recompute_posix.py <meta_x>

# ordering-sensitivity probe
C:/Users/sethb/.local/python/project09d-cpython-3.12.13/python.exe -B order_probe.py <meta_x>
```

Digests observed:

| Quantity | Value |
|---|---|
| Shipped tree, POSIX ordering (authoritative) | `d9a3c5087f55913b57d00f5029f71aafd809312f0dc7979b04279ef0d36f4900` |
| Shipped tree, Windows ordering (artifact) | `0eba2221f030095ec0476a1d1c7f3fba6c93e2d8abded235074dc941a586a4d1` |
| Certification pin (unreproducible from this tree) | `afbcb997f8f3454c890fa01661c7a1a0ec16b00379b43266a31993e96b39824f` |
| Verification manifest, recorded | `eecc2e1039973428be780f49a353f92fe1ddec0ab66282ac0db43056e396b9b8` (40 files) |

No file in either vendor tree was created, modified, or deleted during this audit.
