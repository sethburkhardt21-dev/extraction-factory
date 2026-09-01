# Hermes Kanban Task — Nemo-Supervised Extraction Factory v1.9

## Source of truth

Repository:

`https://github.com/sethburkhardt21-dev/extraction-factory.git`

Execute the current `master` branch.

At task start:

1. `git fetch --all --prune`
2. `git checkout master`
3. `git pull --ff-only`
4. record the exact HEAD SHA
5. verify `factory/VERSION` reports `1.9.0` or a later explicitly reviewed successor

Do not substitute an older ZIP, prior hardening branch, Meta pack, Hermes pack, or historical checkout.

## Mission

Execute, benchmark, and empirically validate the governed anesthesia literature extraction factory. Do not redesign it from scratch.

Nemo/Nemotron is the persistent supervisor/orchestrator. Nemo usage is effectively free for this project, so use it aggressively for supervision, model selection, disagreement analysis, retry planning, specialist routing, benchmark diagnosis, and performance analysis.

The deterministic factory remains authoritative for source hashes, blindness, evidence, leases, CAS, staging, build/runtime integrity, model identity/certification, readiness, 09D read-only enforcement, Motion-2 handoff integrity, and packaging.

Nemo may recommend actions but may not:

- override a failed gate;
- convert `NOT_RUN` into PASS;
- spoof model-family independence;
- canonicalize assertions;
- merge identities;
- write directly to 09D;
- authorize a schema migration;
- authorize a release;
- author `FRONTIER_REVIEW_READY`.

## Current v1.9 behavior that must be preserved

### Runtime / local model scheduling

- External semantic runs fail closed before provider calls if source hash, build integrity, or runtime lock fails.
- Provider family and empirical identity come from the protected model registry, not operator-entered family text.
- `--provider-schedule AUTO` phases distinct local Ollama models by default to avoid VRAM/model-residency thrash.
- Local Ollama providers default to one in-flight request per model unless empirical benchmarking proves a higher role-specific concurrency is better.
- Ollama `keep_alive` defaults to 30m and extraction temperature is deterministic.
- Primary, blind, and cold concurrency are independently tunable.
- Provider inference time, attempts, and controller timing are preserved in provenance.
- Cold audit is deterministic and risk-stratified toward table/figure, numeric, and uncertainty-bearing assertions without increasing the configured sample volume.

### 09D comparison / handoff

The canonical flow is now:

`factory -> read-only 09D comparison -> strict Motion-2 projection -> numeric context guard -> verified package`

Preserve all of these boundaries:

1. **Cycle-safe authority scope.** Default 09D comparison uses only Motion-1/source-witnessed carrier rows. Prior Motion-2 extraction rows are excluded so model output cannot recursively validate later model output.
2. **Conservative identity.** Exact searchable entity aliases are used before lexical fallback. An alias resolving to multiple entities cannot produce SUPPORT or CONTRADICTION.
3. **Conservative predicates.** Exact predicate codes/labels are preferred. Namespaced predicate-tail resolution is allowed only when unique, preferably inside an explicit fact family.
4. **Conservative numerics.** Structured `numeric_values` are preferred over proposition-wide number capture. Decimal formatting equivalence is recognized; overlapping ranges are not contradictions; disjoint exact intervals may contradict only after identity/predicate/family/context compatibility. No automatic unit conversion.
5. **Focused Motion-2 target contract.** `ingest_source_locator` and `source_assertion_candidate` are cryptographically fingerprinted independently of unrelated 09D schema objects. Relevant target drift must invalidate compatibility; unrelated schema growth must not.
6. **Authority binding.** The strict projection binds comparison bytes to the verified 09D database hash, whole-schema fingerprint, focused Motion-2 contract, cycle-safe carrier scope, and comparator target version. Stale/unverified comparison output must not provide loader-ready identity suggestions.
7. **Temperature/pressure context guard.** For candidates with structured target numerics, explicit non-target temperature/pressure dimensions are checked after projection. A matching target value at a different temperature/pressure must be downgraded for review. Original comparison state remains preserved; only the projection-effective state/loader disposition is downgraded.
8. **Read-only governance.** Direct insert, automatic identity merge, automatic canonicalization, automatic schema migration, and automatic release remain false.

