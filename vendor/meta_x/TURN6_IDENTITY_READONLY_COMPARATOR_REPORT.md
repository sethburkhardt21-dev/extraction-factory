# Turn 6 — Provisional Identity Resolution + Read-Only 09D Comparator

## Result

**PASS_OFFLINE_CONTRACT — ACTUAL 09D DATABASE COMPARISON PENDING**

Turn 6 adds a non-authoritative identity/comparison plane after the Turn-5 semantic factory. Project 09D was not modified.

## Implemented

- exact source-mention candidate registration using the 09D source-identity separator contract;
- deterministic `CAND:` IDs for assertion entity mentions;
- fail-closed domain inference for unambiguous roles only;
- no cross-source candidate clustering by name;
- read-only identity lookup states for exact, candidate-tier, multiple, possible-alias, and absent matches;
- SQLite comparator adapter using `mode=ro&immutable=1` plus `PRAGMA query_only=ON`;
- actual-database SHA-256 binding before query;
- assertion classifications: blocked semantic verification, identity ambiguity/not-found, exact existing, supporting existing, contradictory, context different, novel, unresolved;
- numeric conflicts are preserved rather than averaged;
- contextual differences are preserved rather than collapsed;
- Turn-6 package output for candidates, candidate-assertion links, identity cases, identity lookups, and 09D comparisons.

## Critical semantic distinction

`downstream_semantic_ready=false` does not necessarily prohibit **read-only comparison**. A high-risk dosing assertion can be independently `ENTAILED` but still require frontier adjudication before any selection/use. Turn 6 permits read-only comparison of such an entailed claim while all selection/authority locks remain false.

## Frozen 09D database pin

The read-only Project 09D baseline identifies the frozen SQLite checkpoint as:

`11f9e3150e5775f452cd90be7aa33dcb6c3a8df4fc9c3810f41b45248f6d4aee`

The actual 1.67-GB SQLite file is not present in the current workspace. Therefore the real 71,824-assertion 09D comparison has **not** run. Offline comparator certification uses synthetic contract snapshots/databases only.

## Demonstration

Four primary assertions were independently entailed. Three referred to Propofol and one to Ketamine.

Comparison output:

- `EXACT_EXISTING`: 1
- `CONTRADICTORY`: 1
- `CONTEXT_DIFFERENT`: 1
- `IDENTITY_NOT_FOUND`: 1

Candidate records: 4. Canonical assignments: 0. 09D mutations: 0.

## Remaining gates

- actual frozen 09D SQLite read-only run;
- richer legacy assertion-schema adapter if the live assertion table exposes semantics differently than the offline adapter recognizes;
- cross-source support/conflict graph;
- production model role certification and real-source semantic precision/recall;
- public native source canaries;
- mass extraction authorization.
