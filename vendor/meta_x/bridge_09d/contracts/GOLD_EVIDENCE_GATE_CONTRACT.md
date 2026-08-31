# Gold Evidence Gate Contract — v1.0

Purpose: freeze a pre-verifier acceptance denominator for the source-unit substrate. The gold authority is hand-specified expected behavior, never the extractor's own output.

## Non-negotiable rules

- Generated output is evidence under test, never gold merely because the system emitted it.
- Every named case has a stable case ID and an explicit risk/expected behavior.
- Physical fixtures are SHA-256 pinned and paired with hand-authored expectations.
- The gate covers JATS numerics/markup/context/tables/figures, structured JSON, monograph offsets, PubMed abstract-only semantics, deterministic replay, and fail-closed malformed inputs.
- A failed gold case blocks progression to semantic verifier certification.
- Passing this gate does **not** certify real-public-source transport, semantic assertion precision/recall, model quality, 09D comparison, canonical authority, generation, public release, or mass extraction.
- Real public JATS bytes must be classified separately. Structural web/public references are not native transport evidence.

## Current proof classes

1. `HAND_SPECIFIED_RISK_CASE` — small adversarial source construct with manually written expected behavior.
2. `PINNED_PHYSICAL_FIXTURE` — immutable local fixture with SHA-256 and hand-authored expected outputs.
3. `PUBLIC_STRUCTURAL_REFERENCE` — public JATS/API reference used to inform coverage, not represented as locally acquired raw source bytes.
4. `NATIVE_PUBLIC_SOURCE` — reserved for exact bytes acquired through the production source path; currently required separately and not implied by this gate.

## Authority

`gold_gate_pass = true` means only that the deterministic evidence substrate satisfied the frozen acceptance cases on the exact production and verification manifests.

It never means:

- `semantic_verification_performed = true`
- `canonical_authority = true`
- `automatic_selection_allowed = true`
- `generation_eligible = true`
- `public_eligible = true`
- `mass_extraction_authorized = true`
