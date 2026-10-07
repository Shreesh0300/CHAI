"""
Web-based Information Acquisition Source for CHAI.

Encapsulates web search, HTTP page fetching, DOM text extraction, cleaning,
and provenance attribution behind the InformationSource contract.
"""
from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any

from backend.information.source import BaseInformationSource, SOURCE_TYPE_WEB
from backend.information.models import InformationItem, SearchResult
from backend.information.search import BaseSearchProvider, get_search_provider
from backend.information.fetcher import PageFetcher
from backend.information.extractor import ContentExtractor
from backend.information.cleaner import TextCleaner
from backend.information.provenance import build_information_item
from backend.shared.logger import get_logger

logger = get_logger(__name__)


class WebAcquisitionSource(BaseInformationSource):
    """
    Acquires information from the open web using a pluggable search provider,
    resilient async HTTP fetching, deterministic HTML stripping, and text normalization.
    """
    source_type: str = SOURCE_TYPE_WEB

    def __init__(
        self,
        search_provider: Optional[BaseSearchProvider] = None,
        fetcher: Optional[PageFetcher] = None,
        extractor: Optional[ContentExtractor] = None,
        cleaner: Optional[TextCleaner] = None,
        max_results: int = 5,
    ):
        self.search_provider = search_provider or get_search_provider()
        self.fetcher = fetcher or PageFetcher()
        self.extractor = extractor or ContentExtractor()
        self.cleaner = cleaner or TextCleaner()
        self.max_results = max(1, min(max_results, 10))
        self.last_errors: List[str] = []

    async def acquire(
        self,
        query: str,
        context: Optional[str] = None,
    ) -> List[InformationItem]:
        """
        Executes web search, page fetching, extraction, and normalization for the query.
        Returns a list of InformationItem objects with source_type='web'.
        """
        self.last_errors = []
        cleaned_query = (query or "").strip()

        if not cleaned_query:
            return []

        logger.info(f"WebAcquisitionSource: searching for '{cleaned_query[:60]}...'")

        try:
            search_results: List[SearchResult] = await self.search_provider.search(
                query=cleaned_query,
                max_results=self.max_results,
            )
        except Exception as e:
            err_msg = f"Web search provider error: {type(e).__name__}"
            logger.error(f"WebAcquisitionSource search failed: {err_msg}")
            self.last_errors.append(err_msg)
            return []

        items: List[InformationItem] = []

        for sr in search_results:
            target_url = sr.url
            if not target_url:
                continue

            try:
                # 1. Fetch
                fetch_res = await self.fetcher.fetch(target_url)
                if not fetch_res.success:
                    err_note = f"Failed to fetch '{target_url}': {fetch_res.error or 'Unknown error'}"
                    self.last_errors.append(err_note)
                    logger.warning(f"WebAcquisitionSource: {err_note}")
                    continue

                # 2. Extract
                extracted = self.extractor.extract(fetch_res.html, fallback_url=target_url)
                raw_text = extracted.text
                if not raw_text or len(raw_text.strip()) < 10:
                    if sr.snippet and len(sr.snippet.strip()) >= 5:
                        raw_text = f"Overview: {sr.snippet}"
                    else:
                        self.last_errors.append(f"Empty readable content from '{target_url}'.")
                        continue

                # 3. Clean
                cleaned_text = self.cleaner.clean(raw_text)
                if not cleaned_text:
                    self.last_errors.append(f"Cleaned content empty from '{target_url}'.")
                    continue

                # 4. Attach Provenance
                item = build_information_item(
                    content=cleaned_text,
                    title=extracted.title or sr.title,
                    url=target_url,
                    query=cleaned_query,
                    status_code=fetch_res.status_code,
                    metadata={"snippet": sr.snippet},
                )
                items.append(item)

            except Exception as e:
                err_note = f"Error processing web page '{target_url}': {type(e).__name__}"
                self.last_errors.append(err_note)
                logger.warning(f"WebAcquisitionSource: {err_note}")
                continue

        return items


__all__ = ["WebAcquisitionSource"]
