# HERMES EXTRACTION FACTORY — LIVING ARCHITECTURE

## 1. DOCUMENT CONTROL
- Canonical document: `HERMES_EXTRACTION_FACTORY_LIVING_ARCHITECTURE.md`
- Architecture version: `v1.0`
- Program turn: `TURN_10`
- State: `FROZEN_V1`
- Architecture status: **FROZEN**
- Reference deterministic runtime: **OFFLINE_CERTIFIED**
- Semantic model runtime: **NOT_EMPIRICALLY_CERTIFIED**
- Production semantic deployment: **BLOCKED_PENDING_EMPIRICAL_GATES**
- Last major decision: freeze the architecture and offline reference runtime while explicitly refusing to claim empirical model/runtime performance that has not yet been measured.
- Architecture confidence: **HIGH**
- Empirical semantic confidence: **UNESTABLISHED UNTIL BENCHMARK**

## 2. EXECUTIVE ARCHITECTURE

### North star
Build a persistent, governed multi-model extraction factory that can equal or exceed the **whole-estate quality** of the existing GPT-5.6 Sol chat lanes while improving throughput, resumability, specialization, auditability, and cost efficiency.

The factory is organized around capabilities, not permanent model-named lanes.

```text
FROZEN SOURCE
    |
    v
SOURCE ORIENTATION + RISK MAP
    |
    +----------------------------+
    |                            |
    v                            v
PRIMARY PROPOSITION        SPECIALIZED PASSES
EXTRACTION                 numeric / qualifier /
    |                      relation / visual
    +-------------+--------------+
                  |
                  v
          BLIND RECALL REVIEW
                  |
                  v
      DETERMINISTIC RECONCILIATION
                  |
                  v
          PRECISION REVIEW
                  |
                  v
      DETERMINISTIC VALIDATORS
                  |
                  v
              RISK ROUTER
       +----------+-----------+
       |          |           |
       v          v           v
    LOCAL     SPECIALIST   FRONTIER
   ACCEPT     REPAIR       ESCALATE
       \          |           /
        +---------+----------+
                  |
                  v
        SEMANTIC ADJUDICATION
                  |
                  v
        INDEPENDENT COLD AUDIT
                  |
                  v
         PACKAGE ACCEPTANCE
```

### Strategic hypothesis
A free/cheap-heavy Hermes factory can outperform a single frontier chat lane at the estate level **if** it adds blind independent recall, narrow specialization, persistent state, deterministic verification, explicit uncertainty routing, and independent final adjudication.

Cheap-model consensus is never authority.


### Turn 02 routing rule

The factory now distinguishes **task risk** from **source risk**.

```text
TASK CLASS:   W0 Mechanical -> W1 Literal -> W2 Bounded Semantic -> W3 Context/Binding -> W4 Adjudication
SOURCE RISK:  S0 Simple     -> S1 Moderate -> S2 Complex          -> S3 Critical
```

The combined matrix controls compute intensity. Free agents may own W1 and participate heavily in W2, but they may not close W3/W4 tasks. High source risk can upgrade the required reviewer even when the task itself is unchanged.


## 2A. META-DERIVED ENGINEERING ADOPTION REGISTER

Meta is an engineering reference only. It is **not** a production dependency for Morgan, Nagelhout, Kimi, or Machines lanes.

Turn 09 adopts/adapts:
- immutable evidence substrate;
- typed evidence representations;
- provenance before semantics;
- multidimensional rights metadata;
- read-only 09D boundary;
- explicit implementation/certification states;
- schema coverage;
- backend-neutral logical contracts;
- generated canonical preflight;
- empirical certification ladder;
- adversarial canaries;
- one root verification entrypoint;
- root-level test isolation.

The machine-readable register is:
`META_DERIVED_ADOPTION/META_DERIVED_ENGINEERING_ADOPTION_REGISTER_v0_1.json`.

## 2B. IMPLEMENTATION MATURITY MATRIX

Controlled states:
`NOT_IMPLEMENTED`, `SKELETON_ONLY`, `IMPLEMENTED_UNTESTED`, `OFFLINE_CERTIFIED`, `EMPIRICALLY_CERTIFIED`, `LIVE_CERTIFIED`, `EXPERIMENTAL`, `BLOCKED`.

Critical current truth:
- source identity/page artifacts/source units: offline-certified for the Machines pilot;
- capsule generation: implemented for the pilot;
- validators/preflight: offline-certified reference implementation;
- primary/blind model adapters: not implemented;
- scheduler/provider adapters/Buzz bridge: not implemented beyond contracts/skeletons;
- benchmark results: not run;
- model certifications: absent.

The matrix prevents architectural maturity from being mistaken for executable production maturity.

## 3. NON-NEGOTIABLE INVARIANTS

1. **Candidate generation is not truth generation.** All extracted assertions remain `SOURCE_ASSERTION_CANDIDATE / UNREVIEWED / NON_CANONICAL` until downstream adjudication.
2. **Source authority dominates model inference.** Source bytes/pages > cryptographic source identity > exact source-derived evidence > governed schemas/contracts > validated provenance > candidates > queues > state > prompts > inference.
3. **Exact evidence is immutable.** Structured interpretation may change; quoted evidence may not be silently rewritten.
4. **No self-certification.** A producer cannot be the sole certifier of meaningful semantic work.
5. **No candidate-count quotas.** Density is an anomaly detector only.
6. **No silent disappearance.** Material regions must receive explicit disposition.
7. **Rebuilds are new derivatives.** Missing historical bytes may be rebuilt from source, but never impersonated as historical recovery.
8. **Determinism before reasoning.** Use code for mechanical facts whenever possible.
9. **Turnkey review.** Frontier reviewers should not perform filesystem archaeology.
10. **Model identity matters.** Aliases of the same underlying family do not count as fully independent review.
11. **Uncertainty remains visible.** Ambiguity routes to review/defer.
12. **Failure locality.** One blocked work unit must not halt unrelated safe work.

## 4. CURRENT SYSTEM DIAGRAM

### Trust domains

```text
TIER A — CANDIDATE PRODUCTION
free / very cheap agents
        |
        v
TIER B — SPECIALIST REPAIR
strong efficient agents
        |
        v
TIER C — FRONTIER ADJUDICATION
highest-value semantic judges
        |
        v
INDEPENDENT COLD AUDIT
```

### Persistent control plane
Hermes should maintain a control plane separate from semantic workers:

```text
GLOBAL LEDGER
  ├── source identities
  ├── work-unit leases
  ├── state transitions
  ├── checkpoints
  ├── validator receipts
  ├── model identity/version
  ├── calibration history
  └── escalation history
```

Workers must be replaceable without losing state.

## 5. TASK TAXONOMY

Turn 02 decomposes the factory into task classes that differ in **semantic risk, error detectability, and whether a free worker may close the task**.

### 5.1 Work-risk classes

| Class | Name | Definition | Free worker may perform? | Free worker may close? |
|---|---|---|---:|---:|
| `W0` | Mechanical | answer is reproducible by deterministic computation from current bytes | yes, but code preferred | yes, after validator |
| `W1` | Literal enumeration | identify explicit source surface features without interpreting their semantic role | yes | yes only as an inventory, never as semantic truth |
| `W2` | Bounded source semantics | proposition/qualifier/list meaning is local and evidence is explicit | yes | **no sole closure**; independent review required |
| `W3` | Contextual / binding semantics | meaning depends on binding, context, direction, row-column association, cross-page scope, or repair judgment | assist only or primary if benchmarked | **no**; Tier B mandatory |
| `W4` | Adjudicative / authority-sensitive | disputed meaning, ambiguous high-impact interpretation, evidence challenge, merge/reject/promotion decision | assist only | **no**; Tier C required |

`W0–W4` is a task-risk classification, not a quality ranking of models.

### 5.2 Formal risk dimensions

Each semantic task receives a 0–3 score on seven dimensions:

| Code | Dimension | 0 | 3 |
|---|---|---|---|
| `A` | semantic ambiguity | literal/unambiguous | multiple plausible meanings |
| `C` | context dependence | self-contained span | cross-sentence/page/chapter dependent |
| `B` | binding sensitivity | no binding | number/qualifier/endpoint can attach to multiple targets |
| `V` | visual/layout dependence | text-only | table/figure/topology/layout determines meaning |
| `O` | omission consequence | low | omission materially degrades downstream knowledge |
| `F` | false-positive consequence | low | wrong assertion materially misleads downstream knowledge |
| `D` | error detectability difficulty | easy deterministic detection | plausible error hard to detect mechanically |

`TASK_RISK_SCORE = A + C + B + V + O + F + D` (0–21).

This score is a routing aid, not an automatic authority rule. Certain **hard-stop features** force a minimum class regardless of score.

### 5.3 Hard-stop features

The following automatically force at least `W3` unless the task is merely a literal inventory:

- numeric parameter binding;
- range/inequality interpretation;
- pronoun or anaphora resolution;
- cross-page subject/object resolution;
- table row-column association;
- visual topology or diagram meaning;
- OCR-damaged units or symbols;
- relationship directionality;
- exception/negation scope with multiple candidate targets;
- merge/reject decisions;
- conflicting historical state where semantic content differs.

The following force `W4`:

- persistent semantic disagreement after Tier B review;
- `SOURCE_EVIDENCE_CHALLENGE`;
- promotion/rejection of clinically meaningful disputed assertions;
- contradictory source interpretations with no deterministic resolution;
- final adjudication of high-risk families designated by the risk router.

### 5.4 Decomposed task registry

