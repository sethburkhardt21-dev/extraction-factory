# Hermes Extraction Factory Benchmark v0.1

Status: DESIGN COMPLETE / DATASET NOT YET BUILT

## Purpose
Certify models for specific factory roles without treating prior model outputs as ground truth.

## Proposed corpus
48 source units across 8 strata:
B0 prose
B1 dense lists
B2 numeric/range
B3 qualifier/negation
B4 relationships
B5 tables
B6 figures/visuals
B7 OCR/cross-page/mixed

## Gold pipeline
Source-only Gold Builder A
+ source-only Gold Builder B
-> disagreement set
-> Gold Adjudicator C
-> deterministic verification
-> Reference v1
-> reveal historical outputs only for challenge pass
-> Reference v2

## Primary benchmark phases
1. Free-agent screen
2. Specialist comparison
3. Frontier adjudication-value test
4. Long-session controller durability

See SCORING_PROTOCOL.md and CERTIFICATION_RULES.md.
