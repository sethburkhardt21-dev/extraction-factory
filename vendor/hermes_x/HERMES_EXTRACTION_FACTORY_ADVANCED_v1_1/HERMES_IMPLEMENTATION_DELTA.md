# HERMES Advanced v1.1 — Implementation Delta

## New executable production package

A new `hermes_factory/` runtime was added. It is separate from the historical `RUNTIME_REFERENCE_v1/` tree and is the advanced successor execution path.

Implemented in this advancement:

1. **Typed semantic candidate model**
   - source/version/unit identity
   - exact evidence + hash
   - proposition
   - numeric/qualifier/relationship fields
   - table/visual/cross-page states
   - worker/run lineage
   - enforced `SOURCE_ASSERTION_CANDIDATE / UNREVIEWED / NON_CANONICAL`

2. **Primary semantic worker transport**
   - provider-neutral request contract
   - exact-evidence validation
   - worker receipts

3. **Blind recall transport by positive allowlist**
   - forbidden peer/gold/canonical/count fields are excluded by construction
   - nested leakage backstop
   - adversarial injection tests

4. **Deterministic literal inventories**
   - numeric values/ranges/units
   - qualifier/negation/modal/conditional/comparison cues
   - directional relationship cues

5. **Deterministic union**
   - preserves distinct candidate origins
   - no majority vote
   - no semantic last-writer-wins

6. **Evidence-family builder**
   - conservative grouping on exact normalized evidence within source unit
   - preserves primary-only/blind-only and proposition variants

7. **Deterministic specialist control layer**
   - numeric preservation/binding-risk checks
   - qualifier-loss checks
   - relationship-direction cue checks
   - table/visual honesty routing
   - cross-page routing
   - outcomes: supported vs bounded semantic review/defer

8. **Precision integrity reviewer**
   - exact source-span support
   - evidence hash
   - source hash
   - candidate invariants
   - candidate remains noncanonical

9. **Risk/escalation router**
   - hard W3 triggers
   - P0 integrity separation
   - no invented empirical soft thresholds

10. **Cold-audit mechanics**
    - deterministic reproducible sampling
    - independent semantic auditor remains unclaimed

11. **Expanded SQLite/WAL execution ledger**
    - legal state machine
    - exclusive active leases via partial unique index
    - heartbeat
    - lease expiry/requeue
    - staging artifacts
    - validation state
    - CAS accepted commit
    - stale result rejection
    - append-only hash-chained events
    - state/history reconciliation
    - accepted-state commit proof
    - restart reconstruction

12. **Torn-commit protection**
    - staging directories
    - explicit artifact manifest
    - completion receipt
    - declared-vs-actual file set
    - per-file hash/size verification
    - validation before atomic commit

13. **Concurrent worker execution**
    - pre-registers complete primary/blind work graph
    - thread-pool dispatch
    - SQLite per-worker controller connections
    - tested two-controller lease race
    - SAFE_4 / BALANCED_8 / HIGH_12 profiles exposed as executable configuration

14. **Failure/retry mechanics**
    - active work can be abandoned to retry/fail deterministically
    - expired work is requeued
    - stale old workers cannot regain authority

15. **Generic real provider bridge**
    - JSON request on stdin / JSON result on stdout
    - no invented Hermes/Claude CLI command
    - can wrap a real local/cloud model launcher later

16. **Offline fixture provider**
    - exercises full transport and state machinery
    - explicitly marked `FIXTURE_NOT_EMPIRICAL`
    - cannot satisfy semantic-provider certification

17. **Network policy**
    - `LOCAL_ONLY` rejects providers declared network-required
    - `CLOUD_MODEL`/`HYBRID` may permit them

18. **General deterministic PDF ingestion**
    - SHA-256 pinning
    - page selection
    - pypdf text-layer extraction
    - exact deterministic chunks
    - source-unit hashes
    - table/figure/equation risk flagging without pretending visual interpretation

19. **Build integrity / certification split**
    - `CURRENT_BUILD_MANIFEST.json` is recomputed
    - `CERTIFIED_BUILD_MANIFEST.json` is immutable certification evidence
    - ordinary verify never re-certifies changed code
    - added/changed production-path file blocks manifest integrity
    - model certification registry and root launcher are included in the production manifest

20. **Model-certification authority**
    - provider/CLI self-claims are not authoritative
    - certification must come from the model certification registry keyed by provider/model/role/W/S/benchmark
    - registry is currently intentionally empty/unbenchmarked

21. **Runtime lock**
    - exact Python implementation/version
    - exact pypdf version used for canonical PDF ingestion

22. **Read-only 09D SQLite bridge mechanics**
    - `mode=ro`
    - `PRAGMA query_only=ON`
    - behavioral write mutation test
    - no actual current 09D database was supplied to this Hermes-only run

23. **Fail-closed readiness derivation**
    - `PASS`
    - `FAIL_BLOCKING`
    - `FAIL_REVIEW_REQUIRED`
    - `NOT_RUN`
    - `NOT_APPLICABLE`
    - `BLOCKED_EXTERNAL`
    - `NOT_RUN != PASS`
    - bounded review queues may remain review-ready; integrity/provider blockers may not

24. **General offline handoff package builder**
    - self-contained ZIP
    - per-file hash/size manifest
    - CRC test
    - extraction-and-rehash verification

25. **Canonical CLI**
    - `test`
    - `verify`
    - `certify-build`
    - `ingest-pdf`
    - `run`
    - `status`
    - `resume` state recovery
    - `package`
    - `verify-package`

26. **Root one-entrypoint launcher**
    - `./RUN_FACTORY.sh ...`

## Code growth

Frozen v1 production/reference Python: **558 lines across 10 Python files**.

Advanced v1.1 `hermes_factory/` implementation at this stage: **2,826 lines across 33 Python files**, before counting the historical code and test suite.

The increase is implementation, not a replacement architectural essay.
