# Turn 10 Integrated Red-Team Report

## Scope
The v0.9 architecture, Meta-derived adoption, Machines pilot, estate routing,
validator/preflight design, Buzz/Hermes orchestration, and freeze claims were attacked as one system.

## Finding RT-01 — Architecture can freeze before model calibration, but runtime quality cannot
**Severity:** HIGH
**Finding:** The architecture is internally mature enough to freeze as a design and reference-runtime contract.
However, the semantic factory has not executed its model benchmark and no worker model is production-certified.
**Decision:** Freeze architecture/contracts as `FROZEN_V1`. Keep semantic runtime `EMPIRICAL_CERTIFICATION_BLOCKED`.

## Finding RT-02 — Evidence substrate is useful but must remain thin
**Severity:** MEDIUM
**Finding:** SOURCE_VERSION -> PAGE_ARTIFACT -> SOURCE_UNIT adds real provenance value.
It becomes architecture theater if every possible source representation is mandatory.
**Hardening:** Only TEXT/TABLE/FIGURE/EQUATION/MIXED_LAYOUT are required for textbook hot path.
STRUCTURED_JSON/IMAGE_REGION remain optional extension types.

## Finding RT-03 — Rights metadata is not hot-path extraction logic
**Severity:** LOW
**Finding:** Multi-dimensional rights metadata is useful downstream, but source rights uncertainty must not stall private extraction.
**Hardening:** Rights remain extension metadata and cannot block private extraction unless explicit policy says so.

## Finding RT-04 — Machines pilot needed boundary context
**Severity:** HIGH
**Finding:** Pages 299–301 contain cross-page table/section context; a strict 3-page semantic scope can sever antecedents or continuation.
**Hardening:** Added pages 298 and 302 as READ-ONLY boundary context. They do not expand extraction ownership.

## Finding RT-05 — Blindness must be testable from mounted inputs
**Severity:** HIGH
**Finding:** Prompt-level "blindness" is insufficient.
**Hardening:** Added a capsule blindness inspection validator. Primary and blind-recall capsules are forbidden from containing peer outputs or answer keys.

## Finding RT-06 — SQLite is sufficient for the first durable ledger
**Severity:** MEDIUM
**Finding:** Postgres/cloud infrastructure would add deployment complexity without solving a current bottleneck.
**Decision:** SQLite + WAL + append-only hash-chained events is the v1 reference ledger.

## Finding RT-07 — A model must not be the scheduler authority
**Severity:** HIGH
**Finding:** Conversational state cannot safely own leases, current versions, or commit order.
**Hardening:** Implemented a deterministic reference ledger/scheduler with CAS commit semantics and restart reconstruction.

## Finding RT-08 — Buzz native launch is not verified
**Severity:** HIGH
**Finding:** The architecture allows Buzz + Hermes, but this Turn cannot prove Buzz's installed environment can directly spawn/control Hermes.
**Decision:** `SIDECAR` is the v1 production-default deployment mode. Native Buzz launch remains `EXPERIMENTAL` until EXP-019 passes.

## Finding RT-09 — Existing strong estates must not be normalized by re-extraction
**Severity:** HIGH
**Finding:** New architecture can create waste by redoing strong SOL/Gemini extraction.
**Decision:** Preserve Turn09 minimum-rework routing. Conversion/hardening is preferred over virgin re-extraction.

## Finding RT-10 — Freeze language can easily overclaim
**Severity:** CRITICAL
**Finding:** Calling the whole factory "production ready" would be false before model benchmark, live worker adapters, and live pilot execution.
**Decision:** Split freeze state:
- Architecture/contracts: `FROZEN_V1`
- Reference deterministic runtime: `OFFLINE_CERTIFIED`
- Semantic worker runtime: `NOT_EMPIRICALLY_CERTIFIED`
- Production extraction deployment: `BLOCKED_PENDING_EMPIRICAL_GATES`

## Red-team conclusion
The design is ready to freeze. The semantic production system is not yet empirically proven.
The remaining blockers are execution proof, not another architecture expansion.
