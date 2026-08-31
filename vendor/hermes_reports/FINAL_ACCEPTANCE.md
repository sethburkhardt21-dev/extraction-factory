# HERMES Advanced v1.1 — Final Acceptance Answers

## 1. What percentage of the original semantic/runtime skeleton is now actual code?

The frozen v1 maturity matrix contained **25 of 29 components** marked `NOT_IMPLEMENTED` or `SKELETON_ONLY`.

In Advanced v1.1, **23 of those 25 (92%) now have material executable code paths/mechanics**. The two clearest original weak components that remain genuinely unimplemented as full live capabilities are:

- true visual/image semantic interpretation;
- actual Buzz native/sidecar runtime integration in a Buzz environment.

This 92% is an **implementation-presence measure**, not a semantic-certification score.

## 2. Which components remain skeleton-only or absent?

Material remaining gaps:

- true multimodal visual semantic worker;
- independent real semantic cold-audit worker;
- direct Hermes-specific provider wrapper (generic JSON command provider is implemented);
- live Buzz integration;
- source-first semantic gold corpus;
- actual certified model roles;
- actual current 09D database comparison in this Hermes-only environment.

## 3. Can I now launch Hermes from one canonical command?

Yes.

```bash
./RUN_FACTORY.sh run ...
```

The command is real and was executed.

## 4. What happens after launch?

For a PDF run, the current execution path can:

1. hash the source;
2. deterministically ingest selected PDF pages;
3. generate source units;
4. classify source/work risk;
5. register the complete primary/blind work graph;
6. issue exclusive leases;
7. dispatch workers concurrently;
8. construct blind requests by allowlist;
9. stage outputs;
10. verify staging manifests/hashes;
11. CAS-commit accepted work artifacts;
12. build primary/blind union;
13. construct evidence families;
14. run literal inventories;
15. run deterministic specialist controls;
16. precision-check evidence/invariants;
17. route unresolved semantic work;
18. run deterministic cold-audit mechanics;
19. derive readiness from gates;
20. build and independently verify an offline ZIP.

## 5. Can the deterministic factory run completely offline?

Yes, when using local source files and a local/fixture provider. The real Machines fixture run was fully local.

## 6. What requires a model provider?

High-quality semantic assertion generation, true ambiguous W3 binding, independent semantic cold audit, and true visual interpretation.

## 7. What requires internet?

Only a configured provider or source acquisition path that itself requires network access. `LOCAL_ONLY` behavior rejects providers declared network-required.

## 8. If a worker dies, what happens?

Active work can be abandoned to `RETRY`/`FAILED`; leases expire and unfinished work can be requeued. Partial staged artifacts do not become accepted state without a valid completion receipt, manifest, validation, and CAS commit.

## 9. If the controller dies, what happens?

The SQLite/WAL ledger, events, leases, staged artifacts, and accepted commits remain on disk. On restart, state/history reconciliation can verify the durable state and expired leases can be requeued.

## 10. If the machine restarts, what state survives?

Everything persisted to the run directory: SQLite ledger/WAL-recovered state, event history, staging artifacts, commits, source units, receipts, and run outputs. Actual semantic redispatch after restart still requires relaunch with provider configuration.

## 11. If a stale worker returns after replacement work was accepted, what happens?

Its old lease is no longer active and/or its expected parent version is stale. The deterministic controller rejects the action. Wall-clock arrival does not establish authority.

## 12. If blind recall is contaminated, what happens?

The blind packet is rebuilt by positive allowlist. Known peer/gold/canonical/count fields are excluded. Nested forbidden disclosure keys trigger an error. The adversarial test suite exercises this behavior.

## 13. If production code changes after certification, what happens?

`MANIFEST_INTEGRITY` fails because current protected production/config hashes no longer match the immutable certified build manifest. Ordinary `verify` does not overwrite or refresh the certification.

## 14. Can any worker directly mark its own assertion canonical?

No through the supported production path. Extracted assertions are required to remain `SOURCE_ASSERTION_CANDIDATE / UNREVIEWED / NON_CANONICAL`, and invariant tests reject an extractor candidate with canonical state.

## 15. Can the system emit FRONTIER_REVIEW_READY with a required NOT_RUN gate?

No.

## 16. What exact executable gate prevents that?

`hermes_factory.readiness.derive_readiness()` derives the final state exclusively from required gate objects. Required `NOT_RUN`, `BLOCKED_EXTERNAL`, `FAIL_BLOCKING`, or unbounded `FAIL_REVIEW_REQUIRED` results prevent `FRONTIER_REVIEW_READY`. Mutation tests verify this.

## 17. What semantic work has actually been run on Machines pages 299–301?

A complete **offline fixture execution** of primary, blind recall, literal inventories, union, evidence-family construction, deterministic specialists, precision-integrity review, routing, cold-audit mechanics, durable state, and packaging.

No real language-model semantic inference was available in this environment, so the run is correctly labeled fixture/mechanical execution.

## 18. What semantic quality has actually been measured?

No real-model semantic precision/recall has been measured yet. The fixture candidate counts are not a semantic-quality score.

## 19. Which model roles are genuinely certified?

None. The authoritative registry is intentionally empty/unbenchmarked.

## 20. What remains before a long unattended textbook extraction is justified?

The decisive next steps are now empirical rather than architectural:

1. configure at least one real provider wrapper;
2. construct/freeze source-first gold;
3. benchmark/certify primary and independent blind roles;
4. wire/certify W3 semantic specialists where required;
5. wire an independent semantic cold auditor;
6. run the real Machines pilot;
7. measure SAFE_4 and then 8/12 with real provider latency/rate limits;
8. run crash/restart/provider-failure/overnight soak;
9. only then authorize a full unattended textbook extraction.

## Final classification

- Architecture: **FROZEN / STRONG**
- Deterministic execution runtime: **OFFLINE_CERTIFIED**
- Semantic transports and control machinery: **IMPLEMENTED / OFFLINE TESTED**
- Machines fixture execution: **EXECUTED**
- General PDF one-command path: **EXECUTED**
- Real semantic model execution: **BLOCKED_EXTERNAL**
- Semantic model certification: **NOT RUN**
- Real semantic precision/recall: **NOT MEASURED**
- Full production semantic extraction: **NOT YET AUTHORIZED**
