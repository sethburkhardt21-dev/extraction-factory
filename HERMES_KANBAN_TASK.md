# Hermes Kanban Task — Nemo-Supervised Extraction Factory v1.3

## Source of truth

Repository:

`https://github.com/sethburkhardt21-dev/extraction-factory.git`

Execute branch:

`chatgpt-pipeline-optimization-20260901`

Do not substitute an older ZIP, Meta pack, Hermes pack, `master`, or the prior hardening branch. Preserve repository history and the existing rights quarantine.

## Mission

Execute, benchmark, and empirically validate the existing governed anesthesia literature extraction factory. Do not redesign it from scratch.

Nemo/Nemotron is the persistent supervisor/orchestrator. Nemo usage is effectively free for this project, so use it aggressively for supervision, model selection, disagreement analysis, retry planning, specialist routing, benchmark diagnosis, and performance analysis.

The deterministic factory remains authoritative for source hashes, blindness, evidence, leases, CAS, staging, build/runtime integrity, model identity/certification, readiness, 09D read-only enforcement, and packaging. Nemo may recommend actions but may not override a failed gate, canonicalize assertions, spoof independence, write to 09D, or author `FRONTIER_REVIEW_READY`.

## Important v1.3 runtime behavior

This branch contains a throughput/correctness optimization pass. Preserve and test it rather than reverting it:

- external semantic runs fail closed before any provider call if source hash, build integrity, or runtime lock fails;
- provider family/empirical identity comes from the protected model registry, not CLI family text;
- `--provider-schedule AUTO` phases distinct local Ollama models instead of running them concurrently and causing GPU/VRAM model-residency thrash;
- local Ollama providers default to one in-flight request per model unless an empirical benchmark justifies a higher role-specific concurrency;
- Ollama calls keep a role model resident with `keep_alive` (default 30m) and extraction temperature defaults to 0;
- primary, blind, and cold concurrency can be tuned independently;
- provider timing, attempts, and controller timing are preserved in run provenance;
- cold audit is deterministic but risk-stratified toward table/figure, numeric, and uncertainty-bearing assertions before the remaining hash-selected population;
- 09D `CONTRADICTION` requires compatible subject and predicate identity before numeric/polarity conflict is allowed;
- blind recall remains always-on until source-first marginal-recall evidence supports changing that policy.

Do not assume these changes improve wall time merely because they are theoretically better. Measure the same Machines pilot against the previous ~60.8-minute real-provider baseline and report the actual difference.

## Model discovery

First enumerate exact installed Ollama tags with the local runtime. Expected model families include models corresponding to:

- GPT-OSS
- MedGemma
- NuExtract
- Devstral
- DeepSeek-R1 14B
- Qwen 3.6
- Qwen 3.1

Also enumerate the live free Hermes-hosted models. Nemo/Nemotron should supervise.

Do not guess exact model names or families. Add missing model identities to `factory/CURRENT/MODEL_CERTIFICATION_REGISTRY.json` using the exact observed provider/model tag and truthful underlying family / independence group. Different aliases of the same underlying model family do not satisfy independence. Echo/fixture never counts as empirical semantic work.

### Initial role hypothesis

Benchmark this topology; do not treat it as permanently correct:

- Supervisor/orchestrator: Nemo / strongest free Nemotron available
- Primary semantic extractor: strongest local Qwen initially; challenge with MedGemma and GPT-OSS
- Blind recall: NuExtract
- Medical/domain specialist: MedGemma
- Cold audit: DeepSeek-R1 14B or another genuinely independent family
- Code/runtime repair: Devstral
- Overflow/challenger: GPT-OSS and Qwen 3.1
- Hosted escalation: Nemo and other free hosted families for unresolved/disagreement cases

Nemo should normally supervise rather than act simultaneously as primary + blind + cold auditor.

## Phase 1 — forensic preflight and exact certification

Before semantic inference:

1. clone and checkout `chatgpt-pipeline-optimization-20260901`;
2. record exact git HEAD;
3. enumerate exact Ollama tags and free Hermes models;
4. inspect `factory/CURRENT/` and the model registry;
5. run `python -m hermes_factory test` from `factory/`;
6. inspect any CI result for the same commit;
7. verify the protected production surface contains appliance/provider/comparator/benchmark code;
8. verify the portable Machines reconstruction path;
9. verify 09D remains read-only;
10. inspect existing source-first gold work and do not regress it.

