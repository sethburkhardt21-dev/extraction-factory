# Frontier Extraction → Project 09D Boundary Contract

## Authority

Project 09D is **read-only** to this estate. The pinned reference is recorded in
`09D_READONLY_AUTHORITY.json`. No code in the extraction estate may write, migrate,
commit, promote, or update Project 09D.

## Current implemented 09D boundary

The implemented S02 `lane_package_intake.package_kind` accepts only
`FROZEN_PARENT_BACKFILL`. Therefore a new external extraction package is **not** a
valid direct S02 insert. Frontier emits an independent audit package for inspection
by a future separately authorized 09D intake stage.

## Evidence chain

The target evidence path is:

`raw transport/artifact → source record/version → source unit → assertion → source locator/raw evidence → candidate/evidence links → read-only 09D comparison → audit package`

Turn 1 froze the source/candidate/package authority boundary. Turn 2 froze source-unit
and assertion schemas, Turn 3 implemented deterministic source-unit segmentation, and
Turn 4 implements the untrusted assertion-proposal engine. Turn 5 implements an append-only, blind independent semantic verifier with separate numeric, negation, certainty, conditionality, qualifier/scope, relationship, and atomicity checks plus non-authoritative risk routing. 09D comparison, conflict resolution, candidate adjudication, and clinical authority remain separate later gates.

## Candidate rules

Candidate identity follows the implemented 09D deterministic convention:

- `source_identity_sha256 = SHA256(source_table || 0x1f || source_key)`
- `candidate_id = "CAND:" + first 32 hex characters of source_identity_sha256`

Every extraction-created candidate is provisional. The extractor may not create a
canonical 09D identity, reuse the candidate ID as canonical identity, or create a
promotion/approval/decision event.

Every package must state:

- `direct_09d_insert_allowed = false`
- `canonical_authority = false`
- `automatic_identity_merge_allowed = false`
- `automatic_selection_allowed = false`
- `canonical_internal_eligible = false`
- `generation_eligible = false`
- `public_eligible = false`
- `mass_extraction_authorized = false` until the final GO gate

## Release terminology

A successful extractor artifact is a **certified research-ingestion snapshot** or
**09D external audit package**. It is not a Project 09D clinical release, canonical
release, governed-generation allowlist, filtered client export, or public release.

## Fail-closed rule

Missing provenance, ambiguous identity, unresolved conflict, absent source evidence,
or unavailable assertion verification remains explicit. No missing dimension is
inferred as closed.

## Conflict and variant boundary

Project 09D preserves source-specific variants and controlled conflict outcomes. The
extractor must therefore preserve original numeric text, units, population, route,
timing, source era, and scope. It must never average conflicting values, broaden a
route/population, or select a winner merely because one source is newer or more
frequent.

The later conflict engine must support at least:
`DUPLICATE_EQUIVALENT`, `CONTEXTUAL_VARIANT`, `TRUE_CONFLICT`,
`SOURCE_ERA_VARIANT`, `CURRENT_AUTHORITY_SUPERSEDED`, `UNRESOLVED`, and
`NOT_COMPARABLE`. Selection defaults to false. Until that engine is implemented,
`conflict_engine_status = NOT_IMPLEMENTED` and no assertion package can be frontier-ready.

## Current implemented-S02 compatibility

Current S02 is an implemented historical backfill migration, not a general external
intake API. Its candidate rows use `CAND:` identifiers derived from exact
`source_table || 0x1f || source_key` identity and are append-only. This estate adopts
that deterministic identity convention for its provisional candidates, but does not
write those rows into S02. A future 09D-authorized intake stage must decide how an
external audit package is admitted.

## Frozen evidence/intelligence contract through Turn 5

`frontier-source-unit-1.2` and `frontier-atomic-assertion-1.0` are frozen extraction-side contracts. The source-unit segmenter is implemented and offline-certified. The Turn-4 assertion engine is implemented as an untrusted proposal boundary: it computes exact evidence bindings, deterministic assertion/interpretation IDs, provenance, and fail-closed authority fields, while every emitted assertion remains `NOT_VERIFIED`.

General text interpretation uses a provider interface whose production backend is not yet certified. A narrow deterministic ClinicalTrials provider is offline-certified for selected high-confidence structured facts. Provider failures or malformed proposals are quarantined rather than silently dropped.

Assertions are interpretations, not 09D authority. They cannot be automatically selected, canonicalized, generated from, or publicly released. Exact evidence closure and independent source identity/year/version/source-era dimensions are retained so 09D can audit rather than trust the extractor.

Turn 5 verification is an **append-only overlay**. The extractor assertion remains `verification_status = NOT_VERIFIED`; a separate deterministic `VERIF:` event records `ENTAILED`, `NOT_ENTAILED`, `PARTIAL`, `AMBIGUOUS`, or `PROVENANCE_INCOMPLETE`, along with specialist checks, risk tier, required review lanes, and independent verifier provenance. The semantic provider is blind to extractor provenance/reasoning and cannot override deterministic blocking failures. Even an `ENTAILED` verification event grants no canonical, selection, generation, or public authority.

The verifier implements Hermes-compatible semantic separation: numeric census/binding, qualifier detection/scope binding, relationship/causality binding, blind entailment review, precision review routing, and bounded frontier escalation are distinct responsibilities. A production general semantic model backend remains `NOT_CERTIFIED`; offline contract and gold behavior are certified only.

## Turn 6 provisional identity + read-only comparison boundary

Turn 6 adds provisional source-mention candidate registration and Project 09D read-only comparison. This does **not** change the authority boundary.

- assertion mention candidates use the exact 09D source-identity hashing convention and remain `REGISTERED`;
- the same normalized surface in multiple assertions remains multiple source candidates until reviewed;
- ambiguous domains do not receive guessed candidates;
- exact 09D name hits are lookup evidence only and never populate `legacy_entity_id`;
- candidate-to-canonical assignment, merge, promotion, and automatic selection remain false;
- actual 09D SQLite comparison requires the frozen database SHA-256 pin before any query and opens SQLite only with `mode=ro&immutable=1` plus `PRAGMA query_only=ON`;
- high-risk assertions may be compared read-only when independently `ENTAILED` even if downstream use remains frontier-adjudication-gated;
- numeric disagreement is preserved as contradiction and context differences remain distinct; no value is averaged or selected.

The actual frozen 09D database is not present in the current extraction workspace. Therefore Turn 6 is certified against offline contract fixtures only; the real-database comparator gate remains pending.
