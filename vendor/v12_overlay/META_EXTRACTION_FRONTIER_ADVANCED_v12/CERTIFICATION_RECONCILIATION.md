# Certification Reconciliation

The original v11 `EMPIRICAL_CERTIFICATION_PHASE.json` is retained as historical evidence. It pins production manifest `afbcb997...`, while the actual v11 shipped tree computed `d9a3c508...`; v12 does not rewrite that record.

v12 introduces a separate immutable build-certification mechanism:

- `CURRENT_BUILD_MANIFEST.json` is recomputed current state.
- `CERTIFIED_BUILD_MANIFEST.json` is an explicit active certification pointer.
- `certifications/CERT-*.json` are immutable historical certification receipts.
- ordinary `verify`/preflight compares current protected bytes to the certified manifest and fails on mismatch.
- only the explicit `certify-build` operation can establish a new certification.

This closes the previous ambiguity between "hash observed during preflight" and "build certified by prior evidence."
