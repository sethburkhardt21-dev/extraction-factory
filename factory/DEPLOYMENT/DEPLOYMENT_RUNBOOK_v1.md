# Hermes Extraction Factory — Deployment Runbook v1

## Status
Architecture: `FROZEN_V1`
Reference deterministic runtime: `OFFLINE_CERTIFIED`
Semantic production deployment: `BLOCKED_PENDING_EMPIRICAL_GATES`

## Phase 0 — Verify
Run:
`./VERIFY.sh`

Do not proceed on FAIL_BLOCKING.

## Phase 1 — Establish durable state
1. Create local runtime directory.
2. Initialize SQLite ledger in WAL mode.
3. Verify event-chain integrity.
4. Mount frozen source read-only.
5. Register capsule manifests.
6. Generate current preflight.

## Phase 2 — Start sidecar
1. Start deterministic scheduler.
2. Configure provider adapters.
3. Load model certification registry.
4. Set concurrency profile SAFE_4 initially.
5. Set global RCU emergency ceiling.
6. Enable incident auto-stop.

## Phase 3 — Pilot
Execute Machines pages 299–301:
- W2 primary
- blind recall
- numeric literal
- qualifier literal
- W3 visual/table

Do not reuse the same semantic context between primary and blind recall.
Do not reveal peer outputs before deterministic reconciliation.

## Phase 4 — Score
Run:
- evidence/provenance validators
- semantic reference scoring
- addition/precision metrics
- mutation/canary checks
- independence verification

No model is certified from self-report.

## Phase 5 — Expand
If SAFE_4 pilot passes:
- expand to additional benchmark units;
- then BALANCED_8;
- only then HIGH_12.

## Phase 6 — Existing estates
Apply Turn09 routing:
- recovery where state is uncertain;
- harden/continue where incomplete;
- precision/adjudication for strong completed populations;
- no architecture-driven wholesale re-extraction.

## Failure handling
Local failure -> local retry/requeue/escalation.
Global stop only for source/ledger/accepted-artifact authority risk.

## Rollback
Rollback appends superseding state transitions.
Never delete forensic history.
