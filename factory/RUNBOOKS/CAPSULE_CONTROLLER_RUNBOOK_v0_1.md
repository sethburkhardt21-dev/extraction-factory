# Capsule Controller Runbook v0.1

Create: verify source/parent hashes, assign W/S, build manifest, hash inputs, set blindness, mark CREATED.

Lease: choose eligible worker, issue isolated write path, record model/version, mark LEASED/RUNNING.

Close: require receipt, run validators, hash outputs, atomic commit, append transition, mark ACCEPTED.

Failure: tool/mechanical -> retry revision; semantic disagreement -> escalation capsule; source authority -> block; blindness breach -> invalidate independence claim.
