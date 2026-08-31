# Turn 4.5 — External Audit Reconciliation / Evidence-Substrate Repair

The supplied third-party audit targeted Turn 3/v6. It was treated as untrusted adversarial evidence and checked against the actual Turn-4/v7 code before repair.

## Decision

**Do not proceed directly to the independent verifier on the old substrate.** Several critical/high findings remained valid in v7. Turn 4.5 repairs the evidence substrate first. Project 09D remains read-only; mass extraction remains unauthorized.

## Finding-by-finding reconciliation

| Finding | v7 classification | Turn 4.5 disposition |
|---|---|---|
| C1 NFKC corrupts numeric semantics | **VALID** | Fixed: proposition identity now uses NFC; regression covers superscripts/subscripts/vulgar fractions |
| C2 JATS `itertext()` destroys inline numeric semantics | **VALID** | Fixed: semantics-aware JATS/MathML renderer; source artifact SHA + canonical XPath + normalized XML-fragment hash retained |
| C3 evidence-span out-of-range fails open | **VALID** | Fixed: out-of-range is explicit error; unbound assertion validation is explicit failure |
| H1 structured path unchecked | **PARTIALLY VALID** | Turn-4 provider already enforced exact paths; base assertion contract now also resolves canonical absolute JSON paths and numeric leaves |
| H2 source-unit identity omits source/scope dimensions | **VALID** | Fixed in source-unit v1.2; historical v1.0/v1.1 remain readable |
| H3 nested paragraph duplication | **VALID** | Fixed: nested `<p>` units suppressed when already contained by paragraph/caption/table evidence |
| H4 full-text abstract mislabeled FULL_TEXT | **VALID** | Fixed: new `ABSTRACT_WITHIN_FULLTEXT` scope; fallback remains `ABSTRACT_ONLY` |
| H5 PMC endpoint return overstates rights | **PARTIALLY STALE / PARTIALLY VALID** | Current PMC docs explicitly say OAI `pmc` full text is returned only when licenses/usage rights allow reuse. Endpoint return can establish reuse/text-mining eligibility, but detailed redistribution/commercial/derivative rights now require parsed article-license classification and otherwise remain unclassified |
| H6 section titles dropped | **VALID** | Fixed: JATS section titles emitted and section ancestry attached to units |
| H7 back matter becomes clinical FULL_TEXT | **VALID** | Fixed: back matter classified `METADATA` |
| M1 HTML can pass loose content-type marker | **VALID** | Fixed: JATS acquisition requires XML and parseable JATS before persistence |
| M2 localhost silently allowed | **VALID** | Fixed: explicit `allow_local_test_host=True` required |
| M3 CRLF/whitespace monograph paragraphs | **VALID** | Fixed: robust blank-line segmentation preserving original offsets |
| M4 monograph lacks UTF-8 byte offsets | **VALID** | Fixed |
| M5 empty JSON containers invisible | **VALID in part** | Fixed empty `{}`/`[]` retention. Canonical key-sort order remains intentional/deterministic; field allowlisting belongs to downstream semantic extraction rather than raw evidence retention |
| M6 table cells lack context | **VALID** | Fixed basic row/column, colspan/rowspan, same-row and column header context |
| M7 v1.1 `content_representation` not required | **VALID** | Fixed: v1.1+ requires it; only v1.0 can infer |
| M8 full-text artifact not identifier-bound | **VALID** | Fixed for PubMed PMCID and preprint DOI |
| M9 absolute runtime artifact path hurts portability | **VALID / PARTIAL** | Added portable `artifact_locator`; runtime `artifact_path` remains local because raw full-text bytes are intentionally not embedded in current audit packages. Package-level raw-artifact portability remains a future packaging concern |
| M10 evidence-closure metric counts field presence | **VALID** | Fixed: package metric now counts assertions that pass full source-unit assertion validation |
| M11 exact drug link hardcodes confidence=1.0 | **VALID** | Fixed: exact candidate linkage is explicitly unscored; no calibrated confidence is claimed |
| P1 substring greps presented as behavioral gates | **VALID** | Fixed semantics: structural checks are labeled structural/symbol-presence; behavioral claims come from executable suites |
| P2 tests excluded from pinned certification state | **VALID** | Fixed: independent `verification_manifest` SHA-256 is emitted by preflight and checked by the runtime preflight gate |
| P3 invariant tests lack negative cases | **VALID** | Fixed materially for evidence substrate: wrong path, out-of-range span, numeric corruption, localhost, HTML, identity binding, nested markup, duplicate paragraphs, scope, table context, empty containers, and source binding all have negative/adversarial tests |
| P4 happy-path fixture too small | **VALID / PARTIAL** | Dense adversarial JATS fixture added. A real multi-article, license-cleared heterogeneous gold fixture corpus is still OPEN and should precede semantic model certification/precision-recall claims |

## Important rights correction

Current PMC documentation states that OAI-PMH `metadataPrefix=pmc` exposes full text for articles whose license/usage rights allow reuse; not every PMC article is eligible. Therefore the external audit's claim that successful OAI full-text output itself says nothing about reuse eligibility is stale. However, license terms still vary by article, so Turn 4.5 no longer converts endpoint return into detailed commercial/derivative permission.

## What is proven after Turn 4.5

- numeric-safe assertion normalization;
- numeric-safe JATS inline rendering for superscript/subscript and supported MathML;
- source-unit v1.2 identity binds source artifact/resource/scope;
- exact evidence spans fail closed;
- structured evidence paths resolve against source units;
- abstract/back/body evidence scopes are separated;
- section context survives segmentation;
- nested paragraph duplication is suppressed;
- table cell context is materially richer;
- HTML/local-host artifact-forgery paths fail closed;
- PubMed/preprint full-text artifacts are identifier-bound;
- verification suite itself is hash-bound to preflight.

## What is NOT proven

- production general-text assertion-model quality;
- independent semantic entailment verification;
- real heterogeneous multi-article gold precision/recall;
- public-host native full-text canary in this execution environment;
- exact raw XML byte offsets for every JATS element (auditability currently uses exact source-artifact hash + canonical JATS XPath + normalized fragment hash);
- package-embedded raw full-text portability;
- 09D comparator/conflict graph.

## Next transition

The next safe transition is **not automatically Turn 5**. First create/run the heterogeneous evidence gold corpus using the repaired substrate. If that corpus exposes no material segmentation/evidence-closure defect, proceed to the independent verifier. If it does, repair the substrate again before semantic certification.
