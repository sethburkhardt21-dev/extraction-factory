# Hermes Kanban Task — Nemo-Supervised Extraction Factory

## Repository and branch

Use this repository as the source of truth:

`https://github.com/sethburkhardt21-dev/extraction-factory.git`

Use branch:

`chatgpt-hermes-kanban-hardening-20260831`

Do **not** substitute an older ZIP, Meta pack, Hermes pack, or historical handoff. Preserve repository history and the existing rights quarantine.

## Mission

Execute and empirically harden the existing governed anesthesia literature extraction factory. Do not redesign it from scratch. Nemo is the persistent supervisor/orchestrator; deterministic factory machinery remains the authority for source hashes, blindness, leases, CAS, staging, build integrity, model certification, readiness, 09D read-only enforcement, and final packaging.

Nemo usage is effectively free for this project. Use Nemo aggressively for supervision, routing, disagreement analysis, retries, model selection, specialist escalation, and empirical diagnosis. Do not optimize away Nemo calls merely to save usage.

Nemo must **not** override failed gates, directly canonicalize assertions, directly write to 09D, spoof independence, or author `FRONTIER_REVIEW_READY`.

## Available model estate

First enumerate exact currently installed Ollama model tags and currently available free Hermes-hosted models. Do not guess names.

The local Ollama pool is expected to contain models corresponding to:

- GPT-OSS
- MedGemma
- NuExtract
- Devstral
- DeepSeek-R1 14B
- Qwen 3.6
- Qwen 3.1

Free Hermes-hosted models may include Nemo/Nemotron, HY3, Laguna, X/Ox Alpha, or others. Discover the actual live list.

### Initial role topology

Use this as the initial hypothesis, then benchmark it rather than treating it as dogma:

- **Supervisor/orchestrator:** Nemo / strongest free Nemotron available
- **Primary semantic extractor:** strongest local Qwen initially; benchmark against MedGemma and GPT-OSS
- **Blind recall:** NuExtract
- **Medical/domain specialist:** MedGemma
- **Cold audit:** DeepSeek-R1 14B or another genuinely independent family
- **Code/runtime repair:** Devstral
- **Overflow/challenger:** GPT-OSS and Qwen 3.1
- **Hosted escalation:** Nemo and other free hosted families when local workers disagree or fail

Use Nemo as supervisor even when another model performs the primary extraction.

## Independence and model identity

The hardened branch moves model family and empirical-provider status into the protected model registry.

Do not trust operator-entered family labels. Discover actual provider/model identity and add missing identities to `factory/CURRENT/MODEL_CERTIFICATION_REGISTRY.json` only with truthful underlying family / independence-group data.

Different aliases of the same underlying family do not satisfy independence.

Fixture/echo providers never count as empirical semantic providers.

## First phase — forensic preflight

Before model inference:

1. clone the specified branch;
2. inspect actual bytes and current git HEAD;
3. enumerate exact Ollama models/tags;
4. enumerate free Hermes models;
5. inspect `factory/CURRENT/`;
6. run the complete test suite;
7. inspect build-integrity coverage;
8. verify that integration layers are inside the certified production surface;
9. verify the model registry;
10. verify provider wrappers;
11. verify the Machines reconstruction path;
12. verify the 09D boundary remains read-only;
13. inspect the existing source-first gold work and do not regress it.

The current branch intentionally invalidates any older build certificate because production code changed. Do not treat that as a defect. After tests pass in the actual Hermes execution environment, refresh the runtime lock if needed, certify the exact current build, then run verify.

A deterministic source/build/runtime failure must stop before semantic provider calls.

## Machines pilot first

Do **not** launch the full textbook.

Use the governed Machines pilot:

- semantic pages: 299–301
- boundary context: 298 and 302
- expected source SHA-256: `379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197`

The repository intentionally does not version textbook-derived source-unit bytes. Use the portable reconstruction code with the owner-supplied hash-matched `Machines Textbook.pdf`. Reconstruction must produce the exact 8 governed units and verify every expected unit content hash.

