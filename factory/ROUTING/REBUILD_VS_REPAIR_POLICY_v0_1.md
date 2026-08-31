# Rebuild vs Repair Policy v0.1

## Rebuild assessment triggers
- accepted blind-review additions >=20%
- precision action >=25%
- evidence/provenance corruption >=10%
- systemic atomicity failure >=20%
- page mapping wrong
- lineage cannot identify current population
- same systemic failure across >=3 adjacent capsules

## Prefer bounded repair
- isolated defect
- evidence hashes intact
- page map correct
- <10% affected
- typed queue exists
- source regions are present

## Outcomes
KEEP_AND_REPAIR
PARTIAL_REBUILD
FULL_CAPSULE_REBUILD
BATCH_REBUILD_NEW_DERIVATIVE
ESTATE_RESTART_REQUIRED
