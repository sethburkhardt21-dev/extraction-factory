# Turn 4 — Atomic Assertion Extraction Engine Contract

## Trust boundary

The assertion extractor is an **untrusted interpretation layer**. It may propose atomic clinical assertions from validated source units. It may not verify semantic entailment, assign canonical/candidate identity, compare with 09D, resolve conflicts, or grant any clinical/public/generation authority.

Every emitted assertion MUST remain `verification_status = NOT_VERIFIED` and all authority/selection/eligibility booleans MUST remain false.

## Engine-owned fields

A model/provider is forbidden from setting IDs, source identity, source hashes, verification state, candidate IDs, extractor provenance, or any authority field. The engine computes those from the frozen source unit and frozen execution provenance.

## Evidence closure

Text proposals must copy an exact evidence substring. The engine computes character and UTF-8 byte offsets. If the same substring occurs more than once, the provider must supply an exact `char_start`; ambiguity otherwise fails closed.

Structured JSON proposals must reference the exact `json_path` already frozen on the source unit. A provider cannot point at another field.

## Atomicity

One proposal represents one independently auditable proposition. Obvious multi-sentence, newline, and semicolon compounds are rejected. Deeper semantic atomicity remains untrusted until the independent Turn-5 verifier.

## Quarantine

Provider failures, malformed proposals, unknown assertion types, bad spans, wrong structured paths, attempts to set engine-owned authority fields, and ambiguous evidence are preserved in an extraction quarantine. They are never silently dropped and never converted to PASS evidence.

## Determinism

`ASSERT:` identity depends on immutable evidence + proposition + clinical context. `INTERP:` identity additionally binds extractor/model/prompt provenance. Re-running identical evidence/proposal/provenance yields identical IDs. A changed model revision or prompt produces a new interpretation ID without rewriting the assertion/evidence identity.

## Structured ClinicalTrials path

Turn 4 includes a deliberately narrow deterministic provider for high-confidence scalar protocol facts such as enrollment, phase, overall status, conditions, and posted-results availability. It does not generate generic clinical assertions from every JSON leaf.

## Explicitly not implemented in Turn 4

- semantic entailment verification;
- assertion precision/recall certification on a gold corpus;
- general entity/candidate resolution;
- 09D read-only comparison;
- cross-source conflict/support graph;
- automatic clinical authority of any kind.

## Exact running-code binding

Persisted assertion runs and 09D audit packages MUST recompute the current production code/contract manifest and reject a caller/provider provenance hash that does not match the running estate. A syntactically valid 64-hex value is not sufficient evidence of execution provenance.

## Recursive authority-key rejection

Forbidden authority/identity fields are rejected even when nested inside provider-supplied `context`, `numeric`, `study_context`, lists, or other proposal objects. Unresolved entity surfaces are textual mentions only and cannot use a `CAND:` identifier form to masquerade as a resolved 09D candidate.
