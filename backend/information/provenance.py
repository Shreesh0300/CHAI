"""
Provenance generation and attachment for the Information Acquisition Layer.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from backend.information.models import InformationItem
from backend.information.search import extract_domain


def build_information_item(
    content: str,
    title: Optional[str],
    url: Optional[str],
    query: str,
    status_code: int = 200,
    metadata: Optional[Dict[str, Any]] = None,
) -> InformationItem:
    """
    Constructs an InformationItem strictly preserving provenance and retrieval metadata.

    Args:
        content: Cleaned, readable text content.
        title: Page or document title.
        url: Verified source URL.
        query: Search query used to discover this source.
        status_code: HTTP response status code.
        metadata: Optional additional metadata attributes.

    Returns:
        Structured InformationItem with guaranteed provenance.
    """
    domain = extract_domain(url) if url else "web"
    provenance_meta = {
        "query": query,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "status_code": status_code,
        "domain": domain,
        **(metadata or {}),
    }

    resolved_title = (title or "").strip() or domain

    return InformationItem(
        content=content,
        title=resolved_title,
        url=url,
        source=domain,
        source_type="web",
        metadata=provenance_meta,
    )


__all__ = ["build_information_item"]
