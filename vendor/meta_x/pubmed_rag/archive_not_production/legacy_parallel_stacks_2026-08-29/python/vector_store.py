"""
Vector Store - Production abstraction for semantic search with metadata filtering
Supports: memory (brute force numpy), faiss (ANN), pinecone optional
Features: filter by subdomain, study_type, year, journal, relevance threshold
"""
import json
import logging
import threading
from typing import List, Dict, Optional, Tuple, Any
import numpy as np
import os

from .models import PubMedArticle, SearchFilter, Subdomain, StudyType
from .config import settings

logger = logging.getLogger(__name__)

class VectorStore:
    def __init__(self, embedding_dim: int = None):
        self.dim = embedding_dim or settings.embedding_dim
        self.lock = threading.RLock()
        # In-memory storage
        self.articles: Dict[str, PubMedArticle] = {}  # pmid -> article
        self.embeddings: Dict[str, np.ndarray] = {}  # pmid -> normalized vector
        self._faiss_index = None
        self._use_faiss = False
        if settings.vector_store_type == "faiss":
            self._init_faiss()

    def _init_faiss(self):
        try:
            import faiss
            self._faiss_index = faiss.IndexFlatIP(self.dim)  # inner product for cosine (normalized)
            self._use_faiss = True
            # Try load existing
            if os.path.exists(settings.faiss_index_path):
                self._faiss_index = faiss.read_index(settings.faiss_index_path)
                logger.info(f"Loaded FAISS index from {settings.faiss_index_path}, ntotal={self._faiss_index.ntotal}")
            # Also load metadata
            if os.path.exists(settings.metadata_path):
                with open(settings.metadata_path, "r") as f:
                    for line in f:
                        try:
                            data = json.loads(line)
                            # Minimal reconstruction - would need full model
                            self.articles[data['pmid']] = data  # store dict initially
                        except:
                            continue
            logger.info("FAISS initialized")
        except ImportError:
            logger.warning("faiss-cpu not installed, falling back to memory")
            self._use_faiss = False

    def _normalize(self, vec: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vec) + 1e-9
        return vec / norm

    def add_article(self, article: PubMedArticle):
        """Add single article with dedup check - FIX audit"""
        with self.lock:
            if article.pmid in self.articles:
                logger.debug(f"PMID {article.pmid} already exists, skipping")
                return False

            # Additional dedup by hash
            for existing in self.articles.values():
                if isinstance(existing, dict):
                    continue
                if existing.hash_dedup and article.hash_dedup and existing.hash_dedup == article.hash_dedup:
                    logger.info(f"Dedup by hash {article.hash_dedup} pmid {article.pmid} vs {existing.pmid}")
                    return False
                # DOI dedup
                if article.doi_normalized and existing.doi_normalized and article.doi_normalized == existing.doi_normalized:
                    logger.info(f"Dedup by DOI {article.doi_normalized}")
                    return False

            self.articles[article.pmid] = article
            if article.embedding:
                vec = np.array(article.embedding, dtype=np.float32)
                vec = self._normalize(vec)
                self.embeddings[article.pmid] = vec
                if self._use_faiss and self._faiss_index is not None:
                    # FAISS add
                    self._faiss_index.add(vec.reshape(1, -1).astype('float32'))
            return True

    def add_articles(self, articles: List[PubMedArticle]) -> Tuple[int, int]:
        """Batch add with dedup stats"""
        added = 0
        skipped = 0
        for art in articles:
            if self.add_article(art):
                added += 1
            else:
                skipped += 1
        logger.info(f"Vector store add batch: added {added}, skipped (dup) {skipped}")
        return added, skipped

    def _matches_filter(self, article: PubMedArticle, filters: Optional[SearchFilter]) -> bool:
        if not filters:
            return True
        # Handle dict case (if loaded from json)
        if isinstance(article, dict):
            # Convert dict to checks
            sub = article.get('subdomain')
            st = article.get('study_type')
            year = article.get('pub_year')
            journal = article.get('journal')
            relevance = article.get('anesthesia_relevance_score', 0)
        else:
            sub = article.subdomain.value if hasattr(article.subdomain, 'value') else str(article.subdomain)
            st = article.study_type.value if hasattr(article.study_type, 'value') else str(article.study_type)
            year = article.pub_year
            journal = article.journal
            relevance = article.anesthesia_relevance_score

        # Subdomain filter - supports single or list
        if filters.subdomain:
            wanted = filters.subdomain.value if hasattr(filters.subdomain, 'value') else filters.subdomain
            if sub != wanted:
                return False
        if filters.subdomains:
            wanted_list = [s.value if hasattr(s, 'value') else s for s in filters.subdomains]
            if sub not in wanted_list:
                return False

        # Study type
        if filters.study_type:
            wanted = filters.study_type.value if hasattr(filters.study_type, 'value') else filters.study_type
            if st != wanted:
                return False
        if filters.study_types:
            wanted_list = [s.value if hasattr(s, 'value') else s for s in filters.study_types]
            if st not in wanted_list:
                return False

        # Year range
        if filters.year_from and year:
            if year < filters.year_from:
                return False
        if filters.year_to and year:
            if year > filters.year_to:
                return False

        # Journal filter substring
        if filters.journal and journal:
            if filters.journal.lower() not in journal.lower():
                return False

        # Min relevance
        if filters.min_relevance is not None:
            if relevance < filters.min_relevance:
                return False

        return True

    def search(self, query_embedding: List[float], top_k: int = 10, filters: Optional[SearchFilter] = None, min_similarity: float = 0.0) -> List[Tuple[PubMedArticle, float]]:
        """
        Semantic search: query embedding -> top-k with filters
        Returns list of (article, similarity)
        """
        with self.lock:
            if not self.embeddings:
                return []

            q_vec = np.array(query_embedding, dtype=np.float32)
            q_vec = self._normalize(q_vec)

            candidates: List[Tuple[PubMedArticle, float]] = []

            if self._use_faiss and self._faiss_index is not None and self._faiss_index.ntotal > 0:
                # FAISS search - brute for filtering we need to over-fetch then filter
                # Over-fetch 3x to allow filtering
                over_fetch = min(top_k * 3, len(self.articles))
                # Simple case: we have pmid ordering? FAISS doesn't store metadata, so we need to maintain mapping
                # For production with FAISS, maintain id map
                # Here for simplicity, if FAISS, we fallback to in-memory filtered brute force when filters present
                if filters:
                    # Brute force filtered
                    pass
                else:
                    D, I = self._faiss_index.search(q_vec.reshape(1, -1).astype('float32'), over_fetch)
                    # Need id mapping - we would need list of pmids in insertion order
                    # For this implementation, we will use brute force to guarantee correct filtering
                    pass

            # Brute force with filtering - correct for production unless huge index
            # For max anesthesia extraction (maybe 50k papers), brute force is okay, or use FAISS with metadata filtering
            pmids = list(self.embeddings.keys())
            if not pmids:
                return []

            mat = np.stack([self.embeddings[pid] for pid in pmids])  # (N, dim)
            # Cosine similarity (vectors normalized)
            sims = mat @ q_vec  # (N,)

            # Build candidate list with filtering
            for pid, sim in zip(pmids, sims):
                if sim < min_similarity:
                    continue
                art = self.articles.get(pid)
                if art is None:
                    continue
                if not self._matches_filter(art, filters):
                    continue
                candidates.append((art, float(sim)))

            # Sort by similarity desc
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[:top_k]

    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            sub_counts = {}
            study_counts = {}
            year_min = None
            year_max = None
            for art in self.articles.values():
                if isinstance(art, dict):
                    sub = art.get('subdomain', 'other')
                    st = art.get('study_type', 'other')
                    yr = art.get('pub_year')
                else:
                    sub = art.subdomain.value if hasattr(art.subdomain, 'value') else str(art.subdomain)
                    st = art.study_type.value if hasattr(art.study_type, 'value') else str(art.study_type)
                    yr = art.pub_year
                sub_counts[sub] = sub_counts.get(sub, 0) + 1
                study_counts[st] = study_counts.get(st, 0) + 1
                if yr:
                    if year_min is None or yr < year_min:
                        year_min = yr
                    if year_max is None or yr > year_max:
                        year_max = yr

            return {
                "total_papers": len(self.articles),
                "total_embeddings": len(self.embeddings),
                "subdomain_counts": sub_counts,
                "study_type_counts": study_counts,
                "year_range": {"min": year_min, "max": year_max},
                "index_type": settings.vector_store_type,
                "dim": self.dim
            }

    def save(self):
        """Persist index + metadata"""
        if self._use_faiss and self._faiss_index is not None:
            try:
                import faiss
                faiss.write_index(self._faiss_index, settings.faiss_index_path)
                logger.info(f"Saved FAISS index to {settings.faiss_index_path}")
            except Exception as e:
                logger.error(f"Failed to save FAISS index: {e}")

        # Save metadata as JSONL
        try:
            with open(settings.metadata_path, "w") as f:
                for art in self.articles.values():
                    if isinstance(art, dict):
                        f.write(json.dumps(art) + "\n")
                    else:
                        # Exclude embedding for storage efficiency? Keep trimmed
                        data = art.model_dump(exclude={"embedding"})
                        f.write(json.dumps(data) + "\n")
            logger.info(f"Saved metadata to {settings.metadata_path}")
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")

    def load_from_jsonl(self, path: str, embedding_engine=None):
        """Load from JSONL with optional re-embedding"""
        count = 0
        with open(path, "r") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    # If embeddings missing and engine provided, generate
                    if embedding_engine and not data.get("embedding"):
                        emb = embedding_engine.embed_paper(data.get("title",""), data.get("abstract",""), data.get("mesh_terms"))
                        data["embedding"] = emb
                    # Reconstruct PubMedArticle if possible
                    try:
                        art = PubMedArticle(**data)
                    except:
                        # Fallback store dict
                        art = data
                    # Use internal dict for storage compatibility
                    if isinstance(art, PubMedArticle):
                        self.articles[art.pmid] = art
                        if art.embedding:
                            vec = np.array(art.embedding, dtype=np.float32)
                            self.embeddings[art.pmid] = self._normalize(vec)
                    else:
                        self.articles[art['pmid']] = art
                        if art.get('embedding'):
                            vec = np.array(art['embedding'], dtype=np.float32)
                            self.embeddings[art['pmid']] = self._normalize(vec)
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to load line: {e}")
                    continue
        logger.info(f"Loaded {count} papers from {path}")
        return count

# Global singleton
_vector_store: Optional[VectorStore] = None

def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
