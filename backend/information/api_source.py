"""
Generic API Acquisition Source for CHAI.

Fetches structured data from external HTTP JSON APIs (such as Frankfurter or Open-Meteo),
safeguards against SSRF, bounds payload size and timeout, and normalizes the payload
into canonical InformationItem objects with source_type='api'.
"""
from __future__ import annotations

import os
import json
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import httpx

from backend.information.source import BaseInformationSource, SOURCE_TYPE_API
from backend.information.models import InformationItem
from backend.information.fetcher import validate_url
from backend.shared.logger import get_logger

logger = get_logger(__name__)

DEFAULT_API_URL = "https://api.frankfurter.app/latest?from=USD"


class APIAcquisitionSource(BaseInformationSource):
    """
    Generic API acquisition source that retrieves and normalizes JSON data
    from external HTTP/HTTPS REST endpoints into InformationItems.
    """
    source_type: str = SOURCE_TYPE_API

    def __init__(
        self,
        api_url: Optional[str] = None,
        default_params: Optional[Dict[str, Any]] = None,
        timeout_seconds: float = 5.0,
        max_bytes: int = 500_000,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.api_url = api_url or os.getenv("API_SOURCE_URL") or DEFAULT_API_URL
        self.default_params = default_params or {}
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.headers = headers or {"User-Agent": "CHAI-Agent-Intelligence/1.0"}
        self.last_errors: List[str] = []

    async def acquire(
        self,
        query: str,
        context: Optional[str] = None,
    ) -> List[InformationItem]:
        """
        Executes HTTP GET on the configured API endpoint, validates the response,
        parses JSON, and normalizes the contents into InformationItem instances.
        """
        self.last_errors = []
        cleaned_query = (query or "").strip()

        # Offline / Mock mode check
        if os.getenv("CHAI_MOCK_MODE", "").lower() in ("true", "1", "yes"):
            logger.info("APIAcquisitionSource: returning deterministic mock data in mock mode")
            return [self._create_mock_item(cleaned_query)]

        target_url = self.api_url
        is_valid, validation_err = validate_url(target_url)
        if not is_valid:
            err_msg = f"API source URL validation failed: {validation_err}"
            logger.error(err_msg)
            self.last_errors.append(err_msg)
            return []

        parsed = urllib.parse.urlparse(target_url)
        domain = parsed.netloc or "external-api"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = await client.get(
                    target_url,
                    params=self.default_params or None,
                    headers=self.headers,
                )

                if response.status_code >= 400:
                    err_msg = f"API request to '{domain}' failed with status {response.status_code}"
                    logger.warning(err_msg)
                    self.last_errors.append(err_msg)
                    return []

                # Size limit verification
                raw_bytes = response.content
                if len(raw_bytes) > self.max_bytes:
                    err_msg = f"API response size ({len(raw_bytes)} bytes) exceeded limit of {self.max_bytes} bytes."
                    logger.warning(err_msg)
                    self.last_errors.append(err_msg)
                    return []

                try:
                    data = response.json()
                except Exception as json_err:
                    err_msg = f"Failed to parse JSON from API '{domain}': {json_err}"
                    logger.warning(err_msg)
                    self.last_errors.append(err_msg)
                    return []

                content_text = self._normalize_json_to_text(data, domain=domain, query=cleaned_query)

                item = InformationItem(
                    content=content_text,
                    title=f"API Data: {domain}",
                    url=target_url,
                    source=domain,
                    source_type=SOURCE_TYPE_API,
                    metadata={
                        "endpoint": target_url,
                        "status_code": response.status_code,
                        "query": cleaned_query,
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "verified": True,
                        "source_category": "structured_api",
                    },
                )
                return [item]

        except httpx.TimeoutException:
            err_msg = f"API request to '{domain}' timed out after {self.timeout_seconds}s"
            logger.warning(err_msg)
            self.last_errors.append(err_msg)
            return []
        except Exception as e:
            err_msg = f"API acquisition error for '{domain}': {type(e).__name__}"
            logger.error(err_msg)
            self.last_errors.append(err_msg)
            return []

    def _normalize_json_to_text(self, data: Any, domain: str, query: str) -> str:
        """
        Deterministically flattens structured API response JSON into clear readable text.
        Special handling for Frankfurter exchange rates and generic JSON dictionaries.
        """
        if isinstance(data, dict):
            # Special Frankfurter structure: {amount, base, date, rates}
            if "rates" in data and "base" in data:
                base = data.get("base", "USD")
                date = data.get("date", "")
                rates = data.get("rates", {})
                rate_snippets = [f"{cur}: {val}" for cur, val in list(rates.items())[:10]]
                return (
                    f"Official Exchange Rates Reference ({base}, date: {date}):\n"
                    f"Sample exchange benchmarks: {', '.join(rate_snippets)}."
                )

            # Special Open-Meteo structure
            if "current_weather" in data:
                cw = data["current_weather"]
                temp = cw.get("temperature", "N/A")
                wind = cw.get("windspeed", "N/A")
                return f"Live Meteorological Reference for {domain}: Temp: {temp}°C, Wind Speed: {wind} km/h."

            # Generic JSON dict
            parts = [f"Structured API metrics from {domain}:"]
            for k, v in list(data.items())[:8]:
                if isinstance(v, (str, int, float, bool)):
                    parts.append(f"- {k}: {v}")
                elif isinstance(v, dict):
                    parts.append(f"- {k}: {json.dumps(v)[:100]}")
            return "\n".join(parts)

        elif isinstance(data, list):
            items_summary = [json.dumps(x)[:80] for x in data[:5]]
            return f"Structured records from {domain} ({len(data)} items):\n" + "\n".join(f"- {s}" for s in items_summary)

        return str(data)

    def _create_mock_item(self, query: str) -> InformationItem:
        """Returns a plausible mock InformationItem for offline tests."""
        parsed = urllib.parse.urlparse(self.api_url)
        domain = parsed.netloc or "api.frankfurter.app"
        return InformationItem(
            content=(
                f"Official Exchange Rates Reference (USD, date: 2026-04-01):\n"
                f"Sample exchange benchmarks: EUR: 0.92, GBP: 0.79, JPY: 154.2, CAD: 1.36, AUD: 1.52."
            ),
            title=f"API Data: {domain}",
            url=self.api_url,
            source=domain,
            source_type=SOURCE_TYPE_API,
            metadata={
                "endpoint": self.api_url,
                "status_code": 200,
                "query": query,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "verified": True,
                "mock_mode": True,
                "source_category": "structured_api",
            },
        )


__all__ = ["APIAcquisitionSource", "DEFAULT_API_URL"]
