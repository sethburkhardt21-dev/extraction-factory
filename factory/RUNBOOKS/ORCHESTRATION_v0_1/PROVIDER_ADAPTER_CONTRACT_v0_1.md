# Provider Adapter Contract v0.1

Required interface:
- launch(capsule, lease)
- heartbeat(run_id)
- status(run_id)
- cancel(run_id)
- collect(run_id)
- capabilities()
- identity()
- rate_limit_state()

The adapter must never silently substitute an underlying model without a new worker identity/receipt.
