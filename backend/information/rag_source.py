"""
Future RAG (Retrieval-Augmented Generation) Information Source Placeholder.

This module defines the architectural extension point for future private/enterprise
knowledge base retrieval (vector databases, pgvector, embeddings).
It does NOT implement vector storage or embeddings for this milestone.
"""
from __future__ import annotations

from typing import Optional, List
from backend.information.source import BaseInformationSource, SOURCE_TYPE_RAG
from backend.information.models import InformationItem


class RAGInformationSource(BaseInformationSource):
    """
    Placeholder and future adapter for Retrieval-Augmented Generation (RAG).

    When implemented in a future milestone, this source will connect to vector indexes,
    semantic search, or enterprise document stores, returning normalized InformationItems
    with source_type='rag' without requiring any modifications to the Researcher or Coordinator.
    """
    source_type: str = SOURCE_TYPE_RAG

    def __init__(self, index_name: Optional[str] = None):
        self.index_name = index_name or "default-knowledge-base"

    def is_available(self) -> bool:
        """Returns False until vector database infrastructure is configured."""
        return False

    async def acquire(
        self,
        query: str,
        context: Optional[str] = None,
    ) -> List[InformationItem]:
        """
        Future retrieval entry point. Raises NotImplementedError during this milestone
        to guarantee no unconfigured vector DB or embeddings operations are executed.
        """
        raise NotImplementedError(
            "RAGInformationSource is a future architectural milestone. "
            "Vector databases, embeddings, and document chunking are not yet enabled."
        )


__all__ = ["RAGInformationSource"]
