# Semantic Specialist Capsules Contract — v1.0

## Purpose

Specialist capsules are deterministic, independently inspectable semantic checks between an immutable source unit and a proposed atomic assertion. They do not extract new claims, mutate assertions, resolve candidate identity, compare against 09D, or grant authority.

## Required capsules

Every verification event runs these capsules:

1. `PROVENANCE_CLOSURE` — source-unit/assertion cryptographic and locator binding.
2. `NUMERIC_BINDING` — literal numeric census is separate from semantic value/unit binding. Scientific notation, vulgar fractions, microgram aliases, and denominator-exponent units are normalized only for comparison, never identity.
3. `NEGATION_PRESERVATION` — positive/negative polarity cannot reverse.
4. `CERTAINTY_MODALITY` — hedged evidence cannot become a definite claim.
5. `CONDITIONALITY` — source conditions cannot disappear or be invented.
6. `QUALIFIER_SCOPE` — population, route, timing, and other qualifiers are checked separately from detection.
7. `TABLE_BINDING` — table transcription is not semantic binding: row/column coordinates and retained headers are checked independently, and unsupported header claims fail closed.
8. `VISUAL_BINDING` — a figure caption is not the visual payload. Figure-derived claims remain unresolved until an independent visual worker inspects the image/plot itself; caption-only evidence cannot silently certify plotted/image semantics.
8. `RELATIONSHIP_SEMANTICS` — association, causality, no-effect, and directionality are independently checked.
9. `ATOMICITY` — compound claims are routed for precision review rather than silently treated as one fact.

## Hard-failure rule

A `HIGH` or `CRITICAL` deterministic contradiction cannot be waived by a semantic model. Examples include wrong numeric value, unsupported numeric unit in the assertion's structured numeric binding, polarity reversal, certainty strengthening, causal overclaim, directionality reversal, or broken provenance.

Missing or locally unrecoverable context that is not itself contradicted is a `WARN` and routes to specialist/precision review. Absence is not automatically converted into contradiction.

## Risk router

Risk is independent from entailment. `LOW`, `MODERATE`, `HIGH`, and `CRITICAL` determine which independent lanes must review a claim. High-risk claims require blind semantic review. Critical clinical numerics require frontier adjudication even when the claim is semantically entailed.

Automatic selection remains false at every risk tier.
