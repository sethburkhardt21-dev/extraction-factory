"""Canonical PubMed source extraction package.

Source ingestion is intentionally separated from model/RAG enrichment.
"""
from .metadata_schema import PubMedRecordFull, PubDateModel, AuthorModel, MeshHeadingModel

__all__ = ["PubMedRecordFull", "PubDateModel", "AuthorModel", "MeshHeadingModel"]
