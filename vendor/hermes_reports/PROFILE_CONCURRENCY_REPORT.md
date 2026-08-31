# HERMES Advanced v1.1 — Fixture Concurrency Profile Report

All three configured profiles were executed against the real governed Machines/Dorsch pages 299–301 pilot after the current build was certified.

The semantic provider in these tests was deliberately the deterministic **fixture provider**, so these timings measure controller/SQLite/staging/package mechanics only. They do **not** predict cloud-model inference latency.

| Profile | Worker threads | Wall time | Peak RSS | Source units | Union candidates | Final status |
|---|---:|---:|---:|---:|---:|---|
| SAFE_4 | 4 | 1.28 s | 100,196 KB | 8 | 88 | READY_FOR_PROVIDER |
| BALANCED_8 | 8 | 1.35 s | 101,092 KB | 8 | 88 | READY_FOR_PROVIDER |
| HIGH_12 | 12 | 1.33 s | 102,224 KB | 8 | 88 | READY_FOR_PROVIDER |

All three runs preserved the same deterministic output population and stopped at the same three honest external blockers:

1. `INDEPENDENCE = BLOCKED_EXTERNAL` because both fixture workers are the same fixture family.
2. `SEMANTIC_PROVIDER_CERTIFICATION = BLOCKED_EXTERNAL` because no real model role is certified.
3. `COLD_AUDIT_POLICY = BLOCKED_EXTERNAL` because no independent semantic cold-audit model was available.

No SQLite lease collision, stale-commit, state-reconciliation, source-hash, build-integrity, runtime-lock, evidence-hash, or package-integrity failure occurred in these fixture profile runs.
