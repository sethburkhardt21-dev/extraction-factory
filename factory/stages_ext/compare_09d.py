"""Read-only 09D comparator stage.

09D is a governed downstream reference substrate, not a gold label. New
source-grounded candidates are never canonicalized or invalidated here.

v1.5 adds a cycle-safety boundary: comparison defaults to the inherited
Motion-1 carrier only. Prior Motion-2 extraction rows are excluded so model
output cannot recursively become evidence for later model output. Exact subject
aliases, predicate codes, structured numeric values, fact family, qualifiers,
and witness kind are carried in the comparison receipts.
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
    "comparator_target_version": "09d-r3-sealed-1.2",
    "expected_db_sha256": "fa7a97313dc5bbd9b2fbb61b9124a4ecef5c318ad5d070eeefe67816a210f4a3",
    "db_role": (
        "Current 09D chain state: sealed r3 envelope final_s03.sqlite; carrier held 71,824 "
        "Motion-1 inherited assertions and an empty Motion-2 slot at the pinned audit."
    ),
    "default_comparison_scope": "MOTION1_AUTHORITY",
}

CARRIER_SCOPES = {
    "MOTION1_AUTHORITY": (
        "source_resource_id IS NOT NULL AND ingest_locator_id IS NULL",
        "Inherited/source-witnessed 09D carrier only; prevents recursive support from prior extraction rows.",
    ),
    "ALL_CARRIER": (
        "1=1",
        "Diagnostic scope only; includes Motion-2 extraction rows and therefore is not cycle-safe authority comparison.",
    ),
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
        for chunk in iter(lambda: f.read(8 << 20), b""):
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


def _candidate_numbers(candidate: dict, proposition: str) -> tuple[set[tuple[str, str]], str]:
    """Prefer model-bound numeric structures over proposition-wide regex capture."""
    structured: set[tuple[str, str]] = set()
    for item in candidate.get("numeric_values") or []:
        if not isinstance(item, dict):
            continue
        value = item.get("value_literal")
        if value is None:
            continue
        value = re.sub(r"\s+", "", str(value))
        unit = _normalize_unit(str(item.get("unit_literal") or ""))
        structured.add((value, unit))
    if structured:
        return structured, "STRUCTURED_NUMERIC_VALUES"
    return _numbers_with_units(proposition), "PROPOSITION_FALLBACK"


def _qualifier_set(text: str) -> set[str]:
    return {k for k, p in QUALIFIER_PATTERNS.items() if p.search(text or "")}


def _context_qualifiers(text: str) -> set[str]:
    return _qualifier_set(text) - {"NEGATION"}


def _candidate_context(candidate: dict, proposition: str) -> set[str]:
    parts = [proposition]
    parts.extend(str(x) for x in (candidate.get("qualifiers") or []) if x)
    for key in ("conditionality", "temporality", "comparison"):
        if candidate.get(key):
            parts.append(str(candidate[key]))
    return _context_qualifiers(" ".join(parts))


def _witness_kind(source_resource_id: Any, ingest_locator_id: Any) -> str:
    if source_resource_id is not None and ingest_locator_id is None:
        return "MOTION1_SOURCE_WITNESSED"
    if source_resource_id is None and ingest_locator_id is not None:
        return "MOTION2_INGEST_WITNESSED"
    return "INVALID_OR_UNKNOWN_WITNESS"


def load_carrier(db_path: Path, scope: str = "MOTION1_AUTHORITY") -> list[dict]:
    if scope not in CARRIER_SCOPES:
        raise ValueError(f"unknown_09d_carrier_scope:{scope}")
    where_scope, _ = CARRIER_SCOPES[scope]
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        columns = {r[1] for r in conn.execute("PRAGMA table_info(source_assertion_candidate)")}
        witness_needed = {"source_resource_id", "ingest_locator_id"}
        if not witness_needed.issubset(columns):
            raise RuntimeError(
                "09d_witness_scope_unavailable:" + ",".join(sorted(witness_needed - columns))
            )
        rows = conn.execute(
            "SELECT candidate_id, subject_entity_id, predicate_code, value_text, fact_family, "
            "source_resource_id, ingest_locator_id FROM source_assertion_candidate "
            f"WHERE value_text IS NOT NULL AND ({where_scope})"
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
    for cid, subject, predicate, value, fact_family, source_resource_id, ingest_locator_id in rows:
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
            "witness_kind": _witness_kind(source_resource_id, ingest_locator_id),
        })
    return carrier


def build_index(carrier: list[dict]) -> dict[Any, Any]:
    index: dict[Any, Any] = defaultdict(list)
    for i, row in enumerate(carrier):
        for token in row.get("tokens", set()):
            index[token].append(i)
        subject_id = str(row.get("subject_entity_id") or "")
        if subject_id:
            index[("subject_id", subject_id)].append(i)
        aliases = row.get("subject_aliases") or set()
        if not aliases and row.get("subject_tokens"):
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


def _candidate_subject_rows(candidate: dict, index: dict[Any, Any]) -> tuple[set[int], str, str | None]:
    explicit = candidate.get("subject_entity_id") or (candidate.get("metadata") or {}).get("09d_subject_entity_id")
    if explicit:
        sid = str(explicit)
        return set(index.get(("subject_id", sid), [])), "EXPLICIT_ID", sid
    norm = _normalize_phrase(candidate.get("subject") or "")
    if not norm:
        return set(), "NO_SUBJECT_TEXT", None
    rows = set(index.get(("subject_alias", norm), []))
    return rows, ("EXACT_ALIAS" if rows else "LEXICAL_ONLY"), None


def _candidate_predicate_rows(candidate: dict, index: dict[Any, Any]) -> tuple[set[int], str]:
    norm = _normalize_phrase(candidate.get("predicate") or "")
    if not norm:
        return set(), "NO_PREDICATE_TEXT"
    rows = set(index.get(("predicate", norm), []))
    return rows, ("EXACT_CODE_OR_LABEL" if rows else "LEXICAL_ONLY")


def _safe_numeric_conflict(candidate_numbers: set[tuple[str, str]], row_numbers: set[tuple[str, str]]) -> tuple[bool, bool, str | None]:
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
    numbers, numeric_basis = _candidate_numbers(candidate, proposition)
    negated = candidate.get("polarity") == "NEGATIVE" or bool(NEGATION_RE.search(proposition))
    cand_context = _candidate_context(candidate, proposition)
    candidate_family = candidate.get("fact_family") or (candidate.get("metadata") or {}).get("fact_family")

    exact_subject_rows, subject_resolution_mode, explicit_subject_id = _candidate_subject_rows(candidate, index)
    resolved_subject_ids = {
        str(carrier[i].get("subject_entity_id")) for i in exact_subject_rows
        if carrier[i].get("subject_entity_id") is not None
    }
    if explicit_subject_id:
        resolved_subject_ids = {explicit_subject_id}
    subject_resolution_ambiguous = subject_resolution_mode == "EXACT_ALIAS" and len(resolved_subject_ids) > 1

    exact_predicate_rows, predicate_resolution_mode = _candidate_predicate_rows(candidate, index)

    counts: dict[int, int] = defaultdict(int)
    for token in tokens:
        for i in index.get(token, ()):
            counts[i] += 1
    for i in exact_subject_rows:
        counts[i] += 3
    for i in exact_predicate_rows:
        counts[i] += 3

    min_shared = 1 if len(tokens) < 4 else 2
    scored = []
    for i in counts:
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

        row_family = row.get("fact_family")
        family_ok = not candidate_family or not row_family or str(candidate_family) == str(row_family)
        family_explicit = bool(candidate_family and row_family)
        lexical = max(jaccard, containment * 0.9)
        structured_bonus = (0.18 if subj_ok else 0.0) + (0.18 if pred_ok else 0.0) + (0.04 if family_ok else -0.10)
        scored.append((min(1.0, max(0.0, lexical + structured_bonus)), lexical, subj_ok, pred_ok,
                       family_ok, family_explicit, subj_score, pred_score, i))

    scored.sort(reverse=True)
    top = scored[:5]
    reasons: list[str] = []
    comparison_confidence = "LOW"

    if not top or top[0][0] < 0.30:
        state = "MISSING_IN_09D"
        reasons.append("no authority-carrier row reaches conservative retrieval floor 0.30")
    else:
        best_score, lexical_score, subj_ok, pred_ok, family_ok, family_explicit, subj_score, pred_score, best_i = top[0]
        best = carrier[best_i]
        near = [t for t in top if best_score - t[0] <= 0.05]
        distinct_subjects = {str(carrier[t[-1]].get("subject_entity_id")) for t in near}
        lexical_subject_ambiguous = not resolved_subject_ids and len(near) > 1 and len(distinct_subjects) > 1
        subject_ambiguous = subject_resolution_ambiguous or lexical_subject_ambiguous
        structured_comparable = subj_ok and pred_ok and family_ok and not subject_ambiguous
        row_context = set(best.get("context_qualifiers") or _context_qualifiers(best.get("value_text") or ""))
        context_compatible = cand_context == row_context

        numeric_conflict = False
        numeric_ambiguous = False
        numeric_reason = None
        if structured_comparable and context_compatible:
            numeric_conflict, numeric_ambiguous, numeric_reason = _safe_numeric_conflict(numbers, best.get("numbers", set()))
            if numeric_reason:
                reasons.append(numeric_reason)
        polarity_conflict = structured_comparable and context_compatible and negated != bool(best.get("negated")) and lexical_score >= 0.30
        if polarity_conflict:
            reasons.append("negation/polarity differs after subject, predicate, family, and context compatibility")

        if subject_ambiguous:
            state = "IDENTITY_UNCERTAIN"
            reasons.append("candidate subject resolves to multiple plausible 09D entities; support/contradiction suppressed")
        elif numeric_conflict or polarity_conflict:
            state = "CONTRADICTION"
            comparison_confidence = "HIGH" if family_explicit else "MEDIUM"
        elif structured_comparable and not context_compatible:
            state = "CONTEXT_DIFFERENCE"
            comparison_confidence = "HIGH" if subject_resolution_mode in {"EXPLICIT_ID", "EXACT_ALIAS"} else "MEDIUM"
            reasons.append(f"compatible identity/predicate but contextual qualifier sets differ (candidate {sorted(cand_context)} vs 09D {sorted(row_context)})")
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
                    f"retrieval only ({lexical_score:.2f}); support/contradiction suppressed because subject={subj_ok} ({subj_score:.2f}), predicate={pred_ok} ({pred_score:.2f}), family={family_ok}"
                )
        else:
            equal_numeric = bool(numbers) and numbers == best.get("numbers", set())
            no_numeric_either = not numbers and not best.get("numbers", set())
            if best_score >= 0.78 and context_compatible and (equal_numeric or no_numeric_either):
                state = "SUPPORT"
                comparison_confidence = "HIGH" if not subject_resolution_ambiguous else "MEDIUM"
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
        "comparison_receipt_schema_version": "09d-comparison-receipt-1.5",
        "candidate_id": candidate.get("candidate_id"),
        "source_unit_id": candidate.get("source_unit_id"),
        "origin_pass": candidate.get("origin_pass"),
        "proposition": proposition,
        "candidate_subject": candidate.get("subject"),
        "candidate_predicate": candidate.get("predicate"),
        "state": state,
        "comparison_confidence": comparison_confidence,
        "numeric_comparison_basis": numeric_basis,
        "subject_resolution": {
            "mode": subject_resolution_mode,
            "resolved_entity_ids": sorted(resolved_subject_ids),
            "ambiguous": subject_resolution_ambiguous,
        },
        "predicate_resolution": {"mode": predicate_resolution_mode},
        "reasons": reasons,
        "review_required": True,
        "top_matches": [
            {
                "score": round(score, 3),
                "lexical_score": round(lexical, 3),
                "subject_compatible": subj_ok,
                "predicate_compatible": pred_ok,
                "fact_family_compatible": family_ok,
                "fact_family_explicit_on_both": family_explicit,
                "carrier_candidate_id": carrier[i].get("carrier_candidate_id"),
                "subject_entity_id": carrier[i].get("subject_entity_id"),
                "predicate_code": carrier[i].get("predicate_code"),
                "fact_family": carrier[i].get("fact_family"),
                "witness_kind": carrier[i].get("witness_kind", "UNSPECIFIED_TEST_ROW"),
                "value_text": (carrier[i].get("value_text") or "")[:300],
            }
            for score, lexical, subj_ok, pred_ok, family_ok, family_explicit, _, _, i in top
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="compare_09d")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--carrier-scope", choices=["motion1", "all"], default="motion1",
                        help="default motion1 excludes prior Motion-2 extraction rows to prevent recursive support")
    parser.add_argument("--allow-target-drift", action="store_true",
                        help="proceed even if DB hash differs from the declared comparator target")
    parser.add_argument("--skip-db-hash", action="store_true",
                        help="skip full-file hash; comparison output records hash as NOT_MEASURED")
    args = parser.parse_args(argv)

    scope = "MOTION1_AUTHORITY" if args.carrier_scope == "motion1" else "ALL_CARRIER"
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
    capability = motion2_capability_readonly(db_path)
    if not capability.get("carrier_partition_valid"):
        print("09D carrier witness partition is unavailable or invalid; refusing authority comparison", file=sys.stderr)
        return 4

    carrier = load_carrier(db_path, scope=scope)
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

    summary = {
        "stage": "READ_ONLY_09D_COMPARISON",
        "comparison_schema_version": "09d-comparison-summary-1.5",
        "comparator_target": COMPARATOR_TARGET,
        "database_path": str(db_path),
        "database_sha256_measured": measured or "NOT_MEASURED",
        "database_matches_declared_target": target_match,
        "schema_fingerprint_sha256": capability.get("schema_fingerprint_sha256"),
        "motion2_capability": capability,
        "carrier_scope": scope,
        "carrier_scope_reason": CARRIER_SCOPES[scope][1],
        "cycle_safe_authority_comparison": scope == "MOTION1_AUTHORITY",
        "carrier_rows_compared_against": len(carrier),
        "candidate_count": len(candidates),
        "state_counts": dict(sorted(counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "duration_seconds": round(time.time() - started, 2),
        "method": (
            "Motion-1 authority-scoped comparison by default; exact searchable-entity alias and predicate resolution "
            "when available, structured numeric values preferred over proposition-wide number capture, then conservative "
            "retrieval. Contradiction requires compatible subject+predicate+family+context and unambiguous conflict."
        ),
        "claim_boundary": (
            "Every state is reviewable. SUPPORT/POSSIBLE_DUPLICATE do not canonicalize or merge a candidate; "
            "CONTRADICTION and MISSING_IN_09D do not invalidate one. 09D remained read-only throughout."
        ),
    }
    (out_dir / "comparison_09d_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in (
        "state_counts", "confidence_counts", "carrier_scope", "cycle_safe_authority_comparison",
        "candidate_count", "carrier_rows_compared_against", "database_matches_declared_target", "duration_seconds"
    )}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