## Model discovery

First enumerate exact installed Ollama tags and currently available free Hermes-hosted models. Expected local model families include models corresponding to:

- GPT-OSS
- MedGemma
- NuExtract
- Devstral
- DeepSeek-R1 14B
- Qwen 3.6
- Qwen 3.1

Nemo/Nemotron should supervise.

Do not guess model aliases or families. Update `factory/CURRENT/MODEL_CERTIFICATION_REGISTRY.json` only with exact observed provider/model identity and truthful underlying family / independence group. Different aliases of the same underlying family do not satisfy independence. Echo/fixture never counts as empirical semantic work.

### Initial role hypothesis

Benchmark rather than assume this is permanently optimal:

- Supervisor/orchestrator: Nemo / strongest free Nemotron available
- Primary semantic extractor: strongest local Qwen initially; challenge with MedGemma and GPT-OSS
- Blind recall: NuExtract
- Medical/domain specialist: MedGemma
- Cold audit: DeepSeek-R1 14B or another genuinely independent family
- Code/runtime repair: Devstral
- Overflow/challenger: GPT-OSS and Qwen 3.1
- Hosted escalation: Nemo and other free hosted families for unresolved/disagreement cases

Nemo should supervise rather than simultaneously claim independent primary, blind, and cold roles.

## Phase 1 — forensic preflight and recertification

Before semantic inference:

1. clone/update current `master` and record exact HEAD;
2. verify the version;
3. enumerate Ollama models and free Hermes models;
4. inspect `factory/CURRENT/` and the model registry;
5. run the full test suite;
6. inspect GitHub CI for the same or predecessor production commit;
7. verify integration layers (`providers_ext`, `stages_ext`, benchmark code, appliance) are inside the protected production surface;
8. verify the exact Machines reconstruction path;
9. verify 09D remains read-only/immutable;
10. inspect the existing source-first gold work and preserve its independence rules.

Production code has changed substantially since older certificates. Never reuse an old build certificate as authority.

From `factory/`:

```bash
python -m hermes_factory test
python -m hermes_factory certify-build --rerun-tests --refresh-runtime-lock
python -m hermes_factory verify
```

If any deterministic predispatch gate fails, stop before model calls. Repair the defect, rerun tests, recertify the exact changed build, and verify again.

## Phase 2 — governed Machines pilot

Do not start the full 2,724-page textbook.

Use the governed pilot:

- semantic pages 299–301
- boundary context 298 and 302
- expected source SHA-256: `379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197`

Use the owner-supplied hash-matched `Machines Textbook.pdf` and the portable reconstruction code. Reconstruction must produce the exact governed eight source units and validate all expected content hashes.

Never commit textbook bytes, reconstructed source text, screenshots, or source-bearing handoff ZIPs to GitHub.

## Phase 3 — real semantic run

Do not use echo except for infrastructure testing.

Run real providers under factory governance:

`source unit -> bounded packet -> provider -> exact-evidence validation -> staging -> CAS/ledger commit -> union -> specialists -> routing -> independent cold audit -> readiness -> 09D compare/projection/guard -> package`

Blind recall receives only the source-positive-allowlist packet. It must not see primary output, gold, 09D answers, expected counts, or peer decisions.

Start with `--provider-schedule AUTO` and local role concurrency 1. Test higher concurrency only after a clean pilot and compare throughput, model load/swap behavior, memory pressure, malformed output, retry rate, and semantic quality.

## Table and numeric binding remain priority risks

The prior real pilot concentrated sampled failures in Table 6.1. Require explicit binding of:

