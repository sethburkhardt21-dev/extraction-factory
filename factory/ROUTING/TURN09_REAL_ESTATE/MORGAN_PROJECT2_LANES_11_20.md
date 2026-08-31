# Morgan SOL Project 2 — Turn 09 Routing

| Lane | Route | Rationale | Risk |
|---|---|---|---|
| P2-L11 | TARGETED_HARDEN + PACKAGE | 6/6 emitted; deeply re-audit remaining outputs. | MEDIUM |
| P2-L12 | RECOVER + SEMANTIC_RECONCILE | Competing living/recovery states; resolve current authority first. | HIGH |
| P2-L13 | RECOVER + RECALL_HARDEN + CONTINUE | 2/6 persisted; recover/re-harden then continue 4. | HIGH |
| P2-L14 | CONTINUE | Preserve strong 2/6 and continue 4. | LOW |
| P2-L15 | RECOVER_AUTHORITY + TARGETED_HARDEN | Multiple competing output trees; reconstruct authority first. | HIGH |
| P2-L16 | NOT_SUPPLIED / UNKNOWN | Do not infer status. | BLOCKED |
| P2-L17 | HARDEN + CONTINUE | 4/6 current; harden non-hardened outputs and continue 2. | MEDIUM |
| P2-L18 | RECALL_HARDEN + CONTINUE | 3/6 older under-recall; harden 3 and continue 3. | MEDIUM |
| P2-L19 | RECALL_HARDEN + CONTINUE | 2/6 conservative; harden 2 and continue 4. | MEDIUM |
| P2-L20 | RECONCILE_B0002 + CONTINUE | Bounded B0002 conflict; never count-fit; continue missing 2. | HIGH |