Production code changed on this branch, so an older certificate must not be reused. After exact model identities are registered and tests pass in the actual Hermes machine:

```bash
cd factory
python -m hermes_factory test
python -m hermes_factory certify-build --rerun-tests --refresh-runtime-lock
python -m hermes_factory verify
```

If any deterministic predispatch gate fails, stop. Do not spend model calls until it is corrected and the exact changed build is re-certified.

## Phase 2 — governed Machines pilot

Do not start the 2,724-page textbook.

Use the governed pilot:

- semantic pages 299–301
- boundary context 298 and 302
- expected source SHA-256 `379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197`

The repository intentionally excludes copyrighted source-unit text. Use the owner-supplied hash-matched `Machines Textbook.pdf` and the portable reconstruction code. Reconstruction must produce the expected governed eight units and validate their content hashes.

Never commit textbook bytes, reconstructed source text, page screenshots, or source-bearing handoff ZIPs to GitHub.

## Phase 3 — real semantic run

Do not use echo except for infrastructure tests.

Run real providers under factory governance:

`source unit -> bounded packet -> provider -> exact-evidence validation -> staging -> CAS/ledger commit -> union -> specialists -> routing -> independent cold audit -> benchmark/readiness -> package`

Blind recall receives the source-only positive-allowlist packet. It must not see primary output, gold, 09D answers, expected counts, or peer decisions.

Use `--provider-schedule AUTO` initially. For distinct local Ollama models, it should resolve to `PHASED`. This is intentional: keep one role model hot and finish its phase before swapping the next model onto the accelerator. Do not override to parallel until measured GPU memory/load behavior demonstrates that parallel distinct-model residency is actually faster and stable.

Start local role concurrency at 1. Test 2 only after a clean pilot and compare throughput, memory pressure, malformed-output rate, and semantic quality. Higher generic worker counts are not useful if Ollama serializes or thrashes one GPU.

## Tables and numerical binding are priority risk

The previous real pilot concentrated sampled semantic failures in Table 6.1. For table-derived assertions require explicit binding of:

- table identity
- row/entity
- column/property
- value
- unit
- qualifier
- temperature/pressure/context when applicable
- exact source evidence/provenance

Never infer a row/column relationship from a naked flattened number. Ambiguous table structure must be routed or explicitly flagged, not guessed.

Explicitly challenge:

- wrong-row binding
- wrong-column binding
- neighboring-cell leakage
- dropped units
- dropped temperature/pressure qualifiers
- lost qualifier or negation
- false “no value supplied” claims

## Router and specialists

No evidence family with an unresolved hard specialist code may remain `LOCAL_PRECISION_COMPLETE`.

At minimum retain routing for unresolved numeric, table/visual, cross-page, qualifier, negation, and relationship-direction failures. Preserve the hardened suffix-code parser so serialized flags such as `candidate:cue:DIRECTION_CUE_LOST` still trigger review.

## Cold audit

Keep the audit model family independent of both primary and blind families.

The v1.3 sample is risk-stratified without increasing the configured sample volume. Verify that tables/figures and numeric assertions receive priority while preserving deterministic reproducibility. Do not let a clean but unbenchmarked auditor satisfy frontier readiness.

## 09D comparator

09D is read-only comparison evidence, never gold or truth authority.

Never insert, update, delete, merge, canonicalize, promote, or release directly into 09D.

A true `CONTRADICTION` requires compatible subject identity + compatible predicate identity + compatible context/dimension/unit semantics, followed by an actual polarity or value conflict.

Regression cases that must not become contradictions:

- partial pressure vs partial laryngectomy
- absolute desflurane MAC vs percentage MAC reduction
- atmospheric pressure vs anesthetic vapor pressure merely because both use mmHg

If identity is not established, prefer `VARIANT` / `IDENTITY_UNCERTAIN` rather than contradiction.

## Source-first benchmark

Complete the same-pilot source-first gold before any broad expansion. Gold must be built from source, not model candidates, 09D, historical outputs, or expected counts. Preserve independent builders/adjudication and existing phase controls.

Score at least:

- primary candidate model
- NuExtract blind recall
- MedGemma specialist/challenger
- DeepSeek cold audit
- one alternative primary
- Nemo as challenger where useful

Measure separately:

