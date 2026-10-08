"""
Web search abstraction and provider implementations for Information Acquisition.
"""
import os
import urllib.parse
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from backend.information.models import SearchResult
from backend.shared.logger import get_logger

logger = get_logger(__name__)


def extract_domain(url: str) -> str:
    """Safely extracts domain name from URL."""
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc.lower() or "web"
    except Exception:
        return "web"


class BaseSearchProvider(ABC):
    """
    Abstract interface for search providers.
    Allows swappable search backends (e.g., Mock, Tavily, Google Custom Search, etc.).
    """

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """
        Executes a search query and returns structured search results.

        Args:
            query: Non-empty search query string.
            max_results: Upper bound on the number of results to return.

        Returns:
            List of SearchResult objects.
        """
        pass


class MockSearchProvider(BaseSearchProvider):
    """
    Deterministic mock search provider for unit testing, offline development,
    and mock mode execution.
    """

    def __init__(self, fixed_results: Optional[List[SearchResult]] = None, fail: bool = False):
        self.fixed_results = fixed_results
        self.fail = fail

    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        if self.fail:
            raise RuntimeError("Mock search provider simulated failure.")

        if self.fixed_results is not None:
            return self.fixed_results[:max_results]

        cleaned_query = (query or "").strip().lower()
        results: List[SearchResult] = []

        if any(w in cleaned_query for w in ["health", "medical", "clinic", "patient"]):
            results = [
                SearchResult(
                    title="WHO Digital Health Guidelines and Standards",
                    url="https://who.int/publications/digital-health-guidelines",
                    snippet="Official technical frameworks for reliable, private, and accessible clinical applications.",
                    source="who.int",
                ),
                SearchResult(
                    title="HIPAA and GDPR Compliance for Cloud Healthcare Platforms",
                    url="https://healthit.gov/privacy-security/cloud-compliance",
                    snippet="Regulatory safeguards, data residency, and audit trails required for health data storage.",
                    source="healthit.gov",
                ),
                SearchResult(
                    title="Offline-First Edge Synchronization in Rural Clinics",
                    url="https://cdc.gov/informatics/edge-sync-framework",
                    snippet="Architectural guidelines for resilient local caching, delta replication, and battery-friendly operation.",
                    source="cdc.gov",
                ),
            ]
        elif any(w in cleaned_query for w in ["payment", "bank", "financial", "transaction"]):
            results = [
                SearchResult(
                    title="PCI-DSS Requirements for Distributed Payment Processing",
                    url="https://pcisecuritystandards.org/guidelines/cloud-distributed-payments",
                    snippet="Security requirements for tokenization, encryption in transit, and HSM integration in multi-region deployments.",
                    source="pcisecuritystandards.org",
                ),
                SearchResult(
                    title="High-Throughput Distributed Ledger and Settlement Architecture",
                    url="https://acm.org/distributed-systems/settlement-consensus",
                    snippet="Consensus mechanisms, idempotent message processing, and fault tolerance for financial pipelines.",
                    source="acm.org",
                ),
            ]
        elif any(w in cleaned_query for w in ["security", "threat", "vulnerability", "auth"]):
            results = [
                SearchResult(
                    title="OWASP Top 10 API Security Risks and Mitigations",
                    url="https://owasp.org/www-project-api-security",
                    snippet="Analysis of authorization bypasses, rate limiting, and broken object level authorization.",
                    source="owasp.org",
                ),
                SearchResult(
                    title="Zero Trust Architecture Guidelines (NIST SP 800-207)",
                    url="https://nist.gov/publications/zero-trust-architecture",
                    snippet="Principles for continuous authentication, least privilege access, and microsegmentation.",
                    source="nist.gov",
                ),
            ]
        else:
            # General fallback results for arbitrary technical queries
            slug = "-".join(cleaned_query.split()[:4]) or "overview"
            results = [
                SearchResult(
                    title=f"Technical Architecture Reference: {query.title()}",
                    url=f"https://engineering.org/docs/{slug}",
                    snippet=f"Comprehensive engineering practices, specifications, and design guidelines for {query}.",
                    source="engineering.org",
                ),
                SearchResult(
                    title=f"Best Practices and Guidelines for {query.title()}",
                    url=f"https://developer.org/articles/{slug}",
                    snippet=f"Practical patterns, reliability recommendations, and trade-offs for {query}.",
                    source="developer.org",
                ),
            ]

        return results[:max_results]


