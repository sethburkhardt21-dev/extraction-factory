"""Post-projection guard for numeric context dimensions relevant to 09D.

The semantic comparator deliberately avoids inventing numeric bindings. This
stage adds a narrower downstream protection for candidates that *do* carry
structured target numerics: other explicit temperature/pressure dimensions in
the proposition are treated as context. A target value cannot remain loader-
ready when that context conflicts with, or is missing from, the selected 09D
comparison row.

The original comparison state is never overwritten. The guard emits a separate
projection-effective state and may downgrade only the Motion-2 loader
disposition. It never writes to 09D.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from stages_ext.compare_09d import _normalize_unit, _numbers_with_units, _numeric_relation  # noqa: E402

SAFE_CONTEXT_UNITS = {"degc", "mmhg", "cmh2o", "torr"}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def _structured_target_units(row: dict[str, Any]) -> set[str]:
    out = set()
    for item in row.get("numeric_values") or []:
        if isinstance(item, dict) and item.get("value_literal") is not None:
            unit = _normalize_unit(str(item.get("unit_literal") or ""))
            if unit:
                out.add(unit)
    return out


def _by_unit(values: set[tuple[str, str]]) -> dict[str, set[tuple[str, str]]]:
    out: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for value, unit in values:
        if unit:
            out[unit].add((value, unit))
    return out


def evaluate_context(row: dict[str, Any], comparison: dict[str, Any]) -> dict[str, Any]:
    target_units = _structured_target_units(row)
    if not target_units:
        return {
            "factory_candidate_id": row.get("factory_candidate_id"),
            "result": "NOT_EVALUATED_NO_STRUCTURED_TARGET",
            "effective_state": row.get("09d_comparison_state"),
            "context_dimensions": [],
            "review_required": False,
        }

    proposition_numbers = _numbers_with_units(str(row.get("proposition") or ""))
    candidate_context = {
        pair for pair in proposition_numbers
        if pair[1] in SAFE_CONTEXT_UNITS and pair[1] not in target_units
    }

    top_matches = comparison.get("top_matches") or []
    best = top_matches[0] if top_matches else None
    if not best:
        return {
            "factory_candidate_id": row.get("factory_candidate_id"),
            "result": "NOT_EVALUATED_NO_09D_MATCH",
            "effective_state": row.get("09d_comparison_state"),
            "context_dimensions": [],
            "review_required": False,
        }

    row_numbers = _numbers_with_units(str(best.get("value_text") or ""))
    row_context = {
        pair for pair in row_numbers
        if pair[1] in SAFE_CONTEXT_UNITS and pair[1] not in target_units
    }
    cand_by_unit = _by_unit(candidate_context)
    row_by_unit = _by_unit(row_context)
    units = sorted(set(cand_by_unit) | set(row_by_unit))

    dimensions = []
    review_required = False
    hard_context_difference = False
    for unit in units:
        cvals = cand_by_unit.get(unit, set())
        rvals = row_by_unit.get(unit, set())
        if not cvals or not rvals:
            relation = "SCOPE_MISMATCH"
            detail = f"context dimension '{unit}' is explicit on only one side"
            review_required = True
            hard_context_difference = True
        else:
            relation, detail = _numeric_relation(cvals, rvals)
            if relation == "CONFLICT":
                review_required = True
                hard_context_difference = True
            elif relation in {"OVERLAP", "AMBIGUOUS", "NOT_COMPARABLE"}:
                review_required = True
        dimensions.append({
            "unit": unit,
            "relation": relation,
            "detail": detail,
            "candidate_context_values": sorted(v for v, _ in cvals),
            "09d_context_values": sorted(v for v, _ in rvals),
        })

    if not units:
        result = "PASS_NO_EXPLICIT_CONTEXT_DIMENSION"
        effective = row.get("09d_comparison_state")
    elif review_required:
        result = "REVIEW_REQUIRED"
        effective = "CONTEXT_DIFFERENCE" if hard_context_difference else "VARIANT"
    else:
        result = "PASS_CONTEXT_EQUIVALENT"
        effective = row.get("09d_comparison_state")

    return {
        "factory_candidate_id": row.get("factory_candidate_id"),
        "result": result,
        "effective_state": effective,
        "context_dimensions": dimensions,
        "review_required": review_required,
        "target_numeric_units": sorted(target_units),
        "claim_boundary": "Context guard only downgrades the projection; it does not rewrite the original 09D comparison state.",
    }


def run_guard(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    out_dir = run_dir / "09D"
    projection_path = out_dir / "motion2_candidate_projection.jsonl"
    comparison_path = out_dir / "comparison_09d.jsonl"
    summary_path = out_dir / "motion2_projection_summary.json"
    if not projection_path.exists() or not comparison_path.exists() or not summary_path.exists():
        raise RuntimeError("09d_context_guard_requires_projection_comparison_and_summary")

    rows = _read_jsonl(projection_path)
    comparisons = {
        str(x.get("candidate_id")): x for x in _read_jsonl(comparison_path) if x.get("candidate_id")
    }
    guarded_rows = []
    receipts = []
    counts: dict[str, int] = defaultdict(int)
    review_count = 0

    for row in rows:
        cid = str(row.get("factory_candidate_id") or "")
        receipt = evaluate_context(row, comparisons.get(cid) or {})
        receipts.append(receipt)
        counts[receipt["result"]] += 1
        updated = dict(row)
        updated["09d_projection_effective_state"] = receipt["effective_state"]
        updated["09d_numeric_context_guard"] = receipt["result"]
        if receipt["review_required"]:
            updated["loader_disposition"] = "REVIEW_REQUIRED"
            review_count += 1
        guarded_rows.append(updated)

    _write_jsonl_atomic(projection_path, guarded_rows)
    _write_jsonl_atomic(out_dir / "motion2_numeric_context_guard.jsonl", receipts)

    projection_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    projection_summary["numeric_context_guard"] = {
        "guard_schema_version": "09d-numeric-context-guard-1.0",
        "candidate_count": len(rows),
        "review_required_count": review_count,
        "result_counts": dict(sorted(counts.items())),
        "safe_context_units": sorted(SAFE_CONTEXT_UNITS),
    }
    if review_count and projection_summary.get("projection_status") == "SCHEMA_COMPATIBLE_NEEDS_GOVERNED_09D_LOADER":
        projection_summary["projection_status"] = "PROJECTION_REVIEW_REQUIRED"
        projection_summary.setdefault("projection_errors", []).append({
            "code": "09D_NUMERIC_CONTEXT_REVIEW_REQUIRED",
            "candidate_count": review_count,
        })
        projection_summary["projection_error_count"] = len(projection_summary.get("projection_errors", []))
    summary_path.write_text(json.dumps(projection_summary, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    guard_summary = {
        "stage": "09D_NUMERIC_CONTEXT_GUARD",
        "candidate_count": len(rows),
        "review_required_count": review_count,
        "result_counts": dict(sorted(counts.items())),
        "projection_status_after_guard": projection_summary.get("projection_status"),
        "direct_09d_insert_allowed": False,
    }
    (out_dir / "motion2_numeric_context_guard_summary.json").write_text(
        json.dumps(guard_summary, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return guard_summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="guard_09d_numeric_context")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    try:
        summary = run_guard(Path(args.run_dir))
    except Exception as exc:
        print(f"09D numeric context guard failed: {type(exc).__name__}:{exc}", file=sys.stderr)
        return 3
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