- precision / recall / F1
- numeric precision / recall
- qualifier and negation preservation
- relationship-direction accuracy
- table precision / recall
- evidence-span validity
- malformed-output/retry rate
- accepted blind-only marginal recall
- cold-audit detection rate
- disagreement rate

Do not hide weak table performance inside a global average.

Do **not** optimize blind recall away until accepted blind-only marginal recall is measured on frozen source-first gold. If later data shows blind recall contributes near-zero accepted marginal recall for a well-defined low-risk stratum, propose a gated policy change with tests rather than silently skipping it.

## Performance profiling

Capture and report separately:

- provider inference time per role
- provider attempts/retries
- model load/swap behavior
- role concurrency
- queue wait
- controller/staging/ledger overhead
- deterministic specialist time
- cold-audit time
- 09D comparison time
- packaging time
- peak GPU/VRAM and host RAM when available

Compare at least:

1. v1.3 AUTO phased local schedule, concurrency 1;
2. same model topology with concurrency 2 where hardware permits;
3. only then any parallel-distinct-model experiment.

Do not infer speedup; report measured wall-clock change against the prior ~3650-second pilot.

## Code repair policy

If execution reveals a defect:

1. reproduce it;
2. add a failing behavioral regression test;
3. make the smallest responsible fix;
4. run the full suite;
5. run targeted mutation/adversarial tests;
6. because the production build changed, re-certify the exact build;
7. verify;
8. rerun the affected pilot stage.

Devstral may perform code repair; Nemo supervises. Avoid speculative rewrites.

## Mandatory adversarial coverage

Retain and verify protection against:

- blind peer/gold/count leakage
- evidence outside permitted source
- wrong table row/column binding
- wrong numeric target
- qualifier/negation/direction loss
- fake same-family independence
- operator family spoofing
- fixture provider marked empirical
- unbenchmarked cold auditor treated as certified
- stale/expired/duplicate leases
- torn staging/post-stage mutation
- production integration-layer mutation after certification
- 09D write attempts
- lexical false contradictions
- `NOT_RUN` treated as PASS
- `FAIL_BLOCKING` masked by `BLOCKED_EXTERNAL`
- semantic provider calls beginning after deterministic predispatch failure
- distinct local-model parallel scheduling causing unsafe residency/memory behavior

## Readiness precedence

1. any required `FAIL_BLOCKING` or required `NOT_RUN` -> `NOT_READY`
2. any unbounded required `FAIL_REVIEW_REQUIRED` -> `NOT_READY`
3. otherwise required `BLOCKED_EXTERNAL` -> `READY_FOR_PROVIDER`
4. only when all required gates genuinely pass -> `FRONTIER_REVIEW_READY`

No unresolved P0 integrity defect may coexist with frontier readiness.

## Kanban cards

Maintain concrete evidence-backed cards for:

- FORENSIC PREFLIGHT
- MODEL DISCOVERY
- REGISTRY UPDATE
- TEST / CI / BUILD CERTIFICATION
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

A card is complete only when the work ran and evidence exists.

## Expansion rule

Do not process the full Machines textbook until the pilot has source-first gold, measured precision/recall, table metrics, role-specific certification outcomes, independent cold audit, bounded unresolved queues, and passing deterministic gates.

If the pilot succeeds, stop and recommend the next 25–50 page expansion window. Do not automatically run the whole estate.

## Final deliverables

Return the mechanically appropriate package:

- `FRONTIER_REVIEW_READY_<RUN_ID>.zip`
- `READY_FOR_PROVIDER_<RUN_ID>.zip`
- or `REVIEW_PACKAGE_<RUN_ID>.zip`

Do not commit source-bearing output ZIPs to this repository. Deliver them through the Kanban/task artifact channel.

Also produce `EXECUTIVE_RUN_REPORT.md` with exact branch/commit/runtime, discovered and used models, independence groups, code changes, tests/CI/mutations, semantic metrics, table metrics, blind-only marginal recall, cold-audit result, 09D quality, role timing/concurrency, measured wall time versus baseline, remaining blockers, and whether expansion is justified.

## Success condition

The objective is executable evidence that the factory produces extremely high-recall, high-precision, exactly source-grounded anesthesia assertions at scale while preserving provenance, uncertainty, independence, durable state, and read-only downstream governance.

**Begin with forensic preflight and exact model discovery. Do not stop at planning. Execute.**
