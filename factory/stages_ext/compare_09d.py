"""Read-only 09D comparator stage.

Compares a completed factory run's union candidates against the sealed 09D r3
carrier (`source_assertion_candidate`, the ingestion-boundary object extraction
output would eventually target) and classifies every candidate into one of six
REVIEWABLE states:

    SUPPORT · CONTRADICTION · CONTEXT_DIFFERENCE · VARIANT ·
    MISSING_IN_09D · IDENTITY_UNCERTAIN

Nothing here resolves anything. Agreement with 09D does not make a candidate
true; disagreement does not make it false. Every output row carries
review_required=true and the deterministic reasons behind its state.

The database is opened mode=ro&immutable=1 and its SHA-256 is measured and
compared against the declared comparator target. Meta v11's historical pin
(the S00 input DB) is recorded alongside, never overwritten.
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
    "db_role": "Current 09D chain state: sealed r3 envelope final_s03.sqlite (ledger 542d3052…), carrier holds 71,824 Motion-1 inherited assertions; Motion-2 slot empty.",
    "historical_pins_preserved": {
        "meta_v11_09d_readonly_authority": "pins the S00 input DB (canonical_anesthesia_knowledge.sqlite, 11f9e315…) — historical identity, intentionally NOT overwritten",
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
            "SELECT candidate_id, subject_entity_id, predicate_code, value_text "
            "FROM source_assertion_candidate WHERE value_text IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()
    carrier = []
    for cid, subject, predicate, value in rows:
        text = f"{(predicate or '').replace('.', ' ').replace('_', ' ')} {value or ''}"
        carrier.append({
            "carrier_candidate_id": cid,
            "subject_entity_id": subject,
            "predicate_code": predicate,
            "value_text": value,
            "tokens": _tokens(text),
            "numbers": _numbers_with_units(value or ""),
            "negated": bool(NEGATION_RE.search(value or "")),
        })
    return carrier


def build_index(carrier: list[dict]) -> dict[str, list[int]]:
    index: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(carrier):
        for token in row["tokens"]:
            index[token].append(i)
    return index


def classify(candidate: dict, carrier: list[dict], index: dict[str, list[int]]) -> dict:
    proposition = candidate.get("proposition") or ""
    tokens = _tokens(proposition)
    numbers = _numbers_with_units(proposition)
    negated = candidate.get("polarity") == "NEGATIVE" or bool(NEGATION_RE.search(proposition))
    counts: dict[int, int] = defaultdict(int)
    for token in tokens:
        for i in index.get(token, ()):  # postings capped by df at index build? kept full: carrier rows are short
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
        scored.append((max(jaccard, containment * 0.9), jaccard, i))
    scored.sort(reverse=True)
    top = scored[:5]
    reasons: list[str] = []
    if not top or top[0][0] < 0.30:
        state = "MISSING_IN_09D"
        reasons.append("no carrier row reaches similarity 0.30; r3 Motion-2 slot is empty so novel source content is expected here")
    else:
        best_score, _, best_i = top[0]
        best = carrier[best_i]
        near = [t for t in top if best_score - t[0] <= 0.05]
        distinct_subjects = {carrier[i]["subject_entity_id"] for _, _, i in near}
        polarity_conflict = negated != best["negated"] and best_score >= 0.60
        numeric_conflict = False
        for value, unit in numbers:
            for bvalue, bunit in best["numbers"]:
                if unit and unit == bunit and value != bvalue:
                    numeric_conflict = True
                    reasons.append(f"numeric conflict on unit '{unit}': candidate {value} vs 09D {bvalue}")
        if polarity_conflict:
            reasons.append("negation/polarity differs from best 09D match")
        if numeric_conflict or polarity_conflict:
            state = "CONTRADICTION"
        elif len(near) > 1 and len(distinct_subjects) > 1 and best_score >= 0.45:
            state = "IDENTITY_UNCERTAIN"
            reasons.append(f"{len(near)} near-equal matches across {len(distinct_subjects)} distinct 09D subjects")
        elif best_score >= 0.75:
            state = "SUPPORT"
            reasons.append(f"high lexical agreement ({best_score:.2f}) with one carrier row, no detected conflicts")
        else:
            cand_quals = {k for k, p in QUALIFIER_PATTERNS.items() if p.search(proposition)}
            row_quals = {k for k, p in QUALIFIER_PATTERNS.items() if p.search(best["value_text"] or "")}
            if cand_quals != row_quals and best_score >= 0.50:
                state = "CONTEXT_DIFFERENCE"
                reasons.append(f"qualifier-cue sets differ (candidate {sorted(cand_quals)} vs 09D {sorted(row_quals)})")
            else:
                state = "VARIANT"
                reasons.append(f"partial lexical agreement ({best_score:.2f}); phrasing or scope differs")
    return {
        "candidate_id": candidate.get("candidate_id"),
        "source_unit_id": candidate.get("source_unit_id"),
        "origin_pass": candidate.get("origin_pass"),
        "proposition": proposition,
        "state": state,
        "reasons": reasons,
        "review_required": True,
        "top_matches": [
            {
                "score": round(score, 3),
                "carrier_candidate_id": carrier[i]["carrier_candidate_id"],
                "subject_entity_id": carrier[i]["subject_entity_id"],
                "predicate_code": carrier[i]["predicate_code"],
                "value_text": (carrier[i]["value_text"] or "")[:300],
            }
            for score, _, i in top
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="compare_09d")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--allow-target-drift", action="store_true",
                        help="proceed even if the DB hash differs from the declared comparator target (recorded, never silent)")
    parser.add_argument("--skip-db-hash", action="store_true",
                        help="skip the full-file hash (comparison output then records hash as NOT_MEASURED)")
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
            print(f"comparator target drift: measured {measured} != declared "
                  f"{COMPARATOR_TARGET['expected_db_sha256']}; refusing (use --allow-target-drift to record and proceed)",
                  file=sys.stderr)
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
        "method": "deterministic lexical/numeric/negation comparison; thresholds SUPPORT>=0.75, near-tie IDENTITY window 0.05, floor 0.30",
        "claim_boundary": (
            "Every state is reviewable. SUPPORT does not canonicalize a candidate; "
            "CONTRADICTION and MISSING_IN_09D do not invalidate one. 09D remained "
            "read-only throughout (mode=ro&immutable=1)."
        ),
    }
    (out_dir / "comparison_09d_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("state_counts", "candidate_count", "carrier_rows_compared_against",
                                              "database_matches_declared_target", "duration_seconds")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
