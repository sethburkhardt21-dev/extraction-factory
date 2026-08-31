# Experimental enrichment — NOT source-certified

This directory is deliberately outside the active extraction surface. Embeddings,
classification, reranking and RAG are downstream model enrichments and cannot affect
source completeness or source promotion. The legacy PubMedBERT implementation is
retained here for lineage only until it is separately hardened with an explicitly
pinned model revision, input/output hashes, non-empty-text semantics and model-level
certification.
