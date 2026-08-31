# Blind Recall Contract — v1.0

## Purpose

Blind recall is a coverage lane, not an authority lane. A recall worker receives immutable source units without seeing primary extractor assertions and independently enumerates clinically meaningful atomic assertion candidates.

## Independence

The recall packet must not contain primary assertions, extractor reasoning, extractor provenance, interpretation IDs, candidate resolution, 09D comparison, or prior verifier output.

## Output state

Recall assertions remain `NOT_VERIFIED`. They cannot automatically repair, merge, overwrite, select, promote, or release primary assertions.

## Reconciliation states

- `PRIMARY_AND_RECALL_EXACT`
- `SAME_EVIDENCE_SEMANTIC_DISAGREEMENT`
- `PRIMARY_ONLY`
- `RECALL_ONLY_CANDIDATE`

An exact agreement is coverage evidence only. A recall-only candidate is preserved for later verification. Same-evidence semantic disagreement is preserved rather than deduplicated.

## Certification boundary

This turn certifies the blind-recall packet, output invariants, and reconciliation mechanics offline. It does not certify a production recall-model backend or semantic recall rate on a real clinical corpus.


## Persistence

The hash-bound blind-recall pipeline persists recall assertions, quarantine, reconciliation rows, source/primary input hashes, and exact recall-worker provenance. Primary assertions are introduced only after recall extraction, at deterministic reconciliation time.

A production recall backend is not certified until it passes the real semantic recall benchmark.
