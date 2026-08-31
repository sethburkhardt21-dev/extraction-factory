"""
Semantic Search API - FastAPI endpoint for query -> embedding -> top-k anesthesia papers
Production deliverable with filters subdomain study_type year
Fixes audit issues: rate limits, dedup, classification FP, MedlineDate fallback baked into ingestion

Endpoints:
- GET /health
- POST /search (main semantic search)
- GET /search (query params)
- POST /ingest (ingest PMIDs or query)
- GET /stats
- GET /paper/{pmid}

Best practices applied:
- Async embedding + LRU cache
- Metadata filtering pre-search
- Cosine similarity threshold
- Optional cross-encoder reranking
- Pydantic validation
- Rate limit handling for PubMed ingestion
- Deduplication (PMID, hash, DOI)
"""
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import logging
from typing import List, Optional
import numpy as np

from .config import settings, ANESTHESIA_SUBDOMAINS, STUDY_TYPES
from .models import (
    SearchQuery, SearchResponse, SearchResultItem, SearchFilter,
    HealthResponse, IngestRequest, PubMedArticle, Subdomain, StudyType
)
from .embedding_engine import get_embedding_engine
from .vector_store import get_vector_store
from .pubmed_client import PubMedClient
from .anesthesia_classifier import AnesthesiaClassifier
from .ingestion_pipeline import AnesthesiaIngestionPipeline

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Anesthesia Semantic Search API",
    description="Production API: query -> embedding -> top-k anesthesia papers with filters subdomain, study_type, year. Fixes PubMed audit issues.",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global startup time
startup_time = time.time()

@app.get("/health", response_model=HealthResponse)
async def health():
    vs = get_vector_store()
    ee = get_embedding_engine()
    stats = vs.get_stats()
    return HealthResponse(
        status="ok",
        total_papers=stats["total_papers"],
        embedding_model=ee.model_name,
        embedding_dim=ee.dim,
        index_type=stats["index_type"],
        uptime_seconds=time.time() - startup_time
    )

@app.get("/stats")
async def stats():
    vs = get_vector_store()
    return vs.get_stats()

def _to_result_item(article, similarity: float, rerank_score: Optional[float] = None, include_abstract: bool = True) -> SearchResultItem:
    # Handle dict case if loaded from JSONL
    if isinstance(article, dict):
        return SearchResultItem(
            pmid=article.get("pmid",""),
            title=article.get("title",""),
            abstract=article.get("abstract") if include_abstract else None,
            abstract_sections=None,
            authors=[],
            journal=article.get("journal"),
            pub_year=article.get("pub_year"),
            doi=article.get("doi"),
            subdomain=article.get("subdomain","other"),
            subdomain_confidence=article.get("subdomain_confidence",0),
            study_type=article.get("study_type","other"),
            study_type_confidence=article.get("study_type_confidence",0),
            anesthesia_relevance_score=article.get("anesthesia_relevance_score",0),
            mesh_terms=article.get("mesh_terms",[]),
            pub_types=article.get("pub_types",[]),
            similarity=similarity,
            rerank_score=rerank_score
        )
    else:
        # PubMedArticle
        return SearchResultItem(
            pmid=article.pmid,
            title=article.title,
            abstract=article.abstract if include_abstract else None,
            abstract_sections=article.abstract_sections if include_abstract else None,
            authors=article.authors,
            journal=article.journal,
            pub_year=article.pub_year,
            doi=article.doi,
            subdomain=article.subdomain,
            subdomain_confidence=article.subdomain_confidence,
            study_type=article.study_type,
            study_type_confidence=article.study_type_confidence,
            anesthesia_relevance_score=article.anesthesia_relevance_score,
            mesh_terms=article.mesh_terms,
            pub_types=article.pub_types,
            similarity=similarity,
            rerank_score=rerank_score
        )

def _rerank(query: str, candidates: List, top_k: int):
    """Optional cross-encoder reranking - production best practice: 3x fetch -> rerank -> top_k"""
    if not settings.rerank_enabled:
        return candidates

    try:
        from sentence_transformers import CrossEncoder
        model = CrossEncoder(settings.rerank_model)
        pairs = []
        for art, sim in candidates:
            title = art.title if not isinstance(art, dict) else art.get("title","")
            abstract = art.abstract[:1000] if not isinstance(art, dict) else art.get("abstract","")[:1000]
            pairs.append([query, f"{title} {abstract}"])

        scores = model.predict(pairs)  # higher = more relevant
        # Combine with cosine similarity: weighted
        reranked = []
        for (art, sim), ce_score in zip(candidates, scores):
            reranked.append((art, sim, float(ce_score)))

        # Sort by cross-encoder score
        reranked.sort(key=lambda x: x[2], reverse=True)
        return reranked[:top_k]
    except Exception as e:
        logger.warning(f"Reranker failed, fallback to cosine: {e}")
        return [(art, sim, None) for art, sim in candidates[:top_k]]

