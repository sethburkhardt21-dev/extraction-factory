# 09D comparator target state — read-only audit

**Purpose.** Pin the CURRENT 09D comparator target for the read-only
extraction-vs-09D comparison bridge, and record how the two extraction packs'
existing 09D pins relate to it.

**Audit date:** 2026-08-31
**Mode:** strictly read-only. Nothing under `releases\` was created, modified,
or deleted. The sealed database was opened only through
`sqlite3.connect(<file-uri>?mode=ro&immutable=1, uri=True)`.
**Interpreter:** `C:\Users\sethb\.local\python\project09d-cpython-3.12.13\python.exe`
run with `-B` (and `-I -S -B` for the verifier, which requires it).
**Only file written by this audit:** this document.

---

## 0. Headline

The correct comparator target is the **terminal S03 database inside the third
sealed envelope (`r3`)**:

| Field | Value |
| --- | --- |
| Path | `C:\Users\sethb\.codex\.chatgpt-projects\g-p-6a22140cf3d08191bef2524866d4c6fe\releases\r3\Project_09D_Milestone_A_v2\Project_09D_Milestone_A_Verified_Evidence_Checkpoint_v2\database\final_s03.sqlite` |
| Filename | `final_s03.sqlite` |
| **sha256** | **`fa7a97313dc5bbd9b2fbb61b9124a4ecef5c318ad5d070eeefe67816a210f4a3`** |
| Bytes | `1760145408` |
| Anchoring ledger sha256 | `542d3052478789294170a11d5b580a0b8830b4c60fd1ede1535508b38dde1642` |
| Built from commit | `3025950` on branch `project09d-milestone-a-v2-remediation` |
| Verifier result | exit `0`, `VERIFIED` (re-run fresh-process during this audit) |

Neither extraction pack currently pins this. See §5.

---

## 1. Envelope contents (top 2 levels)

Command:

```
Get-ChildItem -LiteralPath <r3> -Recurse -Depth 1 -File
```

Top level of `releases\r3\Project_09D_Milestone_A_v2\`:

```
DIR                   Project_09D_Milestone_A_Verified_Evidence_Checkpoint_v2
DIR                   verification
      594433  2026-08-13 14:43:51  Project_09D_Milestone_A_v2_RELEASE_LEDGER.json
         263  2026-08-13 14:43:51  RELEASE_COMPLETE.json
