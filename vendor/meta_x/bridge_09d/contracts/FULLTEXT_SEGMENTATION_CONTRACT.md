# Full-Text Acquisition + Source-Unit Segmentation Contract v1.1

## Authority boundary

Full-text acquisition creates evidence only. It does not create clinical authority, canonical identity, generation eligibility, or public-release eligibility.

## Rights are multidimensional

`text_mining_allowed`, redistribution status, commercial reuse, and derivative reuse are tracked independently.

PMC documents its OAI-PMH `pmc` full-text surface as returning full text only when licenses/usage rights allow reuse. Endpoint return can establish reuse/text-mining eligibility, but detailed redistribution/commercial/derivative rights are classified only from an article-level license when the extractor can identify it; otherwise those dimensions remain unclassified/unknown.

bioRxiv/medRxiv TDM permission remains distinct from article-level redistribution/license state.

## Exact artifact and host safety

Every acquired artifact retains exact response bytes, SHA-256, byte count, source URL, source/version identity, content type, transport, and rights decision. JATS acquisition requires XML content and a parseable JATS `<article>` before persistence. HTML/paywall/error pages cannot pass as full text. Localhost is disabled in production acquisition unless `allow_local_test_host=True` is explicitly set for a controlled test.

## Deterministic, semantics-preserving segmentation

- JATS paragraphs and section titles → typed text units with canonical XPath and section ancestry.
- `sup`, `sub`, and supported MathML constructs are rendered without collapsing numeric semantics.
- JATS table cells → `TABLE_CELL` units with row/column/header/span context.
- Figure/table captions are typed separately.
- Nested paragraph duplication is suppressed.
- Back matter is `METADATA`.
- PubMed full text must be identifier-bound to the source record's PMCID.
- Preprint JATS must be identifier-bound to the source DOI.
- PubMed without verified full text → explicit `ABSTRACT_ONLY` units.
- ClinicalTrials/structured JSON → canonical absolute JSON-path units, including literal null and empty containers.
- Monographs → exact paragraph substrings with character and UTF-8 byte offsets.

The segmenter performs no clinical interpretation.