- table identity;
- row/entity;
- column/property;
- target value;
- unit;
- qualifier;
- temperature/pressure/context where applicable;
- exact evidence/provenance.

Explicitly challenge:

- wrong-row binding;
- wrong-column binding;
- neighboring-cell leakage;
- dropped units;
- dropped temperature/pressure qualifiers;
- lost negation/modality;
- false “no value supplied” claims.

Do not infer table structure from naked adjacency when binding is ambiguous. Route it.

## 09D real-r3 replay — mandatory before broad expansion

Use the current sealed target only if its hash matches the pinned comparator target. The audited r3 database SHA-256 is:

`fa7a97313dc5bbd9b2fbb61b9124a4ecef5c318ad5d070eeefe67816a210f4a3`

The default comparison must remain Motion-1 authority scoped.

For the same real Machines pilot, report at minimum:

- measured database hash and target-match result;
- whole-schema fingerprint;
- focused Motion-2 target-contract SHA;
- Motion-1 / Motion-2 / invalid witness row counts;
- comparison carrier scope;
- cycle-safe authority result;
- SUPPORT count;
- POSSIBLE_DUPLICATE count;
- CONTEXT_DIFFERENCE count;
- VARIANT count;
- IDENTITY_UNCERTAIN count;
- CONTRADICTION count;
- MISSING_IN_09D count;
- confidence distribution;
- predicate-resolution distribution;
- numeric-relation distribution;
- strict authority-binding result and authority-context ID;
- numeric-context-guard review count;
- Motion-2 mapping gaps / unclassified required columns.

Manually inspect every `CONTRADICTION` in the small pilot. Specifically confirm the previous false examples no longer survive:

- partial pressure vs partial laryngectomy;
- absolute desflurane MAC vs percentage MAC reduction;
- atmospheric pressure vs anesthetic vapor pressure merely because both use mmHg.

Also explicitly test the known context failure class: matching numeric value with mismatched or dropped 20/25°C or pressure context must not remain loader-ready.

09D remains comparison evidence, not truth. SUPPORT does not canonicalize; CONTRADICTION does not invalidate source evidence; MISSING_IN_09D may represent legitimate new source content.

## Source-first gold and role benchmarking

Complete/freeze source-first gold for the same pilot before broad expansion. Gold must be built from source, never from model candidates, 09D rows, historical outputs, or expected counts.

Score at least:

- primary candidate model;
- NuExtract blind recall;
- MedGemma specialist/challenger;
- DeepSeek cold audit;
- one alternative primary;
- Nemo as challenger/supervisor where useful.

Measure separately:

- assertion precision / recall / F1;
- numeric precision / recall;
- qualifier and negation preservation;
- relationship-direction accuracy;
- table precision / recall;
- evidence-span validity;
- malformed-output / retry rate;
- accepted blind-only marginal recall;
- cold-audit detection rate;
- disagreement rate.

Do not hide table performance inside a global average. Do not optimize blind recall away until frozen gold proves accepted marginal recall is negligible for a defined low-risk stratum.

## Code repair policy

If empirical execution discovers a real defect:

1. reproduce it;
2. add a failing behavioral/regression test;
3. fix the smallest responsible component;
4. run the full suite;
5. run relevant adversarial tests;
6. update the current build manifest;
7. recertify the exact changed build;
8. verify;
9. rerun the affected pilot stage.

Use Devstral for coding if useful; Nemo supervises. Avoid speculative rewrites without empirical justification.

## Required adversarial coverage

Retain coverage for:

- blind peer leakage;
- evidence outside the allowed source unit;
- wrong row/column numeric binding;
- qualifier/negation/direction loss;
- same-family fake independence;
- operator family spoofing;
- fixture marked empirical;
- unbenchmarked cold auditor treated as certified;
- stale/expired/duplicate leases;
- torn staging and post-stage mutation;
- production code mutation after certification;
- write attempt against 09D;
- false lexical contradiction;
- Motion-2 recursive support entering authority comparison;
- ambiguous exact entity alias producing support/contradiction;
- decimal-format false conflict;
- scalar/range overlap false conflict;
- stale comparison target used for Motion-2 projection;
- relevant Motion-2 schema drift;
- temperature/pressure context mismatch remaining loader-ready;
- `NOT_RUN` treated as PASS;
- `FAIL_BLOCKING` masked by `BLOCKED_EXTERNAL`;
- provider calls starting despite deterministic predispatch failure.

## Readiness semantics

Required precedence remains:

1. any required `FAIL_BLOCKING` or `NOT_RUN` -> `NOT_READY`;
2. any unbounded required `FAIL_REVIEW_REQUIRED` -> `NOT_READY`;
3. otherwise required `BLOCKED_EXTERNAL` -> `READY_FOR_PROVIDER`;
4. only genuinely satisfied required gates -> `FRONTIER_REVIEW_READY`.

No unresolved P0 integrity defect may coexist with frontier readiness.

## Expansion rule

Do not process the whole Machines textbook until the pilot has:

- frozen source-first gold;
- measured semantic precision/recall;
- table-specific metrics;
- role-specific certification results;
- independent cold audit;
- real-r3 09D replay;
- strict authority binding;
- bounded context/mapping review queues;
- passing deterministic integrity gates.

If successful, stop and recommend a 25–50 page expansion window. Do not automatically start all 2,724 pages.

## Kanban execution

Maintain concrete cards for:

- FORENSIC PREFLIGHT
- MODEL DISCOVERY
- REGISTRY UPDATE
- TEST + BUILD CERTIFICATION
- PILOT RECONSTRUCTION
- PRIMARY EXTRACTION
- BLIND RECALL
- TABLE / NUMERIC / QUALIFIER SPECIALISTS
- COLD AUDIT
- 09D R3 HASH + SCHEMA VERIFICATION
- 09D CYCLE-SAFE COMPARISON
- MOTION-2 TARGET CONTRACT
- STRICT AUTHORITY BINDING
- NUMERIC CONTEXT GUARD
- SOURCE-FIRST GOLD
- ROLE BENCHMARKING
- ADVERSARIAL TESTING
- PERFORMANCE PROFILING
- FINAL CERTIFICATION
- PACKAGE / EXECUTIVE REPORT

A card is complete only when execution evidence exists.

## Final deliverable

Return a self-contained execution package matching mechanically derived state:

- `FRONTIER_REVIEW_READY_<RUN_ID>.zip`, or
- `READY_FOR_PROVIDER_<RUN_ID>.zip`, or
- `REVIEW_PACKAGE_<RUN_ID>.zip`.

Do not commit source-bearing/copyright-bearing output ZIPs to this repository.

Also produce `EXECUTIVE_RUN_REPORT.md` containing:

1. exact git HEAD;
2. runtime and hardware used;
3. models discovered and models actually used per role;
4. truthful independence groups;
5. source reconstruction/hash results;
6. test/build/runtime certification results;
7. semantic precision/recall and table-specific metrics;
8. blind-only marginal recall;
9. cold-audit results;
10. 09D r3 target hash/schema/target-contract results;
11. 09D comparison states and manually reviewed contradictions;
12. strict authority-binding result;
13. numeric-context-guard results;
14. Motion-2 mapping gaps;
15. performance/runtime telemetry;
16. remaining blockers;
17. whether 25–50 page expansion is justified.

## Success condition

The objective is not a green dashboard. The objective is executable evidence that the factory can produce very high-recall, high-precision, exactly source-grounded anesthesia assertions while preserving provenance, uncertainty, model independence, cycle-safe 09D comparison, and a strictly read-only downstream authority boundary.

**Begin with current-master forensic preflight and model discovery. Do not stop at planning. Execute.**