| Task | Class | Cheap/free role | Required closure |
|---|---|---|---|
| `SOURCE_FILE_HASH` | W0 | not needed | deterministic |
| `PAGE_MAP_VERIFY` | W0 | assist | deterministic |
| `SCHEMA_VALIDATE` | W0 | not needed | deterministic |
| `ID_UNIQUENESS` | W0 | not needed | deterministic |
| `MANIFEST_RECOMPUTE` | W0 | not needed | deterministic |
| `ASSET_EXISTENCE_HASH` | W0 | not needed | deterministic |
| `EXACT_DEDUPE` | W0 | assist | deterministic |
| `SOURCE_ORIENTATION` | W1/W2 | good fit | deterministic/independent spot-check |
| `PAGE_RISK_CLASSIFICATION` | W1/W2 | good fit | rule engine + calibrated review |
| `LITERAL_NUMERIC_CENSUS` | W1 | excellent fit | inventory validator |
| `LITERAL_QUALIFIER_CENSUS` | W1 | good fit | inventory only |
| `VISUAL_PRESENCE_CENSUS` | W1 | good fit | asset/page verification |
| `REGION_SEGMENTATION` | W1/W2 | good fit | deterministic overlap checks |
| `PRIMARY_PROPOSITION_EXTRACTION` | W2 | strong candidate use | independent semantic review |
| `BLIND_RECALL_REVIEW` | W2 | strong candidate use | union + later precision |
| `LIST_ITEM_ENUMERATION` | W1/W2 | strong candidate use | parent-scope check |
| `LIST_ATOMICITY_REVIEW` | W2/W3 | useful | Tier B on ambiguous scope |
| `QUALIFIER_DETECTION` | W1/W2 | useful | not semantic closure |
| `QUALIFIER_BINDING` | W3 | assist | Tier B |
| `NEGATION_DETECTION` | W1/W2 | useful | not semantic closure |
| `NEGATION_SCOPE_BINDING` | W3 | assist | Tier B |
| `NUMERIC_PARAMETER_BINDING` | W3 | assist | Tier B |
| `UNIT_NORMALIZATION` | W2/W3 | assist | deterministic dictionary + Tier B on ambiguity |
| `RANGE_INEQUALITY_INTERPRETATION` | W3 | assist | Tier B |
| `RELATIONSHIP_PROPOSAL` | W2/W3 | useful | independent provenance review |
| `RELATIONSHIP_DIRECTION_CERTIFICATION` | W3 | assist | Tier B |
| `CROSS_PAGE_CONTEXT_RESOLUTION` | W3 | assist | Tier B |
| `TABLE_TRANSCRIPTION` | W1/W2 | useful | structural validator / visual check |
| `TABLE_SEMANTIC_BINDING` | W3 | assist | Tier B multimodal |
| `FIGURE_CAPTION_EXTRACTION` | W1/W2 | useful | evidence verification |
| `FIGURE_TOPOLOGY_INTERPRETATION` | W3/W4 | assist | Tier B or C |
| `OCR_CONFLICT_RESOLUTION` | W3 | assist | Tier B + source image |
| `RESIDUAL_REGION_CENSUS` | W1/W2 | good fit | deterministic coverage check |
| `COMPLETENESS_CLAIM` | W4 | no | never inferred from one worker; gate-based only |
| `PRECISION_REVIEW` | W3 | assist | Tier B |
| `STATE_BYTE_RECOVERY` | W0/W1 | good controller task | deterministic |
| `STATE_SEMANTIC_RECONCILIATION` | W3/W4 | assist | Tier B/C |
| `LINEAGE_RECONCILIATION` | W0/W2 | good controller task | deterministic + review on conflicts |
| `EVIDENCE_FAMILY_CONSTRUCTION` | W0/W2 | good fit | deterministic grouping + semantic spot-check |
| `STRUCTURAL_SANITIZATION` | W0/W2 | good fit | validator + spot-check |
| `RISK_ROUTING` | W0/W2 | controller | rule engine; model only for uncertain features |
| `SEMANTIC_ADJUDICATION` | W4 | no | Tier C |
| `FRONTIER_COLD_AUDIT` | W4 | no | independent Tier C |
| `PACKAGE_ACCEPTANCE` | W0 | not needed | deterministic |

### 5.5 Tasks that appear easy but are not

The factory must treat these as common traps:

1. **“Extract all numbers.”** Literal census is easy; deciding what the number modifies is not.
2. **“Capture qualifiers.”** Detecting words like *may*, *except*, *after*, or *unless* is easy; binding their scope is not.
3. **“Split a bullet list.”** Item boundaries can be obvious while shared parent qualifiers silently disappear.
4. **“Read a table.”** Cell text can be transcribed correctly while row/column semantics are wrong.
5. **“Resolve a pronoun.”** A grammatically plausible antecedent may create a clinically wrong relationship.
6. **“Deduplicate.”** Exact duplicates are mechanical; semantic near-duplicates may encode different qualifiers.
7. **“Recover the latest state.”** File timestamps and counts are mechanical; deciding whether two generations represent the same semantic state may not be.
8. **“Check completeness.”** High source coverage does not prove atomic semantic completeness.
9. **“Normalize units.”** OCR corruption can turn harmless normalization into semantic fabrication.
10. **“Build evidence families.”** Shared spans are mechanical; merging semantically distinct assertions is not.

### 5.6 Tier-A default-safe work

Free agents may be the default worker for:

- source orientation proposals;
- page/region risk feature detection;
- literal numeric census;
- literal qualifier/negation census;
- visual/table presence census;
- proposition candidate generation;
- blind recall candidate generation;
- list-item enumeration;
- residual-region discovery;
- low-risk structural sanitation;
- candidate-family suggestions.

They remain bound by exact-evidence and non-canonical rules.

### 5.7 Tier-A prohibited closure

Free workers must not be the final authority for:

- numeric parameter binding;
- ambiguous unit repair;
- qualifier/negation scope;
- relationship directionality;
- table semantic binding;
- figure topology;
- OCR conflict resolution;
- cross-page subject resolution;
- semantic dedupe/merge;
- disputed state reconciliation;
- `RETAIN/REPAIR/MERGE/REJECT` on high-risk candidates;
- completeness certification;
- frontier-ready certification.

## 6. TRUST AND AUTHORITY MODEL

### Tier A — Candidate production
May discover, enumerate, propose, split, flag, and identify omissions. May not canonicalize, override source evidence, silently resolve ambiguity, or self-declare frontier readiness.

### Tier B — Specialist repair
May perform bounded semantic repair, numeric binding, visual interpretation, relationship repair, precision cleanup, and state-recovery assistance. Still non-canonical by default.

### Tier C — Frontier adjudication
Allowed decision vocabulary:
- `RETAIN`
- `REPAIR`
- `MERGE`
- `REJECT`
- `DEFER`
- `SOURCE_EVIDENCE_CHALLENGE`

High-risk adjudication still receives package acceptance and, where appropriate, cold audit.

## 7. MODEL ROLE REGISTRY

All model-role assignments remain hypotheses until they pass the benchmark defined in Turn 03.

### 7.1 Candidate roster

| Model/family | Cost class | Hypothesized strengths | Benchmark emphasis |
|---|---|---|---|
| Muse Spark 1.2 | Free / very low | W2 proposition extraction, multimodal support | W2 recall, atomicity, evidence fidelity |
| X Preview / underlying family | Free / very low | structured precision, atomicity, semantic cleanup | W2 precision, W3-assist |
| HY3 | Free / very low | grounding, omission review | blind recall, evidence fidelity |
| Nemotron Ultra | Free / very low | planning/control/state work | W0/W1 orchestration, durability |
| Laguna | Free / very low | coding/tool execution | validator/tooling reliability, not primary semantic rank |
| Kimi K3 | Specialist | high recall, long-context extraction | W2 extraction, S2/S3 robustness |
| Gemini Flash High | Specialist | multimodal recall, PDF/visual audit | blind recall, tables/figures |
| GLM Max | Specialist | precision and agentic reasoning | W3 binding/repair |
| Qwen Max | Specialist | numeric/relationship/qualifier reasoning | W3 binding/repair |
| DeepSeek V4 | Specialist | alternate reasoning family | W2/W3 assist |
| MiniMax M3 | Specialist/cheap | long-context agent work | secondary W2/W3 assist |
| Sonnet 5 | Specialist/frontier-adjacent | tooling, recovery, long-running orchestration | state recovery, packaging, W3 |
| GPT-5.6 Sol | Frontier | adjudication, cold audit, architecture | W4/cold audit |
| Opus 5 | Frontier | difficult semantic adjudication | W4 |
| Fable 5 | Frontier | prolonged difficult knowledge work | pathological W4 / whole-estate disputes |

### 7.2 Role eligibility is earned, not assumed

A model can hold multiple role certifications. Example:

```text
Muse Spark 1.2
  PRIMARY_W2_S0: CERTIFIED
  PRIMARY_W2_S1: CERTIFIED
  PRIMARY_W2_S2: NOT_CERTIFIED
  BLIND_RECALL_W2: CERTIFIED
  NUMERIC_BINDING_W3: PROHIBITED
```

The factory routes by **certification tuple**:

`(model_id, task_role, W_class, S_class, benchmark_version)`

not by a vague global model rank.

### 7.3 Model identity record

Every benchmark and production run should record, when observable:

- provider;
- public alias;
- underlying family;
- exact model/version string;
- context configuration;
- reasoning/thinking level;
- tool permissions;
- sampling parameters if configurable;
- benchmark date;
- provider endpoint;
- free/paid status at time of test.

An alias change invalidates or downgrades prior certification until a regression test passes.

## 8. MODEL CALIBRATION MATRIX

Turn 03 establishes the benchmark methodology.

### 8.1 Gold-standard principle

**Existing extraction outputs are evidence, not gold.**

SOL, Kimi, Gemini, Opus, or any other prior candidate population may be used only after gold construction to:
- identify additional possible omissions;
- enrich challenge sets;
- analyze historical failure modes.

They may not define the answer key by agreement.

### 8.2 Gold construction pipeline

For each benchmark source unit:

```text
FROZEN SOURCE UNIT
      |
      +--> Gold Builder A — source-only
      |
      +--> Gold Builder B — source-only, independent
      |
      +--> deterministic literal inventories
      |      numbers / units / explicit negation markers / visual presence
      |
      v
DISAGREEMENT SET
      |
      v
Gold Adjudicator C — source + A/B disagreements only
      |
      v
MECHANICAL VERIFICATION
      |
      v
REFERENCE ASSERTION SET v1
      |
      +--> historical outputs revealed only now
              |
              v
          CHALLENGE PASS
              |
              v
REFERENCE ASSERTION SET v2
```

Gold Builder A and B should be strong, different model families where practical. Gold Adjudicator C must not simply majority-vote; it must decide from source evidence.

For the most important benchmark units, a human/source-owner spot audit may be added later, but the architecture does not assume one is always available.

### 8.3 Benchmark corpus design

Initial benchmark should contain **48 bounded source units**, not whole textbooks.

Proposed strata:

