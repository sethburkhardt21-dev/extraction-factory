from __future__ import annotations

import csv
import io
import json
import os
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .bridge_09d import inventory_schema_readonly
from .build_integrity import verify_build, write_current_manifest
from .cold_audit import deterministic_cold_audit
from .cold_audit_semantic import run_semantic_cold_audit
from .contract_09d import verify_09d_contract
from .hashing import sha256_file, sha256_json, sha256_text
from .ledger import Ledger
from .literal import numeric_inventory, qualifier_inventory, relationship_inventory
from .model_registry import certification_key, is_certified, load_registry
from .models import AssertionCandidate, Gate, GateResult, SourceUnit
from .network_policy import enforce_provider_network_policy
from .package import build_offline_package
from .precision import precision_review
from .providers.base import SemanticProvider
from .readiness import derive_readiness
from .risk import classify_source_unit
from .router import route_families
from .runtime_lock import verify_runtime_lock
from .semantic import execute_blind, execute_primary
from .source import load_source_units
from .specialists import run_deterministic_specialists
from .staging import stage_artifact, verify_staged_artifact
from .union import build_evidence_families, deterministic_union


# ---------- crash-safe artifact writers ----------

def _atomic_replace_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        # Best-effort directory fsync on platforms that support opening folders.
        try:
            fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except (OSError, AttributeError):
            pass
    finally:
        tmp.unlink(missing_ok=True)


