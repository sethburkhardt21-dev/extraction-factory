# Turn 4.6 — Heterogeneous Evidence Gold Gate

**Status:** PASS_OFFLINE_GOLD_WITH_NATIVE_PUBLIC_SOURCE_BLOCKER

## Frozen state

- Production code/contract SHA-256: `bca172dab295c35bde24c61ebf93d4f95238c598afcdae384839e325244bb141`
- Verification/test SHA-256: `cd1b2cddb8227495468a75d42374408a4a5b8cab397a7a65b3c66fd92214b0ff`
- Unique regression tests: `200/200`
- Gold acceptance suite: `45/45`
- Named hand-specified risk cases: `36`
- Pinned physical fixtures: `8`
- Project 09D write performed: **FALSE**
- Mass extraction authorized: **FALSE**

## What the gold gate means

The gold authority is hand-specified expected behavior and pinned physical fixtures. Extractor output is never accepted as gold merely because it was emitted. The gate covers JATS numeric semantics, MathML, section context, nested lists, table/figure context, abstract/back-matter scope, source-unit identity, structured JSON edge cases, monograph offsets, PubMed abstract-only behavior, deterministic replay, and fail-closed malformed source inputs.

## New defect found by the gate

`T46-01`: the final monograph paragraph retained a terminal file newline. This made paragraph identity and evidence offsets depend on a formatting artifact. The segmenter now trims boundary whitespace while recomputing exact character and UTF-8 byte offsets. Regression proof is included in the pinned fixture suite.

## Public-source boundary

The package records official NCBI JATS/PMC and public PeerJ JATS references for structural coverage, but does **not** relabel those references as native acquired source bytes. Exact public PMC OAI raw-byte retrieval remains blocked in this runtime. Therefore the gold gate proves the local evidence substrate, not public-host transport.

## Progression decision

- Turn 5 verifier **implementation may proceed**: YES.
- Turn 5 production semantic certification: NO.
- Mass extraction: NO.

The verifier must still be treated as untrusted until model-independent/gold entailment evaluation and real public-source canaries are available.
