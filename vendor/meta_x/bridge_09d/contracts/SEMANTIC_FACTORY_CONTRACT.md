# Semantic Factory Contract — v1.0

## Purpose

The semantic factory is the executable control plane between deterministic source evidence and later 09D audit/governance.

It composes, in this order:

```text
primary NOT_VERIFIED assertions
        ↓
independent blind entailment verifier
        ↓
deterministic numeric / qualifier / relationship / risk capsules
        ↓
optional blind recall worker (source-only; primary outputs hidden)
        ↓
primary ↔ recall reconciliation
        ↓
deterministic semantic review router
        ↓
explicit specialist / precision / frontier / cold-audit work cases
```

## Invariants

- verifier and recall lane bind the same production code/contract hash;
- primary assertions are never mutated;
- recall assertions remain `NOT_VERIFIED`;
- recall-only claims do not automatically join the primary corpus;
- same-evidence semantic disagreement is preserved;
- deterministic hard contradictions cannot be waived by a reviewer;
- critical claims can remain semantically entailed while still requiring frontier adjudication;
- no automatic repair, selection, candidate resolution, 09D comparison, canonical authority, generation, or public authority is granted.

## Meaning of semantic readiness

`downstream_semantic_ready = true` means only that the current semantic contract found sufficient source entailment for later governed processing. It does **not** mean canonical truth, clinical recommendation, release eligibility, or 09D acceptance.

## Certification boundary

Offline certification covers orchestration order, independence boundaries, specialist reconciliation, deterministic routing, and authority locks. It does not certify the quality of a production primary model, blind recall model, blind semantic reviewer, frontier adjudicator, or cold auditor. Those roles must earn task-specific certification on a real hand-annotated corpus.