| Stratum | Units | Primary challenge |
|---|---:|---|
| `B0` ordinary prose | 6 | proposition recall/precision |
| `B1` dense bullet/list | 6 | atomicity/shared qualifiers |
| `B2` numeric/range | 6 | literal census and binding traps |
| `B3` qualifier/negation | 6 | modality, exception, scope |
| `B4` relationships | 6 | directionality/coreference |
| `B5` tables | 6 | row-column semantics |
| `B6` figures/visuals | 6 | visual grounding |
| `B7` OCR/cross-page/mixed | 6 | failure resilience |

Each unit should usually be 1–4 pages. Some cross-page units may be larger when the semantic boundary requires it.

The 48-unit size is an **initial experimental target**, not a permanent requirement.

### 8.4 Source diversity

Benchmark units should be drawn from multiple estates so a model cannot overfit one textbook style.

Preferred initial sources:
- Morgan & Mikhail;
- Nagelhout;
- Understanding Anesthesia Equipment;
- one additional source only if frozen authority and rights/workflow permit.

Use pages already known to exhibit failure modes, but hide historical outputs from workers.

### 8.5 Worker blindness levels

#### BLIND-A — source only
Used for:
- primary extraction;
- blind recall extraction;
- literal inventories.

#### BLIND-B — source + task schema
Used for:
- numeric/qualifier/relationship specialist tasks.

#### REVIEW — source + candidate set
Used for:
- precision;
- repair;
- W3 assist.

#### ADJUDICATION — source + bounded disagreement family
Used for W4 benchmark.

Do not benchmark a primary extractor by showing it the reference answers.

### 8.6 Core metrics

#### W1 literal inventory metrics
Where exact comparison is possible:

- literal recall;
- literal precision;
- exact unit/token fidelity;
- page localization accuracy;
- false invention count.

#### W2 proposition metrics

Because semantic assertions are not always exact-string equivalent, scoring uses a matching protocol:

- **semantic unit recall**
- **semantic unit precision**
- **atomicity**
- **evidence fidelity**
- **qualifier preservation**
- **negation preservation**
- **source localization**
- **unsupported inference rate**

A candidate matches a gold assertion only if:
1. its semantic proposition is equivalent or safely more specific without contradiction;
2. material qualifiers are preserved;
3. evidence actually supports it.

#### W3 assist metrics

Models are scored on:
- correct repair proposal rate;
- harmful repair rate;
- correct defer rate;
- binding accuracy;
- calibration/abstention quality.

A W3 benchmark does **not** grant autonomous closure authority merely from a high aggregate score; certification remains role-specific.

### 8.7 Error severity

Every error receives severity:

- `E0` cosmetic/non-semantic;
- `E1` minor structural;
- `E2` meaningful omission/noise;
- `E3` clinically material semantic distortion;
- `E4` fabricated/contradictory source claim.

`E4` is a hard safety defect.
Repeated `E3` defects can block production certification even with high aggregate recall.

### 8.8 Evidence-fidelity hard gate

For production eligibility:

- ordinary text assertions must not fabricate source evidence;
- evidence hash/location must be reproducible;
- unsupported source quotations are disqualifying until corrected.

Proposed gate:
`E4 evidence fabrication count = 0` on certification benchmark.

### 8.9 Provisional certification thresholds

These are **experimental deployment thresholds**, subject to recalibration after first results.

#### `CERT-W1`
For literal inventory roles:
- recall >= 0.98;
- precision >= 0.98;
- no invented source tokens materially affecting meaning.

#### `CERT-W2-S0`
For primary W2 work on simple regions:
- semantic recall >= 0.92;
- semantic precision >= 0.92;
- evidence fidelity = 1.00 for accepted ordinary text claims;
- E4 = 0;
- E3 rate <= 0.5%;
- atomicity failure <= 5%.

#### `CERT-W2-S1`
- recall >= 0.94;
- precision >= 0.93;
- evidence fidelity = 1.00;
- E4 = 0;
- E3 rate <= 0.5%;
- qualifier preservation >= 0.95 where applicable.

#### `CERT-BLIND-RECALL`
Reviewer judged by **marginal useful recall**, not standalone precision alone:
- finds >= 50% of seeded omissions in challenge set;
- useful-new-candidate precision >= 0.70;
- E4 = 0.

#### `CERT-W3-ASSIST`
- binding/repair accuracy >= 0.95;
- harmful repair rate <= 1%;
- E4 = 0;
- appropriate defer/abstention on ambiguous cases >= 0.90.

No free model certification threshold can authorize W3 closure; W3 certification means **eligible assistant or first-pass specialist only** unless architecture is later amended.

### 8.10 Confidence and sample adequacy

Do not certify from a handful of pages.

Minimum initial certification:
- at least 24 relevant benchmark units for a broad W2 role, or
- all available units for a narrow role with at least 100 adjudicated assertion opportunities.

Report:
- point estimate;
- numerator/denominator;
- Wilson 95% confidence interval for proportions where applicable;
- per-stratum results;
- worst-stratum result.

A strong average cannot hide catastrophic performance in a critical stratum.

### 8.11 Long-session reliability is separate

Semantic intelligence and agent reliability are distinct.

Track:
- capsule completion rate;
- checkpoint correctness;
- accidental overwrite count;
- validator invocation compliance;
- state-reconstruction success;
- tool-call failure recovery;
- instruction drift;
- average work completed before intervention;
- context-reset behavior.

A model can be semantically strong but operationally unfit as a persistent controller.

### 8.12 Model profile states

- `UNBENCHMARKED`
- `BENCHMARKING`
- `PROVISIONAL`
- `CERTIFIED`
- `CERTIFIED_WITH_LIMITS`
- `SUSPENDED`
- `DEMOTED`
- `RETIRED`

### 8.13 Promotion and demotion

Promote when:
- threshold met;
- no hard-gate failure;
- minimum sample satisfied;
- role-specific failure modes understood.

Demote/suspend when:
- provider alias materially changes;
- two consecutive regression samples fall below threshold;
- any unexplained E4 fabrication appears in production;
- long-session state corruption occurs;
- validator bypass or contract drift repeats.

Certification must have an expiry/retest policy in later turns.

## 9. SOURCE RISK CLASSIFICATION

Task risk and source risk are separate. A low-risk task can operate on a high-risk page, but routing may require stronger review.

### 9.1 Source-region risk features

Each region receives feature flags and a weighted score.

| Feature | Weight | Meaning |
|---|---:|---|
| `NUMERIC_DENSE` | +2 | multiple clinically meaningful values/ranges/units |
| `RANGE_THRESHOLD` | +2 | ranges, inequalities, thresholds, incidence or dose limits |
| `QUALIFIER_DENSE` | +2 | multiple conditional/modal/temporal/population qualifiers |
| `NEGATION_EXCEPTION` | +2 | negation, exclusions, except/unless/contraindication structure |
| `RELATIONSHIP_DENSE` | +1 | multiple directional/causal/comparative relations |
| `TABLE_LAYOUT` | +2 | row/column layout carries meaning |
| `FIGURE_VISUAL` | +2 | visual inspection required |
| `FORMULA_EQUATION` | +2 | equation or symbolic relation |
| `OCR_SUSPECT` | +3 | corrupted symbols/units/text suspected |
| `CROSS_PAGE` | +2 | meaning crosses page boundary |
| `MULTICOLUMN_COMPLEX` | +1 | layout may scramble reading order |
| `DENSE_LIST` | +1 | shared parent scope may be lost |
| `ANAPHORA` | +1 | pronouns/referential phrases require antecedent resolution |
| `CONTRAST_EXCEPTION` | +1 | however/whereas/but/except alters scope |
| `CAPTION_DEPENDENT` | +1 | caption/body linkage matters |

### 9.2 Source-risk bands

- `S0 SIMPLE` = score 0–2 and no hard-stop feature.
- `S1 MODERATE` = score 3–5.
- `S2 COMPLEX` = score 6–9 or one hard-stop feature.
- `S3 CRITICAL` = score >=10, OCR conflict, visually dependent high-impact numeric content, or multiple interacting hard-stop features.

These thresholds are **experimental** until EXP-003 calibrates them.

### 9.3 Combined routing matrix

| Task class | S0 | S1 | S2 | S3 |
|---|---|---|---|---|
| W0 | deterministic | deterministic | deterministic | deterministic + manual anomaly review if needed |
| W1 | Tier A | Tier A | Tier A + validation | Tier A inventory + Tier B spot-check |
| W2 | Tier A primary + independent Tier A | Tier A + independent Tier A | Tier A/Tier B primary + independent reviewer | Tier B primary + independent reviewer |
| W3 | Tier B | Tier B | Tier B + independent Tier B/Tier A adversary | Tier B + likely Tier C escalation |
| W4 | Tier C | Tier C | Tier C | Tier C + independent cold audit |

### 9.4 Source-risk classification is advisory, not truth

Risk scoring determines **compute and review intensity**, not semantic outcome. It cannot promote or reject a candidate.

## 10. CAPSULE / WORK-UNIT DESIGN

Turn 04 makes the worker interface operational.

### 10.1 Definition
A capsule is the smallest self-contained governed unit that gives one worker enough context for one role while withholding irrelevant history, prior answers, and authority cues. Original lane ZIPs remain immutable forensic provenance; capsules are production derivatives.

### 10.2 Capsule identity and immutability
ID format: `CAP-<ROLE>-<SOURCE>-<SCOPE>-R###` (for example `CAP-W2PROP-NAG7E-P0321-P0324-R001`). IDs never contain model names. Every capsule pins parent artifact hashes, source SHA-256, primary scope, boundary context, W/S class, blindness class, contract version, expected outputs, validators, retry generation, and allowed statuses.

### 10.3 Standard filesystem
```text
CAPSULE/
├── CAPSULE_MANIFEST.json
├── TASK_CONTRACT.md
├── SOURCE/
│   ├── source_identity.json
│   ├── primary/
│   └── boundary_context/
├── INPUT/
├── OUTPUT/
│   └── .staging/<run_id>/
└── VALIDATION/
    └── validator_contract.json
```
`SOURCE/` and manifest/parent references are read-only to workers.

