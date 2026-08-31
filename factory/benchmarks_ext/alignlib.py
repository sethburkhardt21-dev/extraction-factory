"""Deterministic alignment primitives shared by gold construction and scoring.

Everything here is mechanical: token sets, Jaccard, greedy one-to-one
alignment. No model output is trusted as truth by this module; it only
measures agreement between texts.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

STOPWORDS = {
    "the", "and", "for", "are", "was", "were", "with", "that", "this", "from",
    "into", "when", "then", "than", "which", "will", "has", "have", "had",
    "its", "can", "may", "not", "but", "all", "any", "one", "two", "per",
    "each", "also", "there", "their", "them", "they", "been", "being", "such",
    "is", "at", "of", "to", "in", "on", "by", "as", "an", "it", "or", "be",
}


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9°%./]+", (text or "").lower())
    return {w for w in words if w not in STOPWORDS and len(w) >= 2}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / (len(a | b) or 1)


def greedy_align(
    left: List[Dict[str, Any]], right: List[Dict[str, Any]],
    key: str = "proposition", threshold: float = 0.5,
) -> Tuple[List[Tuple[int, int, float]], List[int], List[int]]:
    """One-to-one greedy alignment by descending similarity.

    Returns (pairs, unmatched_left_indexes, unmatched_right_indexes) where a
    pair is (left_index, right_index, score). Ties break deterministically on
    (score desc, left index, right index).
    """
    left_tokens = [tokens(x.get(key) or "") for x in left]
    right_tokens = [tokens(x.get(key) or "") for x in right]
    scored = []
    for i, lt in enumerate(left_tokens):
        for j, rt in enumerate(right_tokens):
            s = jaccard(lt, rt)
            if s >= threshold:
                scored.append((s, i, j))
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))
    used_left: set[int] = set()
    used_right: set[int] = set()
    pairs: List[Tuple[int, int, float]] = []
    for s, i, j in scored:
        if i in used_left or j in used_right:
            continue
        used_left.add(i)
        used_right.add(j)
        pairs.append((i, j, s))
    unmatched_left = [i for i in range(len(left)) if i not in used_left]
    unmatched_right = [j for j in range(len(right)) if j not in used_right]
    return pairs, unmatched_left, unmatched_right


def multi_match_counts(
    candidates: List[Dict[str, Any]], gold: List[Dict[str, Any]],
    key: str = "proposition", threshold: float = 0.5,
) -> List[int]:
    """For each candidate, how many gold rows it clears the threshold against
    (atomicity probe: >=2 suggests a compound candidate)."""
    gold_tokens = [tokens(x.get(key) or "") for x in gold]
    out = []
    for cand in candidates:
        ct = tokens(cand.get(key) or "")
        out.append(sum(1 for gt in gold_tokens if jaccard(ct, gt) >= threshold))
    return out
