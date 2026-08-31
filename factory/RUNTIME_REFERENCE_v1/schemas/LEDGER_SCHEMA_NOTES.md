# SQLite Ledger v1

Reference backend:
- SQLite
- WAL mode
- foreign keys enabled
- append-only hash-chained event log
- capsule current-state table as derived/transactional view
- leases
- commits
- compare-and-swap version checks

Why SQLite:
- local durability
- crash recovery
- transactional CAS
- no server dependency
- adequate for initial 4/8/12 worker profiles

Migration to Postgres is allowed later if measured contention/scale requires it.
