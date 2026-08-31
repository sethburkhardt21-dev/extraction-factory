"""Apply the pack's provisional certification rules to measured benchmark
scores and write honest MODEL_CERTIFICATION_REGISTRY entries.

Decision logic (BENCHMARKS/BENCHMARK_V0_1/CERTIFICATION_RULES.md):

  CERT-W2-S1 (PRIMARY):   recall>=.94  precision>=.93  evidence_fidelity=1.00
                          qualifier_preservation>=.95  E4=0  E3<=.5%
  CERT-BLIND-RECALL:      omission_recovery>=.50  useful_new_precision>=.70  E4=0

E3 is NOT mechanically measurable and E4 is measured only by mechanical
proxy (cue injection), so a role that clears every MEASURED threshold is
granted at most CERTIFIED_WITH_LIMITS, with the limits enumerated in the
registry entry. Any measured threshold miss -> REJECTED (metrics recorded).
Roles never benchmarked (W3/S3 table-visual, cross-page) stay UNBENCHMARKED —
this script refuses to touch them.

Registry changes alter the certified build surface: re-run
`python -m hermes_factory certify-build --rerun-tests` afterwards.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

FACTORY_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_VERSION = "MACHINES_P0299_P0301_SOURCE_FIRST_v1"

STANDING_LIMITS = [
    "E3 (clinically material distortion) not measured — requires clinical/frontier review",
    "E4 measured by mechanical cue-injection proxy only, not semantic review",
    "benchmark corpus = 8 source units from one source (Machines/Dorsch p299-301), W2/S1 text stratum only",
    "W3/S3 table, figure/visual and cross-page semantic binding NOT benchmarked — those units remain review-queued",
    "gold reference is AI-authored source-first, label MECHANICALLY_CHECKED",
]


def _value(metrics: dict, key: str):
    node = metrics.get(key)
    if isinstance(node, dict):
        return node.get("value")
    return None


def decide_primary(metrics: dict) -> tuple[str, list[str]]:
    checks = {
        "recall>=0.94": (_value(metrics, "semantic_unit_recall"), 0.94),
        "precision>=0.93": (_value(metrics, "semantic_unit_precision"), 0.93),
        "evidence_fidelity==1.00": (_value(metrics, "evidence_fidelity_exact_substring"), 1.0),
        "qualifier_preservation>=0.95": (_value(metrics, "qualifier_preservation"), 0.95),
        "e4_proxy==0": (1.0 - (_value(metrics, "e4_mechanical_proxy_cue_injection") or 0.0), 1.0),
    }
    failures = []
    for name, (measured, floor) in checks.items():
        if measured is None:
            if "qualifier" in name:
                continue  # 'where applicable' — no applicable rows
            failures.append(f"{name}: NOT_MEASURED")
        elif measured + 1e-9 < floor:
            failures.append(f"{name}: measured {measured:.4f}")
    return ("CERTIFIED_WITH_LIMITS" if not failures else "REJECTED"), failures


def decide_blind(metrics: dict) -> tuple[str, list[str]]:
    checks = {
        "omission_recovery>=0.50": (_value(metrics, "blind_omission_recovery"), 0.50),
        "useful_new_precision>=0.70": (_value(metrics, "blind_useful_new_candidate_precision"), 0.70),
        "e4_proxy==0": (1.0 - (_value(metrics, "e4_mechanical_proxy_cue_injection") or 0.0), 1.0),
    }
    failures = []
    for name, (measured, floor) in checks.items():
        if measured is None:
            failures.append(f"{name}: NOT_MEASURED")
        elif measured + 1e-9 < floor:
            failures.append(f"{name}: measured {measured:.4f}")
    return ("CERTIFIED_WITH_LIMITS" if not failures else "REJECTED"), failures


def build_entry(score: dict, provider: str, role: str, status: str, failures: list[str]) -> dict:
    metrics = score["metrics"]
    compact = {}
    for key, node in metrics.items():
        if isinstance(node, dict) and "value" in node:
            compact[key] = node
    return {
        "status": status,
        "decided_at_epoch": round(time.time(), 1),
        "decision_rule": "CERT-W2-S1" if role == "PRIMARY" else "CERT-BLIND-RECALL",
        "measured_metrics": compact,
        "threshold_failures": failures,
        "limits": STANDING_LIMITS,
        "gold_reference_sha256": score["reference_sha256"],
        "gold_label": score["gold_label"],
        "units_in_scope": score["units_in_scope"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="certify_roles")
    parser.add_argument("--primary-score", required=True)
    parser.add_argument("--blind-score", required=True)
    parser.add_argument("--primary-provider", default="CLAUDE")
    parser.add_argument("--blind-provider", default="OLLAMA")
    parser.add_argument("--registry", default=str(FACTORY_ROOT / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json"))
    parser.add_argument("--apply", action="store_true", help="write the registry (default: dry run)")
    args = parser.parse_args(argv)

    primary = json.loads(Path(args.primary_score).read_text(encoding="utf-8"))
    blind = json.loads(Path(args.blind_score).read_text(encoding="utf-8"))
    for score in (primary, blind):
        if score["benchmark_version"] != BENCHMARK_VERSION:
            print(f"benchmark version mismatch: {score['benchmark_version']}", file=sys.stderr)
            return 2

    p_status, p_fail = decide_primary(primary["metrics"])
    b_status, b_fail = decide_blind(blind["metrics"])

    registry_path = Path(args.registry)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["benchmark_version"] = BENCHMARK_VERSION
    certs = registry.setdefault("certifications", {})

    def key(provider: str, model: str, role: str) -> str:
        return "|".join([provider, model, role, "W2", "S1", BENCHMARK_VERSION])

    changes = {
        key(args.primary_provider, primary["model"], "PRIMARY"):
            build_entry(primary, args.primary_provider, "PRIMARY", p_status, p_fail),
        key(args.blind_provider, blind["model"], "BLIND_RECALL"):
            build_entry(blind, args.blind_provider, "BLIND_RECALL", b_status, b_fail),
    }
    certs.update(changes)
    role_status = registry.setdefault("role_status", {})
    role_status["PRIMARY_W2"] = p_status
    role_status["BLIND_RECALL_W2"] = b_status
    registry["claim_boundary"] = (
        "Certifications here are role/W-class/S-class/benchmark specific, carry enumerated limits, "
        "and cover the W2/S1 text stratum only. W3/S3 table-visual and cross-page semantic binding, "
        "PRECISION_REVIEW and COLD_AUDIT roles remain UNBENCHMARKED. Provider self-claims are not authoritative."
    )

    print(json.dumps({
        "primary": {"model": primary["model"], "status": p_status, "failures": p_fail},
        "blind": {"model": blind["model"], "status": b_status, "failures": b_fail},
        "registry_keys_written": sorted(changes),
        "applied": bool(args.apply),
    }, indent=2))
    if args.apply:
        registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")
        print(f"registry updated: {registry_path}")
        print("NOTE: registry is inside the certified-build surface — re-run "
              "`python -m hermes_factory certify-build --rerun-tests` to attach a new certification.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
