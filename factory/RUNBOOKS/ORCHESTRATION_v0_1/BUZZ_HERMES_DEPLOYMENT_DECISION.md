# Buzz + Hermes Deployment Decision

## Decision
YES: run the extraction factory through the Buzz workflow using Hermes as the worker execution runtime.

## Authority boundary
Buzz = collaboration/control surface.
Hermes = execution runtime.
Durable ledger/artifacts = source of truth.

## Preferred deployment order
1. Native/embedded Hermes launch if Buzz supports it reliably.
2. Sidecar/headless Hermes controller bridge as production-safe fallback.
3. Manual launch payload only for pilot validation.

## Non-negotiable
Buzz disconnect must not stop workers or erase state.
