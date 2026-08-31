"""
Ingestion Pipeline - Production pipeline for max anesthesia PubMed extraction
Fixes all audit issues in one flow:
- Rate limits, backoff, dedup (PMID + hash + DOI)
- MedlineDate fallback
- Structured abstract preservation
- CollectiveName handling
- Classification FP reduction
- Embedding + vector store
"""
import logging
import time
from typing import List, Optional
from .pubmed_client import PubMedClient
from .anesthesia_classifier import AnesthesiaClassifier
from .embedding_engine import get_embedding_engine
from .vector_store import get_vector_store
from .models import PubMedArticle
from .config import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class AnesthesiaIngestionPipeline:
    def __init__(self):
        self.pubmed = PubMedClient()
        self.embedding_engine = get_embedding_engine()
        self.classifier = AnesthesiaClassifier(embedding_engine=self.embedding_engine)
        self.vector_store = get_vector_store()

    def ingest_pmids(self, pmids: List[str], generate_embeddings: bool = True, filter_fp: bool = True, batch_size: int = 50) -> List[PubMedArticle]:
        """Ingest by PMID list with full audit fixes"""
        logger.info(f"Ingesting {len(pmids)} PMIDs")
        all_articles = self.pubmed.fetch_by_pmids(pmids)
        logger.info(f"Fetched {len(all_articles)} articles after dedup")

        # Classification - FP reduction
        classified = self.classifier.classify_batch(all_articles)
        if filter_fp:
            filtered = [a for a in classified if a.is_anesthesia_core]
            logger.info(f"After FP filter: {len(filtered)}/{len(classified)} kept ({len(classified)-len(filtered)} FP removed)")
            classified = filtered

        # Embedding
        if generate_embeddings:
            texts = [f"{a.title} {a.abstract}" for a in classified]
            embeddings = self.embedding_engine.embed_batch(texts, batch_size=batch_size)
            for art, emb in zip(classified, embeddings):
                art.embedding = emb
                art.embedding_model = self.embedding_engine.model_name

        # Vector store add
        added, skipped = self.vector_store.add_articles(classified)
        logger.info(f"Vector store: added {added}, skipped {skipped}")

        return classified

    def ingest_query(self, query: str, retmax: int = 500, generate_embeddings: bool = True, filter_fp: bool = True) -> List[PubMedArticle]:
        """Ingest by PubMed query (e.g., anesthesia MeSH)"""
        logger.info(f"Searching PubMed query: {query} retmax={retmax}")
        # Paginated esearch to handle max extraction
        all_pmids = []
        retstart = 0
        batch = 500
        total = None
        while retstart < retmax:
            remaining = min(batch, retmax - retstart)
            pmids, count = self.pubmed.esearch(query, retmax=remaining, retstart=retstart)
            if total is None:
                total = count
                logger.info(f"Total results in PubMed for query: {total}")
            if not pmids:
                break
            all_pmids.extend(pmids)
            retstart += len(pmids)
            if len(pmids) < remaining:
                break
            time.sleep(0.5)  # polite

        # Dedup pmids from esearch overlap (journal overlapping)
        all_pmids = list(dict.fromkeys(all_pmids))  # preserve order, dedup
        logger.info(f"Collected {len(all_pmids)} unique PMIDs for ingestion")
        return self.ingest_pmids(all_pmids, generate_embeddings=generate_embeddings, filter_fp=filter_fp)

    def ingest_max_anesthesia(self) -> List[PubMedArticle]:
        """Max anesthesia extraction - combines multiple high-recall queries with dedup"""
        queries = [
            # High precision MeSH queries
            '("Anesthesia"[Mesh] OR "Anesthesiology"[Mesh]) AND (hasabstract)',
            '("Anesthesia, General"[Mesh] OR "Anesthesia, Intravenous"[Mesh] OR "Anesthesia, Inhalation"[Mesh])',
            '("Anesthesia, Conduction"[Mesh] OR "Nerve Block"[Mesh] OR "Anesthesia, Epidural"[Mesh] OR "Anesthesia, Spinal"[Mesh])',
            '("Anesthetics"[Mesh] OR "Analgesia"[Mesh]) AND (anesthesia)',
            # Subdomain queries
            '("Pediatric Anesthesia" OR "Obstetric Anesthesia" OR "Cardiac Anesthesia" OR "Neuroanesthesia")',
            '("Pain Management"[Mesh] AND "Anesthesia"[Mesh])',
            '("Airway Management"[Mesh] OR "Intubation, Intratracheal"[Mesh]) AND anesthesia',
        ]
        all_articles: List[PubMedArticle] = []
        seen_pmids = set()
        for q in queries:
            try:
                arts = self.ingest_query(q, retmax=2000, generate_embeddings=True, filter_fp=True)
                for a in arts:
                    if a.pmid not in seen_pmids:
                        all_articles.append(a)
                        seen_pmids.add(a.pmid)
                logger.info(f"After query '{q[:50]}' total unique so far: {len(all_articles)}")
                time.sleep(1)
            except Exception as e:
                logger.error(f"Query failed {q}: {e}")
                continue

        # Save checkpoint
        self.vector_store.save()
        logger.info(f"Max extraction complete: {len(all_articles)} papers")
        return all_articles

if __name__ == "__main__":
    pipeline = AnesthesiaIngestionPipeline()
    # Example: ingest max
    pipeline.ingest_max_anesthesia()
