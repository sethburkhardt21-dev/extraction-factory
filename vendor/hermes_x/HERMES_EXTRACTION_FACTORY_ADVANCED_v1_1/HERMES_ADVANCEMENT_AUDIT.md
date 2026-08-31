# HERMES v1 → Advanced v1.1 Baseline Audit

## Frozen input independently verified

- Input: `HERMES_EXTRACTION_FACTORY_FROZEN_V1_TURN10.zip`
- SHA-256: `e4f0f2cabc0a91af73e4f203acb9a604aecba16ea1af74d11cb1a78e6f82d343`
- ZIP entries: 327
- ZIP CRC/integrity: PASS
- Original Python files: 10
- Original Python LOC: 558
- Original canonical preflight: PASS when rerun in this environment

The original package was preserved and a new derivative was created. No historical freeze artifact was rewritten in place.

## What the frozen v1 actually contained

| Capability | Actual starting state |
|---|---|
| Architecture/governance | Strong and frozen |
| Machines source/evidence pilot | Real, deterministic, pages 299–301 with boundary 298/302 |
| SQLite ledger | Small but functional reference implementation |
| Leases | Functional reference implementation |
| CAS stale-write rejection | Functional reference implementation |
| Event chain | Functional reference implementation |
| Restart reconstruction | Functional reference implementation |
| Blindness | File/capsule inspection validator, not worker-request allowlist transport |
| Semantic candidate schema | Contract-oriented; no production semantic engine |
| Primary semantic worker | Not implemented/live |
| Blind recall worker | Not implemented/live |
| Numeric literal pass | Prompt/contract only |
| Qualifier pass | Prompt/contract only |
| Relationship pass | Prompt/contract only |
| Deterministic union | Contract/skeleton |
| Evidence-family builder | Not implemented |
| Precision reviewer | Not implemented |
| Specialist passes | Mostly contracts/routing concepts |
| Cold audit | Design/sampler concept, no real semantic cold auditor |
| Provider integration | Abstract command-template reference only |
| Build certification binding | Architecture freeze existed, but no explicit immutable current-vs-certified production manifest in the advanced runtime sense |
| General PDF ingestion | Not implemented; pilot-specific source units existed |
| One-command extraction | Verification command existed; complete semantic run command did not |
| Offline review package | Pilot-oriented packaging concept, not generalized run appliance |
| Semantic model certification | None |
| Real semantic precision/recall benchmark | Not run |

## Baseline conclusion

The frozen v1 was substantially stronger as a **governed architecture and deterministic-state reference** than as an executable semantic extraction system. The advancement therefore focused on code/test/runtime conversion rather than adding more architecture prose.
