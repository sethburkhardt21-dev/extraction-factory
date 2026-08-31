# Anesthesia Corpus Extraction - Production Fixed

## Overview
Production pipeline for max anesthesia PubMed extraction with full metadata schema + interactive front-end artifact.

### Audit Issues Fixed

| Issue | Fix | File |
|-------|-----|------|
| Rate limits (429) | TokenBucket 3/s no-key, 10/s key, exponential backoff with jitter, Retry-After header parsing, tenacity 5 attempts | `anesthesia_pubmed_extractor.py` PubMedClient |
| Deduplication | PMID set + DOI normalized + title SHA256[:16] + embedding cosine >0.98 secondary | `anesthesia_pubmed_extractor.py` DeduplicationManager, `embedding_pipeline.py` EmbeddingDedupManager |
| Classification FP | Oncology exclusion list, MeSH ontology (D000758 etc), strong title regex, journal whitelist, embedding centroid distance <0.30 flag | `anesthesia_schema.py` + classifier in extractor |
| Missing MedlineDate fallback | If PubDate/Year missing, parse MedlineDate via regex `(19|20)\d{2}`, fallback to ArticleDate | `parse_pubmed_article()` in extractor + `PublicationDate.from_pubmed_article()` in schema |
| Missing metadata | Full schema: authors affiliations, ORCID, journal, volume/issue/pages, MeSH UI, qualifiers, chemicals registry, grant list, language, references | `anesthesia_schema.py` |
| Embedding pipeline | Batch encode, resume checkpoint, PCA/UMAP 2D, vector store NPZ, mock fallback if transformers missing | `embedding_pipeline.py` |

## Files

- `/mnt/data/anesthesia_schema.py` - Pydantic full metadata schema with MedlineDate fallback
- `/mnt/data/anesthesia_pubmed_extractor.py` - Production extractor (argparse, resume, checkpoint)
- `/mnt/data/embedding_pipeline.py` - Embedding pipeline with dedup + FP refinement
- `/mnt/data/api_server.py` - FastAPI backend with semantic search (cosine)
- `/mnt/data/anesthesia_corpus_explorer.html` - **Interactive front-end artifact** (self-contained React 18 + Tailwind, no build needed)

## Front-end Artifact Features (Best Practices from search)

Inspired by: react-force-graph-2d, revelio embeddings visualizer, civil-rights-history-project semantic search, semantic search Django+React+Milvus

- **Search**: hybrid keyword + semantic cosine, relevance scoring, subfield boosting
- **Filters**: year range slider, confidence threshold, subfields (ontology-based), journals, pub types
- **Embeddings Visualization**: Canvas scatter 2D UMAP/PCA, pan/zoom, hover tooltip, click-to-detail, clustered edges, color by subfield/year/confidence/journal, search relevance highlighting (red intensity)
- **Stats**: total records, avg confidence, subfield distribution badges
- **Dedup UX**: shows filtered count, title hash indicator
- **Detail Modal**: full metadata, classification evidence, embedding vector, MedlineDate fix note, PubMed link
- **Performance**: virtualized list (50 visible), requestAnimationFrame canvas, DPR handling

## Usage

### 1. Extraction
```bash
pip install requests tenacity pydantic
export NCBI_API_KEY=your_key  # for 10 req/s else 3 req/s
python /mnt/data/anesthesia_pubmed_extractor.py --max 10000 --mindate 2018/01/01 --api-key $NCBI_API_KEY
# Output: /mnt/data/anesthesia_corpus.jsonl + dedup_state.json + extraction_summary.json
```

### 2. Embedding
```bash
pip install sentence-transformers scikit-learn umap-learn numpy
python /mnt/data/embedding_pipeline.py --input /mnt/data/anesthesia_corpus.jsonl --batch 64
# Outputs:
#  /mnt/data/anesthesia_corpus_embedded.jsonl
#  /mnt/data/vector_store.npz
#  /mnt/data/embeddings_2d.json
#  /mnt/data/embeddings_meta.json
```

### 3. Frontend
Open directly:
```bash
open /mnt/data/anesthesia_corpus_explorer.html
# or serve:
python -m http.server 8000 --directory /mnt/data
# then http://localhost:8000/anesthesia_corpus_explorer.html
```

### 4. API (optional)
```bash
pip install fastapi uvicorn
uvicorn api_server:app --reload --port 8000 --app-dir /mnt/data
# Endpoints: /health, /stats, /search (POST), /embeddings_2d, /record/{pmid}
```

## Validation

- [x] Rate limiter: TokenBucket with burst, sleep calculation, 429 Retry-After handling
- [x] Dedup: Tested with PMID collision, DOI normalization (https://doi.org/ prefix stripping), title hash SHA256
- [x] MedlineDate: Regex year extraction handles "2023 Jan-Feb", "2021 Summer", etc.
- [x] Classification FP: Exclusion regex (corneal anesthesia, skin anesthesia, etc) with journal override, MeSH ontology check
- [x] Embedding: cosine similarity >0.98 dup detection, centroid similarity <0.30 FP flag
- [x] Frontend: Canvas renders 180 demo points clustered by subfield, filters reactive, search relevance, modal details
- [x] No external build needed - single HTML artifact with React CDN + Tailwind CDN + Babel

## Demo Data
If real PubMed not fetched, demo corpus of 150+ realistic anesthesia papers auto-generated in embedding_pipeline.py -> ensures frontend works immediately.

## Production Notes
- For max extraction: use NCBI API key (10 req/s), set mindate 2010/01/01, max 50000, batch 200 per efetch (NCBI recommended), checkpoint every 500
- Resume support: existing JSONL scanned for PMIDs, dedup state persisted
- Rate limit compliance: email + tool params required by NCBI
- Vector store: NPZ compressed, embeddings normalized for cosine
- Frontend can load /mnt/data/embeddings_2d.json if present via fetch, otherwise uses embedded demo

## Architecture
```
Esearch (query + mindate) -> ID list -> efetch batch 200 -> parse XML (with MedlineDate fallback) -> dedup check (PMID/DOI/title) -> classification FP filter -> JSONL append -> dedup checkpoint
-> embedding backend (SentenceTransformers or mock hash) -> dedup embedding similarity -> FP centroid filter -> vector_store.npz + 2D UMAP -> embeddings_2d.json
-> frontend artifact (React) reads 2D + corpus, provides filters, semantic search (query embedding cosine), visualization, detail
```

Built for Swarm C - Agent C7
