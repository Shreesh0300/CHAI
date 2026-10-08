"""
Main InformationAcquisitionService orchestrating multiple heterogeneous information channels:
1. Web Acquisition (Search → Fetch → Extract → Clean → Provenance)
2. External API Acquisition (Generic JSON REST API)
3. Model Knowledge Acquisition (Structured Gemini background knowledge, unverified)
4. RAG Acquisition (Future milestone extension point)

Normalizes all acquired data into the canonical InformationResult contract.
"""
from __future__ import annotations

import os
import time
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from backend.information.models import InformationItem, InformationResult
from backend.information.source import (
    InformationSource,
    BaseInformationSource,
    SOURCE_TYPE_WEB,
    SOURCE_TYPE_API,
    SOURCE_TYPE_MODEL,
    SOURCE_TYPE_RAG,
)
from backend.information.web_source import WebAcquisitionSource
from backend.information.api_source import APIAcquisitionSource
from backend.information.model_source import ModelKnowledgeSource
from backend.information.rag_source import RAGInformationSource
from backend.information.search import BaseSearchProvider, get_search_provider
from backend.information.fetcher import PageFetcher
from backend.information.extractor import ContentExtractor
from backend.information.cleaner import TextCleaner
from backend.shared.logger import get_logger

logger = get_logger(__name__)


