# Turn 5 — Semantic Factory Freeze

Status: **PASS_OFFLINE_SEMANTIC_FACTORY**

## Frozen hashes

- Production code/contract SHA-256: `6404f12057c79af88a894fbd02100aef4956682fb6e13ff12c1503a61241c6c6` (77 files)
- Verification/test SHA-256: `8df8be24a7d4a19d2538b76b8036833b253c7fa3d00b67e7f21755cc82ba4307` (37 files)
- Unique regression tests: **306/306 PASS**
- 09D bridge tests: **210/210 PASS**
- Hand-authored semantic gold: **35 cases**
- Independent verifier gold: **24 cases**

## Semantic plane now implemented

`primary assertions -> blind verifier -> numeric/negation/certainty/conditionality/qualifier/table/visual/relationship/atomicity specialists -> blind recall -> deterministic reconciliation -> risk-aware semantic review router`

Verification is append-only. Source assertions remain `NOT_VERIFIED`; semantic results are separate `VERIF:` evidence. Blind recall never sees primary extractor output before it runs. Recall-only candidates and same-evidence disagreements become `SEMCASE:` review work and are never automatically merged or repaired.

### Table adjudication

SG-016 was intentionally changed from `ENTAILED` to `PARTIAL`: the retained source was only the bare cell `5 mg` without a header proving that the value represented a dose. This is now a regression case proving that an overconfident general reviewer cannot override missing table semantics.

### Visual binding

Figure caption text is explicitly distinguished from the actual image/plot payload. Figure-derived claims route through `VISUAL_BINDING`; caption-only evidence cannot become downstream-semantic-ready as if the image itself had been inspected.

## Controlled factory demonstration

- Primary assertions: 8
- Verification events: 8
- Semantically ready: 2
- Entailed but not ready: 1
- Not entailed: 3
- Partial/ambiguous: 2
- Blind recall assertions: 3
- Recall-only candidates: 1
- Same-evidence semantic disagreements: 1
- Open semantic review cases: 8
- Frontier-adjudication cases: 7

All primary assertions remained `NOT_VERIFIED`. Automatic repair, selection, canonical authority, generation/public eligibility, and mass extraction remained false.

## Still not certified

A production general-text model has not been benchmarked/certified. The visual-image worker is not implemented; only the fail-closed visual route exists. Real-article semantic precision/recall has not yet been measured. 09D comparison and cross-source support/conflict adjudication remain later stages. Native public source canaries and target database execution remain outstanding.

**MASS EXTRACTION AUTHORIZED: NO**
