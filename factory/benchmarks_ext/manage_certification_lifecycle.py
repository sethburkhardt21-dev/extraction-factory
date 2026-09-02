"""Governed administrative demotion for an existing semantic role certificate.

This tool can only move certification authority downward: SUSPENDED, DEMOTED,
EXPIRED, or RETIRED. It cannot promote a role into a certified state. Promotion
and reactivation remain exclusive to source-bound benchmark recomputation through
certify_roles.py.

Dry-run is the default. `--apply` requires `--expect-status` as a compare-and-set
assertion so a stale operator command cannot overwrite a newer registry state.
Lifecycle events are appended to a top-level protected audit log so later
recertification cannot erase administrative history. Every fingerprintable
benchmark evidence set deactivated by a lifecycle action is also recorded so the
same stale evidence cannot silently restore authority. RETIRED additionally
creates a terminal certification-key tombstone enforced by runtime.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from hermes_factory.certification_lifecycle import DOWNWARD_TARGETS, apply_downward_transition  # noqa: E402
from hermes_factory.certification_state import (  # noqa: E402
    aggregate_role_status,
    parse_certification_key,
    record_evidence_invalidation,
)
from hermes_factory.model_registry import ALLOWED, CERTIFIED_STATUSES, certification_entry  # noqa: E402

DEFAULT_REGISTRY = FACTORY_ROOT / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json"


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
    if not isinstance(certs, dict):
        raise ValueError("registry_certifications_not_object")
    certs[key] = updated_entry

    event["provider"] = provider
    event["model_alias"] = model
    event["role"] = role
    event["work_class"] = work_class
    event["source_class"] = source_class
    event["benchmark_version"] = benchmark_version
    event["runtime_authority_after_transition"] = updated_entry["status"] in CERTIFIED_STATUSES

    # Fingerprint the certificate evidence being deactivated. This is deliberately
    # based on benchmark/source/model-authority evidence, not time. Reusing the
    # exact same evidence through certify_roles must not undo a safety action.
    record_evidence_invalidation(
        proposed,
        certification_key=key,
        entry=entry,
        event=event,
    )

    audit = proposed.setdefault("certification_lifecycle_events", [])
    if not isinstance(audit, list):
        raise ValueError("certification_lifecycle_events_not_array")
    if any(isinstance(row, dict) and row.get("event_id") == event["event_id"] for row in audit):
        raise ValueError(f"duplicate_lifecycle_event_id:{event['event_id']}")
    audit.append(dict(event))

    retired = proposed.setdefault("retired_certification_keys", [])
    if not isinstance(retired, list):
        raise ValueError("retired_certification_keys_not_array")
    if updated_entry["status"] == "RETIRED" and key not in retired:
        retired.append(key)
    retired.sort()

    role_status = proposed.setdefault("role_status", {})
    if not isinstance(role_status, dict):
        raise ValueError("registry_role_status_not_object")
    role_status[f"{role}_{work_class}"] = aggregate_role_status(
        certs, role=role, work_class=work_class, benchmark_version=benchmark_version
    )
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
        "schema_version": "hermes-certification-lifecycle-transition-1.2",
        "certification_key": args.key,
        "from_status": event["from_status"],
        "to_status": event["to_status"],
        "event_id": event["event_id"],
        "reason": event["reason"],
        "incident_ref": event.get("incident_ref"),
        "runtime_authority_after_transition": event["runtime_authority_after_transition"],
        "invalidated_evidence_sha256": event.get("invalidated_evidence_sha256"),
        "retirement_tombstone": args.key in proposed.get("retired_certification_keys", []),
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
