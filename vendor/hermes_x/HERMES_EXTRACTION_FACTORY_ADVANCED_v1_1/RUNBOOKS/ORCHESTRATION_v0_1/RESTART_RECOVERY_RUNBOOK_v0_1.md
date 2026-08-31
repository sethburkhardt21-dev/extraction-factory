# Restart Recovery Runbook v0.1

1. Load durable event ledger.
2. Verify source and accepted artifact roots.
3. Enumerate ACTIVE/SUSPECT leases.
4. Inspect worker/process status.
5. Classify:
   - RUNNING
   - ORPHANED_WITH_STAGING
   - ORPHANED_NO_OUTPUT
   - COMPLETED_UNCOMMITTED
6. Re-run validators for completed/uncommitted output.
7. Commit only with valid expected parent version.
8. Create retries for invalid/orphaned work.
9. Rebuild all ready queues from ledger.
10. Emit recovery report.

Do not use chat history to infer current state.
