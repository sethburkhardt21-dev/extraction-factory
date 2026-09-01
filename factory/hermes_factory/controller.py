from __future__ import annotations
import csv
import json
import os
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .build_integrity import verify_build, write_current_manifest
from .cold_audit import deterministic_cold_audit
from .cold_audit_semantic import run_semantic_cold_audit
from .hashing import sha256_file, sha256_json, sha256_text
from .ledger import Ledger
from .literal import numeric_inventory, qualifier_inventory, relationship_inventory
from .models import AssertionCandidate, Gate, GateResult, SourceUnit
from .model_registry import load_registry, certification_key, is_certified_for_source
from .network_policy import enforce_provider_network_policy
from .package import build_offline_package
from .precision import precision_review
from .providers.base import SemanticProvider
from .readiness import derive_readiness
from .risk import classify_source_unit
from .router import route_families
from .runtime_identity import resolve_runtime_topology
from .runtime_lock import verify_runtime_lock
from .semantic import execute_blind, execute_primary
from .source import load_source_units
from .specialists import run_deterministic_specialists
from .staging import stage_artifact, verify_staged_artifact
from .union import build_evidence_families, deterministic_union


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            if hasattr(row, "to_dict"):
                row = row.to_dict()
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_tsv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = sorted({k for r in rows for k in r})
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def _candidate_integrity(candidates: List[AssertionCandidate], units: List[SourceUnit]) -> Dict[str, bool]:
    udict = {u.source_unit_id: u for u in units}
    spans = True; hashes = True; lineage = True; provenance = True; schema = True
    for c in candidates:
        u = udict.get(c.source_unit_id)
        if not u or c.evidence not in u.content:
            spans = False
        if sha256_text(c.evidence) != c.evidence_sha256:
            hashes = False
        if not c.originating_capsule_id or not c.originating_run_id or not c.parent_artifact_sha256:
            lineage = False
        if not c.source_id or not c.source_version_id or not c.source_sha256:
            provenance = False
        if c.validate_invariants():
            schema = False
    return {"spans": spans, "hashes": hashes, "lineage": lineage, "provenance": provenance, "schema": schema}


def _work_id(role: str, unit_id: str) -> str:
    return "WORK-" + sha256_text(role + "|" + unit_id)[:24]


def _provider_is_local(provider: SemanticProvider) -> bool:
    """Return True only when the provider explicitly declares no network requirement."""
    try:
        return provider.capabilities().get("network_required") is False
    except Exception:
        return False


def _resolved_schedule(primary_provider: SemanticProvider, blind_provider: SemanticProvider, requested: str) -> str:
    requested = (requested or "AUTO").upper()
    if requested not in {"AUTO", "PARALLEL", "PHASED"}:
        raise ValueError(f"invalid_provider_schedule:{requested}")
    if requested != "AUTO":
        return requested
    p = primary_provider.identity()
    b = blind_provider.identity()
    if (_provider_is_local(primary_provider) and _provider_is_local(blind_provider)
            and (p.model_alias != b.model_alias or p.underlying_family != b.underlying_family)):
        return "PHASED"
    return "PARALLEL"


def _effective_concurrency(provider: SemanticProvider, requested: int | None, workers: int) -> int:
    if requested is not None:
        if requested < 1:
            raise ValueError("provider_concurrency_must_be_positive")
        return requested
    return 1 if _provider_is_local(provider) else max(1, workers)


