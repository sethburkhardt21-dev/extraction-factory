# Meta v11 Baseline Audit

- Input SHA-256: `52eb089760a12a67a461a443e437f84d2e25cb7a8c9eab34b4431234f5f23fb4`
- Python files: 134
- Python LOC: 28,290
- Full regression suite with importlib mode: 320/320 PASS.
- Existing `run_offline_verification.sh` was stale and stopped at missing `pubmed_rag/c5_validation_tests.py`.
- `EMPIRICAL_CERTIFICATION_PHASE.json` pins production hash `afbcb997...`, while the shipped v11 tree computes `d9a3c508...`. Historical evidence is preserved; it is not silently rebound.
- Preflight computed current hashes but had no separate immutable certified-build artifact to compare against.
- Numerous static checks are explicitly structural-presence checks; v12 adds behavioral tests for critical control surfaces.
- v11 had no durable SQLite lease/CAS/staged-commit runtime comparable to the new v12 control layer.
