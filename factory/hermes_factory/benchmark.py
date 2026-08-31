from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Iterable, List, Set
from .models import AssertionCandidate


def load_gold(path: Path) -> List[dict]:
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def score_exact_evidence(candidates: Iterable[AssertionCandidate], gold: Iterable[dict]) -> Dict:
    """Conservative exact-evidence baseline scorer.

    A richer semantic adjudication scorer may be layered on top, but this function
    never treats prior extraction agreement as gold.
    """
    cand_keys: Set[tuple[str, str]] = {(c.source_unit_id, c.evidence.strip()) for c in candidates}
    gold_list = list(gold)
    gold_keys: Set[tuple[str, str]] = {(g["source_unit_id"], g["evidence"].strip()) for g in gold_list}
    tp = len(cand_keys & gold_keys)
    fp = len(cand_keys - gold_keys)
    fn = len(gold_keys - cand_keys)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"true_positive": tp, "false_positive": fp, "false_negative": fn,
            "precision_exact_evidence": precision, "recall_exact_evidence": recall,
            "scorer": "EXACT_EVIDENCE_BASELINE", "semantic_equivalence_not_inferred": True}
