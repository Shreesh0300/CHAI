"""
Tools and retrieval stubs for the Researcher Agent.
These provide clean async interfaces for the future Information Acquisition Layer
without introducing heavy vector databases, scrapers, or third-party task runners.
"""
from typing import List, Dict, Any, Optional
from backend.agents.researcher.models import Source
from backend.shared.logger import get_logger

logger = get_logger(__name__)


async def retrieve_documents(
    query: str,
    limit: int = 5,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Interface for internal document retrieval.
    To be integrated with the Information Acquisition Layer / RAG store in future phases.

    Args:
        query: Search or problem query.
        limit: Max number of documents to return.
        filters: Optional metadata filters.

    Returns:
        List of retrieved document snippets.
    """
    logger.debug(f"Document retrieval interface called for query: '{query}' (limit={limit})")
    # Clean stub: returns empty list until Information Acquisition Layer is plugged in
    return []


async def search_external_sources(
    query: str,
    limit: int = 5,
) -> List[Source]:
    """
    Interface for external verified source retrieval.
    To be integrated with verified search providers (e.g., Tavily, Google Search API) in future phases.

    Args:
        query: Search term.
        limit: Max results.

    Returns:
        List of verified Source objects with provenance.
    """
    logger.debug(f"External search interface called for query: '{query}' (limit={limit})")
    # Clean stub: returns empty list until Information Acquisition Layer is plugged in
    return []