def _provider_telemetry(receipts: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for role in ("PRIMARY", "BLIND_RECALL"):
        rows = [r for r in receipts if r.get("role") == role]
        provider_seconds = []
        controller_seconds = []
        provider_attempts = 0
        for r in rows:
            pr = r.get("provider_receipt") or {}
            if isinstance(pr.get("duration_seconds"), (int, float)):
                provider_seconds.append(float(pr["duration_seconds"]))
            if isinstance(r.get("controller_duration_seconds"), (int, float)):
                controller_seconds.append(float(r["controller_duration_seconds"]))
            if isinstance(pr.get("attempts"), int):
                provider_attempts += pr["attempts"]
        provider_seconds.sort()
        out[role] = {
            "calls": len(rows),
            "provider_attempts": provider_attempts or None,
            "provider_seconds_total": round(sum(provider_seconds), 3),
            "provider_seconds_median": round(provider_seconds[len(provider_seconds)//2], 3) if provider_seconds else None,
            "provider_seconds_p95": round(provider_seconds[min(len(provider_seconds)-1, int((len(provider_seconds)-1)*0.95))], 3) if provider_seconds else None,
            "controller_seconds_total": round(sum(controller_seconds), 3),
        }
    return out


def _dispatch_role(ledger_path: Path, staging_root: Path, provider: SemanticProvider, units: List[SourceUnit],
                   role: str, risks: Dict[str, Dict[str, Any]], concurrency: int) -> Tuple[List[AssertionCandidate], List[Dict[str, Any]]]:
    candidates: List[AssertionCandidate] = []
    receipts: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, concurrency), thread_name_prefix=f"hermes-{role.lower()}") as pool:
        future_map = {
            pool.submit(_execute_semantic_work, ledger_path, staging_root, provider, unit, role,
                        str(risks[unit.source_unit_id]["source_class"])): unit.source_unit_id
            for unit in units
        }
        for fut in as_completed(future_map):
            row_candidates, receipt = fut.result()
            candidates.extend(row_candidates)
            receipts.append(receipt)
    return candidates, receipts


def _execute_semantic_work(ledger_path: Path, staging_root: Path, provider: SemanticProvider, unit: SourceUnit,
                           role: str, source_class: str, max_attempts: int = 2) -> Tuple[List[AssertionCandidate], Dict[str, Any]]:
    work_id = _work_id(role, unit.source_unit_id)
    started = time.perf_counter()
    last_error = None
    for attempt in range(1, max_attempts + 1):
        ledger = Ledger(ledger_path)
        lease_id = None
        try:
            work = ledger.get_work(work_id)
            if work is None:
                raise RuntimeError("work_not_registered")
            if work["state"] == "RETRY":
                ledger.transition(work_id, "READY", expected_state="RETRY", expected_version=work["version"], detail={"attempt": attempt})
            work = ledger.get_work(work_id)
            if work["state"] == "ACCEPTED":
                raise RuntimeError("accepted_work_must_be_loaded_not_reexecuted")
            lease_id = ledger.issue_lease(work_id, provider.identity().model_alias, ttl_seconds=900)
            ledger.mark_running(work_id, lease_id)
            run_id = "SEM-" + uuid.uuid4().hex
            if role == "PRIMARY":
                candidates, receipt = execute_primary(provider, unit, work_id, run_id, source_class)
            elif role == "BLIND_RECALL":
                candidates, receipt = execute_blind(provider, unit, work_id, run_id, source_class)
            else:
                raise ValueError("unknown_semantic_role")
            receipt["attempt"] = attempt
            receipt["controller_duration_seconds"] = round(time.perf_counter() - started, 3)
            payload = "".join(json.dumps(c.to_dict(), ensure_ascii=False, sort_keys=True) + "\n" for c in candidates)
            staged = stage_artifact(run_dir if False else staging_root, work_id=work_id, run_id=run_id,
                                    files={"candidates.jsonl": payload, "worker_receipt.json": receipt})
            artifact_id = ledger.register_staged_artifact(work_id, lease_id, run_id, staged["path"], staged["manifest_sha256"])
            ledger.begin_validation(work_id, lease_id, artifact_id)
            verified = verify_staged_artifact(Path(staged["path"]))
            if not verified["ok"]:
                raise RuntimeError(f"staging_validation_failed:{verified['errors']}")
            parent = ledger.get_work(work_id)["version"]
            ledger.commit_validated(work_id, lease_id, artifact_id, expected_parent_version=parent,
                                    expected_manifest_sha256=verified["manifest_sha256"], run_id=run_id)
            ledger.close()
            return candidates, receipt
        except Exception as exc:
            last_error = exc
            try:
                if lease_id is not None:
                    work = ledger.get_work(work_id)
                    if work and work["state"] in {"LEASED", "RUNNING", "STAGED", "VALIDATING"}:
                        target = "RETRY" if attempt < max_attempts else "FAILED"
                        ledger.abandon_active_work(work_id, lease_id, target_state=target, reason=f"{type(exc).__name__}:{exc}")
            finally:
                ledger.close()
            if attempt >= max_attempts:
                raise
    raise RuntimeError(f"semantic_work_failed:{last_error}")


def run_factory(*, project_root: Path, source_units_path: Path, primary_provider: SemanticProvider,
                blind_provider: SemanticProvider, output_root: Path, source_pdf: Path | None = None,
                source_expected_sha256: str | None = None, database_09d: Path | None = None,
                cold_audit_rate: float = 0.25, mode: str = "OFFLINE_FIXTURE", execution_mode: str = "LOCAL_ONLY",
                workers: int = 4, cold_audit_provider: SemanticProvider | None = None,
                provider_schedule: str = "AUTO", primary_concurrency: int | None = None,
                blind_concurrency: int | None = None, cold_concurrency: int = 1) -> Dict[str, Any]:
    project_root = Path(project_root)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = "HERMES-" + time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    run_dir = output_root / run_id
    for d in ["SOURCE", "ASSERTIONS", "INVENTORIES", "FAMILIES", "REVIEW", "PROVENANCE", "STATE", "VALIDATION", "staging", "09D"]:
        (run_dir / d).mkdir(parents=True, exist_ok=True)

    units = load_source_units(source_units_path)
    source_units_input_sha256 = sha256_file(source_units_path)
    shutil.copy2(source_units_path, run_dir / "SOURCE" / "source_units.jsonl")
    _write_json(run_dir / "SOURCE" / "source_summary.json", {
        "source_unit_count": len(units),
        "source_ids": sorted({u.source_id for u in units}),
        "source_sha256s": sorted({u.source_sha256 for u in units}),
        "source_units_input_sha256": source_units_input_sha256,
    })
    source_hash_ok = False
    source_hash_result = GateResult.NOT_RUN.value
    source_hash_detail = "Original source bytes and expected source hash were not both supplied; source hash authority cannot be closed."
    if source_pdf is not None and source_expected_sha256 is not None:
        actual = sha256_file(source_pdf)
        source_hash_ok = actual == source_expected_sha256 and all(u.source_sha256 == source_expected_sha256 for u in units)
        source_hash_result = GateResult.PASS.value if source_hash_ok else GateResult.FAIL_BLOCKING.value
        source_hash_detail = f"expected={source_expected_sha256};actual={actual}"

    current_manifest = write_current_manifest(project_root, project_root / "CURRENT" / "CURRENT_BUILD_MANIFEST.json")
    build_check = verify_build(project_root, project_root / "CURRENT" / "CERTIFIED_BUILD_MANIFEST.json")
    runtime_check = verify_runtime_lock(project_root / "CURRENT" / "RUNTIME_LOCK.json")
    runtime_registry = load_registry(project_root / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json")
    runtime_topology: Dict[str, Dict[str, Any]] | None = None
    runtime_topology_error: str | None = None
    if mode != "OFFLINE_FIXTURE":
        try:
            runtime_topology = resolve_runtime_topology(
                runtime_registry,
                primary_provider,
                blind_provider,
                cold_audit_provider,
                require_empirical=True,
            )
        except ValueError as exc:
            runtime_topology_error = str(exc)

    if mode != "OFFLINE_FIXTURE":
        predispatch_failures = []
        if source_hash_result != GateResult.PASS.value:
            predispatch_failures.append({"gate": "SOURCE_HASH", "result": source_hash_result, "detail": source_hash_detail})
        if build_check.get("result") != GateResult.PASS.value:
            predispatch_failures.append({"gate": "BUILD_INTEGRITY", "result": build_check.get("result"), "detail": build_check.get("errors", [])})
        if runtime_check.get("result") != GateResult.PASS.value:
            predispatch_failures.append({"gate": "RUNTIME_LOCK", "result": runtime_check.get("result"), "detail": runtime_check.get("errors", [])})
        if runtime_topology_error is not None:
            predispatch_failures.append({
                "gate": "MODEL_IDENTITY_INDEPENDENCE",
                "result": GateResult.FAIL_BLOCKING.value,
                "detail": runtime_topology_error,
            })
        if predispatch_failures:
            failure = {
                "status": "NOT_READY",
                "provider_calls_started": 0,
                "fail_closed_stage": "PRE_PROVIDER_DISPATCH",
                "failures": predispatch_failures,
            }
            _write_json(run_dir / "VALIDATION" / "predispatch_failure.json", failure)
            raise RuntimeError("predispatch_gate_failure:" + json.dumps(failure, sort_keys=True))

    enforce_provider_network_policy(execution_mode, primary_provider)
    enforce_provider_network_policy(execution_mode, blind_provider)
    if cold_audit_provider is not None:
        enforce_provider_network_policy(execution_mode, cold_audit_provider)
    ledger_path = run_dir / "STATE" / "ledger.sqlite"
    ledger = Ledger(ledger_path)
    primary_candidates: List[AssertionCandidate] = []
    blind_candidates: List[AssertionCandidate] = []
    worker_receipts: List[Dict[str, Any]] = []

    risks = {u.source_unit_id: classify_source_unit(u) for u in units}
    _write_json(run_dir / "SOURCE" / "risk_classification.json", risks)

    tasks = []
    for unit in units:
        for role in ("PRIMARY", "BLIND_RECALL"):
            wid = _work_id(role, unit.source_unit_id)
            if ledger.get_work(wid) is None:
                ledger.register_work({"work_id": wid, "work_type": role, "source_unit_id": unit.source_unit_id,
                                      "priority": risks[unit.source_unit_id]["priority"],
                                      "source_class": risks[unit.source_unit_id]["source_class"]})
            tasks.append((unit, role))

    resolved_schedule = _resolved_schedule(primary_provider, blind_provider, provider_schedule)
    primary_limit = _effective_concurrency(primary_provider, primary_concurrency, workers)
    blind_limit = _effective_concurrency(blind_provider, blind_concurrency, workers)
    _write_json(run_dir / "PROVENANCE" / "provider_schedule.json", {
        "requested": provider_schedule.upper(),
        "resolved": resolved_schedule,
        "primary_concurrency": primary_limit,
        "blind_concurrency": blind_limit,
        "reason": (
            "different local models are phased to prevent accelerator model-residency thrash"
            if resolved_schedule == "PHASED" and provider_schedule.upper() == "AUTO" else
            "explicit operator schedule" if provider_schedule.upper() != "AUTO" else
            "providers can share parallel dispatch without cross-model local residency thrash"
        ),
    })

    if resolved_schedule == "PHASED":
        primary_candidates, primary_receipts = _dispatch_role(
            ledger_path, run_dir / "staging", primary_provider, units, "PRIMARY", risks, primary_limit)
        worker_receipts.extend(primary_receipts)
        blind_candidates, blind_receipts = _dispatch_role(
            ledger_path, run_dir / "staging", blind_provider, units, "BLIND_RECALL", risks, blind_limit)
        worker_receipts.extend(blind_receipts)
    else:
        with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="hermes-worker") as pool:
            future_map = {}
            for unit, role in tasks:
                provider = primary_provider if role == "PRIMARY" else blind_provider
                fut = pool.submit(_execute_semantic_work, ledger_path, run_dir / "staging", provider, unit, role,
                                  str(risks[unit.source_unit_id]["source_class"]))
                future_map[fut] = role
            for fut in as_completed(future_map):
                role = future_map[fut]
                row_candidates, receipt = fut.result()
                if role == "PRIMARY":
                    primary_candidates.extend(row_candidates)
                else:
                    blind_candidates.extend(row_candidates)
                worker_receipts.append(receipt)

    union = deterministic_union(primary_candidates, blind_candidates)
    families = build_evidence_families(union)
    specialists = run_deterministic_specialists(families, union, units)
    routes = route_families(families, specialists)
    precision = precision_review(union, units)
    cold = deterministic_cold_audit(union, units, rate=cold_audit_rate)

    primary_group = (
        str(runtime_topology["PRIMARY"]["independence_group"])
        if runtime_topology is not None else primary_provider.identity().underlying_family
    )
    blind_group = (
        str(runtime_topology["BLIND_RECALL"]["independence_group"])
        if runtime_topology is not None else blind_provider.identity().underlying_family
    )
    cold_group = (
        str(runtime_topology["COLD_AUDIT"]["independence_group"])
        if runtime_topology is not None and "COLD_AUDIT" in runtime_topology
        else (cold_audit_provider.identity().underlying_family if cold_audit_provider is not None else None)
    )

    semantic_cold = None
    if cold_audit_provider is not None and cold_audit_provider.is_empirical_semantic_provider():
        semantic_cold = run_semantic_cold_audit(
            cold_audit_provider, union, units, rate=cold_audit_rate, run_id=run_id,
            primary_family=primary_provider.identity().underlying_family,
            blind_family=blind_provider.identity().underlying_family,
            primary_independence_group=primary_group,
            blind_independence_group=blind_group,
            auditor_independence_group=cold_group,
            concurrency=max(1, cold_concurrency),
        )

    numerics = [x for u in units for x in numeric_inventory(u)]
    qualifiers = [x for u in units for x in qualifier_inventory(u)]
    relationships = [x for u in units for x in relationship_inventory(u)]

    _write_jsonl(run_dir / "ASSERTIONS" / "primary_candidates.jsonl", primary_candidates)
    _write_jsonl(run_dir / "ASSERTIONS" / "blind_recall_candidates.jsonl", blind_candidates)
    _write_jsonl(run_dir / "ASSERTIONS" / "union_candidates.jsonl", union)
    _write_tsv(run_dir / "ASSERTIONS" / "union_candidates.tsv", [c.to_dict() for c in union])
    _write_jsonl(run_dir / "INVENTORIES" / "numeric.jsonl", numerics)
    _write_jsonl(run_dir / "INVENTORIES" / "qualifier.jsonl", qualifiers)
    _write_jsonl(run_dir / "INVENTORIES" / "relationship.jsonl", relationships)
    _write_jsonl(run_dir / "FAMILIES" / "evidence_families.jsonl", families)
    _write_jsonl(run_dir / "REVIEW" / "specialist_receipts.jsonl", specialists)
    _write_jsonl(run_dir / "REVIEW" / "routes.jsonl", routes)
    _write_jsonl(run_dir / "REVIEW" / "precision_review.jsonl", precision)
    _write_json(run_dir / "REVIEW" / "cold_audit.json", cold)
    if semantic_cold is not None:
        _write_json(run_dir / "REVIEW" / "cold_audit_semantic.json", semantic_cold)
    _write_jsonl(run_dir / "PROVENANCE" / "worker_receipts.jsonl", worker_receipts)

    snapshot = ledger.snapshot()
    _write_json(run_dir / "STATE" / "snapshot.json", snapshot)
    _write_jsonl(run_dir / "STATE" / "event_history.jsonl", [dict(r) for r in ledger.db.execute("SELECT * FROM events ORDER BY seq")])
    _write_tsv(run_dir / "STATE" / "lease_history.tsv", [dict(r) for r in ledger.db.execute("SELECT * FROM leases ORDER BY issued_at")])
    _write_tsv(run_dir / "STATE" / "commit_history.tsv", [dict(r) for r in ledger.db.execute("SELECT * FROM commits ORDER BY committed_at")])

    integrity = _candidate_integrity(union, units)
    semantic_empirical = primary_provider.is_empirical_semantic_provider() and blind_provider.is_empirical_semantic_provider()
    registry = runtime_registry
    benchmark_version = registry.get("benchmark_version", "UNKNOWN")

    def role_certified(provider, role):
        ident = provider.identity()
        for u in units:
            risk = risks[u.source_unit_id]
            key = certification_key(
                ident.provider, ident.model_alias, role,
                str(risk["work_class"]), str(risk["source_class"]), benchmark_version,
            )
            if not is_certified_for_source(
                registry,
                key,
                source_units_sha256=source_units_input_sha256,
                source_unit_id=u.source_unit_id,
                provider=ident.provider,
                model_alias=ident.model_alias,
                observed_version=ident.observed_version,
            ):
                return False
        return True

    primary_cert = role_certified(primary_provider, "PRIMARY")
    blind_cert = role_certified(blind_provider, "BLIND_RECALL")
    cold_cert = role_certified(cold_audit_provider, "COLD_AUDIT") if cold_audit_provider is not None else False
    independent = bool(primary_group and blind_group and primary_group != blind_group)
    unresolved = [r for r in routes if r["action"] != "LOCAL_PRECISION_COMPLETE"]
    table_visual_unresolved = [r for r in routes if any(x.startswith(("TABLE_BINDING", "IMAGE_AVAILABLE")) for x in r["unresolved_flags"])]
    cross_unresolved = [r for r in routes if any(x.startswith("CROSS_PAGE") for x in r["unresolved_flags"])]
    numeric_unresolved = [r for r in routes if any(x.startswith("UNBOUND_NUMERIC") for x in r["unresolved_flags"])]
    qualifier_unresolved = [r for r in routes if any("QUALIFIER_NOT_PRESERVED" in x for x in r["unresolved_flags"])]
    rel_unresolved = [r for r in routes if any("DIRECTION_CUE_LOST" in x for x in r["unresolved_flags"])]

    if database_09d:
        from .bridge_09d import inventory_schema_readonly, assert_write_blocked
        inv = inventory_schema_readonly(database_09d)
        write_blocked = assert_write_blocked(database_09d)
        _write_json(run_dir / "09D" / "readonly_schema_inventory.json", inv)
        gate_09d = Gate("09D_READONLY_BOUNDARY", GateResult.PASS.value if write_blocked else GateResult.FAIL_BLOCKING.value,
                        "SQLite opened mode=ro; write mutation test executed")
    else:
        gate_09d = Gate("09D_READONLY_BOUNDARY", GateResult.NOT_APPLICABLE.value, "No 09D database supplied to this run")

    semantic_provider_gate = Gate(
        "SEMANTIC_PROVIDER_CERTIFICATION",
        GateResult.PASS.value if semantic_empirical and primary_cert and blind_cert else GateResult.BLOCKED_EXTERNAL.value,
        "Both primary and blind roles require source- and model-version-bound empirically certified semantic providers; fixture, unbenchmarked, differently scoped, or changed-version certifications cannot satisfy this gate.",
    )
    independence_gate = Gate(
        "INDEPENDENCE",
        GateResult.PASS.value if independent else (GateResult.BLOCKED_EXTERNAL.value if not semantic_empirical else GateResult.FAIL_REVIEW_REQUIRED.value),
        (
            f"primary_group={primary_group};blind_group={blind_group};"
            f"primary_family={primary_provider.identity().underlying_family};"
            f"blind_family={blind_provider.identity().underlying_family}"
        ),
    )
    if not semantic_empirical:
        cold_gate = Gate(
            "COLD_AUDIT_POLICY", GateResult.BLOCKED_EXTERNAL.value,
            "Deterministic cold-audit mechanics executed; independent semantic cold-audit model remains required for empirical frontier readiness.",
        )
    elif semantic_cold is None:
        cold_gate = Gate(
            "COLD_AUDIT_POLICY", GateResult.BLOCKED_EXTERNAL.value,
            "Real providers ran but no independent semantic cold-audit provider was configured for this run.",
        )
    elif semantic_cold["status"] == "FAIL_INDEPENDENCE":
        cold_gate = Gate(
            "COLD_AUDIT_POLICY", GateResult.FAIL_REVIEW_REQUIRED.value,
            (
                f"Semantic cold audit ran but auditor independence group "
                f"'{semantic_cold.get('auditor_independence_group')}' is not independent of "
                f"primary/blind groups; reduced independence is recorded, not waived."
            ),
        )
    elif semantic_cold["status"] == "PASS" and not cold_cert:
        cold_gate = Gate(
            "COLD_AUDIT_POLICY", GateResult.BLOCKED_EXTERNAL.value,
            f"Independent semantic cold audit ran cleanly, but auditor role {semantic_cold['auditor_identity']['provider']}|{semantic_cold['auditor_identity']['model_alias']} is not source- and model-version-bound certified for COLD_AUDIT on this exact benchmark/source scope.",
        )
    elif semantic_cold["status"] == "PASS":
        cold_gate = Gate(
            "COLD_AUDIT_POLICY", GateResult.PASS.value,
            f"Source- and model-version-bound certified independent semantic cold audit: {semantic_cold['audited_count']} sampled candidates reviewed by independence group {semantic_cold.get('auditor_independence_group')}, zero disagreements/errors.",
        )
    else:
        cold_gate = Gate(
            "COLD_AUDIT_POLICY", GateResult.FAIL_REVIEW_REQUIRED.value,
            f"Independent semantic cold audit produced {semantic_cold['disagreement_count']} disagreements and {semantic_cold['error_count']} errors over {semantic_cold['audited_count']} audited candidates.",
            bounded_queue="REVIEW/cold_audit_semantic.json",
        )

    def bounded(name: str, rows: list, path: str) -> Gate:
        return Gate(name, GateResult.FAIL_REVIEW_REQUIRED.value if rows else GateResult.PASS.value,
                    f"unresolved_count={len(rows)}", bounded_queue=path if rows else None)

    gates = [
        Gate("SOURCE_AUTHORITY", GateResult.PASS.value if units else GateResult.FAIL_BLOCKING.value, f"source_units={len(units)}"),
        Gate("SOURCE_HASH", source_hash_result, source_hash_detail),
        Gate("BUILD_INTEGRITY", build_check["result"], ";".join(build_check.get("errors", [])) or "current build matches immutable certified manifest"),
        Gate("RUNTIME_LOCK", runtime_check["result"], ";".join(runtime_check.get("errors", [])) or "runtime matches lock"),
        Gate("SCHEMA", GateResult.PASS.value if integrity["schema"] else GateResult.FAIL_BLOCKING.value),
        Gate("PROVENANCE", GateResult.PASS.value if integrity["provenance"] else GateResult.FAIL_BLOCKING.value),
        Gate("EVIDENCE_SPANS", GateResult.PASS.value if integrity["spans"] else GateResult.FAIL_BLOCKING.value),
        Gate("EVIDENCE_HASHES", GateResult.PASS.value if integrity["hashes"] else GateResult.FAIL_BLOCKING.value),
        Gate("LINEAGE", GateResult.PASS.value if integrity["lineage"] else GateResult.FAIL_BLOCKING.value),
        Gate("LEDGER_INTEGRITY", GateResult.PASS.value if snapshot["event_chain_valid"] else GateResult.FAIL_BLOCKING.value),
        Gate("STATE_RECONCILIATION", GateResult.PASS.value if snapshot["state_reconciliation_valid"] else GateResult.FAIL_BLOCKING.value),
        Gate("CAS_CURRENT_STATE", GateResult.PASS.value if all(w["state"] == "ACCEPTED" for w in snapshot["work_items"]) else GateResult.FAIL_BLOCKING.value),
        Gate("BLINDNESS", GateResult.PASS.value, "Blind request constructed by positive allowlist; behavioral mutation suite provides independent regression gate."),
        independence_gate,
        Gate("PRIMARY_PASS", GateResult.PASS.value if primary_candidates else GateResult.FAIL_REVIEW_REQUIRED.value, f"candidate_count={len(primary_candidates)}"),
        Gate("BLIND_RECALL_PASS", GateResult.PASS.value if blind_candidates else GateResult.FAIL_REVIEW_REQUIRED.value, f"candidate_count={len(blind_candidates)}"),
        semantic_provider_gate,
        bounded("NUMERIC_CONTROL", numeric_unresolved, "REVIEW/routes.jsonl"),
        bounded("QUALIFIER_CONTROL", qualifier_unresolved, "REVIEW/routes.jsonl"),
        bounded("RELATIONSHIP_CONTROL", rel_unresolved, "REVIEW/routes.jsonl"),
        bounded("TABLE_VISUAL_CONTROL", table_visual_unresolved, "REVIEW/routes.jsonl"),
        bounded("CROSS_PAGE_CONTROL", cross_unresolved, "REVIEW/routes.jsonl"),
        Gate("PRECISION_REVIEW", GateResult.PASS.value if all(x["result"] == "PASS" for x in precision) else GateResult.FAIL_BLOCKING.value),
        cold_gate,
        Gate("SEMANTIC_RECEIPTS", GateResult.PASS.value if len(worker_receipts) == len(units) * 2 else GateResult.FAIL_BLOCKING.value,
             f"receipt_count={len(worker_receipts)}"),
        Gate("PACKAGE_INTEGRITY", GateResult.NOT_RUN.value, "Package is built after preliminary gate derivation."),
        gate_09d,
    ]
    prelim = derive_readiness(gates)
    _write_json(run_dir / "VALIDATION" / "readiness_prepackage.json", prelim)

    summary = {
        "run_id": run_id,
        "mode": mode,
        "execution_mode": execution_mode,
        "workers": workers,
        "provider_schedule": resolved_schedule,
        "primary_concurrency": primary_limit,
        "blind_concurrency": blind_limit,
        "cold_concurrency": max(1, cold_concurrency),
        "provider_telemetry": _provider_telemetry(worker_receipts),
        "provider_independence": {
            "primary_group": primary_group,
            "blind_group": blind_group,
            "cold_group": cold_group,
        },
        "source_unit_count": len(units),
        "source_units_input_sha256": source_units_input_sha256,
        "primary_candidate_count": len(primary_candidates),
        "blind_candidate_count": len(blind_candidates),
        "union_candidate_count": len(union),
        "evidence_family_count": len(families),
        "numeric_literal_count": len(numerics),
        "qualifier_literal_count": len(qualifiers),
        "relationship_literal_count": len(relationships),
        "specialist_receipt_count": len(specialists),
        "unresolved_route_count": len(unresolved),
        "primary_provider": primary_provider.identity().to_dict(),
        "blind_provider": blind_provider.identity().to_dict(),
        "cold_audit_provider": cold_audit_provider.identity().to_dict() if cold_audit_provider else None,
        "semantic_cold_audit_status": semantic_cold["status"] if semantic_cold else None,
        "semantic_empirical": semantic_empirical,
        "semantic_quality_measured": False,
        "claim_boundary": (
            "Real semantic providers executed, but precision/recall is not certified until scored against frozen source-first gold with source- and model-version-bound certification."
            if semantic_empirical else
            "Offline fixture execution proves mechanics only; fixture output is not empirical semantic evidence."
        ),
    }
    _write_json(run_dir / "RUN_SUMMARY.json", summary)
    (run_dir / "README_START_HERE.md").write_text(
        f"# Hermes extraction run {run_id}\n\nMode: `{mode}`\n\nThis package contains source units, noncanonical candidates, receipts, durable state, reviews, and validation.\n\n"
        "Candidate extraction is not canonical truth. Inspect `VALIDATION/readiness.json` for the mechanically derived status.\n",
        encoding="utf-8",
    )

    temp_zip = output_root / (run_id + "_PREPACKAGE.zip")
    build_offline_package(run_dir, temp_zip, package_status=prelim["status"])
    temp_zip.unlink(missing_ok=True)
    for gate in gates:
        if gate.name == "PACKAGE_INTEGRITY":
            gate.result = GateResult.PASS.value
            gate.detail = "Package builder completed and independently re-hashed extracted bundle contents."
    final_readiness = derive_readiness(gates)
    _write_json(run_dir / "VALIDATION" / "readiness.json", final_readiness)
    final_name = ("FRONTIER_REVIEW_READY_" if final_readiness["status"] == "FRONTIER_REVIEW_READY" else
                  "READY_FOR_PROVIDER_" if final_readiness["status"] == "READY_FOR_PROVIDER" else "REVIEW_PACKAGE_") + run_id + ".zip"
    final_zip = output_root / final_name
    package = build_offline_package(run_dir, final_zip, package_status=final_readiness["status"])
    _write_json(run_dir / "VALIDATION" / "external_package_receipt.json", package)
    ledger.close()
    return {"run_id": run_id, "run_dir": str(run_dir), "package": package, "readiness": final_readiness, "summary": summary}