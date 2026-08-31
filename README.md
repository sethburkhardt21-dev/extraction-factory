# Integrated Frontier Extraction Factory

One canonical extraction appliance reconciling **Meta v11** (semantic/literature
design plane), **Hermes Advanced v1.1** (durable execution/governance plane), and
**09D** (read-only downstream authority). Directory name shortened from the
suggested `INTEGRATED_FRONTIER_EXTRACTION_FACTORY` because this estate has a
measured Windows spawn-cwd path cliff; same project.

## Layout

| Path | Role |
| --- | --- |
| `vendor/` | Pristine unpacked source packs (READ-ONLY; zip hashes in `AUDIT/INTAKE.md`) |
| `factory/` | **The production tree** — Hermes v1.1 fork + integration code. All execution happens here |
| `factory/providers_ext/` | Real provider plane: `llm_provider.py` (claude CLI / Ollama HTTP / echo) |
| `factory/stages_ext/` | Post-run stages: `compare_09d.py` (six-state read-only 09D comparison) |
| `factory/benchmarks_ext/` | Source-first gold builder, role scorer, certification writer |
| `factory/run_appliance.py` | **The one canonical start command** |
| `AUDIT/` | Byte-audit reports, capability matrix, intake hashes |
| `runs/` | Run outputs (gitignored; each run is self-contained + durable) |

## The canonical command

```
cd factory
<locked-python> -B run_appliance.py --profile SAFE_4 --pilot machines ^
    --primary claude:claude-opus-5:ANTHROPIC_CLAUDE ^
    --blind   ollama:<local-model>:QWEN ^
    --cold    ollama:deepseek-r1:14b:DEEPSEEK
```

Locked interpreter: `C:\Users\sethb\.local\python\project09d-cpython-3.12.13\python.exe`.
Provider specs are `backend:model:FAMILY` (first/last colon split; Ollama tags may
contain `:`). Declared families drive the INDEPENDENCE and COLD_AUDIT gates —
declare them truthfully.

The chain: source hash → certified-build + runtime-lock verification → durable
work registration (SQLite/WAL ledger, exclusive leases, CAS commits) → primary +
allowlist-blind extraction → deterministic union → evidence families →
deterministic specialists → precision review → risk routing → deterministic AND
independent-family semantic cold audit → fail-closed readiness → read-only 09D
comparison (SUPPORT / CONTRADICTION / CONTEXT_DIFFERENCE / VARIANT /
MISSING_IN_09D / IDENTITY_UNCERTAIN, all reviewable) → self-verified offline
review ZIP. Status is derived by `hermes_factory.readiness.derive_readiness`
from gate objects only; nothing authors it.

## Honesty model (do not soften)

- Candidates are `SOURCE_ASSERTION_CANDIDATE / UNREVIEWED / NON_CANONICAL`, always.
- 09D stays read-only: `mode=ro` URI + `PRAGMA query_only` + write-probe gate +
  the estate guard hook. Agreement with 09D proves nothing; disagreement refutes nothing.
- A same-family cold auditor can never produce PASS (`FAIL_INDEPENDENCE`).
- Certification is per (provider, model, role, W-class, S-class, benchmark) with
  enumerated limits; unmeasured metrics force at most `CERTIFIED_WITH_LIMITS`.
- The certified-build manifest is immutable; `verify` never rewrites it
  (Meta's verify-rewrites-its-own-pin defect is documented in
  `AUDIT/meta_cert_mismatch.md` and deliberately not inherited).
- Rights-quarantined textbook bytes never enter git history (`.gitignore` + amended
  root commit); the vendor zips in `Downloads\School Resources` are their archive.

## Verified state (2026-08-31)

- Zip hashes match the owner's expected values (`AUDIT/INTAKE.md`).
- Factory suite **66/66 PASS** (1 justified skip) on the locked 3.12.13; includes the
  Windows staging fix and 13 new behavioral tests.
- Build certified on this runtime: `CERT-5454e02e…` (additive; Linux certs preserved).
- Fixture pilot reproduces the pack's evidence exactly (52/36/88 …) with
  `SOURCE_HASH` PASS against the real 157 MB book and `09D_READONLY_BOUNDARY`
  PASS against sealed r3 (`fa7a9731…`).
- Real providers proven live: claude opus-5 primary (19 assertions/74 s, unit 1),
  deepseek-r1 cold-audit verdict (145.8 s).
- 09D comparator validated: 88 candidates vs 71,824 carrier rows in 6.3 s.

See `AUDIT/CAPABILITY_MATRIX.md` for the full reconciliation and
`AUDIT/*_test_run.md` for raw evidence.
