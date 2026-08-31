# Semantic Gold Gate Contract — v1.0

The Turn-5 semantic layer is evaluated against hand-authored expected outcomes that are not generated from extractor or verifier output.

The gold gate covers:

- exact literal entailment versus paraphrase ambiguity;
- numeric value/unit binding, scientific notation, vulgar fractions, and microgram/unit aliases;
- required structured numeric binding for high-risk numeric claims;
- route/population/timing qualifier scope;
- negation, certainty, and conditionality preservation;
- association versus causation;
- directionality and no-effect semantics;
- atomicity warnings;
- structured ClinicalTrials re-derivation;
- abstract/table risk escalation;
- reviewer failure and authority injection;
- critical-risk frontier routing.

A reviewer may resolve non-contradictory warnings. It may not waive a deterministic hard contradiction.

Passing this gate establishes an offline semantic contract only. Production model benchmarking, real-corpus recall/precision, cold audit, native source canaries, 09D comparison, and release authority remain separate gates.