### 10.4 Blindness classes
- `BLIND_SOURCE_ONLY`: source + contract + schema only. Used for primary extraction, blind recall, literal inventories.
- `BLIND_STRUCTURED_INPUT`: source + bounded structured problem without prior decision/explanation.
- `REVIEW_BOUND`: source + candidate/evidence family + queue reason. Used for W3 repair/precision.
- `ADJUDICATION_BOUND`: source + bounded disagreement + competing proposals + validator facts. Model names/vote counts hidden by default.
- `RECOVERY_BOUND`: only competing bytes/manifests/hashes/checkpoints needed for one authority conflict; source added only when rebuild/reconciliation is authorized.

### 10.5 Boundary context
Primary scope and boundary context are distinct. Boundary pages may inform interpretation but do not silently expand ownership. A candidate supported only by boundary context is marked `BOUNDARY_CONTEXT_ONLY` and deferred/reassigned unless the contract explicitly authorizes cross-boundary resolution.

### 10.6 Capsule types
1. **EXTRACTION_CAPSULE** — W2 primary proposition extraction. Source-only. Outputs candidates, uncertainty queue, coverage regions, receipt.
2. **RECALL_CAPSULE** — independent omission discovery. Must not see primary output until both are complete.
3. **NUMERIC_CAPSULE** — separate `NUMERIC_LITERAL` W1 census from `NUMERIC_BINDING` W3 semantic binding.
4. **QUALIFIER_CAPSULE** — separate literal qualifier/negation detection from W3 scope binding.
5. **RELATIONSHIP_CAPSULE** — proposal mode vs W3 endpoint/direction provenance review.
6. **VISUAL_CAPSULE** — hashed page render/crop plus bounded task; modes include census, table transcription, table binding, figure interpretation, OCR resolution.
7. **PRECISION_CAPSULE** — one evidence family/small cluster plus source and queue reasons; outputs keep/repair/split/merge/reject-proposal/defer.
8. **RECOVERY_CAPSULE** — exact competing state required for one authority question; outputs recover exact/select current/rebuild derivative/semantic reconciliation required/block.
9. **FRONTIER_ADJUDICATION_CAPSULE** — smallest turnkey W4 family; decisions RETAIN/REPAIR/MERGE/REJECT/DEFER/SOURCE_EVIDENCE_CHALLENGE.

### 10.7 Initial context budgets
| Source class | Primary scope | Boundary context |
|---|---:|---:|
| S0 | 6–8 pages | 1 page/side |
| S1 | 4–6 pages | 1 page/side |
| S2 | 2–4 pages | 1–2 pages/side |
| S3 | 1–2 pages or one logical visual/table unit | as required |
For W3/W4, evidence-family capsules are preferred over page-range capsules. These budgets are experimental.

### 10.8 Minimum-context rule
Exclude by default: historical counts, prior PASS claims, candidate-density expectations, model reputations, unrelated queues/history, prior worker reasoning, whole forensic ZIPs, and downstream promotion status. Extra context requires a manifest justification.

### 10.9 Atomic output protocol
Workers write only to `OUTPUT/.staging/<run_id>/`. Closure sequence: worker receipt -> deterministic validators -> required semantic gate -> output hashes -> controller atomic commit to accepted run -> append ledger transition. Failed staging is preserved as a failed derivative; retries never overwrite it.

### 10.10 Worker receipt
Every run records run/capsule/lease IDs, model/provider identity, contract version, observed input hashes, output hashes, uncertainties, tool failures, context-reset events, timestamps, completion state, and no-self-certification acknowledgment.

### 10.11 Lease contract
A controller-issued lease defines capsule ID, worker identity, expiry/heartbeat, retry generation, allowed write path, task role, and cancellation state. No active lease means no production commit.

### 10.12 Retry semantics
Retries create R002/R003... They are for tool failure, timeout, validator failure, context overflow/drift, or provider failure. Semantic disagreement is normally an escalation, not a retry.

### 10.13 Recombination
Accepted capsule outputs are deterministically recombined into batch/region ledger -> evidence families -> candidate global index -> queue index -> state summary -> frontier package. Every global record retains originating capsule/run IDs and immutable evidence/source lineage.

### 10.14 Capsule states
`CREATED -> LEASED -> RUNNING -> STAGED -> VALIDATING -> ACCEPTED`, with `FAILED_RETRYABLE`, `FAILED_ESCALATE`, `DEFERRED`, `CANCELLED`, `SUPERSEDED`. `RUNNING -> ACCEPTED` directly is illegal.

## 11. MULTI-AGENT TOPOLOGY

Turn 05 selects a **risk-adaptive hybrid topology**.

No single execution graph is optimal for every source region.

### 11.1 Topology families considered

#### Topology A — Primary + Blind Recall + Precision

```text
SOURCE
  -> PRIMARY W2
  -> BLIND RECALL W2
  -> DETERMINISTIC UNION
  -> PRECISION
  -> VALIDATORS
```

Strengths:
- simple;
- cheap;
- good independence;
- low review burden.

Weaknesses:
- numeric/qualifier/visual failure modes may remain under-observed.

#### Topology B — Specialized Parallel Passes

```text
SOURCE
  ├-> PROPOSITION
  ├-> NUMERIC
  ├-> QUALIFIER
  ├-> RELATIONSHIP
  └-> VISUAL
        |
        v
      UNION
        |
        v
  BLIND RECALL
        |
        v
   PRECISION
```

Strengths:
- attacks distinct failure modes;
- useful for complex source.

Weaknesses:
- committee inflation;
- duplicated findings;
- increased adjudication cost;
- multiple cheap workers may share correlated blind spots.

#### Topology C — Dual Independent Primary Extraction

```text
SOURCE
  ├-> PRIMARY A
  └-> PRIMARY B
        |
        v
  MATCH / DISAGREEMENT
        |
        v
      PRECISION
```

Strengths:
- strongest direct independence;
- useful for high-risk prose-heavy semantic regions.

Weaknesses:
- expensive;
- disagreement volume can be large;
- two similar model families may create false confidence.

#### Topology D — Specialist-First

```text
SOURCE
  -> TIER B PRIMARY
  -> INDEPENDENT ADVERSARY
  -> PRECISION / VALIDATION
```

Strengths:
- suitable for S3/W3-heavy units;
- avoids cheap-agent churn where semantic complexity is predictably high.

Weakness:
- higher direct cost.

### 11.2 Accepted default: risk-adaptive hybrid

The factory selects topology by **W class + S class + model certification**.

#### `S0 / ordinary W2`
Default:
`Topology A`

```text
Free/cheap certified W2 primary
  -> independent free/cheap blind recall
  -> deterministic union
  -> lightweight precision
```

Goal:
maximize throughput while retaining independent omission detection.

#### `S1 / moderate W2`
Default:
`Topology A+`

```text
W2 primary
  + blind recall
  + targeted literal numeric/qualifier census when features present
  -> union
  -> precision
```

Do not run every specialist pass unless source features justify it.

#### `S2 / complex W2`
Default:
`Topology B-lite or C`

Decision rule:
- if complexity comes from **heterogeneous features** (numbers + qualifiers + tables), use targeted specialized passes;
- if complexity is **dense semantic prose / high omission consequence**, prefer dual independent extraction.

#### `S3 / critical or W3-heavy`
Default:
`Topology D`

```text
Tier B primary/specialist
  -> independent adversary from different family
  -> deterministic validators
  -> bounded precision/adjudication
```

Free agents may still perform W1 literal inventories but should not become the main semantic closure path.

### 11.3 Blindness schedule

The system controls when information becomes visible.

#### Stage 0 — Source classification
Risk classifier sees source only.

#### Stage 1 — Independent candidate generation
Primary and blind recall workers do **not** see each other's outputs.

If dual-primary topology:
Primary A and Primary B remain mutually blind.

#### Stage 2 — Deterministic reconciliation
Only after independent generation finishes:
- normalize IDs/format;
- exact dedupe;
- evidence-span matching;
- candidate-to-source indexing;
- construct disagreement/unique-addition sets.

#### Stage 3 — Precision review
Precision worker sees:
- source;
- reconciled evidence families;
- disagreement markers;
- no model names;
- no vote counts unless explicitly necessary.

#### Stage 4 — Specialist escalation
Specialist sees only unresolved/high-risk families.

#### Stage 5 — Frontier adjudication
Frontier reviewer sees competing semantic proposals but not irrelevant worker reputation.

### 11.4 Deterministic union rules

The union builder may:
- exact-dedupe identical candidate IDs/evidence hashes;
- group equivalent source spans;
- create candidate families;
- mark provenance from multiple independent workers;
- record overlap/disagreement;
- identify unique additions.

It may NOT:
- declare semantic equivalence from superficial lexical similarity;
- merge qualifiers away;
- select a winner based on vote count;
- reject a unique candidate merely because only one worker found it.

Semantic equivalence or merge beyond deterministic rules becomes a precision-review task.

### 11.5 Independence levels

Each reviewer pair gets an independence grade.

- `I3 HIGH`: different providers/families, independent contexts, blind generation.
- `I2 MODERATE`: different model families from same provider or uncertain lineage.
- `I1 LOW`: same underlying family/closely related variant.
- `I0 NONE`: same model/run context or reviewer exposed to primary before independent generation.

For recall certification, prefer `I3` or `I2`.

`I1` agreement must not be treated as strong independent confirmation.

### 11.6 Committee-inflation controls

Every additional worker must justify itself through **marginal yield**.

Metrics:

`MARGINAL_USEFUL_RECALL = accepted unique additions / reference omissions available`

`ADDITION_PRECISION = accepted unique additions / total unique additions proposed`

`REPAIR_YIELD = confirmed repairs / repairs proposed`

`ESCALATION_YIELD = upheld escalations / escalations proposed`

`REVIEW_BURDEN = families requiring human/frontier review / source unit`

A reviewer is not valuable merely because it produces more records.

### 11.7 Reviewer stopping rule

Default stop when ALL are true:
1. latest independent reviewer adds < 2% new accepted semantic units on a rolling calibration window;
2. no new E3/E4 class defect family is discovered;
3. residual-region census has no unexplained material region;
4. numeric/qualifier/visual feature-specific gates pass;
5. current topology meets role-specific benchmark thresholds.

If a new reviewer adds substantial useful recall, the factory may continue one more independent pass or escalate.

Threshold 2% is **experimental** and must be calibrated.

### 11.8 Maximum ordinary reviewer depth

For routine S0/S1 W2 extraction:
- one primary;
- one blind recall worker;
- one precision pass.

A third semantic reviewer is **not default**.

For S2:
- up to two independent candidate generators plus targeted specialist passes.

