# Hermes Kanban Task — Nemo-Supervised Real Validation — v1.12

## Source of truth

Repository:

```text
https://github.com/sethburkhardt21-dev/extraction-factory.git
```

Execute current `master` only.

At task start:

```bash
git fetch --all --prune
git checkout master
git pull --ff-only
cd factory
python -c "import hermes_factory; print(hermes_factory.__version__)"
git rev-parse HEAD
```

Required version for this task: **1.12.0 or later explicitly reviewed successor**.

Do not substitute an older ZIP, cached checkout, historical optimization branch, Meta pack, or prior Hermes pack.

## Mission

Do not redesign the factory from scratch.

Your immediate job is to **execute and measure the current factory end to end on the owner machine** using:

- the exact owner-held Machines textbook;
- the exact sealed 09D r3 database;
- real registered semantic providers;
- contamination-safe source-first gold;
- the protected owner-validation harness.

Read and follow in full:

```text
OWNER_REAL_VALIDATION_RUNBOOK.md
```

Then execute:

```text
factory/validation/owner_real_validation.py
```

Do not stop at planning.

## Nemo's role

Nemo/Nemotron is the persistent supervisor/orchestrator. Use it aggressively for:

- exact model discovery;
- truthful model-lineage classification;
- role selection;
- registry repair proposals;
- retry diagnosis;
- disagreement analysis;
- table/numeric/qualifier review;
- benchmark interpretation;
- performance analysis;
- repair proposals after measured failures.

Nemo is not the deterministic authority.

The factory remains authoritative for:

- source hashes and source-unit identity;
- exact evidence;
- blind-pass isolation;
- leases, CAS, staging and reconciliation;
- build/runtime integrity;
- model registry identity;
- readiness;
- package integrity;
- 09D read-only enforcement;
- Motion-1 authority scope;
- Motion-2 target binding;
- benchmark contamination guards.

Nemo may not override a failed gate, spoof independence, write to 09D, canonicalize assertions, merge identities, or author a readiness PASS.

## Exact owner assets

Machines textbook required SHA-256:

```text
379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197
```

Sealed 09D r3 required SHA-256:

```text
fa7a97313dc5bbd9b2fbb61b9124a4ecef5c318ad5d070eeefe67816a210f4a3
```

The harness must refuse any other bytes.

Never commit the owner assets, reconstructed textbook source text, screenshots containing source text, or source-bearing run ZIPs.

## Model-estate discovery

First run:

```bash
ollama list
```

Record exact model tags. Do not invent aliases.

Also verify whether supported non-Ollama provider CLIs, such as Claude if configured, actually execute through `providers_ext/llm_provider.py` before assigning them a role.

Inspect:

```text
factory/CURRENT/MODEL_CERTIFICATION_REGISTRY.json
```

Every real semantic or gold-construction model must have an exact truthful registry identity.

Registry edits are protected production changes and require tests + new build certification.

## Independence rules — do not weaken

### Semantic run roles

PRIMARY, BLIND, and COLD AUDIT must have three distinct registered independence groups.

Do not use Qwen primary + NuExtract blind if the registry places NuExtract in the Qwen group.

A plausible first hypothesis, subject to actual installed tags and registry lineage, is:

```text
PRIMARY       GPT-OSS or MedGemma
BLIND         NuExtract
COLD AUDIT    DeepSeek-R1 14B
```

Benchmark results, not this suggestion, determine the winning role assignment.

### Gold construction

Gold Builder A, Gold Builder B, and Gold Adjudicator C must be empirical and pairwise independence-group distinct.

### v1.12 benchmark contamination rule

The complete set of gold-construction groups must also be disjoint from **both PRIMARY and BLIND groups being scored**.

Different model aliases from the same independence group do not count as independent.

If the model estate cannot satisfy this graph, stop and report the missing family rather than weakening the benchmark.

## Forensic preflight

Before real inference:

1. update to current master and record exact HEAD;
2. verify version >= 1.12.0;
3. verify owner asset hashes;
4. enumerate exact local/provider model identities;
5. repair registry only with truthful identities;
6. run the full tests;
7. recertify the exact protected build;
8. verify build/runtime lock;
9. verify `validation/**/*.py` is inside the protected build surface;
10. reconstruct the exact eight governed Machines units;
11. confirm gold/scoring-family preflight can be satisfied before expensive model work.

From `factory/`:

```bash
python -m hermes_factory test
python -m hermes_factory certify-build --rerun-tests --refresh-runtime-lock
python -m hermes_factory verify
```

Any deterministic predispatch failure stops model calls.

## Canonical real validation

Use the owner-validation harness rather than manually recreating the stages.

Example shape only:

```bash
python -B validation/owner_real_validation.py \
  --source-pdf "C:/path/to/Machines Textbook.pdf" \
  --database-09d "C:/path/to/final_s03.sqlite" \
  --primary "ollama:<exact-primary-tag>" \
  --blind "ollama:<exact-blind-tag>" \
  --cold "ollama:<exact-cold-tag>" \
  --gold-builder-a "ollama:<exact-gold-a-tag>" \
  --gold-builder-b "ollama:<exact-gold-b-tag>" \
  --gold-adjudicator "ollama:<exact-gold-c-tag>" \
  --provider-schedule auto \
  --ollama-keep-alive 30m \
  --timeout-per-call 900
```