Never commit textbook bytes, reconstructed source-unit text, generated page text, screenshots, or copyright-bearing handoff bundles back to GitHub.

## Real semantic run

Do not use echo except for infrastructure tests.

Run the pilot through real semantic models under factory governance:

`source unit -> bounded packet -> provider -> structured response -> evidence validation -> staging -> CAS/ledger commit -> deterministic union -> specialist controls -> routing -> cold audit -> benchmark/readiness -> package`

Blind recall receives only its permitted source packet. It must not see primary output, gold, 09D answers, expected counts, or peer decisions.

## Tables are the main known semantic risk

The prior real pilot showed most sampled failures clustering in Table 6.1. Treat tables as first-class W3 work.

For table-derived assertions require explicit binding of:

- table identity
- row/entity
- column/property
- value
- unit
- qualifier
- temperature/pressure/context where applicable
- exact evidence/provenance

Do not confidently infer row/column semantics from ambiguous flattened text. Route ambiguity instead.

Explicitly test for:

- wrong-row numeric binding
- wrong-column numeric binding
- neighboring-cell leakage
- dropped units
- dropped temperatures
- dropped qualifiers
- false “no value supplied” claims

Use NuExtract, Qwen, MedGemma, Nemo, or other appropriate specialists as challengers, but keep independence accounting truthful.

## Router requirements

No evidence family containing an unresolved hard specialist code may remain `LOCAL_PRECISION_COMPLETE`.

At minimum route unresolved:

- `UNBOUND_NUMERIC`
- `TABLE_BINDING_REQUIRES_SEMANTIC_OR_VISUAL_REVIEW`
- `IMAGE_AVAILABLE_NOT_MODEL_REVIEWED`
- `CROSS_PAGE_SEMANTIC_REVIEW_REQUIRED`
- `DIRECTION_CUE_LOST`
- `QUALIFIER_NOT_PRESERVED`

The branch contains the fix for legacy serialized flags where the failure code appears as a suffix such as `candidate:cue:DIRECTION_CUE_LOST`. Mutation-test it.

## 09D comparison

09D is read-only evidence, not truth authority.

Never insert, update, delete, merge, canonicalize, promote, or release directly into 09D.

A true contradiction requires compatible subject/entity identity, compatible predicate identity, compatible context/dimension/unit semantics, and then a real polarity/value conflict.

Lexical overlap alone must not produce contradiction. Examples that must **not** be labeled contradictions:

- `partial pressure` vs `partial laryngectomy`
- desflurane MAC value vs a percentage MAC reduction
- atmospheric pressure vs anesthetic vapor pressure merely because both use mmHg

If semantic identity cannot be established, emit uncertainty/variant/possible-match rather than contradiction.

## Source-first gold and role benchmarking

Complete the source-first benchmark for the same pilot before broad expansion.

Gold must be constructed from source, not from model candidates, 09D assertions, historical outputs, or expected counts.

Use independent builders/adjudication and preserve the existing phase controls in the repository.

Score at least:

- primary candidate model
- NuExtract blind recall
- MedGemma specialist/challenger
- DeepSeek cold audit
- at least one alternative primary model
- Nemo as challenger/supervisor where useful

Measure:

- precision
- recall
- F1
- numeric precision/recall
- qualifier preservation
- negation preservation
- relationship-direction accuracy
- table-specific precision/recall
- evidence-span validity
- malformed-output rate
- accepted blind-only marginal recall
- cold-audit detection rate
- disagreement rate

Do not hide weak table performance inside an overall average.

## Code repair policy

If execution reveals a real defect:

1. reproduce it;
2. write a failing behavioral test;
3. fix the smallest responsible component;
4. run the full test suite;
5. run relevant mutation/adversarial tests;
6. update the current build manifest;
7. explicitly re-certify the changed build;
8. verify;
9. rerun the affected pilot stage.

Use Devstral for coding work if useful; Nemo supervises.

Do not perform speculative architecture rewrites without empirical reason.

