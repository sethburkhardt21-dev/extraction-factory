# Owner-Machine Real Validation Runbook — Nemo/Hermes — v1.12

## Objective

Execute the real semantic proof that GitHub Actions cannot perform because the repository intentionally does not contain the copyrighted Machines textbook, the sealed 09D r3 database, or the owner's local model runtimes.

Canonical entrypoint:

```text
factory/validation/owner_real_validation.py
```

This runbook does **not** authorize any write to 09D. The harness hashes the sealed database before and after execution and fails if a byte changes.

The benchmark must also remain contamination-safe: the three families used to construct gold must be distinct from one another **and disjoint from both PRIMARY and BLIND families being scored**.

---

## 1. Start only from current master

```bash
git fetch --all --prune
git checkout master
git pull --ff-only
cd factory
python -c "import hermes_factory; print(hermes_factory.__version__)"
git rev-parse HEAD
```

Required version for this runbook: **1.12.0 or later explicitly reviewed successor**.

Do not substitute an older ZIP, cached worktree, historical hardening branch, Meta pack, or Hermes pack.

Before proceeding, record:

- exact git HEAD;
- Python version;
- `factory/VERSION`;
- exact model registry SHA-256.

---

## 2. Locate and verify the two owner assets

Locate the exact owner-held Machines textbook and sealed 09D r3 database.

Required Machines SHA-256:

```text
379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197
```

Required sealed 09D r3 SHA-256:

```text
fa7a97313dc5bbd9b2fbb61b9124a4ecef5c318ad5d070eeefe67816a210f4a3
```

Do not copy either asset into git.

The harness must refuse any other bytes. Do not bypass those checks.

---

## 3. Discover exact installed model identities

For Ollama:

```bash
ollama list
```

Record exact displayed tags and sizes. Do not invent or normalize aliases.

Potential locally available model classes may include:

- GPT-OSS;
- MedGemma;
- NuExtract;
- Devstral;
- DeepSeek-R1;
- Qwen variants.

Also verify whether the Claude CLI or any other supported provider wrapper is actually callable before assigning it a role.

The provider wrapper's supported backend is authoritative. Do not add a nominal model to the plan if the factory cannot actually invoke it.

---

## 4. Repair the authoritative model registry before inference

Inspect:

```text
factory/CURRENT/MODEL_CERTIFICATION_REGISTRY.json
```

Every model used for PRIMARY, BLIND, COLD AUDIT, Gold Builder A, Gold Builder B, or Gold Adjudicator C must have an exact `PROVIDER|model-tag` registry entry containing truthful:

- `underlying_family`;
- `independence_group`;
- `empirical_semantic_model`;
- `observed_version_policy`.

The registry—not CLI family text—is authoritative.

If a model is missing, identify its actual lineage conservatively and add the exact alias. Do not infer independence from different display names alone.

Registry edits are protected production changes. After any registry edit, the build must be tested and re-certified before inference.

Never mark a model role `CERTIFIED` merely because its identity was registered.

---

## 5. Independence topology is a hard gate

### Semantic roles

PRIMARY, BLIND, and COLD AUDIT must resolve to **three distinct registered independence groups**.

For example, if NuExtract resolves to the Qwen independence group, this is invalid:

```text
PRIMARY = another Qwen-family model
BLIND   = NuExtract
```

A first topology worth evaluating, only if registry lineage confirms the groups are distinct, is:

```text
PRIMARY       GPT-OSS or MedGemma
BLIND         NuExtract
COLD AUDIT    DeepSeek-R1 14B
```

This is a hypothesis, not an override of registry evidence.

### Gold construction

Gold Builder A, Gold Builder B, and Gold Adjudicator C must themselves resolve to **three distinct empirical independence groups**.

### v1.12 contamination rule

All three gold-construction groups must also be disjoint from **both scored PRIMARY and scored BLIND groups**.

Conceptually, the run therefore needs:

```text
PRIMARY family        P
BLIND family          B
COLD family           C
GOLD Builder A        GA
GOLD Builder B        GB
GOLD Adjudicator C    GC

Required:
P != B != C for semantic-role independence
GA, GB, GC pairwise distinct
{GA, GB, GC} ∩ {P, B} = empty
```

