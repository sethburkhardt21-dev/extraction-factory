# Intake record — 2026-08-31

All four instructed artifacts located in `C:\Users\sethb\Downloads\School Resources\`,
hashed before unpacking. Expected values from the owner's task statement.

| Artifact | SHA-256 (measured) | Expected | Verdict | Size |
| --- | --- | --- | --- | --- |
| Meta_Extraction_Frontier_v11_09D_Turn6_FROZEN.zip | `52eb089760a12a67a461a443e437f84d2e25cb7a8c9eab34b4431234f5f23fb4` | same | **MATCH** | 1,202,121 B |
| HERMES_EXTRACTION_FACTORY_ADVANCED_v1_1.zip | `aecd84db91ea466035e2c395dd6a6e470ce750a1be31dab3c1f8eff112e5f6cf` | same | **MATCH** | 1,286,969 B |
| HERMES_EXTRACTION_FACTORY_ADVANCED_v1_1 (1).zip | `aecd84db…5f6cf` (byte-identical duplicate) | — | duplicate | 1,286,969 B |
| META_EXTRACTION_FRONTIER_ADVANCED_v12.zip | `b49c77d66c6a43f148b0e060a993bc6258d24a4b34109a98625365b206d37c53` | none given | recorded | **4,350 B** |
| META_EXTRACTION_FRONTIER_ADVANCED_v12 (1).zip | `b49c77d6…7c53` (byte-identical duplicate) | — | duplicate | 4,350 B |
| HERMES_ADVANCEMENT_REPORTS_v1_1.zip (bonus, found beside the others) | `365d149488849370a4fb97a0e75204630667754f1901137ec870932e89281ef1` | — | recorded | 51,414 B |
| HERMES_BENCHMARK_PACK_v1_1.zip (bonus) | `d992a9890ed3995ee5ab1e1f7ee0e364cebde8f3623c596fe5f77c6132540640` | — | recorded | 4,363 B |

The 4,350-byte size of the v12 zip is physical confirmation of the task statement:
v12 is an audit/report overlay from an interrupted advancement pass (5 markdown
files), NOT a successor source tree. It is used as audit context only; Meta v11
remains the semantic source of truth.

Unpack destinations (vendor trees are READ-ONLY source; never edited):

- `vendor/meta_x/` — Meta v11 FROZEN (bare tree, 614 files)
- `vendor/hermes_x/HERMES_EXTRACTION_FACTORY_ADVANCED_v1_1/` — Hermes Advanced v1.1
- `vendor/v12_overlay/META_EXTRACTION_FRONTIER_ADVANCED_v12/` — v12 audit overlay
- `vendor/hermes_reports/` — advancement evidence pack
- `vendor/hermes_bench/` — benchmark pack

## Rights quarantine

The Hermes pack embeds Machines textbook–derived bytes (3-page PDF slice, page
renders, page text, boundary context, and source-unit JSONL carrying page text).
Textbook extractions are rights-quarantined in this estate. Those paths are
excluded from git via `.gitignore` and MUST NEVER enter git history — especially
not history that could be pushed to any remote. They remain on disk, pinned by
the zip hashes above; the zips in `Downloads\School Resources` are the canonical
archive for those bytes.
