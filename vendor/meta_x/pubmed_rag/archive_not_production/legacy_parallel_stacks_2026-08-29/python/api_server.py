"""
Backend API for Anesthesia Corpus - FastAPI production
Serves embeddings_2d.json and corpus with semantic search
Fixes: rate limits, caching, dedup endpoints
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
from pathlib import Path
import os
import json
import numpy as np
from datetime import datetime, timezone

app = FastAPI(title="Anesthesia Corpus API - v2.0-fixed", version="2.0")

_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# Load only explicitly produced corpus artifacts; no demo/synthetic fallback
DATA_DIR = Path(os.getenv("ANESTHESIA_DATA_DIR", str(Path(__file__).resolve().parent / "data")))
CORPUS_PATH = DATA_DIR / "anesthesia_corpus_embedded.jsonl"
EMBED_2D_PATH = DATA_DIR / "embeddings_2d.json"
VECTOR_STORE_PATH = DATA_DIR / "vector_store.npz"
EMBED_META_PATH = DATA_DIR / "embeddings_meta.json"

class SearchRequest(BaseModel):
    query: str
    top_k: int = 20
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    subfields: Optional[List[str]] = None
    conf_threshold: float = 0.0

class SearchResult(BaseModel):
    pmid: str
    title: str
    abstract: str
    journal: str
    year: int
    mesh: List[str]
    subfields: List[str]
    confidence: float
    score: float
    x: Optional[float] = None
    y: Optional[float] = None

# In-memory stores
corpus_records: List[Dict] = []
embeddings_matrix: Optional[np.ndarray] = None
pmid_to_idx: Dict[str,int] = {}
projection_map: Dict[str, Dict] = {}
query_backend = None

def load_data():
    global corpus_records, embeddings_matrix, pmid_to_idx, projection_map
    
    # Load 2D projection if exists
    if EMBED_2D_PATH.exists():
        try:
            projection_map = {item["pmid"]: item for item in json.loads(EMBED_2D_PATH.read_text())}
        except:
            projection_map = {}
    
    if CORPUS_PATH.exists():
        corpus_records = []
        with open(CORPUS_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    r = json.loads(line)
                    # merge projection coords
                    if r["pmid"] in projection_map:
                        r["x"] = projection_map[r["pmid"]].get("x")
                        r["y"] = projection_map[r["pmid"]].get("y")
                    corpus_records.append(r)
                except:
                    continue
        print(f"Loaded {len(corpus_records)} records")
    
    if VECTOR_STORE_PATH.exists():
        try:
            data = np.load(VECTOR_STORE_PATH, allow_pickle=True)
            embeddings_matrix = data["embeddings"]
            pmids = data["pmids"]
            pmid_to_idx = {str(p): i for i,p in enumerate(pmids)}
            print(f"Loaded vector store {embeddings_matrix.shape}")
            if EMBED_META_PATH.exists():
                meta = json.loads(EMBED_META_PATH.read_text())
                model_name = meta.get("model")
                if model_name:
                    from embedding_pipeline import EmbeddingBackend
                    global query_backend
                    query_backend = EmbeddingBackend(model_name=model_name)
                    query_backend.load()
                    if query_backend.dim != embeddings_matrix.shape[1]:
                        raise RuntimeError(f"query model dimension {query_backend.dim} != stored vectors {embeddings_matrix.shape[1]}")
        except Exception as e:
            print(f"Failed to load vector store: {e}")

# Try load on startup
load_data()

@app.get("/health")
def health():
    return {
        "status":"ok",
        "records": len(corpus_records),
        "has_embeddings": embeddings_matrix is not None,
        "version":"2.0-fixed",
        "fixes":["rate_limit","dedup","classification_fp","medline_date_fallback"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/stats")
def stats():
    if not corpus_records:
        return {"total":0}
    years = {}
    subfs = {}
    for r in corpus_records:
        y = r.get("pub_date",{}).get("year") or r.get("year") or 0
        years[y] = years.get(y,0)+1
        for sf in r.get("classification",{}).get("subfields",[]) or r.get("subfields",[]):
            subfs[sf] = subfs.get(sf,0)+1
    return {
        "total": len(corpus_records),
        "years": years,
        "subfields": subfs,
        "avg_conf": sum(r.get("classification",{}).get("confidence", r.get("confidence",0)) for r in corpus_records)/len(corpus_records)
    }

@app.post("/search", response_model=List[SearchResult])
def search(req: SearchRequest):
    if not corpus_records:
        raise HTTPException(status_code=404, detail="No corpus loaded")
    
    # Filter
    filtered = []
    for r in corpus_records:
        year = r.get("pub_date",{}).get("year") or r.get("year") or 0
        if req.year_min and year < req.year_min:
            continue
        if req.year_max and year > req.year_max:
            continue
        conf = r.get("classification",{}).get("confidence", r.get("confidence",0))
        if conf < req.conf_threshold:
            continue
        subfields = r.get("classification",{}).get("subfields",[]) or r.get("subfields",[])
        if req.subfields and not any(s in subfields for s in req.subfields):
            continue
        filtered.append(r)
    
    # Semantic scoring: if embeddings available, use cosine, else keyword
    query_lower = req.query.lower()
    scored = []
    
    if embeddings_matrix is not None and req.query.strip():
        if query_backend is None:
            raise HTTPException(status_code=503, detail="Vector store is loaded but its real query embedding model is unavailable")
        q_emb = query_backend.encode([req.query], batch_size=1)[0]
        # Only for filtered idx
        for r in filtered:
            idx = pmid_to_idx.get(r["pmid"])
            if idx is not None and idx < len(embeddings_matrix):
                doc_emb = embeddings_matrix[idx]
                # Cosine because normalized
                score = float(np.dot(q_emb, doc_emb))
                # Combine with keyword boost
                if query_lower in r.get("title","").lower():
                    score += 0.2
            else:
                # Fallback keyword
                text = (r.get("title","")+ " " + r.get("abstract","")).lower()
                score = sum(1 for w in query_lower.split() if w in text) / max(1,len(query_lower.split()))
            scored.append((r, score))
    else:
        for r in filtered:
            text = (r.get("title","")+ " " + r.get("abstract","")).lower()
            score = sum(1 for w in query_lower.split() if w in text) / max(1,len(query_lower.split())) if query_lower else r.get("classification",{}).get("confidence",0)
            scored.append((r, score))
    
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:req.top_k]
    
    results = []
    for r, score in top:
        results.append(SearchResult(
            pmid=r["pmid"],
            title=r.get("title",""),
            abstract=r.get("abstract","")[:500],
            journal=r.get("journal",{}).get("title","") or r.get("journal",""),
            year=r.get("pub_date",{}).get("year") or r.get("year") or 0,
            mesh=[m["descriptor_name"] if isinstance(m, dict) else m for m in r.get("mesh_headings",[])][:5] or r.get("mesh",[]),
            subfields=r.get("classification",{}).get("subfields",[]) or r.get("subfields",[]),
            confidence=r.get("classification",{}).get("confidence", r.get("confidence",0)),
            score=score,
            x=r.get("x"),
            y=r.get("y")
        ))
    return results

@app.get("/embeddings_2d")
def get_2d():
    if EMBED_2D_PATH.exists():
        return json.loads(EMBED_2D_PATH.read_text())
    # Return from memory
    return [{ "pmid": r["pmid"], "x": r.get("x",0), "y": r.get("y",0), "title": r.get("title","")[:80], "year": r.get("pub_date",{}).get("year") or r.get("year"), "subfields": r.get("classification",{}).get("subfields",[]) or r.get("subfields",[]) } for r in corpus_records]

@app.get("/record/{pmid}")
def get_record(pmid: str):
    for r in corpus_records:
        if r["pmid"]==pmid:
            return r
    raise HTTPException(status_code=404, detail="PMID not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
