"""
Production Embedding Evaluation Metrics
Agent C5: Embedding Eval Developer - Swarm C Embedding Pipeline

Implements recall@k, MRR, NDCG, Precision@k, MAP with:
- Graded relevance support
- Bootstrap confidence intervals
- BEIR/MTEB compatible evaluation
- Anesthesia-specific benchmark handling

Best practices from search:
- Separate retrieval quality from answer quality
- Use nDCG@10 as primary, recall@k for first-stage
- Deterministic snippet-containment + graded relevance
- Bootstrap CIs for significance testing
"""

from __future__ import annotations
import math
import random
from typing import List, Dict, Set, Tuple, Optional, Union
from collections import defaultdict
import numpy as np

# ---------------------------------------------------------------------
# Core Metrics - Binary & Graded Relevance
# ---------------------------------------------------------------------

def _deduplicate_preserve_order(retrieved: List[str]) -> List[str]:
    """Remove duplicates from retrieved list preserving order (first occurrence)."""
    seen = set()
    out = []
    for doc_id in retrieved:
        if doc_id not in seen:
            seen.add(doc_id)
            out.append(doc_id)
    return out

def recall_at_k(
    retrieved: List[str],
    relevant: Union[Set[str], Dict[str, float], List[str]],
    k: int
) -> float:
    """
    Recall@k = |relevant ∩ retrieved[:k]| / |relevant|
    
    Args:
        retrieved: Ranked list of doc ids (ordered)
        relevant: Set of relevant doc ids OR dict {doc_id: relevance_score} OR list
        k: cutoff
    
    Returns:
        recall in [0,1]
    """
    if isinstance(relevant, dict):
        relevant_set = set(relevant.keys())
    elif isinstance(relevant, list):
        relevant_set = set(relevant)
    else:
        relevant_set = relevant
    
    if not relevant_set:
        return 0.0
    
    retrieved_k = _deduplicate_preserve_order(retrieved)[:k]
    retrieved_set = set(retrieved_k)
    hits = len(relevant_set & retrieved_set)
    return hits / len(relevant_set)

def precision_at_k(
    retrieved: List[str],
    relevant: Union[Set[str], Dict[str, float], List[str]],
    k: int
) -> float:
    """
    Precision@k = |relevant ∩ retrieved[:k]| / k
    """
    if isinstance(relevant, dict):
        relevant_set = set(relevant.keys())
    elif isinstance(relevant, list):
        relevant_set = set(relevant)
    else:
        relevant_set = relevant
    
    if k == 0:
        return 0.0
    retrieved_k = _deduplicate_preserve_order(retrieved)[:k]
    hits = len(relevant_set & set(retrieved_k))
    return hits / k

def reciprocal_rank(
    retrieved: List[str],
    relevant: Union[Set[str], Dict[str, float], List[str]]
) -> float:
    """
    Reciprocal rank for single query: 1 / rank_first_relevant
    Returns 0 if no relevant doc retrieved.
    """
    if isinstance(relevant, dict):
        relevant_set = set(relevant.keys())
    elif isinstance(relevant, list):
        relevant_set = set(relevant)
    else:
        relevant_set = relevant

    deduped = _deduplicate_preserve_order(retrieved)
    for idx, doc_id in enumerate(deduped, start=1):
        if doc_id in relevant_set:
            return 1.0 / idx
    return 0.0

def mrr(
    queries_results: Dict[str, Tuple[List[str], Union[Set[str], Dict[str, float]]]]
) -> float:
    """
    Mean Reciprocal Rank over queries.
    
    queries_results: {q_id: (retrieved_list, relevant_set/dict)}
    """
    if not queries_results:
        return 0.0
    total = 0.0
    for _, (retrieved, relevant) in queries_results.items():
        total += reciprocal_rank(retrieved, relevant)
    return total / len(queries_results)

def average_precision(
    retrieved: List[str],
    relevant: Union[Set[str], Dict[str, float], List[str]]
) -> float:
    """
    Average Precision (AP) for single query - area under precision-recall curve.
    """
    if isinstance(relevant, dict):
        relevant_set = set(relevant.keys())
    elif isinstance(relevant, list):
        relevant_set = set(relevant)
    else:
        relevant_set = relevant
    
    if not relevant_set:
        return 0.0
    
    deduped = _deduplicate_preserve_order(retrieved)
    hits = 0
    sum_prec = 0.0
    for idx, doc_id in enumerate(deduped, start=1):
        if doc_id in relevant_set:
            hits += 1
            sum_prec += hits / idx
    return sum_prec / len(relevant_set) if relevant_set else 0.0

