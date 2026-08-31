# TURN 06 — Decision Delta

## New decisions
- P0–P3 exception priorities
- hard triggers vs soft escalation score
- capability-targeted specialist routing
- frontier eligibility rules
- per-family RCU and review-depth budgets
- rebuild-vs-repair thresholds
- mandatory router receipts
- downgrade/return paths
- durable DEFER

## New experiments
EXP-013 threshold calibration
EXP-014 rebuild/repair crossover
EXP-015 frontier sparsity
EXP-016 exception batching

## Main unresolved issue
Turn 07 must safely orchestrate many concurrent workers and preserve exact state through failures, retries, and out-of-order completion.
