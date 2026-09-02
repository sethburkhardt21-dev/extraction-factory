# ADR-126 — W3 Tier-B routing is source-risk authority

PRIMARY and BLIND_RECALL are noncanonical candidate-generation tasks whose worker request class remains W2. That does not authorize local closure of a source unit classified W3 by the governed risk router.

Starting with v1.26, semantic candidates record the governed source-risk classification derived from the exact `SourceUnit`. Evidence families preserve that metadata. The router MUST force every family stamped `source_risk_work_class=W3` to `SPECIALIST_REVIEW_REQUIRED` with `W3_TIER_B_REVIEW_REQUIRED`, even when narrower deterministic checks find no issue.

Conflicting source-risk stamps inside one evidence family are a P0 integrity failure.

This change does not certify Tier-B review, mutate candidates, promote canonical state, or let W2 model certification stand in for W3 authority. It only prevents accidental local closure and creates an explicit bounded Tier-B review boundary.
