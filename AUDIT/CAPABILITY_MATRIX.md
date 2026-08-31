# Capability matrix — Meta v11 × Hermes Advanced v1.1 × 09D → integrated factory

Byte-audited 2026-08-31. Sources: `AUDIT/hermes_test_run.md`, `AUDIT/meta_test_run.md`,
`AUDIT/meta_cert_mismatch.md`, `AUDIT/09d_target_state.md`, direct code reads, and runs
executed in this session on the locked CPython 3.12.13 / Windows. "Fixture run" = this
session's reproduction (66/66 tests, run `HERMES-20260831T094954`, exit 0).

Legend: **K**=keep · **A**=adapt · **R**=replace/reimplement · **–**=absent.

| Capability | Meta v11 actual | Hermes v1.1 actual | 09D relevant state | Stronger | Final owner | K/A/R | Execution evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Source acquisition (literature transports) | Real: PubMed/CTG/medRxiv/preprint transports, exact-HTTP evidence machinery; needs requests/pydantic, 3.13.5 | PDF-only ingestion via pypdf (lazy import) | 09D consumes packages, never fetches | Meta | Meta (future lane; dep-gated) | K (vendored, not wired) | Meta 161/320 offline pass; all failures = missing 3rd-party deps |
| Source identity/versioning | source_version records, sha pins | source_identity.json + whole-book vs slice sha discipline | r3 ledger double-anchors DB digest | Hermes (simpler, verified) | Hermes | K | Full-book sha `379a5d5c…` re-verified this session; slice `4395d2ff…` matches pilot pin |
| Page artifacts (text/renders) | JATS/XML segmentation focus | Bundled page text + PNG renders + boundary context | — | Hermes (for PDF pilot) | Hermes | K | Pilot capsules carry p298–302 text/renders (rights-quarantined out of git) |
| Source units | 573-line JATS segmenter (real) | Deterministic PDF page→unit generator | — | Meta (XML), Hermes (PDF) | Both, by source type | K | Meta turn5 86/86; Hermes fixture run consumed 8 bundled units |
| Provenance/evidence spans | Evidence substrate contracts | Exact-substring evidence enforced at `semantic.py:89` + integrity gates | Carrier keeps value_text + locator spine | Hermes (enforced at runtime) | Hermes | K | EVIDENCE_SPANS/HASHES gates PASS in fixture + real runs |
| Rights metadata | rights/ machinery, quarantine dirs | rights_metadata field on units (pass-through) | Estate rights-quarantine rule | Meta (design) | Integration (.gitignore quarantine + zips as archive) | A | Textbook bytes excluded from git history at root commit |
| Assertion schema | Logical contract JSON (v0.1) | `AssertionCandidate` dataclass, invariant-validated | Carrier: subject/predicate/value_text + witness CHECK | Hermes (executable) | Hermes | K | 66/66 incl. invariant tests |
| Assertion generation (free text) | **Absent** — CTG template rules + injected stubs only | Transport implemented; needs real provider | Motion-2 slot empty, awaiting extraction | Hermes+real providers | Integration `llm_provider.py` | R (new) | opus-5: 19 assertions/74s on unit 1, 0 rejects |
| Blind recall | 76-line module, no recaller | Positive-allowlist blind transport + adversarial tests | — | Hermes | Hermes + non-Anthropic local model | K | Blindness suite green; allowlist drops 8 injection classes |
| Blindness enforcement | Verifier-side design | Allowlist + nested forbidden-key scan + mutation tests | — | Hermes | Hermes | K | `test_blindness_semantics` 6/6 on 3.12.13 |
| Numeric handling | Lexicon/regex capsules (real, 86/86) | Deterministic numeric inventory + binding specialist | assertion_quantity table exists (0 rows) | Tie (different layers) | Hermes runtime + Meta lexicons later | K | 59 numeric literals inventoried in pilot |
| Qualifier/negation | Capsule lexicons | Qualifier inventory + lexical-preservation specialist + mutation tests | assertion_qualifier table (0 rows) | Hermes (gated) | Hermes | K | Dropped-negation/may mutations detected in suite |
| Relationship direction | — | Direction-cue inventory + preservation check | — | Hermes | Hermes | K | 20 relationship literals in pilot; cue-loss mutation detected |
| Table handling | — | Detected → routed to bounded specialist queue (no overclaim) | — | Hermes | Hermes (W3 review-queued) | K | TABLE_VISUAL_CONTROL bounded queue in runs |
| Visual handling | — | Caption/text-layer only, honestly flagged | — | Hermes | Hermes; qwen2.5vl candidate for future W3 | K | IMAGE_AVAILABLE_NOT_MODEL_REVIEWED flags in routes |
| Cross-page handling | Segmenter-aware | Cross-page state + bounded review queue | — | Hermes | Hermes | K | CROSS_PAGE_CONTROL queue on Table 6-1 unit |
| Atomicity | — | Prompt contract + benchmark metric | one value per assertion row | Integration | Integration | R (new metric) | `score_role.py` atomicity_failure_rate |
| Evidence families | — | Exact-normalized-evidence grouping, no fuzzy merge | conflict surfaces never collapse | Hermes | Hermes | K | 52 families in fixture + real runs |
| Union | — | Deterministic union, no majority truth | — | Hermes | Hermes | K | 88 union candidates, dedupe by candidate_id |
| Verification (independent) | Real reconciliation state machine (ENTAILED etc.) but no judge model | Precision integrity review (deterministic) | — | Split | Hermes now; Meta verifier patterns later | A | precision_review PASS gates in runs |
| Precision review | — | Deterministic invariant re-check over union | — | Hermes | Hermes | K | PRECISION_REVIEW gate PASS |
| Risk routing (W0-W4/S0-S3/P0-P3) | — | classify_source_unit + route_families | — | Hermes | Hermes | K | risk_classification.json per run |
| Frontier escalation | — | Bounded queues + ESCALATE state | — | Hermes | Hermes | K | routes.jsonl unresolved families |
| Cold audit | — | Deterministic mechanics only; **no semantic hook** | — | Neither (gap) | **Integration: `cold_audit_semantic.py`** (third family, fail-closed) | R (new) | deepseek-r1 audit verdict in 145.8s; 5 new gate tests |
| Identity resolution | Provisional identity design (Turn-6) | — | subject_entity_id namespace | Meta (design only, least-verified code) | Integration comparator (IDENTITY_UNCERTAIN state) | A | Comparator run: 8 IDENTITY_UNCERTAIN of 88 |
| Cross-source / 09D comparison | Turn-6 comparator: 0 tests passing offline, deps missing, pins the **S00 input DB** | Read-only open + schema inventory + write-block assert only | r3 sealed `final_s03.sqlite` `fa7a9731…`, 71,824 carrier rows, Motion-2 empty | Neither sufficient | **Integration: `stages_ext/compare_09d.py`** (six reviewable states, target-drift refusal) | R (new, Meta states adopted) | 88 candidates vs 71,824 rows in 6.3s; hash matched declared target |
| Ledger (durable state) | v12 overlay describes one; no code shipped | SQLite+WAL, hash-chained events, snapshot reconciliation | 09D has its own sealed ledger (separate concern) | Hermes | Hermes | K | 11 ledger tests green; restart reconstruction test |
| Leases/heartbeat/expiry | — | Exclusive leases, TTL, expiry requeue, stale rejection | — | Hermes | Hermes | K | expired-lease + stale-worker tests green |
| Scheduler/dispatch | — | Deterministic registration + ThreadPool dispatch | — | Hermes | Hermes | K | 16 work items dispatched SAFE_4 |
| State machine | — | 13-state legal transition set | — | Hermes | Hermes | K | illegal-transition test green |
| Staging + receipts | — | Tmp→atomic rename, manifest+completion receipts | — | Hermes | Hermes | **A (fixed)** | Windows separator defect found+fixed; torn-stage tests green |
| CAS commit | — | Parent-version CAS, stale commit rejected | — | Hermes | Hermes | K | stale-commit test green |
| Restart/recovery | — | WAL + snapshot + resume command | — | Hermes | Hermes | K | restart_reconstructs test green |
| Concurrency profiles | — | SAFE_4/BALANCED_8/HIGH_12 | — | Hermes | Hermes | K | SAFE_4 exercised this session |
| Provider adapters | Injected callables (stubs) | `SemanticProvider` ABC + JSON stdin/stdout command bridge | — | Hermes | Hermes + integration wrapper | K+R | Echo/claude/ollama bridges proven end-to-end |
| Model identity/family | — | WorkerIdentity w/ underlying_family; INDEPENDENCE gate | — | Hermes | Hermes | K | Gate derives from declared families |
| Model certification registry | — | Role/W/S/benchmark-keyed registry, authority-tested | — | Hermes | Hermes + `certify_roles.py` | K+A | registry authority tests green |
| Build certification | **Defective**: verify rewrites the pin; cert `afbcb997…` ≠ shipped `d9a3c508…` | Immutable certified vs current split; versioned certs; refuses overwrite | 09D: sealed envelope ledger (gold standard) | **Hermes** | Hermes | K | CERT_0003 issued on 3.12.13; Meta pin left untouched with supersession note |
| Preflight | 41/46 static gates are string-presence (proven bypassable) | Executable gates incl. tests/lock/manifest | — | **Hermes** | Hermes | R (Meta's replaced) | 134-byte comment file passed Meta's network-interlock gate |
| Mutation tests | pytest fault-injection (dep-gated offline) | 37-class adversarial behavioral suite | 09D mutation discipline precedent | Hermes | Hermes (+5 new classes) | K+A | 66/66 incl. new same-family-auditor + crash-is-finding tests |
| Offline packaging | audit_package dirs | ZIP + independent re-hash verify | sealed envelope precedent | Hermes | Hermes | K | verify-package exit 0 on fixture package |
| 09D bridge safety | read-only design docs | mode=ro + PRAGMA query_only + write-probe | Guard hook + sealed inventory | Hermes | Hermes + comparator | K | 09D_READONLY_BOUNDARY gate PASS vs r3 |
| One-command execution | RUN_META_FACTORY.sh described in overlay only | RUN_FACTORY.sh + full CLI | — | Hermes | **Integration: `run_appliance.py`** (run→audit→compare→package) | A | Appliance validated on fixture path pieces; real run pending |

## 09D boundary settings (defaults, unchanged)

`direct_09d_insert_allowed=false` · `automatic_canonicalization=false` ·
`automatic_identity_merge=false` · `automatic_release=false`. The factory cannot
write 09D at all (ro URI + query_only + guard hook); candidates remain
`SOURCE_ASSERTION_CANDIDATE / UNREVIEWED / NON_CANONICAL` end to end.

## Verdict

Meta and Hermes were never rivals: Meta's genuinely strong planes are literature
transport, segmentation, and verifier *design*; its execution, certification and
preflight planes are the weak ones — and its advertised semantic engine has no
free-text extractor at all. Hermes Advanced v1.1's execution plane survived
independent re-testing almost intact (one real Windows defect, fixed here). The
integrated factory is therefore: **Hermes runtime + this session's real provider
plane, independent semantic cold audit, 09D comparator and benchmark/certification
loop; Meta vendored as design authority and future literature lane.**
