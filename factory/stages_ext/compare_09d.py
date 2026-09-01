"""Read-only 09D comparator with sealed-target and conflict-model alignment.

This stage is deliberately conservative. It never canonicalizes, promotes,
selects, averages, or writes. A TRUE_CONFLICT requires compatible subject,
predicate, context and units before a value/polarity disagreement is allowed.
Lexical retrieval alone can only yield an unresolved/not-comparable review lead.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from hermes_factory.contract_09d import R3_TARGET, open_immutable_readonly, verify_09d_contract  # noqa: E402
from hermes_factory.literal import NUM_RE, QUALIFIER_PATTERNS  # noqa: E402

COMPARATOR_TARGET = R3_TARGET

STOPWORDS = {
    "the", "and", "for", "are", "was", "were", "with", "that", "this", "from", "into",
    "when", "then", "than", "which", "will", "shall", "has", "have", "had", "its",
    "can", "may", "not", "but", "all", "any", "one", "two", "per", "each", "also",
    "used", "use", "using", "there", "their", "them", "they", "been", "being", "such",
    "procedure", "aliases", "value", "values", "code", "type",
}
NEGATION_RE = QUALIFIER_PATTERNS["NEGATION"]


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) >= 3 and w not in STOPWORDS}


def _normalize_number(value: str) -> str:
    cleaned = re.sub(r"\s+", "", value or "")
    try:
        d = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return cleaned
    if d == d.to_integral():
        return str(d.quantize(Decimal(1)))
    return format(d.normalize(), "f")


def _normalize_unit(unit: str | None) -> str:
    return re.sub(r"[\s·]", "", (unit or "").lower()).replace("percent", "%")


def _numbers_with_units(text: str) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for m in NUM_RE.finditer(text or ""):
        out.add((_normalize_number(m.group("value")), _normalize_unit(m.group("unit"))))
    return out


def _qualifier_cues(text: str) -> set[str]:
    return {name for name, pattern in QUALIFIER_PATTERNS.items() if pattern.search(text or "")}


def load_carrier(db_path: Path) -> list[dict]:
    """Load every carrier row, including rows with NULL value_text.

    The earlier bridge dropped value-less rows, which could hide useful governed
    subject/predicate identity evidence. They now remain retrieval candidates;
    numeric/qualifier checks simply have no value text to inspect.
    """
    conn = open_immutable_readonly(db_path)
    try:
        rows = conn.execute(
            "SELECT candidate_id, subject_entity_id, predicate_code, value_text, fact_family "
            "FROM source_assertion_candidate"
        ).fetchall()
        names: dict[str, set[str]] = defaultdict(set)
        try:
            for canonical_id, name_text, normalized_name in conn.execute(
                "SELECT canonical_id, name_text, normalized_name FROM entity_name WHERE is_searchable=1"
            ):
                names[str(canonical_id)].update(_tokens(name_text or ""))
                names[str(canonical_id)].update(_tokens(normalized_name or ""))
        except Exception:
            # Entity-name enrichment is optional for retrieval. Missing/broken
            # enrichment reduces comparability; it never fabricates identity.
            pass
    finally:
        conn.close()

    carrier: list[dict] = []
    for cid, subject, predicate, value, fact_family in rows:
        predicate_text = (predicate or "").replace(".", " ").replace("_", " ")
        value_text = value or ""
        subject_tokens = set(names.get(str(subject), set()))
        predicate_tokens = _tokens(predicate_text)
        value_tokens = _tokens(value_text)
        carrier.append({
            "carrier_candidate_id": cid,
            "subject_entity_id": subject,
            "predicate_code": predicate,
            "fact_family": fact_family,
            "value_text": value,
            "subject_tokens": subject_tokens,
            "predicate_tokens": predicate_tokens,
            "value_tokens": value_tokens,
            "tokens": subject_tokens | predicate_tokens | value_tokens,
            "numbers": _numbers_with_units(value_text),
            "qualifier_cues": _qualifier_cues(value_text),
            "negated": bool(NEGATION_RE.search(value_text)),
        })
    return carrier


def build_index(carrier: list[dict]) -> dict[str, list[int]]:
    index: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(carrier):
        for token in row["tokens"]:
            index[token].append(i)
    return index


def _compatibility(candidate_tokens: set[str], row_tokens: set[str]) -> tuple[bool, float]:
    if not candidate_tokens or not row_tokens:
        return False, 0.0
    shared = len(candidate_tokens & row_tokens)
    ratio = shared / max(1, len(candidate_tokens))
    return (shared >= 1 and ratio >= 0.50), ratio


def _predicate_compatibility(candidate_tokens: set[str], row_tokens: set[str]) -> tuple[bool, float]:
    if not candidate_tokens or not row_tokens:
        return False, 0.0
    shared = len(candidate_tokens & row_tokens)
    union = len(candidate_tokens | row_tokens) or 1
    jaccard = shared / union
    return (shared >= 1 and jaccard >= 0.60), jaccard


def _fact_family_compatible(candidate: dict, row: dict) -> tuple[bool, str]:
    metadata = candidate.get("metadata") or {}
    cand_family = metadata.get("fact_family") or metadata.get("fact_family_hint")
    row_family = row.get("fact_family")
    if not cand_family or not row_family:
        return True, "UNKNOWN_OR_UNSPECIFIED"
    return str(cand_family).strip().lower() == str(row_family).strip().lower(), "EXPLICIT"


def _context_compatible(candidate: dict, row: dict) -> tuple[bool, set[str], set[str]]:
    proposition = candidate.get("proposition") or ""
    cand_cues = _qualifier_cues(proposition)
    row_cues = set(row.get("qualifier_cues") or set())
    # A detected qualifier on only one side is a context difference, not proof of
    # contradiction. Equal empty sets are compatible but carry no extra evidence.
    return cand_cues == row_cues, cand_cues, row_cues


def _legacy_and_conflict_state(
    *,
    target_trusted: bool,
    structured_comparable: bool,
    context_compatible: bool,
    numeric_conflict: bool,
    polarity_conflict: bool,
    best_score: float,
    near_subject_count: int,
    exact_numeric_match: bool,
) -> tuple[str, str]:
    if not target_trusted:
        return ("IDENTITY_UNCERTAIN" if near_subject_count > 1 else "VARIANT", "UNRESOLVED")
    if structured_comparable and context_compatible and (numeric_conflict or polarity_conflict):
        return "CONTRADICTION", "TRUE_CONFLICT"
    if structured_comparable and not context_compatible:
        return "CONTEXT_DIFFERENCE", "CONTEXTUAL_VARIANT"
    if not structured_comparable:
        return ("IDENTITY_UNCERTAIN" if near_subject_count > 1 else "VARIANT", "UNRESOLVED")
    if best_score >= 0.80 and exact_numeric_match:
        return "SUPPORT", "DUPLICATE_EQUIVALENT"
    if best_score >= 0.75:
        return "SUPPORT", "UNRESOLVED"
    return "VARIANT", "UNRESOLVED"


def classify(candidate: dict, carrier: list[dict], index: dict[str, list[int]], *, target_trusted: bool = True) -> dict:
    proposition = candidate.get("proposition") or ""
    tokens = _tokens(proposition)
    cand_subject_tokens = _tokens(candidate.get("subject") or "")
    cand_predicate_tokens = _tokens(candidate.get("predicate") or "")
    numbers = _numbers_with_units(proposition)
    negated = candidate.get("polarity") == "NEGATIVE" or bool(NEGATION_RE.search(proposition))

    counts: dict[int, int] = defaultdict(int)
    for token in tokens:
        for i in index.get(token, ()):
            counts[i] += 1
    min_shared = 1 if len(tokens) < 4 else 2
    scored: list[tuple[float, float, bool, bool, float, float, int]] = []
    for i, shared in counts.items():
        if shared < min_shared:
            continue
        row = carrier[i]
        union_size = len(tokens | row["tokens"]) or 1
        jaccard = shared / union_size
        containment = shared / (len(row["tokens"]) or 1)
        subj_ok, subj_score = _compatibility(cand_subject_tokens, row.get("subject_tokens", set()))
        pred_ok, pred_score = _predicate_compatibility(cand_predicate_tokens, row.get("predicate_tokens", set()))
        family_ok, _ = _fact_family_compatible(candidate, row)
        if not family_ok:
            subj_ok = False
            pred_ok = False
        lexical = max(jaccard, containment * 0.9)
        structured_bonus = (0.10 if subj_ok else 0.0) + (0.10 if pred_ok else 0.0)
        scored.append((min(1.0, lexical + structured_bonus), lexical, subj_ok, pred_ok, subj_score, pred_score, i))
    scored.sort(reverse=True)
    top = scored[:5]
    reasons: list[str] = []

    if not top or top[0][0] < 0.30:
        state = "MISSING_IN_09D"
        conflict_outcome = "NOT_COMPARABLE"
        reasons.append("no carrier row reaches conservative retrieval floor; no identity/conflict conclusion is permitted")
    else:
        best_score, lexical_score, subj_ok, pred_ok, subj_score, pred_score, best_i = top[0]
        best = carrier[best_i]
        near = [t for t in top if best_score - t[0] <= 0.05]
        distinct_subjects = {carrier[t[-1]]["subject_entity_id"] for t in near}
        structured_comparable = subj_ok and pred_ok
        context_ok, cand_quals, row_quals = _context_compatible(candidate, best)

        polarity_conflict = bool(
            structured_comparable and context_ok and negated != best["negated"] and lexical_score >= 0.50
        )
        numeric_conflict = False
        exact_numeric_match = not numbers
        if structured_comparable and context_ok and numbers and best["numbers"]:
            same_unit_pairs = [
                (value, bvalue, unit)
                for value, unit in numbers
                for bvalue, bunit in best["numbers"]
                if unit and unit == bunit
            ]
            if same_unit_pairs:
                numeric_conflict = all(value != bvalue for value, bvalue, _ in same_unit_pairs)
                exact_numeric_match = any(value == bvalue for value, bvalue, _ in same_unit_pairs)
                if numeric_conflict:
                    reasons.append(
                        "numeric disagreement only after subject+predicate+context and unit compatibility were established: "
                        + ", ".join(f"{v} vs {bv} {u}" for v, bv, u in same_unit_pairs[:4])
                    )
            else:
                # Unit/dimension mismatch is not a conflict.
                exact_numeric_match = False
                context_ok = False
                reasons.append("numeric values are not dimensionally comparable because no normalized unit matches")

        state, conflict_outcome = _legacy_and_conflict_state(
            target_trusted=target_trusted,
            structured_comparable=structured_comparable,
            context_compatible=context_ok,
            numeric_conflict=numeric_conflict,
            polarity_conflict=polarity_conflict,
            best_score=best_score,
            near_subject_count=len(distinct_subjects),
            exact_numeric_match=exact_numeric_match,
        )
        if not target_trusted:
            reasons.append("target identity was not cryptographically verified; authoritative support/conflict conclusions are suppressed")
        elif polarity_conflict:
            reasons.append("polarity differs after subject+predicate+context compatibility was established")
        elif structured_comparable and not context_ok:
            reasons.append(f"context/qualifier cues differ: candidate={sorted(cand_quals)} 09D={sorted(row_quals)}")
        elif not structured_comparable:
            reasons.append(
                f"retrieval lead only; subject compatibility={subj_ok} ({subj_score:.2f}), "
                f"predicate compatibility={pred_ok} ({pred_score:.2f})"
            )
        elif state == "SUPPORT":
            reasons.append("subject+predicate compatible and no governed conflict was detected; selection remains disabled")
        else:
            reasons.append("partially comparable variant; no automatic selection is permitted")

    return {
        "candidate_id": candidate.get("candidate_id"),
        "stable_claim_sha256": candidate.get("stable_claim_sha256"),
        "source_unit_id": candidate.get("source_unit_id"),
        "origin_pass": candidate.get("origin_pass"),
        "proposition": proposition,
        "candidate_subject": candidate.get("subject"),
        "candidate_predicate": candidate.get("predicate"),
        "state": state,
        "conflict_outcome": conflict_outcome,
        "selection_allowed": False,
        "automatic_promotion_allowed": False,
        "automatic_canonicalization_allowed": False,
        "target_trusted": target_trusted,
        "reasons": reasons,
        "review_required": True,
        "top_matches": [
            {
                "score": round(score, 3),
                "lexical_score": round(lexical, 3),
                "subject_compatible": subj_ok,
                "predicate_compatible": pred_ok,
                "carrier_candidate_id": carrier[i]["carrier_candidate_id"],
                "subject_entity_id": carrier[i]["subject_entity_id"],
                "predicate_code": carrier[i]["predicate_code"],
                "fact_family": carrier[i].get("fact_family"),
                "value_text": (carrier[i]["value_text"] or "")[:300],
            }
            for score, lexical, subj_ok, pred_ok, _, _, i in top
        ],
    }


def _atomic_json(path: Path, value: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="compare_09d")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument(
        "--diagnostic-unverified-target",
        action="store_true",
        help=(
            "diagnostic only: permit structurally compatible but cryptographically unverified target; "
            "SUPPORT/TRUE_CONFLICT are suppressed and output is never frontier-authoritative"
        ),
    )
    # Backward-compatible unsafe flags are accepted only as aliases for diagnostic
    # mode. They can no longer produce trusted comparison conclusions.
    parser.add_argument("--allow-target-drift", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-db-hash", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    db_path = Path(args.database)
    union_path = run_dir / "ASSERTIONS" / "union_candidates.jsonl"
    if not union_path.exists():
        print(f"union candidates not found: {union_path}", file=sys.stderr)
        return 2

    diagnostic = bool(args.diagnostic_unverified_target or args.allow_target_drift or args.skip_db_hash)
    started = time.time()
    contract_report = verify_09d_contract(
        db_path,
        verify_identity=not diagnostic,
        strict_counts=not diagnostic,
        quick_check=False,
    )
    out_dir = run_dir / "09D"
    out_dir.mkdir(parents=True, exist_ok=True)
    _atomic_json(out_dir / "09d_contract_comparison_preflight.json", contract_report)
    if not contract_report["ok"]:
        print("09D comparator contract failed: " + ";".join(contract_report["errors"]), file=sys.stderr)
        return 3
    target_trusted = bool(contract_report.get("target_identity_verified"))
    if not target_trusted and not diagnostic:
        print("09D comparator target identity is not verified; refusing trusted comparison", file=sys.stderr)
        return 3

    candidates = [json.loads(line) for line in union_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    carrier = load_carrier(db_path)
    index = build_index(carrier)
    results = [classify(c, carrier, index, target_trusted=target_trusted) for c in candidates]
    state_counts: dict[str, int] = defaultdict(int)
    conflict_counts: dict[str, int] = defaultdict(int)
    for row in results:
        state_counts[row["state"]] += 1
        conflict_counts[row["conflict_outcome"]] += 1

    out_path = out_dir / "comparison_09d.jsonl"
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(out_path)

    observed_counts = contract_report.get("observed", {}).get("carrier_counts", {})
    summary = {
        "stage": "READ_ONLY_09D_COMPARISON",
        "comparator_target": COMPARATOR_TARGET,
        "database_path": str(db_path.resolve()),
        "database_sha256_measured": contract_report.get("observed", {}).get("database_sha256"),
        "database_matches_declared_target": target_trusted,
        "target_trust_mode": "SEALED_R3_VERIFIED" if target_trusted else "DIAGNOSTIC_UNVERIFIED",
        "carrier_rows_total": observed_counts.get("total", len(carrier)),
        "carrier_rows_loaded": len(carrier),
        "carrier_rows_indexed": sum(1 for row in carrier if row["tokens"]),
        "candidate_count": len(candidates),
        "state_counts": dict(sorted(state_counts.items())),
        "conflict_outcome_counts": dict(sorted(conflict_counts.items())),
        "selection_allowed_count": 0,
        "automatic_promotion_allowed": False,
        "duration_seconds": round(time.time() - started, 2),
        "method": (
            "sealed-target verification + deterministic retrieval + governed subject/predicate/context/unit compatibility; "
            "TRUE_CONFLICT requires all comparison dimensions before numeric/polarity disagreement"
        ),
        "claim_boundary": (
            "All outcomes are review evidence only. DUPLICATE_EQUIVALENT does not match/canonicalize; TRUE_CONFLICT "
            "does not invalidate source evidence; selection is always false; 09D remained mode=ro&immutable=1."
        ),
    }
    _atomic_json(out_dir / "comparison_09d_summary.json", summary)
    print(json.dumps({
        "state_counts": summary["state_counts"],
        "conflict_outcome_counts": summary["conflict_outcome_counts"],
        "candidate_count": summary["candidate_count"],
        "carrier_rows_total": summary["carrier_rows_total"],
        "database_matches_declared_target": summary["database_matches_declared_target"],
        "duration_seconds": summary["duration_seconds"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
