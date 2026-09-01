# Owner-Machine Real Validation Runbook — Nemo/Hermes

## Objective

Execute the real proof that GitHub Actions cannot perform because the repository intentionally does not contain the copyrighted textbook, the sealed 09D database, or the owner's local Ollama models.

The canonical command is:

`factory/validation/owner_real_validation.py`

This runbook does **not** authorize any write to 09D. The validation harness hashes the sealed database before and after the run and fails if a byte changes.

## 1. Start only from current master

```bash
git fetch --all --prune
git checkout master
git pull --ff-only
cd factory
python -c "import hermes_factory; print(hermes_factory.__version__)"
```

Required version at the time this runbook was authored: **1.11.0 or later**.

Do not use an older ZIP or an old optimization branch.

## 2. Locate the two owner assets

Locate the exact owner-held Machines textbook and the exact sealed r3 09D database.

Expected Machines SHA-256:

`379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197`

Expected sealed 09D r3 SHA-256:

`fa7a97313dc5bbd9b2fbb61b9124a4ecef5c318ad5d070eeefe67816a210f4a3`

The validation harness refuses any other bytes.

Do not copy either asset into git.

## 3. Discover exact Ollama model tags

Run:

```bash
ollama list
```

Expected model types on the owner machine include some subset of:

- GPT-OSS
- MedGemma
- NuExtract
- Devstral
- DeepSeek-R1 14B
- Qwen 3.x models

Use the **exact displayed tags**. Do not invent aliases.

## 4. Repair the authoritative model registry before inference

Inspect:

`factory/CURRENT/MODEL_CERTIFICATION_REGISTRY.json`

Every provider used by the real run or the source-first gold builder must have an exact `PROVIDER|model-tag` identity with a truthful:

- `underlying_family`
- `independence_group`
- `empirical_semantic_model`
- `observed_version_policy`

Do not use CLI family strings to override the registry.

If an identity is missing, research/inspect the actual model lineage and add the truthful entry. Do not guess family independence merely because two tags differ.

### Critical independence rule

NuExtract is currently treated as belonging to a **Qwen independence group**. Therefore:

```text
Qwen primary + NuExtract blind
```

must **not** be treated as independent merely because the model names differ.

A better first topology from the owner's local estate is:

```text
PRIMARY       GPT-OSS (if its registered family is independent of Qwen)
BLIND         NuExtract
COLD AUDIT    DeepSeek-R1 14B
```

MedGemma can challenge GPT-OSS as primary after the first measured run.

If registry lineage shows a proposed pairing is not independent, choose another family.

## 5. Choose source-first gold builders that do not author the scored roles

The PRIMARY and BLIND models being scored must not be Builder A or Builder B for their own gold reference.

Prefer three distinct gold-construction families. One plausible arrangement, subject to the exact registry lineage, is:

```text
Gold Builder A     MedGemma
Gold Builder B     Devstral
Gold Adjudicator   DeepSeek-R1 14B or another third independent family
```

The gold adjudicator may overlap the cold-audit role because COLD_AUDIT is not currently certified by the PRIMARY/BLIND gold scorer, but it must remain independent of Gold Builder A and Gold Builder B.

Do not use GPT-OSS as a gold builder if GPT-OSS is the PRIMARY being scored. Do not use NuExtract as a gold builder if NuExtract is the BLIND role being scored.

If the available model families cannot produce a defensible independent gold trio, stop and report the exact missing independence rather than weakening the benchmark.

## 6. Re-certification is mandatory after registry edits

Registry edits are inside the protected build surface. The real validation harness itself runs the tests/certification/preflight sequence, but the registry must be correct before invoking it.

Do not manually mark a model certified before measurement.

## 7. Run the one-command real proof

Example shape only — substitute exact local tags and exact owner paths:

```bash
python -B validation/owner_real_validation.py \
  --source-pdf "C:/path/to/Machines Textbook.pdf" \
  --database-09d "C:/path/to/final_s03.sqlite" \
  --primary "ollama:<exact-gpt-oss-tag>" \
  --blind "ollama:<exact-nuextract-tag>" \
  --cold "ollama:<exact-deepseek-tag>" \
  --gold-builder-a "ollama:<exact-medgemma-tag>" \
  --gold-builder-b "ollama:<exact-devstral-tag>" \
  --gold-adjudicator "ollama:<exact-third-family-tag>" \
  --provider-schedule auto \
  --ollama-keep-alive 30m \
  --timeout-per-call 900
```

