# HERMES Advanced v1.1 — Adversarial Mutation Report

The executable test suite includes behavioral failure injections rather than relying on source-token presence alone.

## Implemented and passing adversarial classes

- blind request contamination with primary assertions
- peer output leakage
- reference/gold value leakage
- canonical-answer leakage
- review-decision leakage
- expected-count leakage
- hidden-answer leakage
- nested forbidden disclosure key
- non-source evidence from semantic provider
- extractor attempt to emit canonical state
- dropped negation
- dropped modal `may`
- directional relationship cue loss
- numeric literal loss
- duplicate active lease
- illegal direct `READY → ACCEPTED` transition
- expired lease requeue
- old worker action after replacement lease
- stale parent version
- event-log body tampering
- state-table/event-history divergence
- accepted-state commit reconciliation
- restart/reopen reconstruction
- two-controller lease race
- torn staging artifact without completion receipt
- post-stage artifact mutation
- production code changed after certification
- new un-certified production file added after certification
- ordinary build verification does not rewrite certification evidence
- runtime lock mismatch
- required `NOT_RUN` readiness gate
- unbounded review failure
- bounded semantic review queue
- external semantic-provider blocker
- direct read-only 09D write attempt
- package extraction/hash verification
- LOCAL_ONLY mode rejecting network-required provider

## Important residual adversarial work

Not yet honestly completed because it needs external/live execution:

- real model wrong numeric target despite literal preservation
- real table row/column semantic inversion
- real multimodal image misinterpretation
- real model same-family correlated semantic error under cold audit
- hard process kill during SQLite fsync/host reboot
- overnight provider timeout/retry/failover soak
- Buzz disconnect/reconnect against the real Buzz runtime

These remain explicit blockers/experiments rather than being inferred from offline unit tests.