def mean_average_precision(
    queries_results: Dict[str, Tuple[List[str], Union[Set[str], Dict[str, float]]]]
) -> float:
    """MAP over queries"""
    if not queries_results:
        return 0.0
    total = 0.0
    for retrieved, relevant in queries_results.values():
        total += average_precision(retrieved, relevant)
    return total / len(queries_results)

# ---------------------------------------------------------------------
# NDCG - Graded Relevance - Core MTEB / BEIR Primary Metric
# ---------------------------------------------------------------------

def dcg_at_k(
    retrieved: List[str],
    relevance_dict: Dict[str, float],
    k: int,
    method: int = 1
) -> float:
    """
    Discounted Cumulative Gain at k.
    
    method 0: rel_i / log2(i+1) - original
    method 1: (2^rel_i -1) / log2(i+1) - emphasizes high relevance (MTEB/BEIR standard)
    
    relevance_dict: {doc_id: grade} where grade >=0 (0=not relevant)
    retrieved: ranked list
    """
    deduped = _deduplicate_preserve_order(retrieved)[:k]
    dcg = 0.0
    for i, doc_id in enumerate(deduped, start=1):
        rel = relevance_dict.get(doc_id, 0.0)
        if rel <= 0:
            continue
        if method == 0:
            gain = rel
        else:  # method 1 - exponential gain
            gain = (2 ** rel - 1)
        # log2(i+1) discount; i is 1-indexed rank
        dcg += gain / math.log2(i + 1)
    return dcg

def ndcg_at_k(
    retrieved: List[str],
    relevance_dict: Union[Dict[str, float], Set[str], List[str]],
    k: int,
    method: int = 1
) -> float:
    """
    Normalized DCG@k = DCG@k / IDCG@k
    
    Handles binary relevance by converting set/list to {doc:1}
    Handles graded relevance via dict.
    
    Returns 0 if no relevant docs.
    Primary metric for MTEB/BEIR and our anesthesia benchmark.
    """
    # Normalize relevance input to dict
    if isinstance(relevance_dict, set):
        rel_dict = {doc_id: 1.0 for doc_id in relevance_dict}
    elif isinstance(relevance_dict, list):
        rel_dict = {doc_id: 1.0 for doc_id in relevance_dict}
    else:
        rel_dict = relevance_dict

    if not rel_dict or all(v <= 0 for v in rel_dict.values()):
        return 0.0

    dcg = dcg_at_k(retrieved, rel_dict, k, method=method)

    # Ideal DCG: sort relevant docs by descending relevance
    ideal_relevance_sorted = sorted(rel_dict.values(), reverse=True)
    # Construct ideal retrieved list that would achieve max DCG
    # IDCG doesn't depend on retrieved order, only relevance grades
    idcg = 0.0
    for i, rel in enumerate(ideal_relevance_sorted[:k], start=1):
        if rel <= 0:
            continue
        gain = rel if method == 0 else (2 ** rel - 1)
        idcg += gain / math.log2(i + 1)

    if idcg == 0:
        return 0.0
    return dcg / idcg

def ndcg_at_ks(
    retrieved: List[str],
    relevance_dict: Union[Dict[str, float], Set[str]],
    ks: List[int],
    method: int = 1
) -> Dict[int, float]:
    """Compute NDCG for multiple ks efficiently"""
    return {k: ndcg_at_k(retrieved, relevance_dict, k, method) for k in ks}

# ---------------------------------------------------------------------
# Aggregated Evaluation - Single call per benchmark
# ---------------------------------------------------------------------