If a model requires Ollama thinking control, add the appropriate supported flag only after checking the exact model/runtime behavior.

Do not lower the timeout merely to make a failing model look faster.

## 8. What the harness must prove

The run is not complete unless the harness verifies all applicable checks:

- exact Machines PDF SHA-256;
- exact sealed r3 SHA-256;
- exact eight governed source-unit hashes;
- registered empirical provider identities;
- primary/blind/cold independence groups distinct;
- full tests pass;
- exact build re-certified;
- preflight verify passes;
- real provider smoke passes before full pilot;
- source-first gold is hash-bound to the exact source units;
- real eight-unit semantic appliance completes;
- primary and blind both emit non-empty candidate sets;
- 09D bytes are identical before and after;
- comparison used `MOTION1_AUTHORITY` and is cycle-safe;
- comparison verified the exact pinned r3 target;
- Motion-2 authority binding is positively verified;
- numeric temperature/pressure context guard executes;
- every emitted `CONTRADICTION` satisfies the structural contradiction gate;
- W2/S1 PRIMARY and BLIND roles are scored against source-first gold;
- higher-risk units are scored separately;
- Table 6.1 is scored separately when present in the gold reference;
- final owner-validation package verifies.

## 9. Do not hide review-required results

The following are legitimate outcomes and must remain visible:

- Table 6.1 weak precision/recall;
- numeric-context review queue;
- true or possible 09D contradictions;
- failed provisional PRIMARY/BLIND thresholds;
- cold-audit failures;
- unresolved W3/S3 table/visual/cross-page semantics;
- E3 clinically material distortion not mechanically measured;
- historical Reference-v2 challenge pass NOT_RUN.

Do not convert any of these into PASS to improve the dashboard.

## 10. Review every surviving contradiction

The harness writes:

`09D/CONTRADICTION_REVIEW_QUEUE.jsonl`

For every row, inspect:

- candidate proposition;
- exact source evidence;
- subject identity;
- predicate identity;
- fact family;
- context/qualifiers;
- units/dimensions;
- numeric relation;
- top 09D match.

A structurally valid contradiction may still reflect a legitimate source-vs-09D difference. 09D is not the gold label.

## 11. Inspect Table 6.1 independently

Do not rely on an overall metric. Inspect:

- `BENCHMARK/primary_TABLE6_1.json`
- `BENCHMARK/blind_TABLE6_1.json`

The prior real pilot concentrated sampled semantic failures in Table 6.1, including wrong-cell binding and dropped temperature/unit context. Treat this unit as a first-class acceptance surface.

## 12. Required outputs

The successful execution should produce, at minimum:

- `OWNER_REAL_VALIDATION_REPORT.json`
- `OWNER_REAL_VALIDATION_OUTCOME.json`
- `BENCHMARK/primary_W2_S1.json`
- `BENCHMARK/blind_W2_S1.json`
- higher-risk/table benchmark files when applicable
- `BENCHMARK/provisional_certification_dry_run.txt`
- `09D/CONTRADICTION_REVIEW_QUEUE.jsonl`
- the existing comparison/projection/authority/context artifacts
- `OWNER_VALIDATED_<RUN_ID>.zip`

The report's overall label is intentionally conservative:

`EXECUTED_AND_MEASURED_WITH_EXPLICIT_LIMITS`

That means execution and measurement completed. It does **not** mean all semantic strata have been automatically certified.

## 13. After the run

Do not immediately scale to the 2,724-page book.

First inspect:

1. W2/S1 PRIMARY precision/recall;
2. BLIND omission recovery and useful-new precision;
3. Table 6.1 metrics;
4. cold-audit results;
5. every 09D contradiction;
6. numeric-context guard reviews;
7. provider timing/retries;
8. unresolved route counts.

Only after those results are reviewed should Nemo propose either:

- a model-role change;
- prompt/specialist repair;
- a bounded 25–50 page expansion;
- or a new benchmark before expansion.

## 14. Nemo's authority boundary

Nemo supervises this process aggressively, but it may not:

- edit evidence to make a test pass;
- spoof family independence;
- mark its own model certified;
- write to 09D;
- merge identities automatically;
- canonicalize assertions automatically;
- override package/readiness integrity;
- declare W3/S3 certified without an applicable benchmark.

The deterministic factory remains the authority over what counts.