## Mandatory adversarial coverage

Preserve existing tests and ensure coverage for:

- blind peer leakage
- evidence outside allowed source units
- wrong-row/column table binding
- wrong numeric target
- qualifier loss
- negation loss
- relationship direction loss
- fake same-family independence
- operator family spoofing
- fixture provider marked empirical
- unbenchmarked cold auditor treated as certified
- stale/expired/duplicate lease behavior
- torn staging and post-stage mutation
- production integration-layer mutation after certification
- write attempt against 09D
- false lexical 09D contradiction
- `NOT_RUN` treated as PASS
- `FAIL_BLOCKING` masked by `BLOCKED_EXTERNAL`
- semantic provider calls starting despite failed deterministic predispatch gates

## Readiness precedence

Required order:

1. any `FAIL_BLOCKING` or required `NOT_RUN` -> `NOT_READY`
2. any unbounded required `FAIL_REVIEW_REQUIRED` -> `NOT_READY`
3. otherwise required `BLOCKED_EXTERNAL` -> `READY_FOR_PROVIDER`
4. only when all required gates genuinely pass -> `FRONTIER_REVIEW_READY`

No unresolved P0 integrity defect may coexist with frontier readiness.

## Throughput

Correctness first. Run SAFE_4 first. Then profile provider inference, model load/startup, queue wait, staging/validation, ledger work, specialists, cold audit, 09D compare, and packaging separately.

Only after semantic validity is measured should BALANCED_8/HIGH_12 be evaluated.

Nemo is free for this setup, so do not minimize Nemo supervision. Optimize expensive/scarce external model calls instead.

## Kanban cards

Create/update concrete cards for:

- FORENSIC PREFLIGHT
- MODEL DISCOVERY
- REGISTRY UPDATE
- TEST + BUILD CERTIFICATION
- PILOT RECONSTRUCTION
- PRIMARY EXTRACTION
- BLIND RECALL
- TABLE / NUMERIC / QUALIFIER SPECIALISTS
- COLD AUDIT
- 09D COMPARISON
- SOURCE-FIRST GOLD
- ROLE BENCHMARKING
- ADVERSARIAL TESTING
- PERFORMANCE PROFILING
- FINAL CERTIFICATION
- PACKAGE / EXECUTIVE REPORT

Do not mark cards complete because a plan exists. Complete means executed with evidence.

## Expansion rule

Do not process the whole 2,724-page Machines textbook until the pilot has:

- source-first gold
- measured precision/recall
- table-specific metrics
- role-specific certification results
- independent cold audit
- bounded unresolved queues
- passing deterministic integrity gates

If successful, stop and recommend the next 25–50 page expansion window. Do not automatically start the full estate.

## Final deliverable

Return a self-contained execution package appropriate to the mechanically derived state:

- `FRONTIER_REVIEW_READY_<RUN_ID>.zip`, or
- `READY_FOR_PROVIDER_<RUN_ID>.zip`, or
- `REVIEW_PACKAGE_<RUN_ID>.zip`

Do not commit that ZIP to this repository if it contains source-derived copyrighted text or historical handoff material. Deliver it through the Kanban/task artifact channel instead.

Also produce `EXECUTIVE_RUN_REPORT.md` stating exactly:

1. git branch and commit actually executed;
2. runtime actually used;
3. models actually discovered;
4. models actually used per role;
5. independence groups;
6. what failed;
7. what code was changed;
8. test/mutation results;
9. semantic precision/recall;
10. table-specific performance;
11. blind-only marginal recall;
12. cold-audit results;
13. 09D comparison quality;
14. runtime/performance;
15. remaining blockers;
16. whether expansion is justified.

## Success condition

The goal is not a green dashboard. The goal is executable evidence that the factory can produce extremely high-recall, high-precision, exactly source-grounded anesthesia assertions at scale while preserving provenance, uncertainty, independence, and a read-only downstream authority boundary.

**Begin with forensic preflight and model discovery. Do not stop at planning. Execute.**
