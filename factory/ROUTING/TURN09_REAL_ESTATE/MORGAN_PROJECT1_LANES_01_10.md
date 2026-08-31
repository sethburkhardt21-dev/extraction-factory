# Morgan SOL Project 1 — Turn 09 Routing

| Lane | Route | Rationale | Risk |
|---|---|---|---|
| P1-L01 | PARTIAL_REBUILD + RECALL_HARDEN + CONTINUE | Preserve strong governed work; rebuild only untrusted/missing scope from frozen source. | HIGH |
| P1-L02 | RECOVER + RECONCILE | Recover governed artifact chains first; rebuild only unrecoverable chains. | HIGH |
| P1-L03 | RECALL_HARDEN + CONTINUE | 2/7 persisted; harden surviving batches then continue missing 5. | HIGH |
| P1-L04 | RECONCILE + RETRO_RECALL_HARDEN | 7/7 complete with mixed generations; no wholesale re-extraction. | MEDIUM |
| P1-L05 | RECALL_HARDEN + CONTINUE | 3/6 current; harden existing 3 and continue 3. | MEDIUM |
| P1-L06 | CONTINUE + COLD_AUDIT_SAMPLE | 4/6 strong; finish 2 without reextracting strong 4. | LOW |
| P1-L07 | CONTINUE_FINAL + PACKAGE | 5/6 strong; finish final batch and cold-audit sample. | LOW |
| P1-L08 | PRECISION_REPAIR + FRONTIER_CLEANUP | 6/6 recall-hardened; DO_NOT_REEXTRACT. | LOW |
| P1-L09 | PRECISION_REPAIR + SPECIALIST_QUEUES | 6/6 but semantic debt; target repairs only. | MEDIUM |
| P1-L10 | PACKAGE + COLD_AUDIT | 6/6 strengthened; use as exemplar; no re-extraction. | LOW |
