# Meta-Derived Engineering Adoption Register v0.1

**Meta is an engineering reference only. It is not a Hermes runtime dependency.**

Reference pack SHA-256: `a01228e5fb17c6f1d1e9699ffa861441563c4565200a32f1eac74c9a375c9e6a`

| ID | Pattern | Decision | Hermes adaptation | Status |
|---|---|---|---|---|
| META-A | Immutable evidence substrate | **ADOPT** | Formalize TEXTBOOK_SOURCE -> SOURCE_VERSION -> PAGE_ARTIFACT -> SOURCE_UNIT -> ASSERTION_CANDIDATE. SOURCE_UNIT is evidence, not interpretation. | `IMPLEMENTED_FOR_PILOT` |
| META-B | Typed content representation | **ADAPT** | Use TEXT, TABLE, FIGURE, EQUATION, IMAGE_REGION, MIXED_LAYOUT. STRUCTURED_JSON remains available for non-textbook structured sources but is not forced into textbook flow. | `IMPLEMENTED_FOR_PILOT` |
| META-C | Provenance before semantics | **ADOPT** | Capsule generator supplies source/version/page/source-unit lineage and hashes before model execution. | `IMPLEMENTED_FOR_PILOT` |
| META-D | Rights / usage metadata dimensions | **ADAPT** | Add governed rights_metadata object with UNKNOWN allowed; do not block private extraction solely because rights are unresolved. | `SCHEMA_IMPLEMENTED_POLICY_DEFERRED` |
| META-E | Read-only downstream authority boundary | **ADOPT** | 09D bridge defaults direct_insert=false, automatic_canonicalization=false, automatic_release=false. | `CONTRACT_IMPLEMENTED` |
| META-F | Explicit implementation/certification state | **ADOPT** | Controlled maturity states: NOT_IMPLEMENTED, SKELETON_ONLY, IMPLEMENTED_UNTESTED, OFFLINE_CERTIFIED, EMPIRICALLY_CERTIFIED, LIVE_CERTIFIED, EXPERIMENTAL, BLOCKED. | `IMPLEMENTED` |
| META-G | Schema coverage contract | **ADOPT** | Every produced field maps to logical schema, extension/process metadata, quarantine, or explicit drop reason; deterministic validator supplied. | `IMPLEMENTED_OFFLINE_CERTIFIED` |
| META-H | Logical vs physical projection contract | **ADAPT** | Keep logical contracts backend-neutral; initial physical projection uses files/JSONL + optional SQLite later. | `CONTRACT_IMPLEMENTED` |
| META-I | Canonical preflight / release certification | **ADOPT** | One generated PREFLIGHT.json + PREFLIGHT.txt from executable verifier; never manually maintain duplicate current-state claims. | `IMPLEMENTED_OFFLINE_CERTIFIED` |
| META-J | Empirical certification ladder | **ADOPT** | Separate UNIT_VERIFIED, OFFLINE_INTEGRATION_VERIFIED, MUTATION_VERIFIED, EMPIRICALLY_VERIFIED_ON_REAL_SOURCE, LIVE_VERIFIED. | `IMPLEMENTED_AS_POLICY` |
| META-K | External/adversarial canaries | **ADOPT** | Retain Turn08 canaries and link provider/model regression to certification suspension. | `POLICY_IMPLEMENTED` |
| META-L | Single canonical verification entrypoint | **ADOPT** | Provide VERIFY.sh -> verify_factory.py; current reports are generated from the verifier. | `IMPLEMENTED_OFFLINE_CERTIFIED` |
| META-M | Root-level test isolation | **ADOPT** | Reference implementation uses one root verifier and non-colliding direct test entrypoints. | `IMPLEMENTED_FOR_REFERENCE_PACK` |

## Governing rule
Adoption of an engineering pattern does not import Meta's orchestration, connectors, warehouse, model choices, readiness claims, or source-of-truth role.
