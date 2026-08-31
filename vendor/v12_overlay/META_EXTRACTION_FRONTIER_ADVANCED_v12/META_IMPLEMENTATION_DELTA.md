# Meta v12 Implementation Delta

Added a durable local execution layer without replacing Meta's mature semantic engine:

- immutable certified/current build distinction;
- explicit `certify-build` operation;
- SQLite/WAL job ledger;
- legal state machine;
- exclusive leases and expiry recovery;
- hash-chained event history;
- CAS accepted commits;
- staged result receipts and artifact hash validation;
- fail-closed readiness derivation;
- self-contained offline package builder/verifier;
- one canonical `RUN_META_FACTORY.sh` entrypoint;
- offline fixture execution through Meta's actual semantic factory;
- behavioral/adversarial tests for state, blindness, staging, 09D read-only behavior, readiness, and preflight/build binding;
- repaired canonical offline verification script.

No cloud model was run. No real semantic precision/recall certification is claimed.
