# Semantic Review Router Contract — v1.0

## Purpose

The semantic review router converts **review evidence** into explicit work items. It does not decide clinical truth and it does not modify Project 09D.

Inputs are append-only verifier events and optional blind-recall reconciliation rows. Outputs are deterministic `SEMCASE:` review cases.

## Required routing behavior

- `PROVENANCE_INCOMPLETE` → provenance repair + cold audit; fail closed.
- `NOT_ENTAILED` → preserve the assertion and route to cold audit / required specialists; never delete evidence.
- `PARTIAL` or `AMBIGUOUS` → precision/specialist/frontier review according to the verifier route.
- critical entailed claims → frontier adjudication remains required even when semantic entailment passes.
- `RECALL_ONLY_CANDIDATE` → blind entailment + recall review + precision review before it may join the primary corpus.
- `SAME_EVIDENCE_SEMANTIC_DISAGREEMENT` → preserve both interpretations and route to frontier adjudication; never silently deduplicate.
- exact primary/recall agreement is coverage evidence, not automatic promotion.
- `PRIMARY_ONLY` is not automatically treated as an error; recall quality is measured separately against a gold benchmark.

## Authority boundary

Every review case must keep:

```text
automatic_action_allowed = false
automatic_repair_allowed = false
automatic_selection_allowed = false
candidate_resolution_allowed = false
canonical_authority = false
generation_eligible = false
public_eligible = false
```

The router does not compare against 09D, resolve candidate identity, or authorize mass extraction.

## Certification boundary

Offline tests certify deterministic routing mechanics and non-authority. They do **not** certify a production semantic model, recall rate, reviewer accuracy, or frontier adjudicator quality.