def _write_json(path: Path, value: Any) -> None:
    _atomic_replace_text(Path(path), json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def _write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            for row in rows:
                if hasattr(row, "to_dict"):
                    row = row.to_dict()
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _write_tsv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        _atomic_replace_text(Path(path), "")
        return
    keys = sorted({k for r in rows for k in r})
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=keys, delimiter="\t", extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({
            k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
            for k, v in row.items()
        })
    _atomic_replace_text(Path(path), buf.getvalue())


# ---------- deterministic integrity / scheduling ----------

def _candidate_integrity(candidates: List[AssertionCandidate], units: List[SourceUnit]) -> Dict[str, bool]:
    unit_by_id = {u.source_unit_id: u for u in units}
    spans = hashes = lineage = provenance = schema = stable_identity = True
    for candidate in candidates:
        unit = unit_by_id.get(candidate.source_unit_id)
        if not unit or candidate.evidence not in unit.content:
            spans = False
        if sha256_text(candidate.evidence) != candidate.evidence_sha256:
            hashes = False
        if not candidate.originating_capsule_id or not candidate.originating_run_id or not candidate.parent_artifact_sha256:
            lineage = False
        if not candidate.source_id or not candidate.source_version_id or not candidate.source_sha256:
            provenance = False
        if not candidate.stable_witness_sha256 or not candidate.stable_claim_sha256:
            stable_identity = False
        if candidate.validate_invariants():
            schema = False
    return {
        "spans": spans,
        "hashes": hashes,
        "lineage": lineage,
        "provenance": provenance,
        "schema": schema,
        "stable_identity": stable_identity,
    }


def _work_id(role: str, unit_id: str) -> str:
    return "WORK-" + sha256_text(role + "|" + unit_id)[:24]


def _provider_is_local(provider: SemanticProvider) -> bool:
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
    primary = primary_provider.identity()
    blind = blind_provider.identity()
    if (
        _provider_is_local(primary_provider)
        and _provider_is_local(blind_provider)
        and (primary.model_alias != blind.model_alias or primary.underlying_family != blind.underlying_family)
    ):
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
        provider_seconds: list[float] = []
        controller_seconds: list[float] = []
        provider_attempts = 0
        for row in rows:
            provider_receipt = row.get("provider_receipt") or {}
            if isinstance(provider_receipt.get("duration_seconds"), (int, float)):
                provider_seconds.append(float(provider_receipt["duration_seconds"]))
            if isinstance(row.get("controller_duration_seconds"), (int, float)):
                controller_seconds.append(float(row["controller_duration_seconds"]))
            if isinstance(provider_receipt.get("attempts"), int):
                provider_attempts += provider_receipt["attempts"]
        provider_seconds.sort()
        out[role] = {
            "calls": len(rows),
            "provider_attempts": provider_attempts or None,
            "provider_seconds_total": round(sum(provider_seconds), 3),
            "provider_seconds_median": round(provider_seconds[len(provider_seconds) // 2], 3) if provider_seconds else None,
            "provider_seconds_p95": (
                round(provider_seconds[min(len(provider_seconds) - 1, int((len(provider_seconds) - 1) * 0.95))], 3)
                if provider_seconds else None
            ),
            "controller_seconds_total": round(sum(controller_seconds), 3),
        }
    return out


def _execute_semantic_work(
    ledger_path: Path,
    staging_root: Path,
    provider: SemanticProvider,
    unit: SourceUnit,
    role: str,
    source_class: str,
    max_attempts: int = 2,
    lease_ttl_seconds: int = 1800,
) -> Tuple[List[AssertionCandidate], Dict[str, Any]]:
    if lease_ttl_seconds < 60:
        raise ValueError("lease_ttl_seconds_must_be_at_least_60")
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
                ledger.transition(
                    work_id,
                    "READY",
                    expected_state="RETRY",
                    expected_version=work["version"],
                    detail={"attempt": attempt},
                )
            work = ledger.get_work(work_id)
            if work["state"] == "ACCEPTED":
                raise RuntimeError("accepted_work_must_be_loaded_not_reexecuted")
            lease_id = ledger.issue_lease(
                work_id,
                provider.identity().model_alias,
                ttl_seconds=lease_ttl_seconds,
            )
            ledger.mark_running(work_id, lease_id)
            semantic_run_id = "SEM-" + uuid.uuid4().hex
            if role == "PRIMARY":
                candidates, receipt = execute_primary(provider, unit, work_id, semantic_run_id, source_class)
            elif role == "BLIND_RECALL":
                candidates, receipt = execute_blind(provider, unit, work_id, semantic_run_id, source_class)
            else:
                raise ValueError("unknown_semantic_role")
            receipt["attempt"] = attempt
            receipt["lease_ttl_seconds"] = lease_ttl_seconds
            receipt["controller_duration_seconds"] = round(time.perf_counter() - started, 3)
            payload = "".join(
                json.dumps(c.to_dict(), ensure_ascii=False, sort_keys=True) + "\n" for c in candidates
            )
            staged = stage_artifact(
                staging_root,
                work_id=work_id,
                run_id=semantic_run_id,
                files={"candidates.jsonl": payload, "worker_receipt.json": receipt},
            )
            artifact_id = ledger.register_staged_artifact(
                work_id,
                lease_id,
                semantic_run_id,
                staged["path"],
                staged["manifest_sha256"],
            )
            ledger.begin_validation(work_id, lease_id, artifact_id)
            verified = verify_staged_artifact(Path(staged["path"]))
            if not verified["ok"]:
                raise RuntimeError(f"staging_validation_failed:{verified['errors']}")
            parent = ledger.get_work(work_id)["version"]
            ledger.commit_validated(
                work_id,
                lease_id,
                artifact_id,
                expected_parent_version=parent,
                expected_manifest_sha256=verified["manifest_sha256"],
                run_id=semantic_run_id,
            )
            return candidates, receipt
        except Exception as exc:
            last_error = exc
            if lease_id is not None:
                try:
                    work = ledger.get_work(work_id)
                    if work and work["state"] in {"LEASED", "RUNNING", "STAGED", "VALIDATING"}:
                        target = "RETRY" if attempt < max_attempts else "FAILED"
                        ledger.abandon_active_work(
                            work_id,
                            lease_id,
                            target_state=target,
                            reason=f"{type(exc).__name__}:{exc}",
                        )
                except Exception:
                    # Preserve the original provider/staging exception. The main
                    # controller will record a failure artifact and the ledger
                    # reconciliation gate will remain fail-closed.
                    pass
            if attempt >= max_attempts:
                raise
        finally:
            ledger.close()
    raise RuntimeError(f"semantic_work_failed:{last_error}")


def _dispatch_role(
    ledger_path: Path,
    staging_root: Path,
    provider: SemanticProvider,
    units: List[SourceUnit],
    role: str,
    risks: Dict[str, Dict[str, Any]],
    concurrency: int,
    lease_ttl_seconds: int,
) -> Tuple[List[AssertionCandidate], List[Dict[str, Any]]]:
    candidates: List[AssertionCandidate] = []
    receipts: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, concurrency), thread_name_prefix=f"hermes-{role.lower()}") as pool:
        future_map = {
            pool.submit(
                _execute_semantic_work,
                ledger_path,
                staging_root,
                provider,
                unit,
                role,
                str(risks[unit.source_unit_id]["source_class"]),
                2,
                lease_ttl_seconds,
            ): unit.source_unit_id
            for unit in units
        }
        try:
            for future in as_completed(future_map):
                row_candidates, receipt = future.result()
                candidates.extend(row_candidates)
                receipts.append(receipt)
        except Exception:
            for future in future_map:
                future.cancel()
            raise
    return candidates, receipts


def _strict_09d_predispatch(database_09d: Path | None, run_dir: Path, *, external_semantic: bool) -> Dict[str, Any] | None:
    if database_09d is None:
        return None
    report = verify_09d_contract(
        Path(database_09d),
        verify_identity=external_semantic,
        strict_counts=external_semantic,
        quick_check=False,
    )
    _write_json(run_dir / "09D" / "09d_contract_predispatch.json", report)
    if report.get("ok"):
        _write_json(run_dir / "09D" / "readonly_schema_inventory.json", inventory_schema_readonly(Path(database_09d)))
    return report


# ---------- canonical governed run ----------

def run_factory(
    *,
    project_root: Path,
    source_units_path: Path,
    primary_provider: SemanticProvider,
    blind_provider: SemanticProvider,
    output_root: Path,
    source_pdf: Path | None = None,
    source_expected_sha256: str | None = None,
    database_09d: Path | None = None,
    cold_audit_rate: float = 0.25,
    mode: str = "OFFLINE_FIXTURE",
    execution_mode: str = "LOCAL_ONLY",
    workers: int = 4,
    cold_audit_provider: SemanticProvider | None = None,
    provider_schedule: str = "AUTO",
    primary_concurrency: int | None = None,
    blind_concurrency: int | None = None,
    cold_concurrency: int = 1,
    lease_ttl_seconds: int = 1800,
) -> Dict[str, Any]:
    project_root = Path(project_root)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = "HERMES-" + time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    run_dir = output_root / run_id
    for directory in (
        "SOURCE", "ASSERTIONS", "INVENTORIES", "FAMILIES", "REVIEW", "PROVENANCE",
        "STATE", "VALIDATION", "staging", "09D",
    ):
        (run_dir / directory).mkdir(parents=True, exist_ok=True)

    units = load_source_units(source_units_path)
    shutil.copy2(source_units_path, run_dir / "SOURCE" / "source_units.jsonl")
    _write_json(run_dir / "SOURCE" / "source_summary.json", {
        "source_unit_count": len(units),
        "source_ids": sorted({u.source_id for u in units}),
        "source_sha256s": sorted({u.source_sha256 for u in units}),
        "source_units_input_sha256": sha256_file(source_units_path),
    })

    source_hash_result = GateResult.NOT_RUN.value
    source_hash_detail = "Original source bytes and expected source hash were not both supplied; source hash authority cannot be closed."
    if source_pdf is not None and source_expected_sha256 is not None:
        actual = sha256_file(source_pdf)
        source_hash_ok = actual == source_expected_sha256 and all(u.source_sha256 == source_expected_sha256 for u in units)
        source_hash_result = GateResult.PASS.value if source_hash_ok else GateResult.FAIL_BLOCKING.value
        source_hash_detail = f"expected={source_expected_sha256};actual={actual}"

    write_current_manifest(project_root, project_root / "CURRENT" / "CURRENT_BUILD_MANIFEST.json")
    build_check = verify_build(project_root, project_root / "CURRENT" / "CERTIFIED_BUILD_MANIFEST.json")
    runtime_check = verify_runtime_lock(project_root / "CURRENT" / "RUNTIME_LOCK.json")
    external_semantic = mode != "OFFLINE_FIXTURE"
    contract_09d = _strict_09d_predispatch(database_09d, run_dir, external_semantic=external_semantic)

    # Every deterministic dependency that can invalidate an expensive run is
    # evaluated before a provider is contacted.
    if external_semantic:
        predispatch_failures: list[dict] = []
        if not units:
            predispatch_failures.append({"gate": "SOURCE_AUTHORITY", "result": "FAIL_BLOCKING", "detail": "zero source units"})
        if source_hash_result != GateResult.PASS.value:
            predispatch_failures.append({"gate": "SOURCE_HASH", "result": source_hash_result, "detail": source_hash_detail})
        if build_check.get("result") != GateResult.PASS.value:
            predispatch_failures.append({"gate": "BUILD_INTEGRITY", "result": build_check.get("result"), "detail": build_check.get("errors", [])})
        if runtime_check.get("result") != GateResult.PASS.value:
            predispatch_failures.append({"gate": "RUNTIME_LOCK", "result": runtime_check.get("result"), "detail": runtime_check.get("errors", [])})
        if database_09d is not None:
            if not contract_09d or not contract_09d.get("ok") or not contract_09d.get("target_identity_verified"):
                predispatch_failures.append({
                    "gate": "09D_SEALED_SCHEMA_CONTRACT",
                    "result": "FAIL_BLOCKING",
                    "detail": (contract_09d or {}).get("errors", ["09d_contract_not_run"]),
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

    if lease_ttl_seconds < 60:
        raise ValueError("lease_ttl_seconds_must_be_at_least_60")
    _write_json(run_dir / "PROVENANCE" / "lease_policy.json", {
        "lease_ttl_seconds": lease_ttl_seconds,
        "policy": "semantic lease TTL is caller-derived from provider timeout plus safety margin",
    })

    ledger_path = run_dir / "STATE" / "ledger.sqlite"
    ledger = Ledger(ledger_path)
    completed = False
    try:
        primary_candidates: List[AssertionCandidate] = []
        blind_candidates: List[AssertionCandidate] = []
        worker_receipts: List[Dict[str, Any]] = []
        risks = {u.source_unit_id: classify_source_unit(u) for u in units}
        _write_json(run_dir / "SOURCE" / "risk_classification.json", risks)

        tasks: list[tuple[SourceUnit, str]] = []
        for unit in units:
            for role in ("PRIMARY", "BLIND_RECALL"):
                work_id = _work_id(role, unit.source_unit_id)
                if ledger.get_work(work_id) is None:
                    ledger.register_work({
                        "work_id": work_id,
                        "work_type": role,
                        "source_unit_id": unit.source_unit_id,
                        "priority": risks[unit.source_unit_id]["priority"],
                        "source_class": risks[unit.source_unit_id]["source_class"],
                    })
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
                if resolved_schedule == "PHASED" and provider_schedule.upper() == "AUTO"
                else "explicit operator schedule" if provider_schedule.upper() != "AUTO"
                else "providers can share parallel dispatch without cross-model local residency thrash"
            ),
        })

        if resolved_schedule == "PHASED":
            primary_candidates, receipts = _dispatch_role(
                ledger_path, run_dir / "staging", primary_provider, units, "PRIMARY", risks,
                primary_limit, lease_ttl_seconds,
            )
            worker_receipts.extend(receipts)
            blind_candidates, receipts = _dispatch_role(
                ledger_path, run_dir / "staging", blind_provider, units, "BLIND_RECALL", risks,
                blind_limit, lease_ttl_seconds,
            )
            worker_receipts.extend(receipts)
        else:
            with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="hermes-worker") as pool:
                future_map = {}
                for unit, role in tasks:
                    provider = primary_provider if role == "PRIMARY" else blind_provider
                    future = pool.submit(
                        _execute_semantic_work,
                        ledger_path,
                        run_dir / "staging",
                        provider,
                        unit,
                        role,
                        str(risks[unit.source_unit_id]["source_class"]),
                        2,
                        lease_ttl_seconds,
                    )
                    future_map[future] = role
                try:
                    for future in as_completed(future_map):
                        role = future_map[future]
                        row_candidates, receipt = future.result()
                        if role == "PRIMARY":
                            primary_candidates.extend(row_candidates)
                        else:
                            blind_candidates.extend(row_candidates)
                        worker_receipts.append(receipt)
                except Exception:
                    for future in future_map:
                        future.cancel()
                    raise

        union = deterministic_union(primary_candidates, blind_candidates)
        families = build_evidence_families(union)
        specialists = run_deterministic_specialists(families, union, units)
        routes = route_families(families, specialists)
        precision = precision_review(union, units)
        cold = deterministic_cold_audit(union, units, rate=cold_audit_rate)
        semantic_cold = None
        if cold_audit_provider is not None and cold_audit_provider.is_empirical_semantic_provider():
            semantic_cold = run_semantic_cold_audit(
                cold_audit_provider,
                union,
                units,
                rate=cold_audit_rate,
                run_id=run_id,
                primary_family=primary_provider.identity().underlying_family,
                blind_family=blind_provider.identity().underlying_family,
                concurrency=max(1, cold_concurrency),
            )

        numerics = [item for unit in units for item in numeric_inventory(unit)]
        qualifiers = [item for unit in units for item in qualifier_inventory(unit)]
        relationships = [item for unit in units for item in relationship_inventory(unit)]

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
        _write_jsonl(
            run_dir / "STATE" / "event_history.jsonl",
            [dict(r) for r in ledger.db.execute("SELECT * FROM events ORDER BY seq")],
        )
        _write_tsv(
            run_dir / "STATE" / "lease_history.tsv",
            [dict(r) for r in ledger.db.execute("SELECT * FROM leases ORDER BY issued_at")],
        )
        _write_tsv(
            run_dir / "STATE" / "commit_history.tsv",
            [dict(r) for r in ledger.db.execute("SELECT * FROM commits ORDER BY committed_at")],
        )

        integrity = _candidate_integrity(union, units)
        semantic_empirical = (
            primary_provider.is_empirical_semantic_provider()
            and blind_provider.is_empirical_semantic_provider()
        )
        registry = load_registry(project_root / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json")
        benchmark_version = registry.get("benchmark_version", "UNKNOWN")

        def role_certified(provider: SemanticProvider | None, role: str) -> bool:
            if provider is None:
                return False
            identity = provider.identity()
            for unit in units:
                risk = risks[unit.source_unit_id]
                key = certification_key(
                    identity.provider,
                    identity.model_alias,
                    role,
                    str(risk["work_class"]),
                    str(risk["source_class"]),
                    benchmark_version,
                )
                if not is_certified(registry, key):
                    return False
            return True

        primary_cert = role_certified(primary_provider, "PRIMARY")
        blind_cert = role_certified(blind_provider, "BLIND_RECALL")
        cold_cert = role_certified(cold_audit_provider, "COLD_AUDIT")
        independent = primary_provider.identity().underlying_family != blind_provider.identity().underlying_family
        unresolved = [r for r in routes if r["action"] != "LOCAL_PRECISION_COMPLETE"]
        table_visual_unresolved = [
            r for r in routes if any(x.startswith(("TABLE_BINDING", "IMAGE_AVAILABLE")) for x in r["unresolved_flags"])
        ]
        cross_unresolved = [r for r in routes if any(x.startswith("CROSS_PAGE") for x in r["unresolved_flags"])]
        numeric_unresolved = [r for r in routes if any(x.startswith("UNBOUND_NUMERIC") for x in r["unresolved_flags"])]
        qualifier_unresolved = [r for r in routes if any("QUALIFIER_NOT_PRESERVED" in x for x in r["unresolved_flags"])]
        relationship_unresolved = [r for r in routes if any("DIRECTION_CUE_LOST" in x for x in r["unresolved_flags"])]

        if database_09d is not None:
            target_verified = bool(contract_09d and contract_09d.get("ok"))
            if external_semantic:
                target_verified = target_verified and bool(contract_09d.get("target_identity_verified"))
            gate_09d = Gate(
                "09D_READONLY_BOUNDARY",
                GateResult.PASS.value if target_verified else GateResult.FAIL_BLOCKING.value,
                "sealed schema/witness contract verified before provider dispatch; mode=ro&immutable=1; automatic insert/promotion/selection disabled",
            )
        else:
            gate_09d = Gate("09D_READONLY_BOUNDARY", GateResult.NOT_APPLICABLE.value, "No 09D database supplied to this run")

        semantic_provider_gate = Gate(
            "SEMANTIC_PROVIDER_CERTIFICATION",
            GateResult.PASS.value if semantic_empirical and primary_cert and blind_cert else GateResult.BLOCKED_EXTERNAL.value,
            "Both primary and blind roles require empirically certified semantic providers; fixture/unbenchmarked providers cannot satisfy this gate.",
        )
        independence_gate = Gate(
            "INDEPENDENCE",
            GateResult.PASS.value if independent else (
                GateResult.BLOCKED_EXTERNAL.value if not semantic_empirical else GateResult.FAIL_REVIEW_REQUIRED.value
            ),
            f"primary_family={primary_provider.identity().underlying_family};blind_family={blind_provider.identity().underlying_family}",
        )
        if not semantic_empirical:
            cold_gate = Gate(
                "COLD_AUDIT_POLICY",
                GateResult.BLOCKED_EXTERNAL.value,
                "Deterministic cold-audit mechanics executed; independent semantic cold-audit model remains required for empirical frontier readiness.",
            )
        elif semantic_cold is None:
            cold_gate = Gate(
                "COLD_AUDIT_POLICY",
                GateResult.BLOCKED_EXTERNAL.value,
                "Real providers ran but no independent semantic cold-audit provider was configured for this run.",
            )
        elif semantic_cold["status"] == "FAIL_INDEPENDENCE":
            cold_gate = Gate(
                "COLD_AUDIT_POLICY",
                GateResult.FAIL_REVIEW_REQUIRED.value,
                f"Semantic cold audit ran but auditor family '{semantic_cold['auditor_identity']['underlying_family']}' is not independent of primary/blind families.",
            )
        elif semantic_cold["status"] == "PASS" and not cold_cert:
            cold_gate = Gate(
                "COLD_AUDIT_POLICY",
                GateResult.BLOCKED_EXTERNAL.value,
                f"Independent semantic cold audit ran cleanly, but auditor role {semantic_cold['auditor_identity']['provider']}|{semantic_cold['auditor_identity']['model_alias']} is not certified for this benchmark/source-risk scope.",
            )
        elif semantic_cold["status"] == "PASS":
            cold_gate = Gate(
                "COLD_AUDIT_POLICY",
                GateResult.PASS.value,
                f"Certified independent semantic cold audit: {semantic_cold['audited_count']} sampled candidates, zero disagreements/errors.",
            )
        else:
            cold_gate = Gate(
                "COLD_AUDIT_POLICY",
                GateResult.FAIL_REVIEW_REQUIRED.value,
                f"Independent semantic cold audit produced {semantic_cold['disagreement_count']} disagreements and {semantic_cold['error_count']} errors over {semantic_cold['audited_count']} candidates.",
                bounded_queue="REVIEW/cold_audit_semantic.json",
            )

        def bounded(name: str, rows: list, path: str) -> Gate:
            return Gate(
                name,
                GateResult.FAIL_REVIEW_REQUIRED.value if rows else GateResult.PASS.value,
                f"unresolved_count={len(rows)}",
                bounded_queue=path if rows else None,
            )

        gates = [
            Gate("SOURCE_AUTHORITY", GateResult.PASS.value if units else GateResult.FAIL_BLOCKING.value, f"source_units={len(units)}"),
            Gate("SOURCE_HASH", source_hash_result, source_hash_detail),
            Gate("BUILD_INTEGRITY", build_check["result"], ";".join(build_check.get("errors", [])) or "current build matches immutable certified manifest"),
            Gate("RUNTIME_LOCK", runtime_check["result"], ";".join(runtime_check.get("errors", [])) or "runtime matches lock"),
            Gate("SCHEMA", GateResult.PASS.value if integrity["schema"] else GateResult.FAIL_BLOCKING.value),
            Gate("PROVENANCE", GateResult.PASS.value if integrity["provenance"] else GateResult.FAIL_BLOCKING.value),
            Gate("STABLE_SOURCE_IDENTITY", GateResult.PASS.value if integrity["stable_identity"] else GateResult.FAIL_BLOCKING.value),
            Gate("EVIDENCE_SPANS", GateResult.PASS.value if integrity["spans"] else GateResult.FAIL_BLOCKING.value),
            Gate("EVIDENCE_HASHES", GateResult.PASS.value if integrity["hashes"] else GateResult.FAIL_BLOCKING.value),
            Gate("LINEAGE", GateResult.PASS.value if integrity["lineage"] else GateResult.FAIL_BLOCKING.value),
            Gate("LEDGER_INTEGRITY", GateResult.PASS.value if snapshot["event_chain_valid"] else GateResult.FAIL_BLOCKING.value),
            Gate("STATE_RECONCILIATION", GateResult.PASS.value if snapshot["state_reconciliation_valid"] else GateResult.FAIL_BLOCKING.value),
            Gate("CAS_CURRENT_STATE", GateResult.PASS.value if all(w["state"] == "ACCEPTED" for w in snapshot["work_items"]) else GateResult.FAIL_BLOCKING.value),
            Gate("BLINDNESS", GateResult.PASS.value, "Blind request constructed by positive allowlist; behavioral mutation suite is the regression proof."),
            independence_gate,
            Gate("PRIMARY_PASS", GateResult.PASS.value if primary_candidates else GateResult.FAIL_REVIEW_REQUIRED.value, f"candidate_count={len(primary_candidates)}"),
            Gate("BLIND_RECALL_PASS", GateResult.PASS.value if blind_candidates else GateResult.FAIL_REVIEW_REQUIRED.value, f"candidate_count={len(blind_candidates)}"),
            semantic_provider_gate,
            bounded("NUMERIC_CONTROL", numeric_unresolved, "REVIEW/routes.jsonl"),
            bounded("QUALIFIER_CONTROL", qualifier_unresolved, "REVIEW/routes.jsonl"),
            bounded("RELATIONSHIP_CONTROL", relationship_unresolved, "REVIEW/routes.jsonl"),
            bounded("TABLE_VISUAL_CONTROL", table_visual_unresolved, "REVIEW/routes.jsonl"),
            bounded("CROSS_PAGE_CONTROL", cross_unresolved, "REVIEW/routes.jsonl"),
            Gate("PRECISION_REVIEW", GateResult.PASS.value if all(x["result"] == "PASS" for x in precision) else GateResult.FAIL_BLOCKING.value),
            cold_gate,
            Gate("SEMANTIC_RECEIPTS", GateResult.PASS.value if len(worker_receipts) == len(units) * 2 else GateResult.FAIL_BLOCKING.value, f"receipt_count={len(worker_receipts)}"),
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
            "lease_ttl_seconds": lease_ttl_seconds,
            "provider_schedule": resolved_schedule,
            "primary_concurrency": primary_limit,
            "blind_concurrency": blind_limit,
            "cold_concurrency": max(1, cold_concurrency),
            "provider_telemetry": _provider_telemetry(worker_receipts),
            "source_unit_count": len(units),
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
            "09d_contract_verified": bool(contract_09d and contract_09d.get("target_identity_verified")),
            "claim_boundary": (
                "Real semantic providers executed, but precision/recall is not certified until scored against frozen source-first gold."
                if semantic_empirical else
                "Offline fixture execution proves mechanics only; fixture output is not empirical semantic evidence."
            ),
        }
        _write_json(run_dir / "RUN_SUMMARY.json", summary)
        _atomic_replace_text(
            run_dir / "README_START_HERE.md",
            f"# Hermes extraction run {run_id}\n\nMode: `{mode}`\n\n"
            "This package contains source units, noncanonical candidates, receipts, durable state, reviews, and validation.\n\n"
            "Candidate extraction is not canonical truth. 09D comparison is read-only review evidence and cannot promote/select. "
            "Inspect `VALIDATION/readiness.json` for mechanically derived status.\n",
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
        final_name = (
            "FRONTIER_REVIEW_READY_" if final_readiness["status"] == "FRONTIER_REVIEW_READY"
            else "READY_FOR_PROVIDER_" if final_readiness["status"] == "READY_FOR_PROVIDER"
            else "REVIEW_PACKAGE_"
        ) + run_id + ".zip"
        final_zip = output_root / final_name
        package = build_offline_package(run_dir, final_zip, package_status=final_readiness["status"])
        _write_json(run_dir / "VALIDATION" / "external_package_receipt.json", package)
        completed = True
        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "package": package,
            "readiness": final_readiness,
            "summary": summary,
        }
    except Exception as exc:
        failure = {
            "run_id": run_id,
            "status": "FAILED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "completed": False,
            "automatic_promotion_allowed": False,
        }
        try:
            snapshot = ledger.snapshot()
            failure["event_chain_valid"] = snapshot.get("event_chain_valid")
            failure["state_reconciliation_valid"] = snapshot.get("state_reconciliation_valid")
        except Exception as snapshot_exc:
            failure["snapshot_error"] = f"{type(snapshot_exc).__name__}:{snapshot_exc}"
        _write_json(run_dir / "VALIDATION" / "run_failure.json", failure)
        raise
    finally:
        ledger.close()
        if not completed:
            # An incomplete run is deliberately left unpackaged. Its durable
            # ledger + failure record remain available for forensic recovery.
            pass