For S3/W3:
- one strong specialist primary + one independent adversary;
- then frontier escalation only for unresolved families.

This prevents open-ended “review until perfect” loops.

### 11.9 When two free agents beat one paid agent

Prefer two free/cheap independent workers when:
- task is W1/W2;
- source is S0/S1;
- both workers are certified;
- independence grade >= I2;
- expected disagreement/adjudication burden is low;
- historical benchmark shows combined recall materially exceeds either worker alone.

### 11.10 When one paid specialist beats a free committee

Skip cheap semantic committee and route directly to Tier B when:
- task is W3;
- source is S3;
- OCR/visual/table binding dominates;
- numeric/qualifier binding error consequence is high;
- free-agent historical marginal yield is low;
- committee disagreement is known to be high;
- expected review cost exceeds specialist inference cost.

### 11.11 Disagreement routing

Disagreement families receive labels:

- `UNIQUE_PRIMARY`
- `UNIQUE_RECALL`
- `SEMANTIC_CONFLICT`
- `QUALIFIER_CONFLICT`
- `NUMERIC_CONFLICT`
- `RELATIONSHIP_CONFLICT`
- `VISUAL_CONFLICT`
- `ATOMICITY_CONFLICT`
- `SOURCE_SCOPE_CONFLICT`

These route to role-specific precision/specialist capsules.

### 11.12 No vote-based truth

The factory explicitly rejects majority voting as semantic authority.

Examples:
- 3 free agents agreeing does not override exact source evidence.
- one unique worker finding a valid omission is retained for adjudication.
- two related model variants agreeing may count as one low-independence signal.

Votes may inform prioritization, never truth.

## 12. ESCALATION ROUTER

Turn 06 converts escalation from qualitative guidance into an operational policy.

### 12.1 Router objective

The router must protect quality **without converting every difficult paragraph into an expensive frontier call**.

Its core sequence is:

```text
VALIDATED LOCAL OUTPUT
        |
        v
HARD-TRIGGER CHECK
  |           |
 yes          no
  |           v
  |      SOFT-RISK SCORE
  |           |
  v           v
SPECIALIST   KEEP LOCAL / TARGETED REVIEW
  |
  v
REASSESS AFTER REPAIR
  |              |
resolved        unresolved
  |              |
  v              v
LOCAL CLOSE   FRONTIER ELIGIBILITY CHECK
                  |
          +-------+-------+
          |               |
         no              yes
          |               |
          v               v
   MORE BOUNDED      TIER C CAPSULE
   SPECIALIST/DEFER
```

### 12.2 Priority classes

Every exception receives one priority.

#### `P0 — CRITICAL`
Immediate high-value escalation.

Examples:
- source/evidence contradiction;
- E4 fabrication;
- clinically material numeric unit/value conflict;
- mutually exclusive high-risk interpretations;
- source authority ambiguity;
- corrupted/ambiguous visual governing a high-impact assertion;
- repeated state corruption threatening current authority.

Default destination:
Tier B immediately; Tier C if unresolved after one bounded specialist cycle.

#### `P1 — HIGH`
Likely semantic defect or substantial omission.

Examples:
- qualifier/negation scope conflict;
- numeric binding disagreement;
- relationship direction conflict;
- table row/column semantic conflict;
- persistent S2/S3 omission signal;
- precision reject rate indicating systemic overbreadth.

Default destination:
Tier B specialist.

#### `P2 — STANDARD`
Meaningful but bounded review.

Examples:
- atomicity repair;
- semantic near-duplicate;
- low-impact cross-page clarification;
- isolated unsupported inference;
- residual region requiring inspection.

Default destination:
Tier A/Tier B based on W/S class and certification.

#### `P3 — LOW`
Mechanical/cosmetic/organizational issue.

Examples:
- deterministic exact duplicate;
- formatting normalization;
- non-semantic metadata cleanup;
- ordering;
- manifest repair with no semantic conflict.

Default destination:
deterministic code or controller.

### 12.3 Hard escalation triggers

Hard triggers bypass soft scoring.

| Trigger | Priority | Destination |
|---|---|---|
| source SHA mismatch | P0 | block + authority recovery |
| evidence hash mismatch | P0 | quarantine + recovery |
| E4 fabricated/source-contradictory claim | P0 | Tier B review; Tier C if disputed |
| OCR-suspect clinically meaningful unit/value | P0/P1 | numeric/visual specialist |
| numeric parameter/range conflict | P1 | numeric specialist |
| qualifier/negation scope conflict | P1 | qualifier specialist |
| table row/column binding conflict | P1 | multimodal/table specialist |
| relationship endpoint/direction conflict | P1 | relationship specialist |
| source itself contradictory/ambiguous | P0 | Tier C `SOURCE_EVIDENCE_CHALLENGE` |
| competing semantic current states | P0/P1 | recovery specialist; Tier C if unresolved |
| visual-dependent assertion lacks visual asset | P1 | block visual gate |
| W4 task | P0/P1 | Tier C by definition |
| three failed semantic repair attempts on same family | P0/P1 | Tier C or DEFER |
| repeated controller/state corruption | P0 | operational incident + recovery |

### 12.4 Soft escalation signals

Soft signals contribute to an `ESCALATION_SCORE`.

Initial experimental weights:

| Signal | Weight |
|---|---:|
| blind reviewer adds >=10% useful new semantic units | +4 |
| blind reviewer adds 5–9.9% useful new units | +2 |
| precision rejects/repairs >=15% of primary candidates | +4 |
| precision rejects/repairs 8–14.9% | +2 |
| unexplained residual material >=5% of governed regions | +4 |
| unexplained residual material 1–4.9% | +2 |
| model is uncertified for this W/S tuple | +4 |
| model is provisionally certified only | +1 |
| source is S2 | +2 |
| source is S3 | +4 |
| independence grade I1/I0 | +2 |
| retry generation >=2 | +1 |
| retry generation >=3 | +2 additional |
| new E3 defect found | +4 |
| repeated atomicity failure | +1 |
| density anomaly without explained structural cause | +1 |
| specialist historical weakness on this stratum | +3 |

Initial routing:
- score `0–2`: local closure path if gates pass;
- score `3–5`: targeted additional review;
- score `6–8`: Tier B specialist;
- score `>=9`: Tier B immediately and frontier-eligibility flag.

These values are **experimental** and must be calibrated by EXP-003/009/010/012.

### 12.5 Reviewer-addition thresholds

Blind-review useful addition rate is computed as:

`accepted_unique_additions / pre-review accepted semantic units`

Interpretation:
- `<2%`: low marginal yield;
- `2–4.9%`: ordinary useful review;
- `5–9.9%`: elevated omission signal;
- `>=10%`: primary extraction may be under-recalling or source risk underestimated;
- `>=20%`: systemic recall failure candidate; consider rebuild rather than patching.

Do not act on raw additions; use **accepted useful additions** after reconciliation/precision.

### 12.6 Precision-reject thresholds

`precision_action_rate = repaired_or_rejected_primary_candidates / primary_candidates_reviewed`

Interpretation:
- `<5%`: ordinary cleanup;
- `5–7.9%`: monitor;
- `8–14.9%`: elevated precision debt;
- `15–24.9%`: serious primary-quality concern;
- `>=25%`: probable systemic extraction failure; rebuild assessment required.

### 12.7 Residual-region thresholds

Residuals are region-based, not candidate-count based.

- `0% unexplained`: desired state;
- `>0–1%`: inspect before closure;
- `>1–5%`: targeted recall review;
- `>5%`: Tier B recall escalation or rebuild assessment;
- any unexplained high-risk S3 region: immediate specialist review regardless of percentage.

### 12.8 Retry thresholds

- retry 1: ordinary;
- retry 2: controller diagnosis required;
- retry 3: worker/model substitution;
- retry 4: stop repeating same topology; escalate or defer;
- retry >=5: prohibited without explicit architecture exception.

Semantic disagreement does not count as a technical retry.

### 12.9 Specialist capability destinations

The router targets **capability classes**, not permanent model names.

#### `SP-RECALL`
For:
- under-recall;
- missing propositions;
- dense source reconstruction.

Preferred model hypotheses:
Kimi K3, Gemini Flash High, strong GLM/Qwen alternatives.

#### `SP-NUMERIC`
For:
- parameter binding;
- units;
- ranges;
- inequalities;
- thresholds;
- equations.

Preferred hypotheses:
Qwen Max / GLM Max / Kimi; Gemini when visual/table dependent.

#### `SP-QUALIFIER`
For:
- negation;
- exception;
- conditional scope;
- timing/population/modality.

Preferred hypotheses:
GLM Max, Qwen Max, Sonnet, Kimi.

#### `SP-RELATIONSHIP`
For:
- subject/object;
- directionality;
- causal/comparative relationships;
- cross-page endpoints.

Preferred hypotheses:
GLM Max, Qwen Max, Sonnet, Kimi.

#### `SP-VISUAL`
For:
- tables;
- figures;
- diagrams;
- OCR;
- visual topology.

Preferred hypotheses:
Gemini Flash High, Kimi K3, other benchmark-certified multimodal specialist.

#### `SP-RECOVERY`
For:
- state authority;
- lineage;
- conflicting generations;
- tool-heavy filesystem reconciliation.

Preferred hypotheses:
Sonnet, GLM Max, Sol when bounded and high-risk.

#### `SP-PRECISION`
For:
- overbreadth;
- atomicity;
- near-duplicate semantics;
- unsupported inference.

Preferred hypotheses:
GLM Max, Sonnet, Qwen Max, X if benchmark-certified for the relevant W/S tuple.

Model names remain replaceable. Certification governs actual assignment.

### 12.10 Frontier eligibility

A family may enter Tier C when any is true:

1. W4 by definition;
2. P0 source/evidence conflict persists after one Tier B cycle;
3. two independent Tier B specialists disagree materially;
4. three bounded repair cycles fail;
5. `SOURCE_EVIDENCE_CHALLENGE`;
6. semantic decision affects promotion/rejection of a high-impact assertion and ambiguity remains;
7. state authority conflict cannot be resolved mechanically or by Tier B;
8. frontier cold audit sample is required by acceptance policy.

Frontier is **not** justified solely by:
- model disagreement on wording;
- low-risk formatting;
- exact duplicate handling;
- a single free worker expressing low confidence.

