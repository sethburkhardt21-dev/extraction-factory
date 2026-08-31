# Turn 02 — Task × Source Risk Router

## Task classes
W0 Mechanical
W1 Literal Enumeration
W2 Bounded Source Semantics
W3 Contextual / Binding Semantics
W4 Adjudicative / Authority-Sensitive

## Source classes
S0 Simple
S1 Moderate
S2 Complex
S3 Critical

## Default routing
| Task | S0 | S1 | S2 | S3 |
|---|---|---|---|---|
| W0 | deterministic | deterministic | deterministic | deterministic + anomaly review |
| W1 | Tier A | Tier A | Tier A + validation | Tier A inventory + Tier B spot-check |
| W2 | A + independent A | A + independent A | A/B + independent review | Tier B + independent review |
| W3 | Tier B | Tier B | Tier B + independent adversary | Tier B + likely Tier C |
| W4 | Tier C | Tier C | Tier C | Tier C + cold audit |

No Tier-A worker may close W3 or W4.
