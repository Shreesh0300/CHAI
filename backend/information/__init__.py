"""
Information Acquisition Layer for CHAI.

Provides multi-source information retrieval (Web, API, Model Knowledge, and future RAG),
content extraction, normalization, and provenance tracking.
"""
from backend.information.models import (
    InformationItem,
    InformationResult,
    SearchResult,
    FetchResult,
    ExtractedContent,
)
from backend.information.source import (
    InformationSource,
    BaseInformationSource,
    SOURCE_TYPE_WEB,
    SOURCE_TYPE_API,
    SOURCE_TYPE_MODEL,
    SOURCE_TYPE_RAG,
)
from backend.information.web_source import WebAcquisitionSource
from backend.information.api_source import APIAcquisitionSource, DEFAULT_API_URL
from backend.information.model_source import ModelKnowledgeSource, ModelKnowledgeResponse
from backend.information.rag_source import RAGInformationSource
from backend.information.service import InformationAcquisitionService
from backend.information.search import (
    BaseSearchProvider,
    MockSearchProvider,
    TavilySearchProvider,
    HttpSearchProvider,
    get_search_provider,
    get_web_search_api_key,
)
from backend.information.fetcher import PageFetcher
from backend.information.extractor import ContentExtractor
from backend.information.cleaner import TextCleaner
from backend.information.provenance import build_information_item

__all__ = [
    "InformationItem",
    "InformationResult",
    "SearchResult",
    "FetchResult",
    "ExtractedContent",
    "InformationSource",
    "BaseInformationSource",
    "SOURCE_TYPE_WEB",
    "SOURCE_TYPE_API",
    "SOURCE_TYPE_MODEL",
    "SOURCE_TYPE_RAG",
    "WebAcquisitionSource",
    "APIAcquisitionSource",
    "DEFAULT_API_URL",
    "ModelKnowledgeSource",
    "ModelKnowledgeResponse",
    "RAGInformationSource",
    "InformationAcquisitionService",
    "BaseSearchProvider",
    "MockSearchProvider",
    "TavilySearchProvider",
    "HttpSearchProvider",
    "get_search_provider",
    "get_web_search_api_key",
    "PageFetcher",
    "ContentExtractor",
    "TextCleaner",
    "build_information_item",
]