def evaluate_retrieval(
    qrels: Dict[str, Union[Set[str], Dict[str, float]]],
    results: Dict[str, List[str]],
    k_values: List[int] = [1, 5, 10, 20, 100],
    method: int = 1
) -> Dict[str, float]:
    """
    BEIR-compatible evaluation: computes NDCG, MAP, Recall, Precision across ks.
    
    Args:
        qrels: {q_id: {doc_id: relevance} or set(doc_ids)}
        results: {q_id: [ranked doc_ids]}
        k_values: cutoffs
        method: DCG method
    
    Returns:
        dict with keys like "NDCG@10", "Recall@5", "MRR", "MAP" etc
    """
    metrics = defaultdict(list)
    # Per query detailed
    per_query = {}

    for q_id, relevant in qrels.items():
        retrieved = results.get(q_id, [])
        if not retrieved:
            # No results: all metrics 0 for this query
            for k in k_values:
                metrics[f"NDCG@{k}"].append(0.0)
                metrics[f"Recall@{k}"].append(0.0)
                metrics[f"Precision@{k}"].append(0.0)
            metrics["MRR"].append(0.0)
            metrics["MAP"].append(0.0)
            continue

        # Normalize relevant to dict for NDCG, set for binary
        if isinstance(relevant, dict):
            rel_dict = relevant
            rel_set = set(relevant.keys())
        elif isinstance(relevant, set):
            rel_dict = {d: 1.0 for d in relevant}
            rel_set = relevant
        else:  # list
            rel_dict = {d: 1.0 for d in relevant}
            rel_set = set(relevant)

        # Reciprocal rank & AP
        rr = reciprocal_rank(retrieved, rel_set)
        ap = average_precision(retrieved, rel_set)
        metrics["MRR"].append(rr)
        metrics["MAP"].append(ap)

        for k in k_values:
            metrics[f"NDCG@{k}"].append(ndcg_at_k(retrieved, rel_dict, k, method=method))
            metrics[f"Recall@{k}"].append(recall_at_k(retrieved, rel_set, k))
            metrics[f"Precision@{k}"].append(precision_at_k(retrieved, rel_set, k))
            metrics[f"Hit@{k}"].append(1.0 if recall_at_k(retrieved, rel_set, k) > 0 else 0.0)

        per_query[q_id] = {
            "rr": rr,
            "ap": ap,
        }

    # Aggregate mean
    aggregated = {metric: float(np.mean(values)) if values else 0.0 for metric, values in metrics.items()}
    # Also compute median and p90 for robustness
    for metric, values in metrics.items():
        if values:
            aggregated[f"{metric}_median"] = float(np.median(values))
            aggregated[f"{metric}_p90"] = float(np.percentile(values, 90))

    return aggregated

# ---------------------------------------------------------------------
# Bootstrap Confidence Intervals (MTEB practice)
# ---------------------------------------------------------------------

def bootstrap_confidence_interval(
    scores: List[float],
    n_bootstrap: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42
) -> Tuple[float, float, float]:
    """
    Bootstrap 95% CI for a metric.
    
    Returns (mean, lower, upper)
    """
    if not scores:
        return (0.0, 0.0, 0.0)
    rng = np.random.default_rng(seed)
    n = len(scores)
    bootstrap_means = []
    for _ in range(n_bootstrap):
        sample = rng.choice(scores, size=n, replace=True)
        bootstrap_means.append(float(np.mean(sample)))
    lower_pct = (1 - confidence_level) / 2 * 100
    upper_pct = (1 + confidence_level) / 2 * 100
    mean = float(np.mean(scores))
    lower = float(np.percentile(bootstrap_means, lower_pct))
    upper = float(np.percentile(bootstrap_means, upper_pct))
    return (mean, lower, upper)

def evaluate_with_ci(
    qrels: Dict[str, Union[Set[str], Dict[str, float]]],
    results: Dict[str, List[str]],
    k_values: List[int] = [5, 10],
    n_bootstrap: int = 1000
) -> Dict[str, Dict[str, float]]:
    """
    Evaluate with bootstrap CI - returns mean + CI per metric
    """
    # Collect per-query scores
    per_query_scores: Dict[str, List[float]] = defaultdict(list)
    per_query_map: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

    # Actually need per-query lists for each metric
    metric_per_query: Dict[str, List[float]] = defaultdict(list)

    for q_id, relevant in qrels.items():
        retrieved = results.get(q_id, [])
        if isinstance(relevant, dict):
            rel_dict = relevant
            rel_set = set(relevant.keys())
        else:
            rel_set = set(relevant) if isinstance(relevant, set) else set(relevant)
            rel_dict = {d: 1.0 for d in rel_set}

        metric_per_query["MRR"].append(reciprocal_rank(retrieved, rel_set))
        metric_per_query["MAP"].append(average_precision(retrieved, rel_set))
        for k in k_values:
            metric_per_query[f"NDCG@{k}"].append(ndcg_at_k(retrieved, rel_dict, k))
            metric_per_query[f"Recall@{k}"].append(recall_at_k(retrieved, rel_set, k))
            metric_per_query[f"Precision@{k}"].append(precision_at_k(retrieved, rel_set, k))

    result_with_ci = {}
    for metric_name, scores in metric_per_query.items():
        mean, lower, upper = bootstrap_confidence_interval(scores, n_bootstrap=n_bootstrap)
        result_with_ci[metric_name] = {
            "mean": mean,
            "ci_lower": lower,
            "ci_upper": upper,
            "ci_width": upper - lower,
            "n_queries": len(scores)
        }
    return result_with_ci

