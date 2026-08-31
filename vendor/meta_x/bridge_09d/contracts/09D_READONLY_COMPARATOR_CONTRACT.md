# Project 09D Read-Only Comparator Contract — v1.0

## Authority boundary

The actual Project 09D SQLite is opened only with SQLite URI `mode=ro&immutable=1` and `PRAGMA query_only=ON`. Before any query, its SHA-256 must equal the frozen checkpoint hash pinned by the read-only 09D architecture authority.

Current pinned checkpoint database SHA-256:

`11f9e3150e5775f452cd90be7aa33dcb6c3a8df4fc9c3810f41b45248f6d4aee`

No database write is allowed or required.

## Identity lookup states

- `EXACT_NAME_SINGLE_CANONICAL_TARGET`
- `EXACT_NAME_SINGLE_CANDIDATE_TARGET`
- `MULTIPLE_EXACT_MATCHES`
- `POSSIBLE_ALIAS_MATCHES`
- `NO_MATCH`

Even a single exact canonical-name target is only a proposed target. `canonical_assignment_performed=false` always.

## Assertion comparison classifications

- `BLOCKED_SEMANTIC_VERIFICATION`
- `IDENTITY_AMBIGUOUS`
- `IDENTITY_NOT_FOUND`
- `EXACT_EXISTING`
- `SUPPORTING_EXISTING`
- `CONTRADICTORY`
- `CONTEXT_DIFFERENT`
- `NOVEL`
- `UNRESOLVED`

`NOVEL` is allowed only when the comparison snapshot explicitly exposes sufficient typed assertion coverage. Missing legacy assertion semantics produce `UNRESOLVED`, not a novelty claim.

## Conflict safety

Different numeric values in the same entity/type/context are preserved as `CONTRADICTORY`; they are never averaged or selected. Different route/population/timing/context remains `CONTEXT_DIFFERENT`.

## Certification boundary

Offline certification proves the comparator contract and a hash-bound read-only SQLite adapter against synthetic contract databases. It does not claim that the actual 09D checkpoint database was present or compared in this run.