```

Second level — evidence checkpoint subdirectories:

```
acquisition  architecture  benchmark  database  environment  evidence
governance   reports       rollbacks  runtime    source       stages    tests
```

plus `milestone_a_manifest.json` (7121 bytes) at the checkpoint root, and under
`verification\`: `verify_release.py` (3394 bytes), `contracts\`, `src\`.

**Identification:**

- **Primary SQLite database — exactly one.** A full recursive walk of the
  envelope returns a single database file:
  `Project_09D_Milestone_A_Verified_Evidence_Checkpoint_v2\database\final_s03.sqlite`
  (1,760,145,408 bytes, mtime 2026-08-13 14:41:03). There is no second `.sqlite`,
  `.sqlite3`, or `.db` anywhere inside the envelope.
- **Ledger:** `Project_09D_Milestone_A_v2_RELEASE_LEDGER.json` (594,433 bytes) at
  the envelope root.
- On-disk inventory matches the sibling provenance record: 87 files across 29
  directories = 85 ledger-anchored artifacts + the ledger + `RELEASE_COMPLETE.json`.

---

## 2. Hashes

Command: `Get-FileHash -Algorithm SHA256`

| File | sha256 | Bytes |
| --- | --- | --- |
| `final_s03.sqlite` | `fa7a97313dc5bbd9b2fbb61b9124a4ecef5c318ad5d070eeefe67816a210f4a3` | 1760145408 |
| `Project_09D_Milestone_A_v2_RELEASE_LEDGER.json` | `542d3052478789294170a11d5b580a0b8830b4c60fd1ede1535508b38dde1642` | 594433 |
| `RELEASE_COMPLETE.json` | `0d50aeb55205276c4cbd8db2e8f2ddefcf9bdb1dc8ba013b6c0d5391abc25dc1` | 263 |

**Ledger hash check: MATCH — no discrepancy.** The computed ledger digest equals
the expected
`542d3052478789294170a11d5b580a0b8830b4c60fd1ede1535508b38dde1642`
byte for byte, and equals `release.ledger_sha256` in
`releases\PROVENANCE_r3_Project_09D_Milestone_A_v2.json`.

**Database hash is doubly anchored inside the ledger.** The ledger records
`fa7a9731…` for the DB in two independent places:

- `artifacts[16]` → `{path: …/database/final_s03.sqlite, sha256: fa7a9731…, bytes: 1760145408}`
- `evidence.s03` → `{path: …/database/final_s03.sqlite, sha256: fa7a9731…, build_id: 954a24c9c131708844fbafb6a1d17861b6838c2d52d69c162736354cbde810a1}`

Both equal the freshly computed digest. The trust chain is therefore closed:
DB bytes → ledger anchor → ledger digest → out-of-band expected digest.

---

## 3. Verifier — fresh process, exit 0

The envelope vendors its own verifier at
`verification\verify_release.py`. `releases\README.md` documents the invocation
and states that `-I -S -B` is mandatory (the verifier checks `sys.flags` at
startup and exits `3` without them), and that the expected digest must be
supplied out of band because the verifier deliberately refuses to read it from
the envelope it is checking.

Command actually run (cwd `releases\r3`, which is *outside* the envelope):

```
C:\Users\sethb\.local\python\project09d-cpython-3.12.13\python.exe -I -S -B ^
  Project_09D_Milestone_A_v2\verification\verify_release.py ^
  --expected-ledger-sha256 542d3052478789294170a11d5b580a0b8830b4c60fd1ede1535508b38dde1642 ^
  Project_09D_Milestone_A_v2
```

**Exit code: `0`.** The verifier wrote nothing anywhere — no abort was needed.
Tail of output:

```json
{
  "artifact_count": 85,
  "contract_version": "2.0.0",
  "evidence": {
    "cross_bindings_checked": 52,
    "documents_checked": [ 26 documents ],
    "evidence_directory": "Project_09D_Milestone_A_Verified_Evidence_Checkpoint_v2",
    "manifest_sha256": "ff3905327db334645a17f05317c61fa7c7cd047be36d3e06d4a7baf2b46a5172",
    "status": "EVIDENCE_VERIFIED"
  },
  "ledger_sha256": "542d3052478789294170a11d5b580a0b8830b4c60fd1ede1535508b38dde1642",
  "publication_qualified": false,
  "release_name": "milestone-a-v2",
  "release_payload_verified": true,
  "release_version": "0.2.0",
  "status": "VERIFIED"
}
```

Every field reproduces the `verification.result` block recorded in
`PROVENANCE_r3_Project_09D_Milestone_A_v2.json` (artifact_count 85, 52
cross-bindings, evidence manifest `ff390532…`, `publication_qualified: false`).
The envelope has not drifted since it was sealed on 2026-08-13.

---

## 4. Database contents (opened `mode=ro&immutable=1`)

SQLite library version reported: **3.50.4** (the locked interpreter's).

Schema shape: **276 tables** in `sqlite_master` (275 excluding `sqlite_`
internals), 201 indexes, 190 triggers, 41 views. 253 of 275 tables are
non-empty; 3,389,277 rows total.

### 4.1 S04 carrier for inherited assertions

The carrier table is **`source_assertion_candidate`**.

```
select count(*) from source_assertion_candidate;   -->  71824
```

**71,824 — matches the expected value exactly.** Breakdown:

| Dimension | Value |
| --- | --- |
| `ingest_state` | `REGISTERED` × 71,824 (no `QUARANTINED`, no `DEFERRED`) |
| `intake_package_id` | `FROZEN_PARENT_BACKFILL` × 71,824 (the sole row in `ingest_package_intake`) |
| Motion-1 witnessed (`source_resource_id IS NOT NULL`) | **71,824** |
| Motion-2 witnessed (`ingest_locator_id IS NOT NULL`) | **0** |

The sibling `assertion` table also holds exactly 71,824 rows, consistent with
`stages/S04/stage_result.json`'s
`inherited_assertion_count = carrier_row_count = 71824`.

### 4.2 `source_assertion_candidate_witness_by_kind` — CORRECTION

**This is not a table. It is a named CHECK constraint on
`source_assertion_candidate`.** The task brief anticipated a table with a row
count; that premise is wrong and the corrected finding is recorded here so the
bridge does not go looking for a table that will never exist.

Evidence:

```
select type, name, tbl_name from sqlite_master where name = 'source_assertion_candidate_witness_by_kind';
  -->  NONE