COLD may overlap a gold-construction family only because COLD is not scored by the PRIMARY/BLIND gold benchmark. Prefer a fully separate family when the model estate permits it, but do not weaken PRIMARY/BLIND contamination rules merely to obtain a run.

If the available model estate cannot satisfy the required family graph, stop and report the exact missing independent family. Do not weaken the benchmark.

---

## 6. Test and re-certify after any protected change

From `factory/`:

```bash
python -m hermes_factory test
python -m hermes_factory certify-build --rerun-tests --refresh-runtime-lock
python -m hermes_factory verify
```

All must pass.

`validation/**/*.py`, the benchmark tools, provider wrappers, stages, registry, runtime, and core factory code are in the protected build surface as of v1.12. A post-certification modification to the owner-validation harness must invalidate the certificate.

Do not continue using an old certificate after modifying protected files.

---

## 7. Let the harness reconstruct the exact governed source units

Do not hand-edit the eight Machines units.

The harness reconstructs them from the owner PDF and verifies the governed unit IDs and content hashes. The gold builder independently recomputes SHA-256 from each unit's actual `content` text; it does not trust a declared `content_sha256` field.

Any mismatch must stop the run.

---

## 8. Choose gold builders before spending inference budget

The v1.12 owner validator preflights gold-family disjointness before expensive gold construction and again after loading an existing gold directory.

If building new gold, select three empirical model families that satisfy Section 5.

Example shape only:

```text
PRIMARY          GPT-OSS
BLIND            NuExtract/Qwen group
COLD             DeepSeek
GOLD A           MedGemma/Gemma group
GOLD B           Devstral/Mistral group
GOLD C           another group disjoint from PRIMARY and BLIND
```

The exact choices depend on the installed estate and truthful registry lineage.

Do not use a model from the PRIMARY family to author gold used to score PRIMARY. Do not use a model from the BLIND family to author gold used to score BLIND. This restriction applies at the **independence-group/family level**, not merely to exact aliases.

---

## 9. Smoke the selected providers first

The owner harness performs bounded one-unit provider smoke before the full pilot. A configured provider timeout or malformed response is a failure.

Do not treat successful CLI startup as semantic validation. Smoke proves invocation and schema plumbing only.

---

## 10. Run the one-command real proof

Example command shape only; substitute exact owner paths and registered tags:

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

If using an existing frozen gold directory, use `--gold-dir` instead of the three gold-construction arguments. The harness must still verify the gold source hash, exact unit-hash manifest, reference hash, construction identities, and family disjointness.

If a provider needs an Ollama thinking option, use only a value supported by that runtime/model and record it.

Do not lower timeouts merely to make a slow model appear better.

---

## 11. Required end-to-end proof

A successful owner run must establish all applicable items below:

- exact Machines PDF SHA-256;
- exact sealed 09D r3 SHA-256;
- exact eight governed source units;
- recomputed source-unit content hashes match governed hashes;
- declared source-unit hashes match recomputed hashes;
- PRIMARY/BLIND/COLD are registered empirical models;
- PRIMARY/BLIND/COLD role independence passes;
- full factory tests pass;
- exact protected build is re-certified;
- preflight verify passes;
- real-provider smoke passes;
- source-first gold is bound to the exact source units;
- gold construction has three distinct empirical groups;
- gold groups are disjoint from PRIMARY and BLIND groups;
- real eight-unit semantic appliance completes;
- PRIMARY and BLIND both emit non-empty candidate sets;
- 09D bytes are unchanged before and after;
- comparison is `MOTION1_AUTHORITY` and cycle-safe;
- comparison verifies the exact pinned r3 target;
- strict Motion-2 authority binding is positively verified;
- numeric temperature/pressure context guard executes;
- every emitted `CONTRADICTION` satisfies the structural contradiction gate;
- W2/S1 PRIMARY and BLIND roles are scored against contamination-safe source-first gold;
- BLIND score uses an independent PRIMARY baseline;
- higher-risk units are scored separately;
- Table 6.1 is scored separately when present;
- final owner-validation package verifies.

The final report label is intentionally conservative:

```text
EXECUTED_AND_MEASURED_WITH_EXPLICIT_LIMITS
```

That means execution and measurement completed. It does not mean every semantic stratum is certified.

---

## 12. Review-required outcomes must remain visible

Do not convert any of these into PASS merely to improve the dashboard:

- Table 6.1 low precision/recall;
- table-cell binding ambiguity;
- lost units or temperature/pressure qualifiers;
- numeric-context review rows;
- surviving 09D contradictions;
- failed provisional PRIMARY/BLIND thresholds;
- cold-audit disagreement/failure;
- unresolved W3/S3 visual/table/cross-page semantics;
- E3 clinically material distortion remaining `NOT_MEASURED`;
- Reference-v2 historical challenge expansion remaining `NOT_RUN`.

`NOT_RUN` never means `PASS`.

---

## 13. Contradictions remain review evidence, not truth

The harness writes:

```text
09D/CONTRADICTION_REVIEW_QUEUE.jsonl
```

For every surviving contradiction inspect:

- source evidence;
- proposition;
- subject identity;
- predicate identity;
- fact family;
- context/qualifiers;
- unit/dimension;
- numeric relation;
- highest-ranked 09D comparison row.

The contradiction gate requires high-confidence structural compatibility before emitting the state, but even a structurally valid contradiction may represent a legitimate source-vs-09D difference.

09D is not gold.

---

## 14. Table 6.1 is a separate acceptance surface

Inspect independently:

```text
BENCHMARK/primary_TABLE6_1.json
BENCHMARK/blind_TABLE6_1.json
```

Do not let strong prose performance hide weak table performance.

Specifically review:

- wrong row/column binding;
- neighboring-value leakage;
- dropped unit;
- dropped temperature qualifier;
- pressure/context confusion;
- incorrect assertion that a table cell is absent when it is present.

W3/S3 table/visual semantics remain outside automatic certification unless an applicable governed benchmark is added.

---

## 15. Required outputs

At minimum preserve:

- `OWNER_REAL_VALIDATION_REPORT.json`;
- `OWNER_REAL_VALIDATION_OUTCOME.json`;
- `OWNER_VALIDATED_<RUN_ID>.zip`;
- `BENCHMARK/primary_W2_S1.json`;
- `BENCHMARK/blind_W2_S1.json`;
- higher-risk benchmark reports when applicable;
- Table 6.1 benchmark reports when applicable;
- `BENCHMARK/provisional_certification_dry_run.txt`;
- `09D/CONTRADICTION_REVIEW_QUEUE.jsonl`;
- comparison/projection/authority/context artifacts;
- provider timing/retry telemetry;
- exact registry/model lineage used.

Do not automatically apply provisional certification changes to the registry. Review the dry run first.

---

## 16. Acceptance decision before expansion

Do **not** launch the entire 2,724-page textbook automatically after one eight-unit run.

First assess:

1. PRIMARY W2/S1 recall and precision;
2. BLIND omission recovery and useful-new precision;
3. evidence fidelity;
4. qualifier and numeric preservation;
5. E4 mechanical cue-injection proxy;
6. Table 6.1 metrics and row-level errors;
7. cold-audit findings;
8. every surviving 09D contradiction;
9. numeric-context review rows;
10. unresolved route count;
11. provider latency/retries/failure rate.

Then choose one of:

- repair the prompt/provider/specialist layer and rerun the same pilot;
- change a model role and rerun the same benchmark;
- expand the benchmark;
- or proceed to a bounded 25–50 page pilot.

Only after a bounded expansion behaves consistently should Nemo propose a larger extraction wave.

---

## 17. Nemo/Hermes authority boundary

Nemo/Hermes may supervise aggressively, diagnose failures, and propose fixes, but may not:

- edit source evidence to make a test pass;
- trust spoofed declared content hashes;
- spoof model-family independence;
- use same-family aliases to bypass gold contamination rules;
- mark its own model role certified;
- write to 09D;
- canonicalize assertions automatically;
- merge identities automatically;
- override readiness/package integrity;
- convert review-required or NOT_RUN states to PASS;
- declare W3/S3 certified without an applicable benchmark.

The deterministic factory remains the authority over what counts as proof.
