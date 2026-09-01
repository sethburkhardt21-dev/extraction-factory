"""Read-only 09D comparator stage.

Compares a completed factory run's union candidates against the sealed 09D r3
carrier and emits reviewable comparison states. Agreement never canonicalizes a
candidate and disagreement never invalidates one. CONTRADICTION is deliberately
conservative: subject and predicate compatibility must be established before a
numeric or polarity conflict is allowed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from hermes_factory.literal import NUM_RE, QUALIFIER_PATTERNS  # noqa: E402

COMPARATOR_TARGET = {
    "comparator_target_version": "09d-r3-sealed-1.0",
    "expected_db_sha256": "fa7a97313dc5bbd9b2fbb61b9124a4ecef5c318ad5d070eeefe67816a210f4a3",
    "db_role": "Current 09D chain state: sealed r3 envelope final_s03.sqlite; carrier holds 71,824 Motion-1 inherited assertions; Motion-2 slot empty.",
    "historical_pins_preserved": {
        "meta_v11_09d_readonly_authority": "historical S00 input DB identity is intentionally not overwritten",
        "hermes_v1_1_bridge_contract": "policy-only contract, pins no database identity",
    },
}

STOPWORDS = {
    "the", "and", "for", "are", "was", "were", "with", "that", "this", "from", "into",
    "when", "then", "than", "which", "will", "shall", "has", "have", "had", "its",
    "can", "may", "not", "but", "all", "any", "one", "two", "per", "each", "also",
    "used", "use", "using", "there", "their", "them", "they", "been", "being", "such",
    "procedure", "aliases", "value", "values", "code", "type",
}

NEGATION_RE = QUALIFIER_PATTERNS["NEGATION"]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) >= 3 and w not in STOPWORDS}


def _numbers_with_units(text: str) -> set[tuple[str, str]]:
    out = set()
    for m in NUM_RE.finditer(text or ""):
        value = re.sub(r"\s+", "", m.group("value"))
        unit = re.sub(r"\s+", "", (m.group("unit") or "").lower())
        out.add((value, unit))
    return out


def load_carrier(db_path: Path) -> list[dict]:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute(
            "SELECT candidate_id, subject_entity_id, predicate_code, value_text, fact_family "
            "FROM source_assertion_candidate WHERE value_text IS NOT NULL"
        ).fetchall()
        names: dict[str, set[str]] = defaultdict(set)
        try:
            for canonical_id, name_text, normalized_name in conn.execute(
                "SELECT canonical_id, name_text, normalized_name FROM entity_name WHERE is_searchable=1"
            ):
                names[str(canonical_id)].update(_tokens(name_text or ""))
                names[str(canonical_id)].update(_tokens(normalized_name or ""))
        except sqlite3.Error:
            pass
    finally:
        conn.close()
    carrier = []
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


def classify(candidate: dict, carrier: list[dict], index: dict[str, list[int]]) -> dict:
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
    scored = []
    for i, shared in counts.items():
        if shared < min_shared:
            continue
        row = carrier[i]
        union_size = len(tokens | row["tokens"]) or 1
        jaccard = shared / union_size
        containment = shared / (len(row["tokens"]) or 1)
        subj_ok, subj_score = _compatibility(cand_subject_tokens, row.get("subject_tokens", set()))
        pred_ok, pred_score = _predicate_compatibility(cand_predicate_tokens, row.get("predicate_tokens", set()))
        lexical = max(jaccard, containment * 0.9)
        structured_bonus = (0.10 if subj_ok else 0.0) + (0.10 if pred_ok else 0.0)
        scored.append((min(1.0, lexical + structured_bonus), lexical, subj_ok, pred_ok, subj_score, pred_score, i))
    scored.sort(reverse=True)
    top = scored[:5]
    reasons: list[str] = []
    if not top or top[0][0] < 0.30:
        state = "MISSING_IN_09D"
        reasons.append("no carrier row reaches conservative retrieval floor 0.30; novel source content is expected because the Motion-2 slot is empty")
    else:
        best_score, lexical_score, subj_ok, pred_ok, subj_score, pred_score, best_i = top[0]
        best = carrier[best_i]
        near = [t for t in top if best_score - t[0] <= 0.05]
        distinct_subjects = {carrier[t[-1]]["subject_entity_id"] for t in near}
        structured_comparable = subj_ok and pred_ok
        polarity_conflict = structured_comparable and negated != best["negated"] and lexical_score >= 0.50
        numeric_conflict = False
        if structured_comparable:
            for value, unit in numbers:
                for bvalue, bunit in best["numbers"]:
                    if unit and unit == bunit and value != bvalue:
                        numeric_conflict = True
                        reasons.append(f"numeric conflict on matched subject+predicate and unit '{unit}': candidate {value} vs 09D {bvalue}")
        if polarity_conflict:
            reasons.append("negation/polarity differs after subject and predicate compatibility were established")
        if numeric_conflict or polarity_conflict:
            state = "CONTRADICTION"
        elif not structured_comparable:
            if len(near) > 1 and len(distinct_subjects) > 1:
                state = "IDENTITY_UNCERTAIN"
                reasons.append("lexical retrieval found multiple candidate subjects, but subject+predicate identity was not established")
            else:
                state = "VARIANT"
                reasons.append(
                    f"lexical retrieval only ({lexical_score:.2f}); contradiction/support suppressed because subject compatibility={subj_ok} ({subj_score:.2f}) and predicate compatibility={pred_ok} ({pred_score:.2f})"
                )
        elif best_score >= 0.75:
            state = "SUPPORT"
            reasons.append(f"subject+predicate compatible with high combined agreement ({best_score:.2f}); no detected conflict")
        else:
            cand_quals = {k for k, p in QUALIFIER_PATTERNS.items() if p.search(proposition)}
            row_quals = {k for k, p in QUALIFIER_PATTERNS.items() if p.search(best["value_text"] or "")}
            if cand_quals != row_quals and best_score >= 0.50:
                state = "CONTEXT_DIFFERENCE"
                reasons.append(f"subject+predicate compatible but qualifier-cue sets differ (candidate {sorted(cand_quals)} vs 09D {sorted(row_quals)})")
            else:
                state = "VARIANT"
                reasons.append(f"subject+predicate compatible with partial agreement ({best_score:.2f}); phrasing/value scope differs")
    return {
        "candidate_id": candidate.get("candidate_id"),
        "source_unit_id": candidate.get("source_unit_id"),
        "origin_pass": candidate.get("origin_pass"),
        "proposition": proposition,
        "candidate_subject": candidate.get("subject"),
        "candidate_predicate": candidate.get("predicate"),
        "state": state,
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="compare_09d")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--allow-target-drift", action="store_true",
                        help="proceed even if the DB hash differs from the declared comparator target")
    parser.add_argument("--skip-db-hash", action="store_true",
                        help="skip the full-file hash (comparison output records hash as NOT_MEASURED)")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    db_path = Path(args.database)
    union_path = run_dir / "ASSERTIONS" / "union_candidates.jsonl"
    if not union_path.exists():
        print(f"union candidates not found: {union_path}", file=sys.stderr)
        return 2

    started = time.time()
    measured = None
    target_match = None
    if not args.skip_db_hash:
        measured = _sha256_file(db_path)
        target_match = measured == COMPARATOR_TARGET["expected_db_sha256"]
        if not target_match and not args.allow_target_drift:
            print(f"comparator target drift: measured {measured} != declared {COMPARATOR_TARGET['expected_db_sha256']}; refusing", file=sys.stderr)
            return 3

    candidates = [json.loads(line) for line in union_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    carrier = load_carrier(db_path)
    index = build_index(carrier)
    results = [classify(c, carrier, index) for c in candidates]
    counts: dict[str, int] = defaultdict(int)
    for r in results:
        counts[r["state"]] += 1

    out_dir = run_dir / "09D"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "comparison_09d.jsonl").open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    summary = {
        "stage": "READ_ONLY_09D_COMPARISON",
        "comparator_target": COMPARATOR_TARGET,
        "database_path": str(db_path),
        "database_sha256_measured": measured or "NOT_MEASURED",
        "database_matches_declared_target": target_match,
        "carrier_rows_compared_against": len(carrier),
        "candidate_count": len(candidates),
        "state_counts": dict(sorted(counts.items())),
        "duration_seconds": round(time.time() - started, 2),
        "method": "conservative deterministic retrieval plus governed entity-name/predicate compatibility; CONTRADICTION requires compatible subject+predicate before numeric/polarity conflict is allowed",
        "claim_boundary": (
            "Every state is reviewable. SUPPORT does not canonicalize a candidate; "
            "CONTRADICTION and MISSING_IN_09D do not invalidate one. 09D remained "
            "read-only throughout (mode=ro&immutable=1)."
        ),
    }
    (out_dir / "comparison_09d_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("state_counts", "candidate_count", "carrier_rows_compared_against",
                                              "database_matches_declared_target", "duration_seconds")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
