"""
Embedding Engine - Production semantic embedding with caching, batching, multi-provider
Fixes: caching to avoid re-embedding identical queries, batch support, dimension handling
"""
import hashlib
import logging
from typing import List, Dict, Optional, Union
import numpy as np
from collections import OrderedDict
import time
import threading

from .config import settings

logger = logging.getLogger(__name__)

class LRUCache:
    """Simple LRU cache for embeddings - prod would use Redis"""
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def _key(self, text: str, model: str) -> str:
        h = hashlib.sha256(f"{model}::{text}".encode()).hexdigest()
        return h

    def get(self, text: str, model: str) -> Optional[List[float]]:
        k = self._key(text, model)
        with self.lock:
            if k in self.cache:
                self.cache.move_to_end(k)
                return self.cache[k]
        return None

    def set(self, text: str, model: str, embedding: List[float]):
        k = self._key(text, model)
        with self.lock:
            self.cache[k] = embedding
            self.cache.move_to_end(k)
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)

class EmbeddingEngine:
    def __init__(self, provider: Optional[str] = None, model_name: Optional[str] = None):
        self.provider = provider or settings.embedding_provider
        self.model_name = model_name or settings.embedding_model_name
        self.dim = settings.embedding_dim
        self.cache = LRUCache(max_size=settings.embedding_cache_size)
        self._model = None  # lazy load
        self._openai_client = None
        self._load_model()

    def _load_model(self):
        if self.provider == "sentence_transformers":
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading embedding model {self.model_name}")
                self._model = SentenceTransformer(self.model_name)
                # Update dim from actual model
                self.dim = self._model.get_sentence_embedding_dimension()
                logger.info(f"Embedding dim: {self.dim}")
            except ImportError:
                logger.warning("sentence_transformers not installed, falling back to hashing embedding for dev")
                self._model = None
        elif self.provider == "openai":
            try:
                from openai import OpenAI
                if not settings.openai_api_key:
                    raise ValueError("OPENAI_API_KEY not set")
                self._openai_client = OpenAI(api_key=settings.openai_api_key)
                # Adjust dim for openai
                self.dim = 1536 if "small" in settings.openai_embedding_model else 3072
            except ImportError:
                logger.error("openai package not installed")
                raise

    def _hash_embedding(self, text: str) -> List[float]:
        """Fallback deterministic embedding for testing without model"""
        h = hashlib.sha256(text.encode()).digest()
        # Create pseudo embedding by repeating hash
        vec = []
        for i in range(0, self.dim):
            # Use hash bytes to generate float -1 to 1
            byte_val = h[i % len(h)]
            vec.append((byte_val / 127.5) - 1.0)
        # Normalize
        arr = np.array(vec)
        norm = np.linalg.norm(arr) + 1e-9
        return (arr / norm).tolist()

    def embed_text(self, text: str, use_cache: bool = True) -> List[float]:
        if not text or not text.strip():
            return [0.0] * self.dim
        text_clean = text.strip()[:8000]  # truncate for model limits
        if use_cache:
            cached = self.cache.get(text_clean, self.model_name)
            if cached is not None:
                return cached

        if self.provider == "sentence_transformers" and self._model is not None:
            emb = self._model.encode(text_clean, normalize_embeddings=True).tolist()
        elif self.provider == "openai" and self._openai_client is not None:
            resp = self._openai_client.embeddings.create(
                model=settings.openai_embedding_model,
                input=text_clean
            )
            emb = resp.data[0].embedding
        else:
            emb = self._hash_embedding(text_clean)

        if use_cache:
            self.cache.set(text_clean, self.model_name, emb)
        return emb

    def embed_batch(self, texts: List[str], batch_size: int = 32, use_cache: bool = True) -> List[List[float]]:
        """Batch embedding with caching - production best practice"""
        if not texts:
            return []

        # Separate cached vs need to compute
        results: List[Optional[List[float]]] = [None] * len(texts)
        to_compute: List[str] = []
        to_compute_idx: List[int] = []

        for idx, txt in enumerate(texts):
            clean = txt.strip()[:8000] if txt else ""
            if use_cache and clean:
                cached = self.cache.get(clean, self.model_name)
                if cached is not None:
                    results[idx] = cached
                    continue
            to_compute.append(clean)
            to_compute_idx.append(idx)

        if to_compute:
            if self.provider == "sentence_transformers" and self._model is not None:
                # Encode in batches using model
                for i in range(0, len(to_compute), batch_size):
                    batch_texts = to_compute[i:i+batch_size]
                    embeddings = self._model.encode(batch_texts, normalize_embeddings=True, show_progress_bar=False)
                    for j, emb in enumerate(embeddings):
                        emb_list = emb.tolist()
                        global_idx = to_compute_idx[i + j]
                        results[global_idx] = emb_list
                        # Cache
                        if use_cache:
                            self.cache.set(batch_texts[j], self.model_name, emb_list)
            else:
                # Fallback sequential
                for text, g_idx in zip(to_compute, to_compute_idx):
                    emb = self.embed_text(text, use_cache=use_cache)
                    results[g_idx] = emb

        # Fill any None (empty strings)
        for idx in range(len(results)):
            if results[idx] is None:
                results[idx] = [0.0] * self.dim

        return results  # type: ignore

    def embed_paper(self, title: str, abstract: str, mesh_terms: Optional[List[str]] = None) -> List[float]:
        """Create composite embedding for paper: title + abstract + MeSH"""
        parts = [title]
        if abstract:
            parts.append(abstract[:6000])  # limit abstract length
        if mesh_terms:
            parts.append("MeSH: " + ", ".join(mesh_terms))
        composite = " ".join(parts)
        return self.embed_text(composite)

    def cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Cosine similarity - vectors assumed normalized if using ST"""
        av = np.array(a)
        bv = np.array(b)
        # If already normalized, dot product = cosine
        dot = float(np.dot(av, bv))
        return dot

# Global singleton for API
_embedding_engine: Optional[EmbeddingEngine] = None

def get_embedding_engine() -> EmbeddingEngine:
    global _embedding_engine
    if _embedding_engine is None:
        _embedding_engine = EmbeddingEngine()
    return _embedding_engine