def get_web_search_api_key() -> str:
    """Safely retrieves the web search API key from environment."""
    return os.getenv("WEB_SEARCH_API_KEY", "").strip()


class TavilySearchProvider(BaseSearchProvider):
    """
    Search provider backed by Tavily Search API.
    Adapts Tavily JSON requests/responses into CHAI SearchResult models.
    Uses the WEB_SEARCH_API_KEY environment variable.
    """

    DEFAULT_ENDPOINT: str = "https://api.tavily.com/search"

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint_url: str = DEFAULT_ENDPOINT,
        timeout_seconds: float = 8.0,
    ):
        self.api_key = (api_key if api_key is not None else get_web_search_api_key()).strip()
        self.endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds

    def _redact_key(self, msg: str) -> str:
        """Helper to ensure API key is never leaked in logs or error messages."""
        if self.api_key and self.api_key in msg:
            return msg.replace(self.api_key, "[REDACTED]")
        return msg

    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        cleaned_query = (query or "").strip()
        if not cleaned_query:
            return []

        if not self.api_key:
            raise ValueError("WEB_SEARCH_API_KEY is not configured.")

        import httpx

        clamped_max_results = max(1, min(max_results, 20))
        payload = {
            "api_key": self.api_key,
            "query": cleaned_query,
            "max_results": clamped_max_results,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(
                    self.endpoint_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as exc:
            logger.warning(
                f"TavilySearchProvider timeout after {self.timeout_seconds}s for query '{cleaned_query[:40]}'"
            )
            raise TimeoutError(f"Tavily search timed out after {self.timeout_seconds}s") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            safe_msg = f"Tavily API returned HTTP status {status}"
            logger.error(f"TavilySearchProvider HTTP error: {safe_msg}")
            raise RuntimeError(safe_msg) from exc
        except httpx.RequestError as exc:
            safe_msg = f"Tavily search network error: {type(exc).__name__}"
            logger.error(f"TavilySearchProvider network error: {safe_msg}")
            raise RuntimeError(safe_msg) from exc
        except Exception as exc:
            err_msg = self._redact_key(str(exc))
            logger.error(f"TavilySearchProvider unexpected error: {err_msg}")
            raise RuntimeError(f"Tavily search error: {type(exc).__name__}") from None

        if not isinstance(data, dict):
            logger.warning("TavilySearchProvider received non-dict JSON response.")
            return []

        raw_results = data.get("results", [])
        if not isinstance(raw_results, list):
            logger.warning("TavilySearchProvider 'results' field is not a list.")
            return []

        results: List[SearchResult] = []
        for item in raw_results[:clamped_max_results]:
            if not isinstance(item, dict):
                continue

            url = (item.get("url") or "").strip()
            if not url:
                continue

            title = (item.get("title") or "").strip()
            snippet = (item.get("content") or item.get("snippet") or "").strip()
            domain = extract_domain(url)

            meta: Dict[str, Any] = {}
            if "score" in item and item["score"] is not None:
                meta["score"] = item["score"]

            results.append(
                SearchResult(
                    title=title or domain,
                    url=url,
                    snippet=snippet,
                    source=domain,
                    metadata=meta,
                )
            )

        return results


# Backward compatibility alias
HttpSearchProvider = TavilySearchProvider


def get_search_provider(
    provider_type: Optional[str] = None,
    fixed_results: Optional[List[SearchResult]] = None,
) -> BaseSearchProvider:
    """
    Factory function returning the appropriate search provider based on
    environment variables and explicit configuration.
    """
    if fixed_results is not None:
        return MockSearchProvider(fixed_results=fixed_results)

    if provider_type == "mock":
        return MockSearchProvider()

    if provider_type in ("tavily", "http"):
        api_key = get_web_search_api_key()
        return TavilySearchProvider(api_key=api_key)

    is_mock = os.getenv("CHAI_MOCK_MODE", "").lower() in ("true", "1", "yes")
    api_key = get_web_search_api_key()

    if is_mock or not api_key:
        return MockSearchProvider()

    return TavilySearchProvider(api_key=api_key)


__all__ = [
    "BaseSearchProvider",
    "MockSearchProvider",
    "TavilySearchProvider",
    "HttpSearchProvider",
    "get_search_provider",
    "get_web_search_api_key",
    "extract_domain",
]
