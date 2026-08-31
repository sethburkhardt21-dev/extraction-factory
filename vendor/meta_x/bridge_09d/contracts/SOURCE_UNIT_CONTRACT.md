# Source Unit Contract v1.2

A source unit is immutable evidence, not interpretation. It belongs to exactly one immutable source artifact/version and retains an exact UTF-8 text representation or canonical structured-JSON representation.

## Deterministic identity

New `UNIT:<32 hex>` identities bind:

- `source_record_key`
- `source_resource_id`
- `source_version_id`
- exact source-artifact SHA-256
- evidence scope (`FULL_TEXT`, `ABSTRACT_WITHIN_FULLTEXT`, `ABSTRACT_ONLY`, etc.)
- unit kind
- canonical locator JSON
- exact unit-content SHA-256

This prevents evidence from different source artifacts/scopes from colliding merely because derived text and locators happen to match. Historical v1.0/v1.1 units remain readable using their historical identity algorithm; new units are v1.2.

## Numeric-safe normalization

The source-unit layer never applies Unicode compatibility normalization to evidence. JATS inline semantics are rendered explicitly: superscripts/subscripts and supported MathML structures retain their numeric meaning (`10^6`, `H_2`, fractions) rather than being flattened into ambiguous strings.

## Locator closure

Every unit requires an actionable typed locator. JATS units carry the exact source-artifact SHA-256 plus canonical JATS XPath and a normalized XML-fragment hash. Table cells additionally carry row/column indices, spans, and header context. Monograph paragraphs carry both character and UTF-8 byte offsets. Structured JSON uses one canonical absolute `$...` path grammar and preserves literal `null` plus empty containers.

## Scope/context rules

- Abstract text acquired inside a full-text JATS artifact is `ABSTRACT_WITHIN_FULLTEXT`.
- Abstract fallback without full text is `ABSTRACT_ONLY`.
- Back matter such as acknowledgements/conflict statements is `METADATA`, not clinical `FULL_TEXT` evidence.
- JATS section titles are retained and section ancestry is copied into unit locators/metadata.
- Nested paragraphs already represented by an outer paragraph are not duplicated as independent evidence units.

## v1.1 structured-null correction retained

`content_representation` distinguishes `TEXT` from `JSON`, so literal JSON `null` is representable. v1.1+ requires the field explicitly; only historical v1.0 rows may infer it.

## 09D provenance dimensions

The unit carries source SHA-256 plus independent nullable `publication_year`, `edition_or_version`, and `source_era`. Missing dimensions remain missing. A source unit confers no canonical identity, selection, generation, release, or public authority.