The harness must fail closed before expensive gold/appliance work if family independence is invalid.

## Required proof

Do not call the task complete until the harness has attempted and preserved evidence for all applicable checks:

- exact Machines source hash;
- exact sealed r3 hash;
- exact eight governed source units;
- actual source-unit content rehashing;
- PRIMARY/BLIND/COLD empirical identity and independence;
- exact build tests/certification/preflight;
- real provider smoke;
- exact-source gold construction/integrity;
- gold-builder trio independence;
- gold groups disjoint from PRIMARY/BLIND groups;
- real eight-unit semantic appliance;
- nonempty PRIMARY and BLIND candidate output;
- byte-for-byte 09D immutability;
- Motion-1 cycle-safe comparison;
- exact r3 comparator target verification;
- positive strict Motion-2 authority binding;
- numeric-context guard;
- structurally gated contradiction queue;
- W2/S1 PRIMARY/BLIND metrics;
- BLIND omission recovery and useful-new precision;
- higher-risk metrics separately;
- Table 6.1 metrics separately when present;
- final owner-validation package verification.

## 09D boundary

09D is read-only comparison evidence, not gold.

Never:

- insert;
- update;
- delete;
- auto-canonicalize;
- auto-merge identities;
- migrate its schema;
- promote or release rows.

The owner validator must prove the database SHA-256 is unchanged after the real run and final packaging.

SUPPORT does not canonicalize. CONTRADICTION does not invalidate source evidence. MISSING_IN_09D may represent legitimate new source content.

## Table 6.1 is an explicit acceptance surface

The earlier empirical pilot concentrated sampled semantic errors in Table 6.1. Inspect it separately from global metrics.

Explicitly examine:

- wrong row binding;
- wrong column/property binding;
- neighboring-cell leakage;
- dropped unit;
- dropped temperature/pressure qualifier;
- context loss;
- false "value absent" claims.

Do not allow strong prose performance to hide weak table performance.

## Do not hide weak or incomplete results

Preserve and report:

- failed semantic thresholds;
- cold-audit failures;
- Table 6.1 errors;
- numeric-context review rows;
- surviving 09D contradictions;
- provider errors/retries/timeouts;
- unresolved W3/S3 table/visual/cross-page semantics;
- E3 clinically material distortion as `NOT_MEASURED` when it remains unmeasured;
- Reference-v2 historical challenge expansion as `NOT_RUN` while unimplemented.

`NOT_RUN` never means `PASS`.

## Code repair policy

If the owner run reveals a defect:

1. reproduce it;
2. add a failing behavioral/adversarial test;
3. repair the smallest responsible component;
4. run the full suite;
5. recertify the exact changed protected build;
6. verify;
7. rerun the affected pilot stage;
8. preserve before/after evidence.

Do not perform speculative rewrites without an observed failure or benchmark evidence.

## Expansion rule

Do not automatically process the 2,724-page textbook.

After the eight-unit owner proof, inspect:

1. PRIMARY W2/S1 recall and precision;
2. BLIND omission recovery and useful-new precision;
3. evidence fidelity;
4. numeric/qualifier preservation;
5. Table 6.1 metrics and row-level failures;
6. cold-audit results;
7. every contradiction;
8. numeric-context guard rows;
9. unresolved routes;
10. latency/retries/resource pressure.

Then either repair and rerun the same pilot, change a model role, enlarge the benchmark, or recommend a bounded 25–50 page expansion.

Do not launch all 2,724 pages automatically.

## End-of-task deliverable

Return the complete owner-validation evidence, including at minimum:

- `OWNER_REAL_VALIDATION_REPORT.json`;
- `OWNER_REAL_VALIDATION_OUTCOME.json`;
- `OWNER_VALIDATED_<RUN_ID>.zip`;
- all benchmark score files;
- `BENCHMARK/provisional_certification_dry_run.txt`;
- all 09D comparison/projection/authority/context artifacts;
- `09D/CONTRADICTION_REVIEW_QUEUE.jsonl`;
- provider timing/retry telemetry;
- exact model tags/families/groups;
- exact remaining blockers and explicit limits.

Then summarize:

1. exact git HEAD/runtime;
2. exact models and independence groups;
3. source and r3 hashes;
4. whether 09D stayed byte-identical;
5. strict Motion-2 authority-binding result;
6. W2/S1 precision/recall;
7. BLIND omission recovery/useful-new precision;
8. Table 6.1 results;
9. cold-audit outcome;
10. surviving contradictions;
11. runtime/provider bottlenecks;
12. whether a 25–50 page expansion is justified.

The intended overall label remains conservative:

```text
EXECUTED_AND_MEASURED_WITH_EXPLICIT_LIMITS
```

That is evidence of execution and measurement, not blanket semantic certification.

**Begin with current-master forensic preflight and model discovery. Execute; do not stop at planning.**
