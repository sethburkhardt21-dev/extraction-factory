# Buzz + Hermes Deployment v1

## Frozen decision
**Production default: SIDECAR.**

Buzz is the collaboration/control surface.
A local sidecar process owns the deterministic scheduler and SQLite ledger.
Hermes workers are launched through provider/command adapters.
Accepted artifacts remain on the durable filesystem.

## Why sidecar is default
- Buzz native process launch has not been empirically verified.
- Sidecar keeps execution alive if Buzz disconnects.
- Sidecar cleanly separates UI from authority.
- Native Buzz integration can be added later as an adapter without changing extraction contracts.

## Native mode
Status: `EXPERIMENTAL_UNVERIFIED`.
It may become preferred only after EXP-019 proves:
1. worker launch,
2. disconnect survival,
3. reconnect reconstruction,
4. cancellation,
5. identity/receipt preservation.

## Rollback
If Buzz integration fails:
1. stop Buzz-originated launches;
2. keep sidecar + ledger running;
3. allow existing Hermes workers to finish;
4. reconnect through sidecar status API/CLI;
5. no accepted artifact or state transition is lost.
