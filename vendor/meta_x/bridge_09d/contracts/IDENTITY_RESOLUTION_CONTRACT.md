# Provisional Identity Resolution Contract — v1.0

## Purpose

Turn 6 converts explicit unresolved entity surfaces carried by source-grounded assertions into provisional candidate records suitable for **read-only** identity lookup. It does not create or assign canonical identity.

## Candidate identity

Each candidate is the exact source mention occurrence:

```text
source_table = frontier.assertion_entity_surface
source_key   = assertion_id | mention_role | exact_surface_text
candidate_id = CAND:<09D source-identity hash prefix>
```

The same normalized name occurring in two assertions therefore remains two source candidates. Cross-source clustering is review evidence, never identity mutation.

## Domain inference

A domain may be inferred only where the assertion type makes the role unambiguous (for example, the subject of DOSING is a drug). Ambiguous domains create a `DOMAIN_AMBIGUOUS` review case and no candidate.

## Semantic gate

Read-only identity lookup may proceed when the independent verifier verdict is `ENTAILED`, even if high clinical risk means `downstream_semantic_ready=false`. Comparison and lookup are evidence-gathering operations, not selection.

## Authority locks

Every candidate remains `REGISTERED`; `legacy_entity_id` remains null. Automatic match, merge, promotion, selection, canonical authority, generation, and public authority are false.
