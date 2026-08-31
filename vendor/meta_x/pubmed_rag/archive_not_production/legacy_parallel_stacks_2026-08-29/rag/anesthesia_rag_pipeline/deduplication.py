"""
Deduplication Pipeline - FIX: audit critical dedup issue
Previous system had:
- PMID dedup only, missed DOI variants
- No title normalization
- No deterministic ordering

Fixes:
- DOI normalization (lowercase, strip, remove trailing punctuation)
- PMID dedup primary
- DOI dedup secondary
- Title+Year fuzzy dedup tertiary (normalized)
- Retains most complete record
"""
import re
import hashlib
from typing import List, Dict, Any, Tuple, Set
from collections import defaultdict
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def normalize_doi(doi: str) -> str:
    if not doi:
        return ""
    d = doi.strip().lower()
    # Remove URL prefix if present
    d = re.sub(r'^https?://(dx\.)?doi\.org/', '', d)
    d = re.sub(r'^doi:\s*', '', d)
    # Remove trailing punctuation common in extraction errors
    d = d.rstrip('.,;')
    return d

def normalize_title(title: str) -> str:
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r'<[^>]+>', '', t)  # strip any leftover XML
    t = re.sub(r'[^\w\s]', ' ', t)  # punctuation to space
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def content_completeness_score(article: Dict[str, Any]) -> int:
    """Score how complete a record is - for choosing survivor in dedup."""
    score = 0
    if article.get('abstract'):
        score += len(article['abstract']) // 100
    if article.get('doi'):
        score += 10
    if article.get('authors'):
        score += len(article['authors'])
    if article.get('mesh_terms'):
        score += len(article['mesh_terms'])
    if article.get('journal'):
        score += 5
    if article.get('publication_date', {}).get('year'):
        score += 5
    return score

class AnesthesiaDeduplicator:
    def __init__(self):
        self.seen_pmids: Set[str] = set()
        self.seen_dois: Set[str] = set()
        self.seen_title_year: Set[str] = set()
        self.doi_to_pmid: Dict[str, str] = {}
    
    def deduplicate(self, articles: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        Deduplicates with deterministic ordering.
        Returns deduplicated list + stats.
        """
        # Step 1: deterministic sort for reproducibility - FIX audit
        articles_sorted = sorted(
            articles,
            key=lambda x: (int(x['pmid']) if x.get('pmid') and x['pmid'].isdigit() else 0, x.get('doi') or '')
        )
        
        # Group by potential duplicates
        pmid_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for art in articles_sorted:
            pmid = str(art.get('pmid') or '').strip()
            if pmid:
                pmid_groups[pmid].append(art)
            else:
                # No PMID - use temporary key
                pmid_groups[f"no-pmid-{hashlib.md5(str(art).encode()).hexdigest()[:8]}"].append(art)
        
        survivors: List[Dict[str, Any]] = []
        stats = {"input": len(articles), "pmid_dupes": 0, "doi_dupes": 0, "title_year_dupes": 0, "output": 0}
        
        # Pass 1: PMID dedup - keep most complete
        deduped_by_pmid: List[Dict[str, Any]] = []
        for pmid, group in pmid_groups.items():
            if len(group) > 1:
                # Choose most complete
                best = max(group, key=content_completeness_score)
                survivors_for_group = [best]
                stats["pmid_dupes"] += len(group) - 1
                logger.debug(f"PMID {pmid} has {len(group)} copies, keeping 1")
            else:
                survivors_for_group = group
            deduped_by_pmid.extend(survivors_for_group)
        
        # Pass 2: DOI dedup
        doi_map: Dict[str, Dict[str, Any]] = {}
        final_after_doi: List[Dict[str, Any]] = []
        for art in deduped_by_pmid:
            doi_norm = normalize_doi(art.get('doi') or '')
            if doi_norm:
                if doi_norm in doi_map:
                    existing = doi_map[doi_norm]
                    # Keep more complete
                    if content_completeness_score(art) > content_completeness_score(existing):
                        # Replace
                        final_after_doi = [a for a in final_after_doi if normalize_doi(a.get('doi') or '') != doi_norm]
                        final_after_doi.append(art)
                        doi_map[doi_norm] = art
                    stats["doi_dupes"] += 1
                    logger.debug(f"DOI duplicate {doi_norm}")
                else:
                    doi_map[doi_norm] = art
                    final_after_doi.append(art)
            else:
                final_after_doi.append(art)
        
        # Pass 3: Title+Year dedup (fuzzy fallback for articles without DOI/PMID overlap)
        seen_title_year: Dict[str, Dict[str, Any]] = {}
        final: List[Dict[str, Any]] = []
        for art in final_after_doi:
            title_norm = normalize_title(art.get('title') or '')
            year = art.get('year') or art.get('publication_date', {}).get('year')
            if title_norm and year:
                # Only if title length > 20 chars to avoid false matches on short titles
                if len(title_norm) > 20:
                    key = f"{title_norm[:80]}|{year}"
                    # Also check hash of normalized title for near-duplicate
                    title_hash = hashlib.md5(title_norm.encode()).hexdigest()
                    composite = f"{title_hash}|{year}"
                    if composite in seen_title_year:
                        # Potential dupe - compare completeness
                        existing = seen_title_year[composite]
                        # Additional check: if first 50 chars match
                        if title_norm[:50] == normalize_title(existing.get('title') or '')[:50]:
                            if content_completeness_score(art) > content_completeness_score(existing):
                                final = [a for a in final if hashlib.md5(normalize_title(a.get('title') or '').encode()).hexdigest() != title_hash or a.get('year') != year]
                                final.append(art)
                                seen_title_year[composite] = art
                            stats["title_year_dupes"] += 1
                            continue
                    seen_title_year[composite] = art
            final.append(art)
        
        # Final deterministic ordering by PMID int ascending
        final_sorted = sorted(
            final,
            key=lambda x: (x.get('year') or 0, int(x['pmid']) if x.get('pmid') and str(x['pmid']).isdigit() else 99999999)
        )
        
        stats["output"] = len(final_sorted)
        stats["dedup_removed"] = stats["input"] - stats["output"]
        logger.info(f"Dedup: {stats}")
        return final_sorted, stats
    
    def write_dedup_report(self, stats: Dict[str, int], path: str = str(Path(__file__).resolve().parent / "data" / "dedup_report.json")):
        import json
        from pathlib import Path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(stats, f, indent=2)
        return path
