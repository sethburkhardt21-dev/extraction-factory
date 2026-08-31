# Semantic Verifier Gold Gate — v1.0

The semantic verifier is not certified by unit-test count alone. A pinned case matrix under `bridge_09d/tests/fixtures/semantic_verifier/CASES.json` defines named expected outcomes for clinically material semantic failure modes.

The matrix currently covers exact entailment, blind paraphrase ambiguity, dosing number preservation, numeric mismatch, negation preservation/loss, certainty strengthening, conditionality preservation/loss, association-vs-causation, qualifier support, abstract-only escalation, compound-claim atomicity, controlled ClinicalTrials semantic paths, unknown structured paths, boolean result-state semantics, and high-risk/frontier routing.

Gold expectations are authored independently of verifier output. Changing code to match an observed output without an explicit gold-case adjudication is prohibited.

Passing this gate establishes only offline semantic-contract behavior. It does not certify a production model backend, clinical truth, candidate identity, 09D comparison, public-host source access, or release authority.

Machine schema identifier: `semantic-verifier-gold-1.0`.

## Turn-5 v1.1 amendment

Risk expectations were tightened: adverse-effect and other safety-sensitive claims may route higher than the original scaffold; structured-registry facts are at least moderate risk; abstract-scope relationship claims are escalated; unsupported structured numeric units are hard binding failures. Source hedging cannot be waived by a reviewer.
