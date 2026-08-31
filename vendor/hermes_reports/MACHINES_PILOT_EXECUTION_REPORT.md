# Machines/Dorsch Pilot Execution — HERMES Advanced v1.1

## Source

- Full PDF: `Machines Textbook.pdf`
- SHA-256: `379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197`
- Full PDF pages: 2,724
- Governed pilot extraction ownership: PDF pages 299–301
- Read-only boundary context: pages 298 and 302
- Bundled deterministic source units: 8

## Current certified build

- Certification ID: `CERT-37a078672d274bcbb6c1beaa82faaa5e`
- Protected production/config manifest SHA-256: `ddecb7523bd1a62aaa8635fc521cf7979f3da51aebeba8bf7189a3c650597294`
- Runtime: Python 3.13.5
- pypdf: 5.9.0
- Canonical advanced preflight: PASS
- Advanced tests: 53 PASS

## Executed SAFE_4 governed fixture run

The final SAFE_4 run produced:

- primary candidates: 52
- blind-recall candidates: 36
- deterministic union candidates: 88
- evidence families: 52
- numeric literals: 59
- qualifier literals: 32
- relationship literals: 20
- specialist receipts: 260
- unresolved routed families: 11
- worker receipts: 16
- source hash: PASS
- build integrity: PASS
- runtime lock: PASS
- schema: PASS
- provenance: PASS
- evidence spans: PASS
- evidence hashes: PASS
- lineage: PASS
- ledger integrity: PASS
- state reconciliation: PASS
- CAS current state: PASS
- blindness transport: PASS
- precision-integrity review: PASS
- offline package integrity: PASS

Bounded semantic review queues were produced for numeric, qualifier, relationship, table/visual, and cross-page risk where deterministic code correctly refused to overclaim semantic closure.

## Correct final status

`READY_FOR_PROVIDER`

The run did **not** emit `FRONTIER_REVIEW_READY` because the only semantic providers available in this runtime were deterministic fixtures. In particular, the readiness engine blocked on:

- independent semantic model family;
- empirically certified primary/blind semantic providers;
- independent semantic cold audit.

This is the intended fail-closed behavior.

## Separate automatic-ingestion proof

The new one-command PDF path was also exercised directly against Machines pages 299–301. It automatically:

1. hashed the 150 MB source PDF;
2. confirmed the 2,724-page source;
3. ingested pages 299–301 into deterministic source units;
4. launched the SAFE_4 fixture factory;
5. executed primary + blind work;
6. reconciled/validated/packaged the run;
7. emitted `READY_FOR_PROVIDER` rather than a false semantic-ready claim.

That automatic path produced 3 page-derived source units and 93 fixture union candidates. It is an execution proof of the one-command ingestion/runtime path, not a semantic-quality benchmark.
