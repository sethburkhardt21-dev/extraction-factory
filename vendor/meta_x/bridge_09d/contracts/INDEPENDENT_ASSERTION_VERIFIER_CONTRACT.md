# Independent Assertion Verifier Contract — v1.0

## Authority boundary

Verification is append-only. The extractor-produced assertion remains `NOT_VERIFIED`; the verifier emits a separate `VERIF:` event. Verification never mutates the source assertion, resolves candidate identity, compares against 09D, enables automatic selection, or grants canonical/generation/public authority.

## Blindness

The semantic verifier receives only the proposed proposition, exact cited evidence, source scope/locator/context, numeric/qualifier fields, and study context. It does **not** receive extractor model identity, prompt, reasoning, candidate IDs, prior verifier output, or authority state.

## Specialized lanes

The verifier executes independent deterministic checks for:

1. provenance/evidence closure;
2. literal numeric binding;
3. negation preservation;
4. qualifier/scope binding;
5. relationship/causality binding;
6. atomicity.

A blind semantic provider may adjudicate paraphrase entailment, but it cannot override deterministic blocking failures. In particular, a numeric or provenance mismatch cannot be converted to `ENTAILED` by a model verdict.

## Verdicts

- `ENTAILED`
- `NOT_ENTAILED`
- `PARTIAL`
- `AMBIGUOUS`
- `PROVENANCE_INCOMPLETE`

`ENTAILED` means "entailed by this cited source evidence under this verification contract." It does **not** mean clinically canonical, current authority, safe for generation, or eligible for public release.

## Risk and review routing

Each verification event carries a non-authoritative risk tier (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) and required review lanes drawn from:

- `BLIND_ENTAILMENT`
- `NUMERIC_BINDING`
- `QUALIFIER_SCOPE`
- `RELATIONSHIP_BINDING`
- `PRECISION_REVIEW`
- `FRONTIER_ADJUDICATION`
- `COLD_AUDIT`

Critical dosing/concentration/contraindication/interaction claims remain routed to frontier adjudication even when semantically entailed.

## Hermes compatibility

This contract intentionally implements the Hermes semantic separation:

- literal numeric census is distinct from numeric binding;
- qualifier detection is distinct from qualifier scope binding;
- relationship extraction is distinct from relationship semantic binding;
- blind review is independent from the primary extractor;
- risk routing is distinct from truth/entailment;
- expensive/frontier review is reserved for bounded high-risk or unresolved cases.

## Turn-5 consolidation amendment

There is exactly one verifier implementation: `bridge_09d.verifier`. Historical `assertion_verifier` and `verification_pipeline` import surfaces are compatibility shims only and contain no independent decision logic.

Exact literal free-text equality may be deterministically labeled `ENTAILED`, but without an independent blind reviewer it remains `downstream_semantic_ready=false`. This separates proof of literal entailment from independent semantic readiness.

Deterministic hard contradictions are non-waivable. Missing non-contradictory context is escalation evidence rather than an invented contradiction.