@app.post("/search", response_model=SearchResponse)
async def semantic_search(req: SearchQuery):
    start = time.time()
    ee = get_embedding_engine()
    vs = get_vector_store()

    if not req.query or len(req.query.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query too short")

    top_k = min(req.top_k, settings.max_top_k)

    # Query -> embedding (cached)
    query_emb = ee.embed_text(req.query)

    # Top-k with filters - we over-fetch for reranking then filter
    fetch_k = top_k * 3 if req.rerank else top_k
    candidates = vs.search(
        query_embedding=query_emb,
        top_k=fetch_k,
        filters=req.filters,
        min_similarity=req.min_similarity
    )

    total_candidates = len(candidates)

    # Reranking
    if req.rerank and candidates:
        reranked = _rerank(req.query, candidates, top_k)
        results = []
        for art, sim, ce_score in reranked:
            results.append(_to_result_item(art, sim, ce_score, include_abstract=req.include_abstract))
    else:
        results = [_to_result_item(art, sim, None, include_abstract=req.include_abstract) for art, sim in candidates[:top_k]]

    elapsed_ms = (time.time() - start) * 1000

    return SearchResponse(
        query=req.query,
        query_embedding_model=ee.model_name,
        top_k=top_k,
        filters=req.filters,
        results=results,
        total_candidates=total_candidates,
        search_time_ms=elapsed_ms,
        cached=False
    )

@app.get("/search", response_model=SearchResponse)
async def semantic_search_get(
    query: str = Query(..., min_length=2, max_length=500, description="Natural language query"),
    top_k: int = Query(10, ge=1, le=100),
    subdomain: Optional[Subdomain] = Query(None, description="Filter by subdomain"),
    subdomains: Optional[str] = Query(None, description="Comma-separated subdomain list"),
    study_type: Optional[StudyType] = Query(None),
    study_types: Optional[str] = Query(None, description="Comma-separated study_type list"),
    year_from: Optional[int] = Query(None, ge=1900, le=2030),
    year_to: Optional[int] = Query(None, ge=1900, le=2030),
    min_similarity: float = Query(0.2, ge=0, le=1),
    include_abstract: bool = Query(True),
    rerank: bool = Query(True)
):
    # Parse list params
    filters = SearchFilter()
    if subdomain:
        filters.subdomain = subdomain
    if subdomains:
        try:
            vals = [s.strip() for s in subdomains.split(",")]
            filters.subdomains = [Subdomain(v) for v in vals]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid subdomains: {e}")
    if study_type:
        filters.study_type = study_type
    if study_types:
        try:
            vals = [s.strip() for s in study_types.split(",")]
            filters.study_types = [StudyType(v) for v in vals]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid study_types: {e}")
    if year_from:
        filters.year_from = year_from
    if year_to:
        filters.year_to = year_to

    req = SearchQuery(
        query=query,
        top_k=top_k,
        filters=filters,
        min_similarity=min_similarity,
        include_abstract=include_abstract,
        rerank=rerank
    )
    return await semantic_search(req)

@app.get("/paper/{pmid}")
async def get_paper(pmid: str):
    vs = get_vector_store()
    art = vs.articles.get(pmid)
    if not art:
        raise HTTPException(status_code=404, detail="Paper not found")
    if isinstance(art, dict):
        return art
    return art.model_dump()

@app.post("/ingest")
async def ingest(req: IngestRequest):
    """
    Ingest papers: by PMID list or PubMed query, with audit fixes
    Production: rate-limited, deduped, classified FP filtered
    """
    pipeline = AnesthesiaIngestionPipeline()
    try:
        if req.pmids:
            articles = pipeline.ingest_pmids(req.pmids, generate_embeddings=req.generate_embeddings)
        elif req.query:
            articles = pipeline.ingest_query(req.query, retmax=req.retmax, generate_embeddings=req.generate_embeddings)
        else:
            raise HTTPException(status_code=400, detail="Provide pmids or query")

        # Save after ingest
        pipeline.vector_store.save()

        return {
            "ingested": len(articles),
            "pmids": [a.pmid if not isinstance(a, dict) else a.get("pmid") for a in articles[:20]],
            "total_in_store": pipeline.vector_store.get_stats()["total_papers"]
        }
    except Exception as e:
        logger.exception(f"Ingest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/subdomains")
async def list_subdomains():
    return {"subdomains": ANESTHESIA_SUBDOMAINS}

@app.get("/study_types")
async def list_study_types():
    return {"study_types": STUDY_TYPES}

# For local dev
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("semantic_search_api:app", host=settings.api_host, port=settings.api_port, reload=True)
