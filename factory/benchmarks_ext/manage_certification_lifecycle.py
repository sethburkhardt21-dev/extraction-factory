"""Governed administrative demotion for an existing semantic role certificate.

This tool can only move certification authority downward: SUSPENDED, DEMOTED,
EXPIRED, or RETIRED. It cannot promote a role into a certified state. Promotion
and reactivation remain exclusive to source-bound benchmark recomputation through
certify_roles.py.

Dry-run is the default. `--apply` requires `--expect-status` as a compare-and-set
assertion so a stale operator command cannot overwrite a newer registry state.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from hermes_factory.certification_lifecycle import DOWNWARD_TARGETS, apply_downward_transition  # noqa: E402
from hermes_factory.model_registry import ALLOWED, CERTIFIED_STATUSES, certification_entry  # noqa: E402

DEFAULT_REGISTRY = FACTORY_ROOT / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json"


def parse_certification_key(key: str) -> tuple[str, str, str, str, str, str]:
    parts = str(key or "").split("|")
    if len(parts) != 6 or any(not x for x in parts):
        raise ValueError("certification_key_must_have_6_nonempty_fields")
    return tuple(parts)  # type: ignore[return-value]


def aggregate_role_status(certifications: dict, *, role: str, work_class: str, benchmark_version: str) -> str:
    statuses = []
    for key, entry in certifications.items():
        if not isinstance(entry, dict):
            continue
        try:
            _, _, key_role, key_work, _, key_benchmark = parse_certification_key(key)
        except ValueError:
            continue
        if key_role == role and key_work == work_class and key_benchmark == benchmark_version:
            status = str(entry.get("status") or "UNBENCHMARKED").upper()
            if status in ALLOWED:
                statuses.append(status)
    if "CERTIFIED" in statuses:
        return "CERTIFIED"
    if "CERTIFIED_WITH_LIMITS" in statuses:
        return "CERTIFIED_WITH_LIMITS"
    for state in (
        "SUSPENDED", "DEMOTED", "EXPIRED", "PROVISIONAL", "BENCHMARKING",
        "BLOCKED_EXTERNAL", "REJECTED", "FIXTURE_NOT_EMPIRICAL", "RETIRED", "UNBENCHMARKED",
    ):
        if state in statuses:
            return state
    return "UNBENCHMARKED"


def propose_transition(*, registry: dict, key: str, target_status: str, reason: str,
                       incident_ref: str | None = None, actor: str = "OPERATOR",
                       expected_status: str | None = None, now_epoch: float | None = None) -> tuple[dict, dict]:
    provider, model, role, work_class, source_class, benchmark_version = parse_certification_key(key)
    entry = certification_entry(registry, key)
    if entry is None:
        raise ValueError(f"certification_key_not_found:{key}")
    current = str(entry.get("status") or "UNBENCHMARKED").upper()
    if current not in ALLOWED:
        raise ValueError(f"invalid_certification_status:{current}")
    if expected_status is not None and current != str(expected_status).upper():
        raise ValueError(f"lifecycle_compare_and_set_failed:{current}!={str(expected_status).upper()}")

    updated_entry, event = apply_downward_transition(
        entry,
        certification_key=key,
        target_status=target_status,
        reason=reason,
        incident_ref=incident_ref,
        actor=actor,
        now_epoch=now_epoch,
    )
    proposed = json.loads(json.dumps(registry))
    certs = proposed.setdefault("certifications", {})
    certs[key] = updated_entry
    role_status = proposed.setdefault("role_status", {})
    role_status[f"{role}_{work_class}"] = aggregate_role_status(
        certs, role=role, work_class=work_class, benchmark_version=benchmark_version
    )
    event["provider"] = provider
    event["model_alias"] = model
    event["role"] = role
    event["work_class"] = work_class
    event["source_class"] = source_class
    event["benchmark_version"] = benchmark_version
    event["runtime_authority_after_transition"] = updated_entry["status"] in CERTIFIED_STATUSES
    return proposed, event


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="manage_certification_lifecycle")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--key", required=True, help="exact provider|model|role|W|S|benchmark certification key")
    parser.add_argument("--to", required=True, choices=sorted(DOWNWARD_TARGETS))
    parser.add_argument("--reason", required=True)
    parser.add_argument("--incident-ref")
    parser.add_argument("--actor", default="OPERATOR")
    parser.add_argument("--expect-status", choices=sorted(ALLOWED),
                        help="required with --apply; compare-and-set guard against stale lifecycle commands")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    if args.apply and not args.expect_status:
        print("refusing --apply without --expect-status compare-and-set assertion", file=sys.stderr)
        return 3

    registry_path = Path(args.registry)
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        proposed, event = propose_transition(
            registry=registry,
            key=args.key,
            target_status=args.to,
            reason=args.reason,
            incident_ref=args.incident_ref,
            actor=args.actor,
            expected_status=args.expect_status,
        )
    except (ValueError, KeyError, json.JSONDecodeError, OSError) as exc:
        print(f"certification lifecycle transition refused: {exc}", file=sys.stderr)
        return 4

    output = {
        "schema_version": "hermes-certification-lifecycle-transition-1.0",
        "certification_key": args.key,
        "from_status": event["from_status"],
        "to_status": event["to_status"],
        "event_id": event["event_id"],
        "reason": event["reason"],
        "incident_ref": event.get("incident_ref"),
        "runtime_authority_after_transition": event["runtime_authority_after_transition"],
        "applied": bool(args.apply),
        "automatic_time_expiry": "NOT_DEFINED_BY_ARCHITECTURE",
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    if args.apply:
        registry_path.write_text(json.dumps(proposed, indent=2, sort_keys=True), encoding="utf-8")
        print(f"registry updated: {registry_path}")
        print("NOTE: registry is protected production state — rerun tests and certify-build after this change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
