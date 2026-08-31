# Swarm C - Agent C1: PubMedBERT Embedding Developer - Production Deliverables

## Focus
PubMedBERT embeddings for anesthesia title+abstract - sentence-transformers, 768-dim, batch encoding, cosine similarity
Max anesthesia PubMed extraction with full metadata schema

## Files Generated
### Core Production Code
1. **pubmedbert_embedding_pipeline.py** - PubMedBERT 768-dim embedder
   - Model: NeuML/pubmedbert-base-embeddings (768-dim) - alt S-PubMedBert-MS-MARCO validated from search
   - batch_size=32 (16-32 optimal per search)
   - normalize_embeddings=True for cosine similarity
   - max_seq_length=512 (350 optimization option)
   - Device auto: cuda > mps > cpu
   - Methods: encode_batch, encode_weighted (title 0.3 + abstract 0.7), cosine_similarity, batch_cosine_similarity
   - L2 norm ~1.0 verification, FAISS export ready

2. **metadata_schema.py** - Full metadata schema
   - PubMedRecordFull: 39 fields
   - PubDateModel with MedlineDate fallback chain parser
   - AnesthesiaClassificationModel with FP risk provenance
   - High-precision MeSH sets: 18 core + moderate, exclusion patterns, core journals
   - Dedup keys: dedup_key_title_norm, dedup_key_doi_norm

3. **pubmed_anesthesia_extraction.py** - Max extraction with audit fixes
   - RateLimitedPubMedClient: 3 req/s no key (0.34s delay), 10 req/s with key (0.11s), exponential backoff, User-Agent with email/tool
   - ESearch + EFetch 500 batch, usehistory
   - DedupManager: DOI norm -> PMID -> title norm + hash, properly sets is_duplicate (fixes audit: was read/counted/purged but NEVER set)
   - MedlineDate fallback: Journal PubDate -> MedlineDate parsing -> ArticleDate -> PubMedPubDate pubmed/entrez/medline status - full chain prevents missing dates
   - AnesthesiaClassifier: MeSH major boost (0.95), mesh 0.78-0.85, journal+keyword 0.82, keyword alone high FP risk, embedding threshold 0.72, pub type penalty
   - Multi-query federation for max recall: 7 queries covering Anesthesia[mh], Anesthetics[mh], etc then FP filter

4. **production_pipeline.py** - End-to-end orchestration
   - Extract -> Embed -> Validate cosine -> Save npy + jsonl + manifest + sample search
   - CLI: --email --api-key --retmax --mindate --maxdate --model --batch-size --device

5. **requirements.txt** - sentence-transformers, torch, pydantic, etc

## Audit Fixes Implemented (Critical)

| Audit Issue | Fix |
|-------------|-----|
| **Rate limits** | RateLimitConfig, _throttle 0.34s/0.11s, exponential backoff 2**attempt+random, session with User-Agent, 429 handling |
| **Dedup** | DedupManager multi-stage: DOI normalized (strip doi.org) -> PMID -> title norm (lower, strip xml, punct collapse) -> title hash collision protection. Proper is_duplicate+duplicate_of set. |
| **Classification FP** | AnesthesiaClassifier: MeSH high-precision set from UW library guide Anesthesia[mh], major_topic boost, core journals boost only with keyword, single keyword=high FP risk, threshold 0.65, pub type Letter/Editorial penalty, exclusion_reason |
| **Missing MedlineDate fallback** | parse_medline_date handles "2020", "2020 Jan-Feb", "2019 Fall", etc via regex + month map; get_best_pub_date chain: Journal PubDate (incl MedlineDate str) -> ArticleDate -> PubMedPubDate pubmed/entrez/medline -> unknown_fallback never None |

## Validation
- All files compile ✓
- 768-dim confirmed ✓
- normalize_embeddings ✓
- batch_size 32 ✓
- Cosine similarity (dot on normalized) ✓
- Rate limits 3/10 rps ✓
- Dedup DOI->PMID->title_norm ✓
- MedlineDate parser tested: "2020"->2020-01-01, "2020 Jan-Feb"->2020-01-01, "2019 Fall"->2019-10-01, "2020 Dec 12"->2020-12-12 ✓

## Usage
```bash
pip install -r requirements.txt
python production_pipeline.py --email your@email.com --api-key YOUR_NCBI_KEY --retmax 10000 --output /mnt/data/outputs/anesthesia_max
```

## Embedding Best Practices (from browser.search)
- Model: NeuML/pubmedbert-base-embeddings 768-dim L2-normalized (search result: 768-dimensional L2-normalized vectors suitable for cosine similarity)
- Batch 32 normalized output float32 (search: batch_size=32, normalize_embeddings=True output 768-dim float32)
- Max length 350 optimized for 768-dim vectors (search: dimension 768 max_length 350 batch_size 16 optimized)
- FAISS IndexFlatIP for cosine (normalized dot product) or IndexFlatL2 after normalization
- Device auto cuda/mps/cpu configurable
