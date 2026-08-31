# HERMES Advanced v1.1 Deployment Runbook

## Canonical entrypoint

```bash
./RUN_FACTORY.sh <command>
```

## Verify exact build

```bash
./RUN_FACTORY.sh verify
```

Verification compares the current protected production/config tree with the immutable certified build manifest. It does **not** silently re-certify modified code.

## Offline fixture installation test

```bash
./RUN_FACTORY.sh run \
  --pilot machines \
  --mode offline-fixture \
  --execution-mode LOCAL_ONLY \
  --profile SAFE_4
```

This runs the actual durable pipeline against the real Machines pilot source units using a deterministic fixture provider. It proves mechanics, not semantic model quality. Its correct final status is `READY_FOR_PROVIDER`, not `FRONTIER_REVIEW_READY`.

## Run an arbitrary local PDF through deterministic ingestion + fixture runtime

```bash
./RUN_FACTORY.sh run \
  --source-pdf /path/to/book.pdf \
  --pages 1-20 \
  --mode offline-fixture \
  --execution-mode LOCAL_ONLY \
  --profile SAFE_4
```

## Real provider integration

Wrap the desired model/provider in a command that:

1. reads one Hermes worker-request JSON object from stdin;
2. writes one provider-output JSON object to stdout;
3. exits nonzero on failure.

Then run with `--mode external-command` and separate primary/blind identities/commands. Do not label a model certified merely through CLI arguments: the model-certification registry is authoritative and is currently empty.

## Concurrency profiles

- `SAFE_4` → 4 worker threads
- `BALANCED_8` → 8 worker threads
- `HIGH_12` → 12 worker threads

Only SAFE_4 fixture mechanics have been exercised in the real Machines advancement run. 8/12 live-model performance is not certified.

## State and recovery

Each run keeps:

- `STATE/ledger.sqlite`
- leases
- event chain
- artifact staging records
- commits
- snapshots

Check state:

```bash
./RUN_FACTORY.sh status --run-dir <RUN_DIR>
```

Recover expired leases and verify durable state:

```bash
./RUN_FACTORY.sh resume --run-dir <RUN_DIR>
```

The current `resume` command performs deterministic state recovery/requeue. Re-dispatching external semantic providers after a controller restart still requires relaunch with provider configuration; accepted work is never overwritten.

## Build certification

After code/config changes:

```bash
./RUN_FACTORY.sh test
./RUN_FACTORY.sh certify-build --refresh-runtime-lock
./RUN_FACTORY.sh verify
```

Certification is explicit and versioned. Ordinary `verify` never mutates certification identity.