class InformationAcquisitionService:
    """
    Facade for the Multi-Source Information Acquisition Layer.
    Orchestrates Web, API, and Model Knowledge sources with isolated failure handling.
    The Coordinator and Researcher consume only the resulting normalized InformationResult.
    """

    def __init__(
        self,
        web_source: Optional[WebAcquisitionSource] = None,
        api_source: Optional[APIAcquisitionSource] = None,
        model_source: Optional[ModelKnowledgeSource] = None,
        rag_source: Optional[RAGInformationSource] = None,
        sources: Optional[List[InformationSource]] = None,
        # Backward-compatible parameters for earlier tests:
        search_provider: Optional[BaseSearchProvider] = None,
        fetcher: Optional[PageFetcher] = None,
        extractor: Optional[ContentExtractor] = None,
        cleaner: Optional[TextCleaner] = None,
        max_results: int = 5,
    ):
        if web_source is not None:
            self.web_source = web_source
        else:
            self.web_source = WebAcquisitionSource(
                search_provider=search_provider,
                fetcher=fetcher,
                extractor=extractor,
                cleaner=cleaner,
                max_results=max_results,
            )

        self.api_source = api_source or APIAcquisitionSource()
        self.model_source = model_source or ModelKnowledgeSource()
        self.rag_source = rag_source or RAGInformationSource()

        if sources is not None:
            self._sources = sources
        else:
            # If caller explicitly provided custom web components (e.g. search_provider or fetcher)
            # without supplying api_source or model_source, retain web-only source list
            # for 100% backward compatibility with isolated web unit tests.
            is_custom_web = any(
                x is not None for x in (search_provider, fetcher, extractor, cleaner)
            )
            if is_custom_web and api_source is None and model_source is None:
                self._sources = [self.web_source]
            else:
                self._sources = [
                    self.web_source,
                    self.api_source,
                    self.model_source,
                ]

    # Expose search_provider property for backward compatibility with existing unit tests
    @property
    def search_provider(self) -> BaseSearchProvider:
        return self.web_source.search_provider

    @search_provider.setter
    def search_provider(self, val: BaseSearchProvider) -> None:
        self.web_source.search_provider = val

    @property
    def fetcher(self) -> PageFetcher:
        return self.web_source.fetcher

    @fetcher.setter
    def fetcher(self, val: PageFetcher) -> None:
        self.web_source.fetcher = val

    @property
    def extractor(self) -> ContentExtractor:
        return self.web_source.extractor

    @property
    def cleaner(self) -> TextCleaner:
        return self.web_source.cleaner

    async def acquire(
        self,
        query: str,
        context: Optional[str] = None,
        source_types: Optional[List[str]] = None,
    ) -> InformationResult:
        """
        Executes multi-source information acquisition for a query.

        Args:
            query: Problem or query string.
            context: Optional contextual parameters.
            source_types: Optional list of specific source types to query (e.g. ['web', 'api']).
                          If None, queries all active configured sources.

        Returns:
            InformationResult containing normalized InformationItem objects from all sources.
        """
        start_time = time.monotonic()
        cleaned_query = (query or "").strip()

        if not cleaned_query:
            return InformationResult(
                status="completed",
                query="",
                items=[],
                errors=["Empty query provided; skipping information acquisition."],
                metadata={"duration_ms": 0.0, "total_items": 0},
            )

        # 1. Deterministic source selection
        target_sources = self._select_sources(cleaned_query, requested_types=source_types)

        all_items: List[InformationItem] = []
        all_errors: List[str] = []
        source_counts: Dict[str, int] = {}
        sources_used: List[str] = []

        logger.info(
            f"InformationAcquisitionService: acquiring from {[s.source_type for s in target_sources]} "
            f"for query: '{cleaned_query[:50]}...'"
        )

        # 2. Execute each source concurrently with strict error isolation
        async def _run_source(src):
            stype = getattr(src, "source_type", "unknown")
            try:
                src_items = await asyncio.wait_for(
                    src.acquire(query=cleaned_query, context=context),
                    timeout=12.0,
                )
                last_errs = list(getattr(src, "last_errors", []) or [])
                return stype, src_items or [], last_errs, None
            except asyncio.TimeoutError:
                err_msg = f"{stype.capitalize()} acquisition source timed out (12s limit)"
                logger.warning(f"InformationAcquisitionService: {err_msg}")
                return stype, [], [], err_msg
            except Exception as src_err:
                err_msg = f"{stype.capitalize()} acquisition source failed: {type(src_err).__name__}"
                logger.error(f"InformationAcquisitionService: {err_msg} ({src_err})")
                return stype, [], [], err_msg

        results = await asyncio.gather(*[_run_source(src) for src in target_sources])
        for stype, src_items, last_errs, err_msg in results:
            if src_items:
                all_items.extend(src_items)
                sources_used.append(stype)
                source_counts[stype] = len(src_items)
            else:
                source_counts[stype] = 0
            if last_errs:
                all_errors.extend(last_errs)
            if err_msg:
                all_errors.append(err_msg)

        # 3. Deduplicate items by URL / title
        deduped_items = self._deduplicate_items(all_items)

        # 4. Determine overall status
        # If at least one source succeeded or search returned 0 matches cleanly, mark completed
        # Only mark failed if all attempted sources produced errors and 0 items were acquired
        is_completed = len(deduped_items) > 0 or len(all_errors) < len(target_sources)
        status = "completed" if is_completed else "failed"

        duration = (time.monotonic() - start_time) * 1000

        return InformationResult(
            status=status,
            query=cleaned_query,
            items=deduped_items,
            errors=all_errors,
            metadata={
                "duration_ms": round(duration, 2),
                "total_items": len(deduped_items),
                "sources_used": sources_used,
                "source_counts": source_counts,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _select_sources(
        self,
        query: str,
        requested_types: Optional[List[str]] = None,
    ) -> List[InformationSource]:
        """
        Determines which information sources to execute.
        Filters by requested_types if provided; otherwise runs all active configured sources.
        """
        if requested_types:
            req_set = {t.lower() for t in requested_types}
            return [s for s in self._sources if getattr(s, "source_type", "").lower() in req_set]

        # By default, run configured active sources (web, api, model)
        return list(self._sources)

    def _deduplicate_items(self, items: List[InformationItem]) -> List[InformationItem]:
        """Deduplicates items with identical content or identical non-empty URL."""
        seen_keys = set()
        deduped = []
        for item in items:
            key = (item.url or item.content[:80]).strip()
            if key not in seen_keys:
                seen_keys.add(key)
                deduped.append(item)
        return deduped


__all__ = ["InformationAcquisitionService"]
