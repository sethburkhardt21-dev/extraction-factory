"""Read-only 09D comparator stage.

The comparator is deliberately asymmetric: 09D is a governed downstream
reference substrate, not a gold label. New source-grounded candidates are never
canonicalized or invalidated here.

v1.4 makes comparison more useful to 09D by resolving exact searchable entity
aliases and exact predicate codes before falling back to lexical similarity.
CONTRADICTION requires compatible subject + predicate + fact-family/context and
an unambiguous numeric or polarity conflict. Ambiguity is routed for review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from hermes_factory.bridge_09d import motion2_capability_readonly  # noqa: E402
from hermes_factory.literal import NUM_RE, QUALIFIER_PATTERNS  # noqa: E402

COMPARATOR_TARGET = {
    "comparator_target_version": "09d-r3-sealed-1.1",
    "expected_db_sha256": "fa7a97313dc5bbd9b2fbb61b9124a4ecef5c318ad5d070eeefe67816a210f4a3",
    "db_role": "Current 09D chain state: sealed r3 envelope final_s03.sqlite; carrier holds 71,824 Motion-1 inherited assertions; Motion-2 slot was empty at the pinned audit.",
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
    "procedure", "aliases", "value", "values", "code", "type", "is", "of", "to", "in",
}

UNIT_ALIASES = {
    "mm hg": "mmhg", "mmhg": "mmhg", "mm-hg": "mmhg",
    "cm h2o": "cmh2o", "cmh₂o": "cmh2o", "cmh2o": "cmh2o",
    "°c": "degc", "c": "degc", "degrees c": "degc",
    "%": "%", "percent": "%",
    "ml": "ml", "ml/kg": "ml/kg", "mg": "mg", "mcg": "mcg", "ug": "mcg",
}

NEGATION_RE = QUALIFIER_PATTERNS["NEGATION"]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_phrase(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = text.replace("μ", "u").replace("µ", "u")
    return " ".join(re.findall(r"[a-z0-9%]+", text))


def _tokens(text: str) -> set[str]:
    return {w for w in _normalize_phrase(text).split() if len(w) >= 3 and w not in STOPWORDS}


def _normalize_unit(unit: str) -> str:
    unit = unicodedata.normalize("NFKC", unit or "").lower().strip()
    unit = re.sub(r"\s+", " ", unit)
    return UNIT_ALIASES.get(unit, unit.replace(" ", ""))


def _numbers_with_units(text: str) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for m in NUM_RE.finditer(text or ""):
        value = re.sub(r"\s+", "", m.group("value"))
        unit = _normalize_unit(m.group("unit") or "")
        out.add((value, unit))
    return out


def _qualifier_set(text: str) -> set[str]:
    return {k for k, p in QUALIFIER_PATTERNS.items() if p.search(text or "")}


def _context_qualifiers(text: str) -> set[str]:
    # Polarity is compared explicitly. Other qualifier differences are context.
    return _qualifier_set(text) - {"NEGATION"}


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
                if name_text:
                    names[str(canonical_id)].add(_normalize_phrase(str(name_text)))
                if normalized_name:
                    names[str(canonical_id)].add(_normalize_phrase(str(normalized_name)))
        except sqlite3.Error:
            pass
    finally:
        conn.close()

    carrier: list[dict] = []
    for cid, subject, predicate, value, fact_family in rows:
        subject_id = str(subject) if subject is not None else ""
        predicate_code = str(predicate or "")
        predicate_text = predicate_code.replace(".", " ").replace("_", " ")
        value_text = str(value or "")
        aliases = {a for a in names.get(subject_id, set()) if a}
        subject_tokens: set[str] = set()
        for alias in aliases:
            subject_tokens.update(_tokens(alias))
        predicate_tokens = _tokens(predicate_text)
        value_tokens = _tokens(value_text)
        carrier.append({
            "carrier_candidate_id": cid,
            "subject_entity_id": subject,
            "predicate_code": predicate,
            "predicate_norm": _normalize_phrase(predicate_text),
            "fact_family": fact_family,
            "value_text": value,
            "subject_aliases": aliases,
            "subject_tokens": subject_tokens,
            "predicate_tokens": predicate_tokens,
            "value_tokens": value_tokens,
            "tokens": subject_tokens | predicate_tokens | value_tokens,
            "numbers": _numbers_with_units(value_text),
            "qualifiers": _qualifier_set(value_text),
            "context_qualifiers": _context_qualifiers(value_text),
            "negated": bool(NEGATION_RE.search(value_text)),
        })
    return carrier


def build_index(carrier: list[dict]) -> dict[Any, Any]:
    """Build token, alias, subject-id, and predicate indexes in one pass.

    Tuple keys are internal namespaces so the legacy ``index.get(token)`` path
    remains compatible with existing tests/callers.
    """
    index: dict[Any, Any] = defaultdict(list)
    for i, row in enumerate(carrier):
        for token in row.get("tokens", set()):
            index[token].append(i)
        subject_id = str(row.get("subject_entity_id") or "")
        if subject_id:
            index[("subject_id", subject_id)].append(i)
        aliases = row.get("subject_aliases") or set()
        if not aliases and row.get("subject_tokens"):
            # Synthetic test rows often only provide subject_tokens.
            aliases = {" ".join(sorted(row["subject_tokens"]))}
        for alias in aliases:
            if alias:
                index[("subject_alias", _normalize_phrase(alias))].append(i)
        predicate_norm = row.get("predicate_norm") or _normalize_phrase(
            str(row.get("predicate_code") or "").replace(".", " ").replace("_", " ")
        )
        if predicate_norm:
            index[("predicate", predicate_norm)].append(i)
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


def _candidate_subject_ids(candidate: dict, index: dict[Any, Any]) -> tuple[set[str], str]:
    explicit = candidate.get("subject_entity_id") or (candidate.get("metadata") or {}).get("09d_subject_entity_id")
    if explicit:
        return {str(explicit)}, "EXPLICIT_ID"
    norm = _normalize_phrase(candidate.get("subject") or "")
    if not norm:
        return set(), "NO_SUBJECT_TEXT"
    rows = index.get(("subject_alias", norm), [])
    ids = {str(index_row) for index_row in []}  # explicit empty-set initialization for deterministic type
    ids.clear()
    # resolve row indexes to subject ids later in classify, where carrier is available
    return {f"@row:{i}" for i in rows}, ("EXACT_ALIAS" if rows else "LEXICAL_ONLY")


def _candidate_predicate_rows(candidate: dict, index: dict[Any, Any]) -> tuple[set[int], str]:
    norm = _normalize_phrase(candidate.get("predicate") or "")
    if not norm:
        return set(), "NO_PREDICATE_TEXT"
    rows = set(index.get(("predicate", norm), []))
    return rows, ("EXACT_CODE_OR_LABEL" if rows else "LEXICAL_ONLY")


def _safe_numeric_conflict(candidate_numbers: set[tuple[str, str]], row_numbers: set[tuple[str, str]]) -> tuple[bool, bool, str | None]:
    """Return (conflict, ambiguous, reason) without performing unit conversion.

    A contradiction is allowed only for exactly one value on each side sharing a
    non-empty normalized unit. Multi-number statements are routed instead of
    guessed because neighboring values are common in tables and ranges.
    """
    comparable_units = sorted({u for _, u in candidate_numbers if u} & {u for _, u in row_numbers if u})
    if not comparable_units:
        return False, False, None
    conflicts = []
    for unit in comparable_units:
        cvals = sorted({v for v, u in candidate_numbers if u == unit})
        rvals = sorted({v for v, u in row_numbers if u == unit})
        if len(cvals) != 1 or len(rvals) != 1:
            return False, True, f"multiple numeric values share unit '{unit}'; automatic contradiction suppressed"
        if cvals[0] != rvals[0]:
            conflicts.append((unit, cvals[0], rvals[0]))
    if len(conflicts) == 1:
        unit, cval, rval = conflicts[0]
        return True, False, f"numeric conflict on matched subject+predicate+context and unit '{unit}': candidate {cval} vs 09D {rval}"
    if len(conflicts) > 1:
        return False, True, "multiple numeric dimensions conflict; automatic contradiction suppressed"
    return False, False, None


def classify(candidate: dict, carrier: list[dict], index: dict[Any, Any]) -> dict:
    proposition = candidate.get("proposition") or ""
    tokens = _tokens(proposition)
    cand_subject_tokens = _tokens(candidate.get("subject") or "")
    cand_predicate_tokens = _tokens(candidate.get("predicate") or "")
    numbers = _numbers_with_units(proposition)
    negated = candidate.get("polarity") == "NEGATIVE" or bool(NEGATION_RE.search(proposition))
    cand_context = _context_qualifiers(proposition)
    candidate_family = candidate.get("fact_family") or (candidate.get("metadata") or {}).get("fact_family")

    raw_subject_ids, subject_resolution_mode = _candidate_subject_ids(candidate, index)
    resolved_subject_ids: set[str] = set()
    exact_subject_rows: set[int] = set()
    for value in raw_subject_ids:
        if value.startswith("@row:"):
            i = int(value.split(":", 1)[1])
            exact_subject_rows.add(i)
            sid = carrier[i].get("subject_entity_id")
            if sid is not None:
                resolved_subject_ids.add(str(sid))
        else:
            resolved_subject_ids.add(value)
            exact_subject_rows.update(index.get(("subject_id", value), []))

    exact_predicate_rows, predicate_resolution_mode = _candidate_predicate_rows(candidate, index)

    counts: dict[int, int] = defaultdict(int)
    for token in tokens:
        for i in index.get(token, ()):
            counts[i] += 1
    # Structured retrieval gets enough weight to survive weak proposition overlap.
    for i in exact_subject_rows:
        counts[i] += 3
    for i in exact_predicate_rows:
        counts[i] += 3

    min_shared = 1 if len(tokens) < 4 else 2
    scored = []
    for i, shared in counts.items():
        row = carrier[i]
        lexical_shared = len(tokens & row.get("tokens", set()))
        if lexical_shared < min_shared and i not in exact_subject_rows and i not in exact_predicate_rows:
            continue
        union_size = len(tokens | row.get("tokens", set())) or 1
        jaccard = lexical_shared / union_size
        containment = lexical_shared / (len(row.get("tokens", set())) or 1)

        if resolved_subject_ids:
            subj_ok = str(row.get("subject_entity_id")) in resolved_subject_ids
            subj_score = 1.0 if subj_ok else 0.0
        else:
            subj_ok, subj_score = _compatibility(cand_subject_tokens, row.get("subject_tokens", set()))

        if exact_predicate_rows:
            pred_ok = i in exact_predicate_rows
            pred_score = 1.0 if pred_ok else 0.0
        else:
            pred_ok, pred_score = _predicate_compatibility(cand_predicate_tokens, row.get("predicate_tokens", set()))

        family_ok = not candidate_family or not row.get("fact_family") or str(candidate_family) == str(row.get("fact_family"))
        lexical = max(jaccard, containment * 0.9)
        structured_bonus = (0.18 if subj_ok else 0.0) + (0.18 if pred_ok else 0.0) + (0.04 if family_ok else -0.10)
        scored.append((min(1.0, max(0.0, lexical + structured_bonus)), lexical, subj_ok, pred_ok, family_ok, subj_score, pred_score, i))

    scored.sort(reverse=True)
    top = scored[:5]
    reasons: list[str] = []
    comparison_confidence = "LOW"

    if not top or top[0][0] < 0.30:
        state = "MISSING_IN_09D"
        reasons.append("no carrier row reaches conservative retrieval floor 0.30; novel source content is expected because the pinned r3 Motion-2 slot was empty")
    else:
        best_score, lexical_score, subj_ok, pred_ok, family_ok, subj_score, pred_score, best_i = top[0]
        best = carrier[best_i]
        near = [t for t in top if best_score - t[0] <= 0.05]
        distinct_subjects = {str(carrier[t[-1]].get("subject_entity_id")) for t in near}
        subject_ambiguous = len(resolved_subject_ids) > 1 or (not resolved_subject_ids and len(near) > 1 and len(distinct_subjects) > 1)
        structured_comparable = subj_ok and pred_ok and family_ok and not subject_ambiguous
        row_context = best.get("context_qualifiers")
        if row_context is None:
            row_context = _context_qualifiers(best.get("value_text") or "")
        context_compatible = cand_context == set(row_context)

        numeric_conflict = False
        numeric_ambiguous = False
        numeric_reason = None
        if structured_comparable and context_compatible:
            numeric_conflict, numeric_ambiguous, numeric_reason = _safe_numeric_conflict(numbers, best.get("numbers", set()))
            if numeric_reason:
                reasons.append(numeric_reason)
        polarity_conflict = structured_comparable and context_compatible and negated != bool(best.get("negated")) and lexical_score >= 0.30
        if polarity_conflict:
            reasons.append("negation/polarity differs after subject, predicate, fact-family, and context compatibility were established")

        if subject_ambiguous:
            state = "IDENTITY_UNCERTAIN"
            reasons.append("candidate subject resolves to multiple plausible 09D entities; automatic support/contradiction suppressed")
        elif numeric_conflict or polarity_conflict:
            state = "CONTRADICTION"
            comparison_confidence = "HIGH"
        elif structured_comparable and not context_compatible:
            state = "CONTEXT_DIFFERENCE"
            comparison_confidence = "HIGH"
            reasons.append(f"subject+predicate compatible but contextual qualifier sets differ (candidate {sorted(cand_context)} vs 09D {sorted(row_context)})")
        elif structured_comparable and numeric_ambiguous:
            state = "VARIANT"
            comparison_confidence = "MEDIUM"
        elif not structured_comparable:
            if len(near) > 1 and len(distinct_subjects) > 1:
                state = "IDENTITY_UNCERTAIN"
                reasons.append("retrieval found multiple candidate subjects but structured identity was not established")
            else:
                state = "VARIANT"
                reasons.append(
                    f"retrieval only ({lexical_score:.2f}); support/contradiction suppressed because subject compatibility={subj_ok} ({subj_score:.2f}), predicate compatibility={pred_ok} ({pred_score:.2f}), fact-family compatibility={family_ok}"
                )
        else:
            equal_numeric = bool(numbers) and numbers == best.get("numbers", set())
            no_numeric_either = not numbers and not best.get("numbers", set())
            if best_score >= 0.78 and context_compatible and (equal_numeric or no_numeric_either):
                state = "SUPPORT"
                comparison_confidence = "HIGH"
                reasons.append(f"subject+predicate+context compatible with high agreement ({best_score:.2f}); no detected conflict")
            elif best_score >= 0.62 and context_compatible:
                state = "POSSIBLE_DUPLICATE"
                comparison_confidence = "MEDIUM"
                reasons.append("structured identity is compatible, but value/scope equality is not strong enough for SUPPORT")
            else:
                state = "VARIANT"
                comparison_confidence = "MEDIUM"
                reasons.append(f"subject+predicate compatible with partial agreement ({best_score:.2f}); phrasing/value scope differs")

    return {
        "candidate_id": candidate.get("candidate_id"),
        "source_unit_id": candidate.get("source_unit_id"),
        "origin_pass": candidate.get("origin_pass"),
        "proposition": proposition,
        "candidate_subject": candidate.get("subject"),
        "candidate_predicate": candidate.get("predicate"),
        "state": state,
        "comparison_confidence": comparison_confidence,
        "subject_resolution": {
            "mode": subject_resolution_mode,
            "resolved_entity_ids": sorted(resolved_subject_ids),
        },
        "predicate_resolution": {
            "mode": predicate_resolution_mode,
        },
        "reasons": reasons,
        "review_required": True,
        "top_matches": [
            {
                "score": round(score, 3),
                "lexical_score": round(lexical, 3),
                "subject_compatible": subj_ok,
                "predicate_compatible": pred_ok,
                "fact_family_compatible": family_ok,
                "carrier_candidate_id": carrier[i].get("carrier_candidate_id"),
                "subject_entity_id": carrier[i].get("subject_entity_id"),
                "predicate_code": carrier[i].get("predicate_code"),
                "fact_family": carrier[i].get("fact_family"),
                "value_text": (carrier[i].get("value_text") or "")[:300],
            }
            for score, lexical, subj_ok, pred_ok, family_ok, _, _, i in top
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
    confidence_counts: dict[str, int] = defaultdict(int)
    for r in results:
        counts[r["state"]] += 1
        confidence_counts[r["comparison_confidence"]] += 1

    out_dir = run_dir / "09D"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "comparison_09d.jsonl").open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    capability = motion2_capability_readonly(db_path)
    summary = {
        "stage": "READ_ONLY_09D_COMPARISON",
        "comparator_target": COMPARATOR_TARGET,
        "database_path": str(db_path),
        "database_sha256_measured": measured or "NOT_MEASURED",
        "database_matches_declared_target": target_match,
        "schema_fingerprint_sha256": capability.get("schema_fingerprint_sha256"),
        "motion2_capability": capability,
        "carrier_rows_compared_against": len(carrier),
        "candidate_count": len(candidates),
        "state_counts": dict(sorted(counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "duration_seconds": round(time.time() - started, 2),
        "method": "exact searchable-entity alias and predicate resolution when available, then conservative deterministic retrieval; contradiction requires compatible subject+predicate+fact-family+context before an unambiguous numeric/polarity conflict is allowed",
        "claim_boundary": (
            "Every state is reviewable. SUPPORT/POSSIBLE_DUPLICATE do not canonicalize or merge a candidate; "
            "CONTRADICTION and MISSING_IN_09D do not invalidate one. 09D remained read-only throughout "
            "(mode=ro&immutable=1)."
        ),
    }
    (out_dir / "comparison_09d_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("state_counts", "confidence_counts", "candidate_count",
                                              "carrier_rows_compared_against", "database_matches_declared_target",
                                              "duration_seconds")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
