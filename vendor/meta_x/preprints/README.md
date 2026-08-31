# Repaired medRxiv/bioRxiv extraction engine

Key corrections relative to the supplied Meta bundle:

- pagination does **not** assume 100 records/page; cursor advances by the actual collection length and extraction ends only on an empty collection;
- raw version history identity is `(server, doi, version)` rather than DOI alone;
- conflicting records with the same `(server, doi, version)` fail closed instead of choosing an arbitrary survivor;
- the latest-version projection is emitted separately from immutable version history;
- invalid records are quarantined, never silently promoted into canonical output;
- dry-run does not write fake canonical records;
- atomic manifests include counts and SHA-256 output hashes;
- duplicate `_1`, `_1_1`, `_2` shadow copies are not carried into the production tree.

Run offline verification: `python -m pytest -q tests/test_offline.py`.
Network access is opt-in with `--network` and is not part of the offline certification.