select type, name, tbl_name from sqlite_master where sql like '%source_assertion_candidate_witness_by_kind%';
  -->  [('table', 'source_assertion_candidate', 'source_assertion_candidate')]
```

The constraint text, read verbatim out of the sealed `sqlite_master` (it is the
final table-level constraint before `) WITHOUT ROWID`):

```sql
CONSTRAINT source_assertion_candidate_witness_by_kind CHECK(
     (source_resource_id IS NOT NULL AND ingest_locator_id IS NULL)
  OR (source_resource_id IS NULL
      AND ingest_locator_id IS NOT NULL
      AND parent_assertion_id IS NULL
      AND source_locator_id IS NULL
      AND raw_cell_id IS NULL
      AND carried_status IS NULL
      AND carried_confidence_basis IS NULL
      AND carried_source_era IS NULL)
)
```

Zero `--` comment lines are stored in the table SQL, matching the provenance
record's `verified_in_sealed_schema` claim.

**"Present but empty" resolves cleanly, just against the right object.** The
constraint is present; its **Motion-2 branch holds zero rows** (0 rows with
`ingest_locator_id` set, and `ingest_source_locator` itself has 0 rows). This is
exactly the state the provenance describes: *"First envelope whose carrier can
legally hold Motion-2 (extracted corpus) rows. It holds none yet."*

This is the single most important fact for the extraction bridge: **r3 is the
first sealed schema that will accept extracted Motion-2 rows, and the extraction
lane's output has not yet entered it.** A comparison against r3 is therefore a
comparison against an empty Motion-2 slot, not against rival extracted content.

### 4.3 Fifteen largest tables by row count

| Rows | Table |
| ---: | --- |
| 2,714,366 | `raw_import_cell` |
| 182,705 | `raw_import_record` |
| 71,824 | `source_assertion_candidate` |
| 71,824 | `assertion` |
| 43,497 | `clinical_value_candidate_ledger` |
| 24,612 | `procedure_consideration` |
| 17,678 | `regional_controller_edge` |
| 15,387 | `equipment_source_item_ledger` |
| 13,262 | `source_locator` |
| 9,934 | `regional_controller_node` |
| 9,519 | `special_population_source_assertion` |
| 8,954 | `search_document_evidence_v4` |
| 8,777 | `search_route_member_v4` |
| 8,603 | `search_route_group_v4` |
| 8,323 | `search_alias_policy` |

Other tables of interest to an extraction comparator: `candidate_registry`
(2,233), `concept_source_assertion` (4,407), `drug_candidate_mention` (2,756),
`disease_candidate_claim` (1,357), `equipment_source_assertion` (1,140),
`crisis_source_assertion` (987), `regional_source_assertion` (737),
`clinical_value_source_assertion` (641). Empty and therefore diagnostic:
`assertion_qualifier` (0), `assertion_quantity` (0),
`candidate_promotion_event` (0), `ingest_conflict_candidate` (0),
`ingest_source_locator` (0).

### 4.4 The sealed stage chain, by digest

Read from `Project_09D_Milestone_A_Verified_Evidence_Checkpoint_v2\stages\S0*\stage_result.json`.
The parent/child digests link into a single chain and confirm the documented
order **S00 → S01 → S02 → S04 → S03**:

| Stage | Parent sha256 | Child sha256 |
| --- | --- | --- |
| S01 | `11f9e315…4aee` (S00 input) | `b1ca5494…b743` |
| S02 | `b1ca5494…b743` | `2ddd4837…064a` |
| S04 | (from S02) | `4fdc6a22…32e5` |
| S03 | `4fdc6a22…32e5` | **`fa7a9731…f4a3`** ← sealed terminal |

Every stage carries `endpoint_classification: UNSEALED_STRUCTURAL_MIGRATION_CHECKPOINT`.
S02 recorded `candidate_count 2233 / drug_candidate_count 676 / governance_count 3624`;
S04 recorded `carrier_row_count 71824`, `legacy_predicate_code_count 3633`;
S03 recorded `build_id 954a24c9…810a1` and document counts
`CANDIDATE_REVIEW 2233 / CANONICAL_INTERNAL 2244 / GOVERNED_GENERATION 0 / PUBLIC 0`.

**The chain's root input digest `11f9e315…4aee` matters for §5** — it is what
the Meta pack pins.

### 4.5 Endpoint status — do not upgrade this wording

From the ledger's `endpoint` block and the verifier output:

```
checkpoint                  UNSEALED_STRUCTURAL_MIGRATION_CHECKPOINT
database                    FINALIZED_UNSEALED_NONPRODUCTION
runtime                     UNSEALED_NONPRODUCTION
automatic_selection_allowed false
publication_qualified       false
```

A built, structurally verified release is **not** a publication-qualified
release. Any bridge document quoting this target must carry the caveat.

---

## 5. What the two extraction packs currently pin

### 5.1 Meta — `extraction_factory\vendor\meta_x\09D_READONLY_AUTHORITY.json`

Schema `frontier-09d-readonly-authority-1.0`. What it pins:

| Key | Pinned value | Status against current r3 |
| --- | --- | --- |
| `frozen_checkpoint_database.relative_path` | `03_portable/canonical_anesthesia_knowledge.sqlite` | **Different artifact** — not the sealed output DB |
| `frozen_checkpoint_database.sha256` | `11f9e3150e5775f452cd90be7aa33dcb6c3a8df4fc9c3810f41b45248f6d4aee` | **Byte-accurate, but it is the chain INPUT (S00), not the output** |
| `frozen_checkpoint_database.bytes` | `1669615616` | accurate |
| `frozen_checkpoint_database.availability_in_current_turn` | `NOT_PRESENT` | stale — the file **is** present locally |
| `git_tree_sha` | `0e626962ccc64e11ae2fa5ff09e4780b55c40377` | resolves as a **commit** (mislabelled), 156 commits behind current HEAD |
| `ref` / `repository` | `main` / `sethburkhardt21-dev/Project_09D_Database_Structure_Implementation` | frame does not correspond to local state (all work is on `project09d-milestone-a-v2-remediation`, never pushed) |
| `authoritative_artifacts` (9 entries) | git blob SHA-1s | still resolve at current HEAD — see below |

**Verified findings.**

1. Meta's pinned checkpoint DB **exists on disk** at
   `C:\Users\sethb\.codex\.chatgpt-projects\g-p-6a22140cf3d08191bef2524866d4c6fe\checkpoint_work\extracted\Project_Canonical_Anesthesia_Knowledge_Platform_09D_MACHINE_REMEDIATED_CHECKPOINT_v1\03_portable\canonical_anesthesia_knowledge.sqlite`,
   1,669,615,616 bytes, and hashes to exactly `11f9e315…4aee`. **The pin is not
   wrong — it is aimed one layer upstream.** That digest is precisely
   `stages/S01/stage_result.json`'s `source_database_sha256` / `parent_sha256`:
   the pre-migration parent that the whole S01→S02→S04→S03 chain was built from.
   Its `availability_in_current_turn: NOT_PRESENT` is stale.
2. Meta's `git_tree_sha` is actually a **commit** object, `0e62696`
   ("fix: align project09d benchmark purpose contract"). It is an ancestor of the
   r3 build commit `3025950` and sits **156 commits** behind the live HEAD.
3. Meta's nine `authoritative_artifacts` blob SHA-1s **still resolve at current
   HEAD** — spot-checked `src/project09d/candidates.py`
   (`c973be7555be9788b632adf4a4129e8e038888ec`),
   `architecture_v1_1/04_TARGET_DOMAIN_MODEL.md`
   (`5877b899467794a964d95c20aac0e1632e6f887a`) and
   `migrations/S02/forward.sql` (`d73950848534c719c1c784cb16caba8f633a5a1d`),
   all three exact. Those files simply have not changed since `0e62696`; the pins
   are still valid but they are not evidence that the *database* is current.
4. Meta's `observed_implementation_constraints` remain accurate against r3:
   `current_s02_package_kind: FROZEN_PARENT_BACKFILL` matches the carrier's sole
   intake package, and `write_allowed: false`,
   `automatic_selection_allowed: false`,
   `candidate_to_canonical_by_status_update_forbidden: true`,
   `extraction_lane_max_authority: RESOLUTION_READY` are all consistent with the
   sealed endpoint block.

**Verdict — Meta: DOES NOT MATCH the current r3 DB.** It pins the chain's frozen
*parent input* (`11f9e315…`), not the sealed *terminal output* (`fa7a9731…`), at
a commit 156 behind HEAD, and it predates the S04 carrier and the
witness-by-kind amendment entirely. Its pinned bytes are still honest — nothing
here is corrupt or fabricated — so this is a **scope gap, not a corruption**.

### 5.2 Hermes — `…\hermes_x\HERMES_EXTRACTION_FACTORY_ADVANCED_v1_1\CONTRACTS\EVIDENCE_SUBSTRATE_v0_1\09D_READONLY_BRIDGE_CONTRACT_v0_1.json`

543 bytes, `bridge_version: 0.1`. Full content is policy only:

- `direct_09d_insert_allowed: false`
- `automatic_canonicalization_allowed: false`
- `automatic_identity_merge_allowed: false`
- `automatic_release_allowed: false`
- `factory_output_role: AUDIT_READY_CANDIDATE_AND_EVIDENCE`
- `projection_must_preserve`: 11 items — `assertion_identity`, `exact_evidence`,
  `source_locator`, `provenance`, `qualifiers`, `numeric_structure`,
  `relationships`, `uncertainty`, `review_status`, `model_lineage`,
  `semantic_decision_receipts`

**Verdict — Hermes: pins NO 09D identity at all.** There is no hash, no path, no
commit, no database reference, no version anywhere in the file. It therefore
neither matches nor mismatches the current r3 DB — it is **unanchored**, and
cannot detect 09D drift by construction. Its policy clauses are all still
consistent with the sealed endpoint (r3 is `publication_qualified: false`,
`automatic_selection_allowed: false`), so nothing in it needs retracting; it
simply has no comparator target to be right or wrong about.

### 5.3 Historical pin vs current reality — summary

| | Meta | Hermes |
| --- | --- | --- |
| Pins a 09D database? | Yes — the S00 input | **No** |
| Digest pinned | `11f9e315…4aee` | — |
| Digest of current target | `fa7a9731…f4a3` | `fa7a9731…f4a3` |
| Match? | **No** (upstream artifact) | **No pin to compare** |
| Pinned bytes still accurate? | Yes, verified | n/a |
| Aware of S04 carrier / 71,824 rows? | No | No |
| Aware of witness-by-kind CHECK? | No | No |

Neither pin should be overwritten. Meta's `11f9e315…` is a correct and useful
record of the chain root and should stay as history; a **new comparator-target
version** should be *added* alongside it rather than replacing it, so the
pre-migration identity and the sealed-output identity are both retrievable.

---

## 6. Is there a newer candidate than sealed r3?

### 6.1 Live worktree — no competing database

Live worktree:
`…\Project_09D_Database_Structure_Implementation\.worktrees\project09d-milestone-a-v2-remediation`

- Branch `project09d-milestone-a-v2-remediation`, HEAD `29f7649` at audit time
  (HEAD advances; do not pin it).
- The r3 build commit `3025950` ("feat: carrier witness-by-kind binding
  (owner-signed S04 amendment)") **is an ancestor of HEAD** — the envelope was
  built from real branch history, and the branch has advanced by exactly **2
  commits** since:
  - `399ac23 feat: corpus-pack intake emitter (Motion-2 P0b)`
  - `29f7649 fix(guard): add staged-09d-copy rule for the writable sealed-DB copies (RISK-001)`
- Those two commits touched **no schema, no migrations, no architecture pack**.
  Changed files: `.claude/hooks/guard_immutable_paths.py`, `docs/MODULE_MAP.*`,
  `src/project09d/ingest.py`, and four test/support files. So the live tree has
  Motion-2 *emitter code* but no Motion-2 *data* and **no schema drift from the
  sealed r3**.
- **A full recursive search of the live worktree returns ZERO `.sqlite`,
  `.sqlite3`, or `.db` files.** There is no live database artifact anywhere in
  it. (Note: `Grep`/`rg` cannot see into `.worktrees\` — it is both gitignored
  and a dot-directory — but `Get-ChildItem`/`Glob`/`Read` descend normally, and
  this search used the former.)

### 6.2 `releases\` — no r4

`releases\` holds exactly three envelopes (`Project_09D_Milestone_A_v2\`,
`r2\`, `r3\`), their three sibling `PROVENANCE_*.json` files, `README.md`,
`.rgignore`, and `rebuild_S04_2026-08-12\` (refused-build failure evidence, no
envelope). **There is no r4.** r3 is the newest sealed envelope.

### 6.3 Staged copies outside the tree — decoys to name explicitly

`C:\Users\sethb\project09d_db_copies_2026-08-17\Project 09D Help for other AI\`
(the RISK-001 staging copies made for other AIs; all files now read-only,
covered by the `staged-09d-copy` guard rule) contains two databases:

| File | Bytes | sha256 | What it is |
| --- | --- | --- | --- |
| `r3_final_s03.sqlite` | 1760145408 | `fa7a97313dc5bbd9b2fbb61b9124a4ecef5c318ad5d070eeefe67816a210f4a3` | **byte-identical mirror** of the sealed r3 DB |
| `s04_pilot.sqlite` | 1744953344 | `2dcc81b3853eb1839ac9f913cd999279c034640b4b3f9b7d6aacc703131a8670` | a **working pilot child** — NOT sealed chain state |

`s04_pilot.sqlite` has a **later mtime** (2026-08-13 23:57) than the sealed DB
(14:41) and is an obvious trap: newer on disk, but it is a working child that
has never entered the sealed lineage, carries no ledger anchor, and is verified
by nothing. **A comparator must not target it.** The `r3_final_s03.sqlite` copy
*is* faithful (verified identical this audit) and may be used as a convenience
read path, but the sealed original remains the authority — a copy outside the
envelope has no ledger anchoring it and could drift without detection.

### 6.4 Conclusion

**The sealed r3 database is the correct comparator target.** It is the newest
sealed envelope, it is the only ledger-anchored database, its verifier passes
fresh-process at exit 0, the live worktree holds no database at all, and the
only two commits since its build commit changed no schema. Project documentation
independently designates r3 as current chain state.

---

## 7. Recommended comparator target declaration

Add this as a **new version** in both packs. Do not overwrite Meta's
`frozen_checkpoint_database` block — re-label it as the chain root and add the
target beside it.

```json
{
  "comparator_target_version": "09d-r3-sealed-1.0",
  "declared_at": "2026-08-31",
  "mode": "READ_ONLY",
  "write_allowed": false,

  "target_database": {
    "role": "SEALED_TERMINAL_S03_OUTPUT",
    "path": "C:\\Users\\sethb\\.codex\\.chatgpt-projects\\g-p-6a22140cf3d08191bef2524866d4c6fe\\releases\\r3\\Project_09D_Milestone_A_v2\\Project_09D_Milestone_A_Verified_Evidence_Checkpoint_v2\\database\\final_s03.sqlite",
    "sha256": "fa7a97313dc5bbd9b2fbb61b9124a4ecef5c318ad5d070eeefe67816a210f4a3",
    "bytes": 1760145408,
    "open_with": "sqlite3 URI, mode=ro&immutable=1"
  },

  "anchoring": {
    "ledger_sha256": "542d3052478789294170a11d5b580a0b8830b4c60fd1ede1535508b38dde1642",
    "evidence_manifest_sha256": "ff3905327db334645a17f05317c61fa7c7cd047be36d3e06d4a7baf2b46a5172",
    "artifact_count": 85,
    "verifier_exit_code": 0,
    "verified_at": "2026-08-31"
  },

  "source": {
    "source_commit": "3025950",
    "source_branch": "project09d-milestone-a-v2-remediation",
    "note": "commit BUILT FROM, not branch HEAD; the branch advances"
  },

  "chain": {
    "order": ["S00", "S01", "S02", "S04", "S03"],
    "root_input_sha256": "11f9e3150e5775f452cd90be7aa33dcb6c3a8df4fc9c3810f41b45248f6d4aee",
    "terminal_output_sha256": "fa7a97313dc5bbd9b2fbb61b9124a4ecef5c318ad5d070eeefe67816a210f4a3"
  },

  "carrier": {
    "table": "source_assertion_candidate",
    "total_rows": 71824,
    "motion_1_rows": 71824,
    "motion_2_rows": 0,
    "intake_package_id": "FROZEN_PARENT_BACKFILL",
    "witness_constraint": {
      "name": "source_assertion_candidate_witness_by_kind",
      "kind": "CHECK_CONSTRAINT_NOT_TABLE",
      "present": true,
      "motion_2_branch_populated": false
    }
  },

  "endpoint": {
    "checkpoint": "UNSEALED_STRUCTURAL_MIGRATION_CHECKPOINT",
    "database": "FINALIZED_UNSEALED_NONPRODUCTION",
    "publication_qualified": false,
    "automatic_selection_allowed": false
  },

  "supersedes_historical_pin": {
    "meta_x_frozen_checkpoint_database_sha256": "11f9e3150e5775f452cd90be7aa33dcb6c3a8df4fc9c3810f41b45248f6d4aee",
    "relationship": "the historical pin is the chain ROOT INPUT (S00 parent), not the sealed output; it stays valid as history and must not be deleted"
  },

  "do_not_target": {
    "s04_pilot_sqlite_sha256": "2dcc81b3853eb1839ac9f913cd999279c034640b4b3f9b7d6aacc703131a8670",
    "reason": "working pilot child outside the sealed lineage; newer mtime, no ledger anchor, verified by nothing"
  }
}
```

### Guidance for the bridge

1. **Compare against `fa7a9731…f4a3` only.** Re-hash before trusting; the file is
   sealed and must not change, so any deviation is a real alarm.
2. **Treat r3's Motion-2 slot as empty by design.** Zero extracted rows is the
   expected state, not a failure. Extraction lands in working children and enters
   the sealed lineage only via a future owner-signed wave.
3. **Never write.** The `sealed-release` guard rule refuses writes to
   `releases\` from `Edit`/`Write` **and** from `Bash`/`PowerShell`. Reads,
   listings, hashes, and verifier runs are all permitted.
4. **Do not pin the live HEAD.** It advances. Pin the branch name and the build
   commit `3025950` instead.
5. **Never describe this target as publication-qualified.** It is built and
   structurally verified; it is not authorized for clinical execution, automatic
   selection, candidate promotion, or public release.

---

## 8. Provenance of this document

Every value above was derived during this audit from live bytes: hashes from
`Get-FileHash`, envelope inventory from `Get-ChildItem -Recurse`, verifier block
from an actual fresh-process exit-0 run, all counts from read-only SQLite
queries against the sealed database, and all git facts from `git` against the
live worktree. Nothing was copied from prose without re-derivation.

This file sits outside any git repository, so
`tests/unit/test_documentation_coordinates.py` does not watch it and a stale
figure here will fail nothing. Re-derive before trusting. The sealed digests
(`fa7a9731…`, `542d3052…`, `11f9e315…`, `ff390532…`) are frozen by seal and are
safe to cite; the live HEAD, the commit-count deltas, and the staged-copy
inventory all drift and must be re-checked.
