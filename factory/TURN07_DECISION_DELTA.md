# TURN 07 — Decision Delta

## New decisions
- YES: factory can operate in the Buzz workflow using Hermes.
- Buzz is control/collaboration, not canonical authority.
- Hermes is execution runtime, not durable truth.
- deterministic scheduler/ledger owns queues, leases, commits, and state.
- capsule-level concurrency and work stealing.
- SAFE_4/BALANCED_8/HIGH_12 experimental profiles.
- compare-and-swap commits.
- Buzz disconnect does not stop headless execution.
- local recovery is autonomous; global stop only for systemic authority/integrity risk.

## New experiments
EXP-017 concurrency scaling
EXP-018 crash/restart reconstruction
EXP-019 Buzz disconnect
EXP-020 provider failover
EXP-021 overnight soak

## Remaining Buzz-specific unknown
Whether the actual Buzz environment can natively launch Hermes processes/sessions. If not, use the sidecar/headless bridge; the architecture does not otherwise change.