### 12.11 Frontier capability classes

#### `FC-ADJUDICATION`
Difficult semantic retain/repair/merge/reject/defer.

Hypotheses:
Opus 5, GPT-5.6 Sol, Fable.

#### `FC-COLD-AUDIT`
Independent final challenge to a frontier-ready package.

Hypotheses:
GPT-5.6 Sol / Opus, preferably different from principal adjudicator.

#### `FC-PATHOLOGICAL`
Rare whole-estate or highly entangled dispute requiring prolonged reasoning.

Hypothesis:
Fable or strongest available frontier agent.

### 12.12 Escalation budgets

Each evidence family receives a budget envelope.

#### Default semantic escalation budget
- Tier A semantic passes: max 2 independent candidate-generation passes;
- Tier B repair passes: max 2;
- Tier C adjudication passes: max 1 principal + optional 1 independent cold challenge;
- total semantic decision depth: normally <=5 model passes.

#### Budget override
May exceed only for:
- P0 source-authority dispute;
- unresolved E4;
- explicitly designated critical evidence family;
- architecture/red-team experiment.

The router must record why.

### 12.13 Cost ceilings

Because provider prices/quotas vary, use **relative compute units (RCU)** rather than fixed dollars in architecture.

Default:
- free/cheap W1/W2 pass = 1 RCU;
- Tier B bounded specialist = 5 RCU;
- frontier bounded adjudication = 20 RCU;
- prolonged frontier/pathological = 50 RCU.

Initial per-family soft ceilings:
- P3: 2 RCU;
- P2: 8 RCU;
- P1: 20 RCU;
- P0: 50 RCU.

Ceilings are budgeting signals, not permission to close unresolved quality gates.

### 12.14 Rebuild vs bounded repair

Open a **REBUILD ASSESSMENT** when any is true:
- accepted blind-review additions >=20%;
- precision action rate >=25%;
- evidence/provenance corruption affects >=10% of reviewed candidates;
- repeated systemic atomicity failure across >=20% of candidates;
- source page mapping is wrong;
- state lineage cannot distinguish current candidate population;
- same failure mechanism recurs across >=3 adjacent capsules.

Prefer bounded repair when:
- defect is isolated;
- evidence hashes are intact;
- source mapping is correct;
- <10% of population is affected;
- failure has a clear typed queue;
- repair does not require reconstructing missing source regions.

### 12.15 Rebuild outcomes

`KEEP_AND_REPAIR`
`PARTIAL_REBUILD`
`FULL_CAPSULE_REBUILD`
`BATCH_REBUILD_NEW_DERIVATIVE`
`ESTATE_RESTART_REQUIRED`

Whole-estate restart is an exceptional conclusion and requires Tier C architecture review.

### 12.16 Router receipt

Every non-local escalation emits `router_receipt.json` with:

- exception ID;
- evidence-family/capsule ID;
- W/S class;
- priority P0–P3;
- hard triggers;
- soft signals;
- escalation score;
- current reviewer depth;
- current RCU spend;
- destination capability;
- candidate models eligible by certification;
- chosen model/endpoint;
- reason;
- expected decision/output;
- maximum additional budget;
- return/downgrade path.

### 12.17 Downgrade/return paths

Frontier or specialist output should not remain trapped in a high tier.

Examples:
- frontier says evidence is mechanically resolvable -> return to deterministic repair;
- Tier B says candidate is unsupported -> return to precision/rejection queue;
- Tier C says `DEFER` -> durable defer queue, not repeated automatic frontier retries;
- specialist finds source corruption -> recovery capsule;
- specialist resolves conflict -> local validators -> accepted state.

Escalation is a route, not a permanent status.

## 13. DETERMINISTIC VALIDATORS

Turn 08 converts validator concepts into explicit fail-closed contracts.

### 13.1 Validator classes

#### `V0 — AUTHORITY`
Protect frozen source and artifact identity.

Examples:
- source SHA;
- parent artifact SHA;
- source/page-map identity;
- accepted-manifest integrity.

Failure severity:
`BLOCKING / P0`

#### `V1 — STRUCTURE`
Protect parseability and schema.

Examples:
- JSON/JSONL parse;
- schema;
- required fields;
- ID uniqueness;
- review-status vocabulary.

Failure severity:
`BLOCKING` for production commit.

#### `V2 — PROVENANCE`
Protect source traceability.

Examples:
- evidence hash;
- source span presence;
- page localization;
- visual asset hash;
- originating capsule/run/lease lineage.

Failure severity:
usually `BLOCKING`.

#### `V3 — RECONCILIATION`
Protect cross-worker/state integrity.

Examples:
- union provenance;
- family referential integrity;
- queue referential integrity;
- independence metadata;
- blindness conformance;
- stale parent version;
- duplicate current-state authority.

Failure severity:
`BLOCKING` where current authority could diverge.

#### `V4 — COVERAGE CONTROL`
Detect omissions/anomalies without pretending to prove completeness.

Examples:
- residual-region census;
- numeric literal inventory reconciliation;
- qualifier/negation inventory reconciliation;
- visual/table presence census;
- candidate-density anomaly.

Failure severity:
usually `REVIEW_REQUIRED`, not automatic semantic rejection.

#### `V5 — SEMANTIC GATE RECEIPTS`
These are not deterministic truth validators. They verify that required semantic reviews occurred.

Examples:
- W3 had Tier B closure receipt;
- W4 had Tier C adjudication receipt;
- high-risk family has required cold-audit receipt;
- precision gate completed.

Failure severity:
`BLOCKING` for state transition.

### 13.2 Fail-closed rule

A gate must explicitly declare one of:

- `PASS`
- `FAIL_BLOCKING`
- `FAIL_REVIEW_REQUIRED`
- `NOT_APPLICABLE`
- `NOT_RUN`

`NOT_RUN` is never equivalent to `PASS`.

A package cannot claim a higher readiness state if a required gate is:
- FAIL_BLOCKING;
- FAIL_REVIEW_REQUIRED without resolved downstream route;
- NOT_RUN.

### 13.3 Mechanical PASS is not semantic PASS

A package may be:
- schema-valid;
- hash-valid;
- lineage-valid;
- internally consistent;

and still be semantically wrong.

Therefore acceptance is a vector:

```text
AUTHORITY
STRUCTURE
PROVENANCE
RECONCILIATION
COVERAGE_CONTROL
SEMANTIC_REVIEW
COLD_AUDIT
PACKAGE_CLAIMS
```

No single scalar `PASS` may hide which dimension remains unverified.

### 13.4 Validator contract

Every validator records:
- validator ID;
- validator version;
- input artifact hashes;
- run timestamp;
- algorithm/config version;
- result;
- severity;
- findings;
- remediation route;
- receipt hash.

### 13.5 Core validator registry

| ID | Validator | Class | Failure |
|---|---|---|---|
| `VAL-SOURCE-SHA` | frozen source hash | V0 | blocking |
| `VAL-PARENT-SHA` | parent artifact hash | V0 | blocking |
| `VAL-PAGE-MAP` | governed page mapping | V0/V2 | blocking |
| `VAL-SCHEMA` | record schema | V1 | blocking |
| `VAL-ID-UNIQUE` | candidate IDs unique | V1 | blocking |
| `VAL-STATUS` | status vocabulary | V1 | blocking |
| `VAL-EVIDENCE-HASH` | evidence bytes/hash | V2 | blocking |
| `VAL-SPAN-PRESENCE` | text evidence appears in governed text | V2 | blocking/review for visual |
| `VAL-VISUAL-ASSET` | referenced render exists and hash matches | V2 | blocking visual gate |
| `VAL-LINEAGE` | capsule/run/parent lineage complete | V2/V3 | blocking |
| `VAL-FAMILY-REF` | evidence-family references valid | V3 | blocking |
| `VAL-QUEUE-REF` | queue references valid | V3 | blocking |
| `VAL-INDEPENDENCE` | reviewer family/blindness metadata | V3 | blocking for independence claim |
| `VAL-BLINDNESS` | prohibited inputs absent | V3 | invalidates blind review |
| `VAL-CAS-VERSION` | expected parent version matches | V3 | blocking commit |
| `VAL-UNION-PROVENANCE` | all union candidates retain worker provenance | V3 | blocking |
| `VAL-NUMERIC-CENSUS` | source numerics accounted for | V4 | review required |
| `VAL-QUALIFIER-CENSUS` | qualifier/negation cues accounted for | V4 | review required |
| `VAL-RESIDUAL-CENSUS` | material regions dispositioned | V4 | review required |
| `VAL-VISUAL-CENSUS` | visual/table regions dispositioned | V4 | review required |
| `VAL-SEMANTIC-RECEIPT` | required W3/W4 review occurred | V5 | blocking |
| `VAL-COLD-AUDIT-RECEIPT` | required cold audit occurred | V5 | blocking where required |
| `VAL-PACKAGE-CLAIMS` | counts/hashes/states recomputed | V0/V1/V3 | blocking |

### 13.6 Validator composition

Readiness requires a named **gate profile**, not arbitrary validator selection.

Profiles:

#### `PROFILE-STAGING-ACCEPT`
Required:
authority + structure + provenance + state-version.

#### `PROFILE-W2-CLOSE`
Required:
staging accept + independence/recall receipt + coverage controls + precision receipt.

#### `PROFILE-W3-CLOSE`
Required:
W2 structural base + Tier B semantic receipt + typed conflict resolution + relevant feature gates.

#### `PROFILE-FRONTIER-READY`
Required:
all relevant mechanical validators + unresolved families explicitly queued/deferred + package claims recomputed.

`FRONTIER_READY` means suitable for frontier adjudication, not semantically canonical.

#### `PROFILE-PROMOTION-READY`
Required:
adjudication receipts + required cold audit + no blocking unresolved source/provenance issue + package claims recomputed.

### 13.7 Validator versioning

Validator changes are governed artifacts.

Any validator change affecting:
- pass/fail semantics;
- hash computation;
- source matching;
- schema acceptance;
- readiness profile;

requires:
- new version;
- regression suite;
- changelog;
- revalidation policy for affected current packages.

### 13.8 Deterministic validator limitations

Validators may detect:
- missing evidence;
- malformed evidence;
- missing reviews;
- unmatched numerics;
- unexplained regions;
- impossible state transitions.

They cannot independently prove:
- clinical meaning;
- qualifier scope;
- relationship correctness;
- correct table interpretation.

