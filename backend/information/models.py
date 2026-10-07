"""
Data models and contracts for the Information Acquisition Layer.
"""
from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, Field


class InformationItem(BaseModel):
    """
    Normalized, cleaned piece of extracted information with provenance.
    """
    content: str = Field(description="Readable, cleaned text content extracted from the source")
    title: Optional[str] = Field(default=None, description="Title of the source or web page")
    url: Optional[str] = Field(default=None, description="Original source URL")
    source: str = Field(description="Domain or source identifier, e.g. 'cdc.gov' or 'wikipedia.org'")
    source_type: Literal["web", "api", "model", "rag"] = Field(
        default="web",
        description="Type of acquisition source: 'web', 'api', 'model', or 'rag'"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata such as retrieval timestamp, query, etc.")


class InformationResult(BaseModel):
    """
    Structured outcome of the Information Acquisition pipeline.
    """
    status: Literal["completed", "failed"] = Field(
        default="completed",
        description="Overall execution status of the acquisition layer"
    )
    query: str = Field(description="The query evaluated during information acquisition")
    items: List[InformationItem] = Field(
        default_factory=list,
        description="List of successfully fetched and extracted InformationItems"
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Safe, bounded error messages encountered during search or fetching"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Execution metadata such as timing, result counts, and provider info"
    )


class SearchResult(BaseModel):
    """
    Structured result returned by a WebSearch provider.
    """
    title: str = Field(description="Title of the search result")
    url: str = Field(description="URL of the web page")
    snippet: str = Field(default="", description="Snippet or summary from the search provider")
    source: Optional[str] = Field(default=None, description="Domain or provider identifier")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional search metadata")


class FetchResult(BaseModel):
    """
    Result of an HTTP webpage fetch operation.
    """
    url: str
    status_code: int = 200
    html: str = ""
    content_type: str = "text/html"
    success: bool = True
    error: Optional[str] = None


class ExtractedContent(BaseModel):
    """
    Intermediate representation of extracted web content.
    """
    title: str = ""
    text: str = ""
    headings: List[str] = Field(default_factory=list)


__all__ = [
    "InformationItem",
    "InformationResult",
    "SearchResult",
    "FetchResult",
    "ExtractedContent",
]
