# Atomic Assertion Contract v1.1

An assertion is one independently auditable proposition interpreted from one immutable source unit. It is evidence-linked interpretation, never canonical truth.

## Numeric-safe proposition identity

`normalized_proposition` uses Unicode NFC plus whitespace normalization. NFKC is prohibited because compatibility normalization can destroy clinically material superscripts, subscripts, and vulgar fractions. Search-only compatibility forms, if ever added, must be separate from assertion identity.

## Evidence closure

Every assertion must be validated with its referenced source unit.

Text evidence requires:

- in-range character offsets;
- exact source-unit substring equality;
- exact UTF-8 byte offsets;
- exact evidence-text SHA-256.

Out-of-range spans are errors, not conditions that skip validation. Calling the validator without a source unit explicitly returns an unbound-assertion error.

Structured evidence uses one canonical absolute JSON-path grammar. The path must resolve against the referenced structured source unit. Numeric values, when supplied over a numeric structured leaf, must equal the resolved source value.

## Identity/versioning

`ASSERT:<32 hex>` binds source-unit identity, evidence identity, controlled assertion type, NFC-normalized proposition, and clinically material context. `INTERP:<32 hex>` additionally binds extractor provenance. New model/prompt interpretations cannot overwrite history.

## Extraction provenance and authority

`DETERMINISTIC_PARSER` and `MODEL_ASSISTED` remain separate modes. All assertions start `NOT_VERIFIED`; automatic-selection, canonical, internal-generation, public, and release authority remain false. Verification may establish entailment later but never grants 09D authority by itself.