Those require semantic review.

## 14. HERMES ORCHESTRATION

### 14.1 Frozen v1 runtime split

```text
BUZZ
collaboration / status / operator controls
        |
        v
SIDECAR CONTROLLER  <-- v1 production default
SQLite ledger + scheduler + leases + CAS commits
        |
        v
HERMES WORKER ADAPTERS
free W1/W2 / specialists / frontier
        |
        v
IMMUTABLE ARTIFACT PLANE
```

### 14.2 Buzz deployment decision

`SIDECAR` is the v1 default.

Native Buzz spawning/control remains `EXPERIMENTAL_UNVERIFIED`.
This is not a rejection of native mode; it prevents the architecture from depending on an unverified platform behavior.

Buzz disconnect must not stop the scheduler or workers.

### 14.3 Durable state backend

v1 reference backend:
**SQLite + WAL + append-only hash-chained event log.**

Rationale:
- transactional compare-and-swap;
- crash recovery;
- no server dependency;
- sufficient for initial SAFE_4/BALANCED_8/HIGH_12 experiments.

Postgres or another backend is permitted later only when measured operational needs justify it.

### 14.4 Deterministic authority

Code owns:
- ready queues;
- leases;
- retries;
- current versions;
- commit legality;
- event history;
- validator execution;
- restart reconstruction.

Models may advise routing/diagnosis but cannot override deterministic state rules.

### 14.5 Reference implementation

`RUNTIME_REFERENCE_v1/` now contains:
- SQLite ledger;
- scheduler;
- event-chain integrity;
- leases;
- expiry/requeue;
- CAS commits;
- restart reconstruction;
- provider-adapter abstraction;
- Buzz sidecar request contract;
- offline runtime tests.

This reference runtime is **not** a live Hermes integration.

## 15. STATE MACHINE

### 15.1 Capsule state machine

```text
CREATED
  -> READY
  -> LEASED
  -> RUNNING
  -> CHECKPOINTED*     # repeatable internal event
  -> STAGED
  -> VALIDATING
      -> ACCEPTED
      -> FAILED_RETRYABLE -> READY (new revision)
      -> FAILED_ESCALATE -> ESCALATION_CAPSULE_CREATED
      -> DEFERRED
```

Side states:
- `PAUSED`
- `ORPHANED`
- `CANCELLED`
- `SUPERSEDED`
- `BLINDNESS_COMPROMISED`

### 15.2 Lease states

`ISSUED -> ACTIVE -> COMPLETED`

Failure paths:
- `ACTIVE -> SUSPECT -> EXPIRED`
- `ACTIVE -> CANCELLED`
- `ACTIVE -> ORPHANED`

### 15.3 Estate-level state machine

```text
DISCOVERED
  -> SOURCE_VERIFIED
  -> ORIENTED
  -> CAPSULATED
  -> PRIMARY_IN_PROGRESS
  -> PRIMARY_COMPLETE
  -> RECALL_REVIEW_IN_PROGRESS
  -> RECALL_REVIEWED
  -> STRUCTURALLY_VALIDATED
  -> PRECISION_REVIEW_IN_PROGRESS
  -> PRECISION_REVIEWED
  -> RISK_ROUTED
  -> SPECIALIST_REPAIR_IN_PROGRESS
  -> FRONTIER_READY
  -> SEMANTICALLY_ADJUDICATED
  -> COLD_AUDITED
  -> PROMOTION_READY
```

Side states:
- `RECOVERY_REQUIRED`
- `CONTINUITY_BLOCKED`
- `VISUAL_REVIEW_REQUIRED`
- `NUMERIC_REVIEW_REQUIRED`
- `SOURCE_CONFLICT`
- `QUARANTINED`
- `DEFERRED`
- `REBUILD_REQUIRED`
- `PAUSED_INCIDENT`

### 15.4 Append-only events

Every transition is an event. Current state is reconstructed by replaying accepted events.

Required event fields:
- event ID;
- entity ID;
- prior version;
- resulting version;
- event type;
- capsule/run/lease ID;
- controller identity;
- validator receipts;
- artifact hashes;
- timestamp;
- reason.

### 15.5 Out-of-order completion

Workers may finish in any order.

A result can commit only if:
- dependency prerequisites still hold;
- expected parent version matches current;
- lease/identity valid;
- validators pass.

Otherwise result becomes:
- stale derivative;
- reconciliation candidate;
- or retry input.

### 15.6 Rollback

Rollback appends a superseding transition; it never deletes prior accepted bytes.

## 16. QUALITY GATES

Turn 08 hardens gates into explicit acceptance barriers.

### GATE 1 — SOURCE AUTHORITY
Required:
- source hash;
- source ID;
- page map.

Fail behavior:
`FAIL_CLOSED / BLOCK_SCOPE`

### GATE 2 — STRUCTURAL VALIDITY
Required:
- parse;
- schema;
- IDs;
- statuses.

Fail behavior:
`FAIL_CLOSED / RETRY_OR_REPAIR`

### GATE 3 — EVIDENCE INTEGRITY
Required:
- evidence hash;
- source span;
- exact page/region;
- visual hash when applicable.

Fail behavior:
`FAIL_CLOSED / QUARANTINE`

### GATE 4 — BLIND INDEPENDENCE
Required where review claims independence.

Checks:
- reviewer did not receive primary output;
- underlying model/family recorded;
- benchmark key absent;
- separate run/context.

Fail behavior:
review may be retained as non-blind precision evidence but **cannot count as independent recall**.

### GATE 5 — NUMERIC
Literal numeric census reconciles with candidate coverage.

A numeric assertion cannot close merely because the token exists; binding is W3 where applicable.

### GATE 6 — QUALIFIER / NEGATION
Material qualifier cues must be dispositioned.

Binding disagreements route W3.

### GATE 7 — ATOMICITY
Reject/repair:
- paragraph dumps;
- list items losing shared qualifiers;
- multiple independent claims fused without justified context.

### GATE 8 — RELATIONSHIP
Subject/object/direction/context provenance must be explicit.

### GATE 9 — VISUAL / TABLE
Visual-dependent assertion requires:
- actual asset;
- page identity;
- honest provenance;
- W3 review for semantic binding.

### GATE 10 — RESIDUAL ACCOUNTING
Every material region receives a disposition.

This detects silent disappearance; it does not prove semantic completeness.

### GATE 11 — SEMANTIC-TIER CLOSURE
W3 requires Tier B receipt.
W4 requires Tier C receipt.

### GATE 12 — STATE / LINEAGE
No stale commit, lineage break, competing current-authority record, or unverifiable parent.

### GATE 13 — PACKAGE CLAIMS
Recompute:
- counts;
- hashes;
- queues;
- families;
- readiness state;
- validator profile.

Self-reported counts are never accepted.

### GATE 14 — COLD AUDIT
Apparently clean work is sampled adversarially.

Cold auditor receives:
- source;
- accepted candidate families;
- no prior PASS narrative where possible.

Purpose:
catch unanimously wrong or systematically omitted work that ordinary disagreement routing would never escalate.

### GATE 15 — FRONTIER READY SEMANTICS
`FRONTIER_READY` means:
- source/provenance/state mechanically trustworthy;
- semantic queues explicitly bounded;
- reviewer can begin immediately.

It does **not** mean:
- canonical;
- fully correct;
- guaranteed complete.

### 16.1 Fail-open vs fail-closed

Fail closed:
- source identity;
- evidence identity;
- schema/current-state corruption;
- W3/W4 missing semantic receipt;
- stale commit;
- broken lineage;
- missing required visual.

May continue with explicit review state:
- residual anomaly;
- candidate-density anomaly;
- minor atomicity queue;
- non-critical literal inventory mismatch.

### 16.2 Cold-audit sampling

Initial experimental cold-audit policy:

- all P0 accepted families;
- 25% random P1 accepted families;
- 5% random P2;
- 1% random P3/W2 apparently clean families;
- additional risk-weighted sample of families with high model agreement but low independence.

Cold-audit thresholds must be calibrated.

### 16.3 Canary families

Maintain a small hidden set of known tricky cases:
- numeric binding trap;
- shared qualifier trap;
- reversed relationship trap;
- visual/table trap;
- source-span fabrication trap.

Periodically inject into worker/validator regression suites.

A system that starts passing bad canaries is suspended pending investigation.

## 17. FAILURE / RECOVERY POLICY

### Frozen v1 rules

1. Local failure remains local unless authority/integrity is systemic.
2. Accepted state is never reconstructed from chat memory.
3. SQLite/event ledger + artifact manifests are sufficient to rebuild runtime state.
4. Lease expiry requeues unfinished work.
5. Stale out-of-order commits fail compare-and-swap and cannot overwrite current state.
6. Duplicate completions are preserved as derivatives, not last-writer-wins.
7. Event-chain integrity failure pauses canonical commits.
8. Provider outage may requeue to another certified model without changing success criteria.
9. Buzz disconnect is not an extraction incident under sidecar mode.
10. Rollback appends superseding transitions; forensic history is retained.

## 18. EXISTING-ESTATE ROUTING

Turn 09 applies a **minimum-rework rule**: do not re-extract strong governed candidate populations merely to make them native to Hermes v0.9.

### Morgan SOL Project 1
- L01 partial rebuild only for untrusted scope + harden/continue.
- L02 recover/reconcile before rebuild.
- L03 harden 2/7 + continue 5.
- L04 reconcile mixed generations + retro harden.
- L05 harden 3/6 + continue 3.
- L06 finish 2 + cold audit.
- L07 finish final + package.
- L08 `DO_NOT_REEXTRACT`; precision/frontier cleanup only.
- L09 targeted semantic repair.
- L10 package/cold audit; exemplar.

### Morgan SOL Project 2
- L11 targeted harden.
- L12 recover + semantic reconcile.
- L13 recover/re-harden + continue.
- L14 preserve strong 2/6 + continue.
- L15 authority recovery before hardening.
- L16 `NOT_SUPPLIED / UNKNOWN`.
- L17 harden + continue.
- L18 recall harden + continue.
- L19 recall harden + continue.
- L20 reconcile B0002; never count-fit; continue missing scope.

### Nagelhout Gemini p281–544
**DO NOT RE-EXTRACT.**
Project 13,830 candidates / 10,114 families and bounded queues into Hermes review capsules. P0/P1 receive risk-appropriate Tier B/Tier C; P2 bounded review; P3 local/cheap with cold audit.

