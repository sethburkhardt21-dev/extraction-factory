# ADR-125 — COLD_AUDIT runtime certification uses W4

`FRONTIER_COLD_AUDIT` is an architectural W4 role. Dedicated cold-audit benchmark certificates are therefore keyed as `COLD_AUDIT|W4|<source_class>`.

Runtime certification lookup MUST use W4 for `COLD_AUDIT` regardless of the ordinary extraction work class assigned to the source unit. PRIMARY and BLIND_RECALL continue to use the source unit's classified extraction work class.

This changes lookup only. It does not weaken source-unit, source hash, model-version, lifecycle, registry-authority, or independence checks.
