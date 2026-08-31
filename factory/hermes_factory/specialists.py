from __future__ import annotations
import re
import uuid
from typing import Dict, Iterable, List
from .literal import NUM_RE, QUALIFIER_PATTERNS, REL_PATTERNS
from .models import AssertionCandidate, EvidenceFamily, ReviewOutcome, SpecialistReceipt, SourceUnit


def _receipt(family: EvidenceFamily, kind: str, outcome: ReviewOutcome, rationale: str,
             unresolved: List[str] | None = None) -> SpecialistReceipt:
    return SpecialistReceipt(
        receipt_id="SP-" + uuid.uuid4().hex,
        family_id=family.family_id,
        specialist_type=kind,
        outcome=outcome.value,
        rationale=rationale,
        candidate_ids=list(family.member_candidate_ids),
        unresolved_flags=list(unresolved or []),
        worker_identity={"provider": "DETERMINISTIC", "model_alias": "hermes-specialist-rules", "underlying_family": "CODE", "observed_version": "1.1"},
        run_id="DETERMINISTIC",
    )


def numeric_binding_check(family: EvidenceFamily, candidates: Dict[str, AssertionCandidate]) -> SpecialistReceipt:
    members = [candidates[x] for x in family.member_candidate_ids]
    evidence = " ".join(m.evidence for m in members)
    literals = [m.group(0).strip() for m in NUM_RE.finditer(evidence)]
    if not literals:
        return _receipt(family, "NUMERIC_BINDING", ReviewOutcome.SUPPORTED, "No numeric literal in evidence; numeric specialist not applicable.")
    missing = []
    for literal in literals:
        if not any(literal in m.proposition for m in members):
            missing.append(literal)
    if missing:
        return _receipt(family, "NUMERIC_BINDING", ReviewOutcome.AMBIGUOUS_DEFER,
                        "Numeric literals in evidence are absent from proposition text; deterministic code cannot safely bind them.",
                        ["UNBOUND_NUMERIC:" + x for x in missing])
    return _receipt(family, "NUMERIC_BINDING", ReviewOutcome.SUPPORTED,
                    "All numeric literals present in evidence are preserved in at least one candidate proposition; semantic target binding remains model/human-reviewable where complex.")


def qualifier_scope_check(family: EvidenceFamily, candidates: Dict[str, AssertionCandidate]) -> SpecialistReceipt:
    members = [candidates[x] for x in family.member_candidate_ids]
    unresolved = []
    for m in members:
        for kind, pattern in QUALIFIER_PATTERNS.items():
            ev = [x.group(0).lower() for x in pattern.finditer(m.evidence)]
            if ev and not any(x in m.proposition.lower() for x in ev):
                unresolved.append(f"{m.candidate_id}:{kind}:QUALIFIER_NOT_PRESERVED")
    if unresolved:
        return _receipt(family, "QUALIFIER_SCOPE", ReviewOutcome.AMBIGUOUS_DEFER,
                        "At least one explicit qualifier cue was lost between evidence and proposition.", unresolved)
    return _receipt(family, "QUALIFIER_SCOPE", ReviewOutcome.SUPPORTED,
                    "Explicit qualifier cues in evidence are lexically preserved in candidate propositions. Scope semantics beyond lexical preservation are not overclaimed.")


def relationship_direction_check(family: EvidenceFamily, candidates: Dict[str, AssertionCandidate]) -> SpecialistReceipt:
    members = [candidates[x] for x in family.member_candidate_ids]
    unresolved = []
    for m in members:
        for kind, pattern in REL_PATTERNS:
            ev = [x.group(0).lower() for x in pattern.finditer(m.evidence)]
            if ev and not any(x in m.proposition.lower() for x in ev):
                unresolved.append(f"{m.candidate_id}:{kind}:DIRECTION_CUE_LOST")
    if unresolved:
        return _receipt(family, "RELATIONSHIP_DIRECTION", ReviewOutcome.AMBIGUOUS_DEFER,
                        "Directional relationship cue present in evidence was not preserved.", unresolved)
    return _receipt(family, "RELATIONSHIP_DIRECTION", ReviewOutcome.SUPPORTED,
                    "Directional lexical cues are preserved. Causal interpretation still requires semantic review when not explicit.")


def table_visual_check(family: EvidenceFamily, candidates: Dict[str, AssertionCandidate], unit: SourceUnit) -> SpecialistReceipt:
    if unit.content_representation == "TABLE":
        return _receipt(family, "TABLE_VISUAL", ReviewOutcome.AMBIGUOUS_DEFER,
                        "Table source detected. Text-layer preservation is insufficient to certify row/column semantic binding.",
                        ["TABLE_BINDING_REQUIRES_SEMANTIC_OR_VISUAL_REVIEW"])
    if unit.content_representation == "FIGURE":
        return _receipt(family, "TABLE_VISUAL", ReviewOutcome.AMBIGUOUS_DEFER,
                        "Figure/caption source detected. Caption semantics must not be treated as full image interpretation.",
                        ["IMAGE_AVAILABLE_NOT_MODEL_REVIEWED"])
    return _receipt(family, "TABLE_VISUAL", ReviewOutcome.SUPPORTED, "No table/figure binding required for this family.")


def cross_page_check(family: EvidenceFamily, candidates: Dict[str, AssertionCandidate], unit: SourceUnit) -> SpecialistReceipt:
    pages = unit.locator.get("pdf_pages", [])
    if len(pages) > 1 or unit.locator.get("cross_page"):
        return _receipt(family, "CROSS_PAGE_CONTEXT", ReviewOutcome.AMBIGUOUS_DEFER,
                        "Cross-page source unit detected; deterministic integrity is valid but semantic continuation must be reviewed.",
                        ["CROSS_PAGE_SEMANTIC_REVIEW_REQUIRED"])
    return _receipt(family, "CROSS_PAGE_CONTEXT", ReviewOutcome.SUPPORTED, "Single-page/local context.")


def run_deterministic_specialists(families: Iterable[EvidenceFamily], candidates: Iterable[AssertionCandidate], units: Iterable[SourceUnit]) -> List[SpecialistReceipt]:
    cdict = {c.candidate_id: c for c in candidates}
    udict = {u.source_unit_id: u for u in units}
    receipts: List[SpecialistReceipt] = []
    for family in families:
        unit = udict[family.source_unit_id]
        receipts.extend([
            numeric_binding_check(family, cdict),
            qualifier_scope_check(family, cdict),
            relationship_direction_check(family, cdict),
            table_visual_check(family, cdict, unit),
            cross_page_check(family, cdict, unit),
        ])
    return receipts