### Nagelhout Opus legacy
`LEGACY_MIGRATION + SALVAGE + CONTINUATION`.
Classify `KEEP / RECALL_HARDEN / REBUILD / PARTIAL / BLOCKED`.
No completion claim without byte/state reconstruction.

### Kimi
Historical high-recall evidence, benchmark challenge material, failure-mode reference; **not gold**.
Known final Turn012 bytes are not mounted in this runtime; older packs must not be relabeled as final.

### Machines / Dorsch
First largely virgin Hermes deployment.
Source SHA-256:
`379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197`

Turn 09 created a real-source pages 299–301 pilot with evidence units and five runnable capsule types.
Status: `READY_TO_EXECUTE / NOT_CERTIFIED`.
Meta is not required.

## 19. COST / COMPUTE STRATEGY

Turn 06 formalizes cost control around exception economics.

### 19.1 Compute hierarchy

1. deterministic computation;
2. certified free/cheap agents;
3. Tier B specialists;
4. Tier C frontier;
5. prolonged/pathological frontier only when explicitly justified.

### 19.2 Relative Compute Units (RCU)

Architecture uses provider-independent relative units:

| Class | RCU |
|---|---:|
| deterministic mechanical work | ~0 |
| free/cheap bounded pass | 1 |
| specialist bounded repair | 5 |
| frontier bounded adjudication | 20 |
| prolonged frontier/pathological | 50 |

Actual dollars/credits may later be mapped onto RCU.

### 19.3 Spend follows uncertainty, not page count

The factory should not allocate equal expensive compute per page.

Spend concentrates where:
- model disagreement persists;
- source complexity is high;
- omission/reject signals are abnormal;
- evidence is visual/OCR-dependent;
- decisions are authority-sensitive.

### 19.4 Exception batching

Tier B/Tier C calls should batch **compatible evidence families** only when all are true:
- same specialist capability;
- same source context or adjacent logical unit;
- batching does not break blindness;
- total context remains below risk-adjusted limit;
- one family's evidence cannot anchor another incorrectly.

Do not batch unrelated families merely to reduce API calls.

### 19.5 Frontier utilization target

The factory should aim for frontier models to touch a **minority** of total candidates but a **majority of unresolved high-risk ambiguity**.

No fixed percentage is frozen before benchmark data.

### 19.6 Economic success metric

Track:

`QUALITY_ADJUSTED_COST = total RCU / accepted source-grounded semantic units`

alongside:
- E3/E4 residual rate;
- frontier escalation rate;
- accepted recall;
- review burden.

The cheapest system is not preferred if it creates higher semantic debt.

## 20. SECURITY / SOURCE-INTEGRITY RULES

Existing rules remain.

Turn 09 additions:
27. `SOURCE_UNIT` is evidence, not semantic interpretation.
28. Source-unit identity/hash is generated before semantic execution.
29. Every produced worker field requires schema coverage/disposition.
30. Rights metadata must not collapse into one ambiguous boolean.
31. Unknown rights does not by itself block private extraction; release remains separately governed.
32. 09D bridge is read-only/non-canonical by default.
33. Implementation status is machine-readable and may not be inflated.
34. Preflight reports are generated from executable checks.
35. One canonical verifier orchestrates current reference checks.
36. Meta reference artifacts must not become hidden runtime dependencies.

## 21. EXPERIMENTS AND BENCHMARKS

EXP-001 through EXP-029 remain part of the empirical program.

### EXP-030 — SQLite Ledger / CAS / Restart
**Status:** `OFFLINE_CERTIFIED`

Reference test covers:
- priority claim;
- duplicate lease prevention;
- commit;
- stale CAS rejection;
- expired lease requeue;
- hash-chain validation;
- restart reconstruction.

### EXP-031 — Pilot Boundary-Context Hardening
**Status:** `OFFLINE_CERTIFIED`

Added PDF pages 298 and 302 as read-only boundary context around primary pages 299–301.
Ownership remains pages 299–301.

### EXP-032 — Blindness Input Mutation
**Status:** `OFFLINE_CERTIFIED`

Clean blind capsule must pass.
Injected answer-key artifact must fail blindness validation.

### EXP-033 — Semantic Factory Empirical Certification
**Status:** `BLOCKED / NEXT EXECUTION PROGRAM`

This is no longer an architecture-design experiment.
It must execute the benchmark and live worker adapters.

## 22. ACCEPTED ARCHITECTURAL DECISIONS

ADR-001 through ADR-092 remain except where explicitly superseded.

### ADR-093 — Freeze architecture v1.0
**Status:** ACCEPTED

### ADR-094 — SQLite is the v1 reference ledger
**Status:** ACCEPTED

### ADR-095 — Buzz sidecar is the v1 production-default integration
**Status:** ACCEPTED  
Native Buzz launch remains experimental until verified.

### ADR-096 — Boundary context is mandatory when local scope risks context severance
**Status:** ACCEPTED

### ADR-097 — Blindness must be machine-inspectable
**Status:** ACCEPTED

### ADR-098 — Architecture freeze and empirical certification are separate
**Status:** ACCEPTED

### ADR-099 — No new architecture turn is required before empirical benchmark execution
**Status:** ACCEPTED  
Further design changes require a concrete failed test, incident, benchmark result, or deployment blocker.

### ADR-100 — v1 production claims are fail-closed
**Status:** ACCEPTED  
Until empirical gates pass, semantic production status remains blocked.

## 23. REJECTED OR SUPERSEDED IDEAS

Existing rejections remain.

### SUP-035 — Continue architecture brainstorming after v1 without evidence
Rejected. New architecture work now requires empirical trigger.

### SUP-036 — Call the semantic factory production-ready because offline code tests pass
Rejected.

### SUP-037 — Make Postgres/cloud infrastructure mandatory before pilot
Rejected; SQLite is sufficient for v1 reference runtime.

### SUP-038 — Make native Buzz integration a prerequisite
Rejected; sidecar is the stable authority boundary.

### SUP-039 — Treat model leaderboard rank as role certification
Rejected; benchmark tuples remain authoritative.

## 24. UNRESOLVED QUESTIONS

These are now empirical, not architectural:

1. Which free model certifies for W2 primary?
2. Which independent free model certifies for blind recall?
3. Which Tier-B models certify for numeric/qualifier/relationship/visual repair?
4. What measured capsule sizes, escalation thresholds, cold-audit rates, and concurrency profile perform best?

No further architecture turn is required to answer them.

## 25. RISKS / FAILURE MODES

### Residual v1 risks

- `RISK-075` model benchmark absent — production semantic quality unknown.
- `RISK-076` provider adapter not live — Hermes execution not yet proven.
- `RISK-077` Buzz native mode unverified — mitigated by sidecar default.
- `RISK-078` SQLite contention at large concurrency — measure before changing backend.
- `RISK-079` threshold miscalibration — keep experimental until benchmark.
- `RISK-080` pilot-source overfitting — benchmark across multiple estates.
- `RISK-081` architecture ossification — permit changes only when empirical evidence identifies a failure.

These risks block empirical production claims where applicable, but do not block architecture freeze.

## 26. CHANGELOG

### v0.1–v0.9
The ten-turn program progressively established governance, risk taxonomy, benchmark design, capsules, topology, escalation economics, Buzz/Hermes orchestration, fail-closed validation, Meta-derived evidence engineering, real-estate routing, and a real-source Machines pilot.

### v1.0 / TURN_10
Integrated red-team and architecture freeze.

Added:
- integrated red-team report;
- SQLite/WAL reference ledger;
- append-only hash-chained events;
- deterministic scheduler;
- lease expiry/requeue;
- CAS commit;
- restart reconstruction;
- provider adapter abstraction;
- Buzz sidecar request contract;
- sidecar-first deployment decision;
- Machines boundary context pages 298/302;
- machine-inspectable blindness validator;
- real-source mutation tests;
- deployment runbook;
- empirical gates to production;
- v1 freeze manifest;
- ADR-093 through ADR-100;
- EXP-030 through EXP-033.

Architecture is now frozen at v1.0.
The next action is empirical execution, not more speculative architecture.

## 27. NEXT-TURN AGENDA

### POST-FREEZE EXECUTION PROGRAM

Do not create `TURN_11 architecture` by default.

Next work should be empirical:

1. wire one real Hermes/provider adapter;
2. build the benchmark source-unit set;
3. run free-worker bake-off;
4. certify or reject primary/blind roles;
5. execute the Machines pilot;
6. run deterministic union + precision;
7. cold-audit the result;
8. run SAFE_4 concurrency;
9. run crash/restart/failover;
10. only reopen architecture if evidence reveals a concrete design defect.

The canonical question is now:

> Does Factory v1 actually outperform or match the existing SOL/Kimi extraction quality at lower marginal cost and higher operational durability?

## 28. FACTORY FREEZE READINESS

| Requirement | State |
|---|---|
| authority/trust model | FROZEN |
| task/source risk taxonomy | FROZEN |
| evidence substrate | FROZEN / PILOT IMPLEMENTED |
| capsule contracts | FROZEN |
| blindness/independence | FROZEN |
| topology | FROZEN |
| escalation architecture | FROZEN |
| cost abstraction | FROZEN |
| estate minimum-rework routing | FROZEN |
| validator semantics | FROZEN |
| 09D read-only boundary | FROZEN |
| durable ledger design | FROZEN |
| SQLite reference ledger | OFFLINE_CERTIFIED |
| reference scheduler | OFFLINE_CERTIFIED |
| Buzz sidecar deployment architecture | FROZEN |
| Buzz native launch | EXPERIMENTAL_UNVERIFIED |
| model benchmark | NOT RUN |
| model certifications | ABSENT |
| live Hermes/provider adapter | NOT IMPLEMENTED |
| Machines semantic pilot | READY_TO_EXECUTE / NOT RUN |
| production semantic certification | BLOCKED |

**Architecture freeze:** `FROZEN_V1`

**Reference runtime:** `OFFLINE_CERTIFIED`

**Semantic factory:** `NOT_EMPIRICALLY_CERTIFIED`

**Production deployment:** `BLOCKED_PENDING_EMPIRICAL_GATES`

This is the intended final state of the 10-turn architecture program. Further architectural changes require empirical evidence.