# ---------------------------------------------------------------------
# Embedding-specific utilities
# ---------------------------------------------------------------------

def cosine_similarity_search(
    query_embedding: np.ndarray,
    corpus_embeddings: np.ndarray,
    corpus_ids: List[str],
    top_k: int = 10,
) -> List[str]:
    """
    Brute-force cosine similarity retrieval (for evaluation).
    Production would use FAISS/HNSW.
    
    query_embedding: [dim] or [1, dim]
    corpus_embeddings: [N, dim] L2-normalized ideally
    """
    if query_embedding.ndim == 1:
        query_embedding = query_embedding.reshape(1, -1)
    
    # L2 normalize if not already
    q_norm = query_embedding / (np.linalg.norm(query_embedding, axis=1, keepdims=True) + 1e-12)
    c_norm = corpus_embeddings / (np.linalg.norm(corpus_embeddings, axis=1, keepdims=True) + 1e-12)

    # Cosine similarity = dot of normalized
    scores = c_norm @ q_norm.T  # [N, 1]
    scores = scores.flatten()

    # Top-k indices
    if top_k >= len(scores):
        top_indices = np.argsort(-scores)
    else:
        # argpartition for efficiency
        top_indices = np.argpartition(-scores, top_k)[:top_k]
        top_indices = top_indices[np.argsort(-scores[top_indices])]

    return [corpus_ids[i] for i in top_indices]

def evaluate_embedding_model(
    query_embeddings: Dict[str, np.ndarray],  # q_id -> embedding
    corpus_embeddings: np.ndarray,
    corpus_ids: List[str],
    qrels: Dict[str, Union[Set[str], Dict[str, float]]],
    k_values: List[int] = [1,5,10,20,100],
    top_k_for_retrieval: int = 100,
) -> Dict[str, float]:
    """
    End-to-end embedding evaluation: embed queries -> retrieve -> compute metrics
    
    Use this to benchmark PubMedBERT, AnesBERT, general embeddings on anesthesia queries.
    """
    results: Dict[str, List[str]] = {}
    for q_id, q_emb in query_embeddings.items():
        retrieved = cosine_similarity_search(q_emb, corpus_embeddings, corpus_ids, top_k=top_k_for_retrieval)
        results[q_id] = retrieved

    return evaluate_retrieval(qrels, results, k_values=k_values)

# ---------------------------------------------------------------------
# Significance testing - Paired bootstrap to compare two systems
# ---------------------------------------------------------------------

def paired_significance_test(
    scores_a: List[float],
    scores_b: List[float],
    n_bootstrap: int = 1000,
    seed: int = 42
) -> Dict[str, float]:
    """
    Paired bootstrap test comparing system A vs B per-query scores.
    
    Returns p-value approx: proportion of bootstrap where mean(B) <= mean(A) if we expect B>A
    Implementation: bootstrap difference distribution.
    """
    assert len(scores_a) == len(scores_b)
    rng = np.random.default_rng(seed)
    n = len(scores_a)
    diffs = np.array(scores_b) - np.array(scores_a)
    mean_diff = float(np.mean(diffs))
    
    # Bootstrap distribution of mean diff under resampling
    bootstrap_diffs = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        bootstrap_diffs.append(float(np.mean(diffs[idx])))
    
    bootstrap_diffs = np.array(bootstrap_diffs)
    # Two-sided p-value: proportion with opposite sign to observed
    if mean_diff >= 0:
        p_val = float(np.mean(bootstrap_diffs <= 0))
    else:
        p_val = float(np.mean(bootstrap_diffs >= 0))
    # Two-sided
    p_val_two_sided = min(2 * p_val, 1.0)
    
    return {
        "mean_diff_b_minus_a": mean_diff,
        "p_value_one_sided": p_val,
        "p_value_two_sided": p_val_two_sided,
        "ci_lower_diff": float(np.percentile(bootstrap_diffs, 2.5)),
        "ci_upper_diff": float(np.percentile(bootstrap_diffs, 97.5)),
        "significant_95": p_val_two_sided < 0.05
    }
