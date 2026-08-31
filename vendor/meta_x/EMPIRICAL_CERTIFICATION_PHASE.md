# Frontier Extraction v4 — Empirical Certification Phase

## Decision

**Mass extraction remains LOCKED.** The software, schema, retry/resume, projection, and control-plane gates pass on the frozen code revision, but public-host native canaries are still blocked by the current execution runtime's DNS policy. No mass extraction was performed.

## Frozen production state

- Frontier preflight: **PASS**
- Production manifest files: **47**
- Production manifest SHA-256: `afbcb997f8f3454c890fa01661c7a1a0ec16b00379b43266a31993e96b39824f`
- Regression tests: **93/93 PASS**
  - ClinicalTrials: 19
  - preprints: 9
  - drug references: 15
  - PubMed: 21
  - warehouse: 9
  - control plane: 20

## Empirical HTTP / failure-injection certification

A real localhost HTTP server was used to exercise the requests-based production network paths rather than only in-memory fake clients.

### Native-path exact-transport run: PASS

The production-native transport-capture branches were executed with controlled endpoint routing to localhost.

- ClinicalTrials:
  - page 1 durably committed
  - injected 503 caused a hard interruption
  - checkpoint retained `next_page_token=p2`
  - restart resumed from the checkpoint
  - final result contained exactly 3 unique NCT IDs
  - exact HTTP response artifacts were retained and hash-bound
  - warehouse projection passed
- medRxiv:
  - injected 429 was retried
  - 30-record page followed by 5-record page did not truncate
  - empty page terminated pagination
  - exact HTTP response artifacts were retained and hash-bound
  - warehouse projection passed
- PubMed:
  - injected 429 was retried
  - ESearch→EFetch reconciliation passed
  - exact HTTP response artifacts were retained and hash-bound
  - raw XML/source hash retained
  - warehouse projection passed

This proof is **not** a public-host native canary and therefore has `mass_unlock_eligible=false`.

## Relational execution smoke test

A real transactional SQLite relational database was loaded from projected warehouse JSONL:

- tables loaded: **13**
- rows inserted: **224**
- transaction: PASS
- primary-key enforcement: PASS
- explicit broken-FK negative test: PASS

This proves emitted rows can survive executable relational insertion and constraint checking, but it does **not** certify PostgreSQL or BigQuery.

## Control-plane negative execution

- full extraction attempted without a native canary certificate: **BLOCKED**
- release attempted from injected/non-orchestrated evidence: **BLOCKED**
- mass extraction performed: **FALSE**

The control plane therefore fails closed under invalid promotion attempts.

## Current-code external schema-conformance evidence

The retained reconstructed-live-shape fixtures for ClinicalTrials, medRxiv, and bioRxiv were revalidated against the exact current production hash. All pass parser/schema conformance, and all remain explicitly non-unlocking.

## Public-host native canary

A bounded ClinicalTrials canary was attempted on the exact frozen production hash. The runtime failed before source access because DNS resolution for `clinicaltrials.gov` is disabled.

Result: **BLOCKED_ENVIRONMENT_DNS**

- source failure: no
- parser failure: no
- mass extraction: no
- native canary certificate issued: no
- mass unlock: no

## PostgreSQL / BigQuery execution status

A disposable Neon PostgreSQL project was created for target-database certification. The Neon connector in this environment exposes camelCase arguments but its backend rejects them while demanding inaccessible snake_case arguments; the same mismatch blocks SQL execution, table inspection, and cleanup calls. This is a connector/tooling blocker, not evidence of a PostgreSQL schema failure.

A local executable relational smoke test passed, and the static physical projection contract already reports zero missing emitted tables/columns for PostgreSQL and BigQuery. **Target PostgreSQL and BigQuery execution certification remain PENDING.**

### Cleanup note

The disposable Neon project `frontier-extraction-cert-20260829` may still exist because the same connector argument-mapping defect prevented the deletion action from executing. It contains no application data and no schema/data load was successfully performed.

## Promotion state

| Gate | Status |
|---|---|
| Offline frontier preflight | PASS |
| Exact-code regression suites | PASS — 93/93 |
| Logical schema coverage | PASS |
| Physical projection contract | PASS |
| Native-path local HTTP exact transport | PASS |
| Forced interruption/resume | PASS |
| Retry/backoff 429/503 | PASS |
| Warehouse projection | PASS |
| Relational executable smoke | PASS |
| Control-plane fail-closed tests | PASS |
| External source-shape conformance | PASS, non-unlocking |
| Public-host native CTG canary | BLOCKED — runtime DNS |
| Public-host native PubMed canary | PENDING |
| Public-host native medRxiv canary | PENDING |
| Public-host native bioRxiv canary | PENDING |
| PostgreSQL target execution | BLOCKED — connector defect |
| BigQuery target execution | PENDING |
| Mass extraction | **LOCKED / NOT RUN** |

## Next legal transition

The next allowed transition is **public-host native canary certification on a network-capable runtime using the exact frozen production code hash**. Only a `PASS` certificate with `transport=native_http`, `mass_unlock_eligible=true`, and the same production-code hash can authorize a full extraction.
