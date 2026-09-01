# Hermes Kanban Task — Nemo-Supervised Real Validation

## Source of truth

Repository:

`https://github.com/sethburkhardt21-dev/extraction-factory.git`

Execute the current `master` branch only.

At task start:

```bash
git fetch --all --prune
git checkout master
git pull --ff-only
cd factory
python -c "import hermes_factory; print(hermes_factory.__version__)"
```

Required version at the time this task was authored: **1.11.0 or later**.

Record the exact git HEAD. Do not substitute an older ZIP, historical hardening branch, Meta pack, Hermes pack, or cached checkout.

## Mission

Do not redesign the factory from scratch.

Your immediate job is to **prove the current factory end to end on the owner machine** using:

- the exact owner-held Machines textbook;
- the exact sealed 09D r3 database;
- real registered semantic providers;
- a source-first gold reference;
- the current validation harness.

Read and follow, in full:

`OWNER_REAL_VALIDATION_RUNBOOK.md`

Then execute:

`factory/validation/owner_real_validation.py`

Do not stop at planning.

## Nemo's role

Nemo/Nemotron is the persistent supervisor and orchestrator.

Use Nemo aggressively for:

- model discovery;
- truthful family/independence classification;
- role selection;
- retry diagnosis;
- disagreement analysis;
- table/numeric/qualifier review;
- benchmark interpretation;
- performance analysis;
- proposing repairs after measured failures.

Nemo is not the deterministic authority.

The factory remains authoritative for:

- source hashes;
- source-unit identity;
- evidence;
- blindness;
- leases;
- CAS/state transitions;
- build/runtime integrity;
- model registry identity;
- readiness;
- package integrity;
- 09D read-only enforcement.

Nemo may not override a failed gate, spoof independence, write to 09D, canonicalize assertions, merge identities, or author a readiness PASS.

## Model-estate discovery

Enumerate the exact installed Ollama tags first with `ollama list`.

Expected local model types include some subset of:

- GPT-OSS
- MedGemma
- NuExtract
- Devstral
- DeepSeek-R1 14B
- Qwen 3.x

Also inspect any currently available free Hermes-hosted models for supervisory/challenger use, but the current factory provider wrapper should only be given backends it actually supports.

Do not invent model names.

Update `factory/CURRENT/MODEL_CERTIFICATION_REGISTRY.json` only with truthful observed identities and lineage. Registry edits are protected production changes and require recertification.

## Independence warning

Do **not** use Qwen primary + NuExtract blind if the registry places both in the Qwen independence group.

A reasonable first local hypothesis is:

```text
PRIMARY       GPT-OSS or MedGemma
BLIND         NuExtract
COLD AUDIT    DeepSeek-R1 14B
```

but use the actual registry lineage and benchmark results rather than this suggestion as authority.

The PRIMARY, BLIND, and COLD roles used by the owner validation harness must have distinct registered independence groups.

## Gold-reference independence

The PRIMARY and BLIND models being scored must not author their own gold reference.

Prefer three separate gold-construction families. Follow the runbook's restrictions.

If the available model pool cannot provide a defensible gold construction, stop and report the exact independence gap. Do not weaken the gold rules to make the task complete.

## Exact owner assets

Machines textbook required SHA-256:

`379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197`

Sealed 09D r3 required SHA-256:

`fa7a97313dc5bbd9b2fbb61b9124a4ecef5c318ad5d070eeefe67816a210f4a3`

The harness must refuse any other bytes.

Never commit these owner assets or reconstructed textbook text to GitHub.

## Required proof

The run is not complete until the owner validation harness has attempted all executable proof steps, including:

- exact source/database hashes;
- exact eight governed source-unit hashes;
- tests;
- recertification;
- preflight verification;
- real provider smoke;
- real eight-unit semantic run;
- byte-for-byte 09D immutability;
- cycle-safe Motion-1 comparison;
- positive strict Motion-2 target authority binding;
- numeric-context guard;
- contradiction structural gating + review queue;
- source-first gold integrity;
- W2/S1 PRIMARY and BLIND scores;
- blind omission-recovery/useful-new metrics;
- separate high-risk/Table 6.1 metrics;
- final package verification.

## Do not hide weak results

Preserve, report, and route:

- failed semantic thresholds;
- cold-audit failures;
- Table 6.1 errors;
- temperature/pressure context mismatches;
- unresolved W3/S3 visual/table/cross-page semantics;
- surviving 09D contradictions;
- malformed provider responses/retries;
- E3 clinically material distortion as NOT_MEASURED where it remains unmeasured;
- historical Reference-v2 challenge expansion as NOT_RUN while it remains unimplemented.

NOT_RUN never means PASS.

## 09D boundary

09D is read-only comparison evidence, not gold.

Never:

- insert;
- update;
- delete;
- canonicalize;
- merge;
- promote;
- release;
- auto-migrate its schema.

The owner validation harness must prove the database SHA-256 is unchanged after the real run and validation packaging.

## Table 6.1 is an explicit acceptance surface

Inspect Table 6.1 independently from global averages.

The prior real pilot concentrated sampled semantic failures there. Review wrong-row/wrong-column binding, neighboring-value leakage, lost units, and lost temperature/pressure context.

Do not allow strong prose performance to hide weak table performance.

## End-of-task deliverable

Return the complete owner-validation outcome and package, including at minimum:

- `OWNER_REAL_VALIDATION_REPORT.json`
- `OWNER_REAL_VALIDATION_OUTCOME.json`
- `OWNER_VALIDATED_<RUN_ID>.zip`
- all benchmark reports;
- all 09D comparison/projection/authority/context artifacts;
- `09D/CONTRADICTION_REVIEW_QUEUE.jsonl`;
- provider timing/retry telemetry;
- exact remaining blockers/limits.

Then summarize:

1. what actually ran;
2. exact model tags/families;
3. whether provider independence held;
4. whether source and 09D hashes matched;
5. whether 09D remained byte-identical;
6. whether strict Motion-2 authority binding passed;
7. W2/S1 precision/recall;
8. BLIND omission recovery/useful-new precision;
9. Table 6.1 metrics;
10. cold-audit outcome;
11. number and nature of surviving contradictions;
12. runtime/provider bottlenecks;
13. whether a 25–50 page expansion is justified.

Do not launch the 2,724-page extraction automatically.
