"""
Deterministic mocked unit and integration tests for the Tavily Search Provider.
Verifies payload structuring, response normalization, timeout/error handling,
API key protection, and integration with WebAcquisitionSource.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from backend.information.models import SearchResult, InformationItem
from backend.information.search import (
    BaseSearchProvider,
    MockSearchProvider,
    TavilySearchProvider,
    HttpSearchProvider,
    get_search_provider,
    get_web_search_api_key,
    extract_domain,
)
from backend.information.fetcher import PageFetcher
from backend.information.extractor import ContentExtractor
from backend.information.cleaner import TextCleaner
from backend.information.web_source import WebAcquisitionSource
from backend.information.service import InformationAcquisitionService


# ==============================================================================
# Sample Tavily API responses
# ==============================================================================
SAMPLE_TAVILY_RESPONSE = {
    "query": "Kubernetes production best practices",
    "response_time": 0.42,
    "results": [
        {
            "title": "Kubernetes Production Best Practices Guide",
            "url": "https://kubernetes.io/docs/setup/best-practices",
            "content": "Official guidelines covering resource quotas, pod disruption budgets, and network policies.",
            "score": 0.98,
            "raw_content": None,
        },
        {
            "title": "Hardening Multi-Tenant Kubernetes Clusters",
            "url": "https://cloud.google.com/architecture/gke-security-hardening",
            "content": "Security recommendations for RBAC, admission controllers, and workload identity.",
            "score": 0.92,
            "raw_content": None,
        },
    ],
}


# ==============================================================================
# 1. API Key Resolution and Validation
# ==============================================================================
def test_tavily_api_key_from_env(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "tvly-test-env-key-12345")
    provider = TavilySearchProvider()
    assert provider.api_key == "tvly-test-env-key-12345"


def test_tavily_api_key_explicit_override(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "tvly-env-key")
    provider = TavilySearchProvider(api_key="tvly-explicit-key")
    assert provider.api_key == "tvly-explicit-key"


@pytest.mark.asyncio
async def test_tavily_missing_api_key_raises_value_error(monkeypatch):
    monkeypatch.delenv("WEB_SEARCH_API_KEY", raising=False)
    provider = TavilySearchProvider(api_key="")
    with pytest.raises(ValueError) as excinfo:
        await provider.search("some technical query")
    assert "WEB_SEARCH_API_KEY" in str(excinfo.value)


# ==============================================================================
# 2. Backward compatibility alias
# ==============================================================================
def test_http_search_provider_alias():
    assert HttpSearchProvider is TavilySearchProvider


# ==============================================================================
# 3. Successful Search and Normalization into SearchResult
# ==============================================================================
@pytest.mark.asyncio
async def test_successful_tavily_search():
    provider = TavilySearchProvider(api_key="tvly-mock-secret")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_TAVILY_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        results = await provider.search("Kubernetes production best practices", max_results=5)

        # Verify request payload
        assert mock_post.called
        call_kwargs = mock_post.call_args.kwargs
        payload = call_kwargs.get("json", {})
        assert payload.get("api_key") == "tvly-mock-secret"
        assert payload.get("query") == "Kubernetes production best practices"
        assert payload.get("max_results") == 5
        assert payload.get("search_depth") == "basic"

        # Verify returned SearchResult objects
        assert len(results) == 2
        assert isinstance(results[0], SearchResult)
        assert results[0].title == "Kubernetes Production Best Practices Guide"
        assert results[0].url == "https://kubernetes.io/docs/setup/best-practices"
        assert "resource quotas" in results[0].snippet
        assert results[0].source == "kubernetes.io"
        assert results[0].metadata.get("score") == 0.98

        assert results[1].title == "Hardening Multi-Tenant Kubernetes Clusters"
        assert results[1].url == "https://cloud.google.com/architecture/gke-security-hardening"
        assert results[1].source == "cloud.google.com"


# ==============================================================================
# 4. Empty or Whitespace Query Handling
# ==============================================================================
@pytest.mark.asyncio
async def test_empty_query_returns_empty_list():
    provider = TavilySearchProvider(api_key="tvly-mock-secret")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        res1 = await provider.search("")
        res2 = await provider.search("   ")
        assert res1 == []
        assert res2 == []
        assert not mock_post.called


# ==============================================================================
# 5. Resilience to Incomplete / Malformed Response Items
# ==============================================================================
@pytest.mark.asyncio
async def test_malformed_and_missing_field_items():
    provider = TavilySearchProvider(api_key="tvly-mock-secret")

    raw_data = {
        "results": [
            # Item with url but no title or content
            {"url": "https://example.com/item1"},
            # Item with no url (should be skipped)
            {"title": "No URL", "content": "Skipped"},
            # Non-dict item (should be skipped)
            "corrupted_entry",
            # Item using snippet field instead of content
            {"url": "https://example.org/item2", "snippet": "Alternative snippet", "score": 0.85},
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = raw_data
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        results = await provider.search("arbitrary query")

        assert len(results) == 2
        assert results[0].url == "https://example.com/item1"
        assert results[0].title == "example.com"  # fallback to domain
        assert results[0].snippet == ""

        assert results[1].url == "https://example.org/item2"
        assert results[1].snippet == "Alternative snippet"
        assert results[1].metadata.get("score") == 0.85


# ==============================================================================
# 6. Timeout and Network Error Handling
# ==============================================================================
@pytest.mark.asyncio
async def test_tavily_timeout_handling():
    provider = TavilySearchProvider(api_key="tvly-mock-secret", timeout_seconds=1.0)

    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timed out")):
        with pytest.raises(TimeoutError) as excinfo:
            await provider.search("timeout query")
        assert "timed out" in str(excinfo.value)


@pytest.mark.asyncio
async def test_tavily_network_connection_error():
    provider = TavilySearchProvider(api_key="tvly-mock-secret")

    req = httpx.Request("POST", "https://api.tavily.com/search")
    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused", request=req)):
        with pytest.raises(RuntimeError) as excinfo:
            await provider.search("network error query")
        assert "network error" in str(excinfo.value).lower()


# ==============================================================================
# 7. HTTP Error Status Handling (401, 429, 500) & Redaction
# ==============================================================================
@pytest.mark.asyncio
async def test_tavily_401_unauthorized():
    provider = TavilySearchProvider(api_key="tvly-secret-key-to-redact")

    req = httpx.Request("POST", "https://api.tavily.com/search")
    resp = httpx.Response(401, request=req, text='{"error": "Invalid API key tvly-secret-key-to-redact"}')
    http_error = httpx.HTTPStatusError("401 Unauthorized", request=req, response=resp)

    with patch("httpx.AsyncClient.post", side_effect=http_error):
        with pytest.raises(RuntimeError) as excinfo:
            await provider.search("auth test query")
        err_text = str(excinfo.value)
        assert "401" in err_text
        # Ensure secret key is NEVER leaked in the exception message
        assert "tvly-secret-key-to-redact" not in err_text


@pytest.mark.asyncio
async def test_tavily_500_server_error():
    provider = TavilySearchProvider(api_key="tvly-mock-secret")

    req = httpx.Request("POST", "https://api.tavily.com/search")
    resp = httpx.Response(500, request=req, text='{"error": "Internal server error"}')
    http_error = httpx.HTTPStatusError("500 Server Error", request=req, response=resp)

    with patch("httpx.AsyncClient.post", side_effect=http_error):
        with pytest.raises(RuntimeError) as excinfo:
            await provider.search("server error query")
        assert "500" in str(excinfo.value)


# ==============================================================================
# 8. Factory get_search_provider Resolution
# ==============================================================================
def test_factory_returns_mock_when_chai_mock_mode_active(monkeypatch):
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "tvly-valid-key")
    provider = get_search_provider()
    assert isinstance(provider, MockSearchProvider)


def test_factory_returns_tavily_when_not_mock_and_key_present(monkeypatch):
    monkeypatch.setenv("CHAI_MOCK_MODE", "false")
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "tvly-valid-key")
    provider = get_search_provider()
    assert isinstance(provider, TavilySearchProvider)
    assert provider.api_key == "tvly-valid-key"


def test_factory_returns_mock_when_no_api_key(monkeypatch):
    monkeypatch.setenv("CHAI_MOCK_MODE", "false")
    monkeypatch.delenv("WEB_SEARCH_API_KEY", raising=False)
    provider = get_search_provider()
    assert isinstance(provider, MockSearchProvider)


def test_factory_explicit_provider_type(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "tvly-key")
    provider = get_search_provider(provider_type="tavily")
    assert isinstance(provider, TavilySearchProvider)

    mock_provider = get_search_provider(provider_type="mock")
    assert isinstance(mock_provider, MockSearchProvider)


# ==============================================================================
# 9. Full WebAcquisitionSource Pipeline Preservation
#    Tavily Search → Fetch → Extract → Clean → Provenance → InformationResult
# ==============================================================================
@pytest.mark.asyncio
async def test_full_pipeline_with_tavily_provider():
    # 1. Tavily Search Provider with mocked API response
    tavily_provider = TavilySearchProvider(api_key="tvly-pipeline-test-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_TAVILY_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    # 2. Page Fetcher with preconfigured HTML responses for the returned URLs
    target_url = "https://kubernetes.io/docs/setup/best-practices"
    mock_html = (
        "<!DOCTYPE html><html><head><title>K8s Best Practices</title></head>"
        "<body><article><h1>Production Standards</h1>"
        "<p>Pod disruption budgets and mutual TLS must be enforced for high availability.</p>"
        "</article></body></html>"
    )
    fetcher = PageFetcher(mock_html_responses={target_url: mock_html})
    extractor = ContentExtractor()
    cleaner = TextCleaner()

    web_source = WebAcquisitionSource(
        search_provider=tavily_provider,
        fetcher=fetcher,
        extractor=extractor,
        cleaner=cleaner,
        max_results=1,
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        items = await web_source.acquire("Kubernetes production best practices")

        # Verify pipeline flow
        assert len(items) == 1
        item = items[0]
        assert isinstance(item, InformationItem)
        assert item.source_type == "web"
        assert item.url == target_url
        assert item.title == "K8s Best Practices"
        assert "Pod disruption budgets" in item.content
        assert item.source == "kubernetes.io"
        assert item.metadata.get("query") == "Kubernetes production best practices"


# ==============================================================================
# 10. WebAcquisitionSource Safe Degradation on Tavily Failure
# ==============================================================================
@pytest.mark.asyncio
async def test_web_acquisition_source_handles_tavily_failure_safely():
    tavily_provider = TavilySearchProvider(api_key="tvly-mock-key")

    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timeout")):
        web_source = WebAcquisitionSource(search_provider=tavily_provider)
        items = await web_source.acquire("query that times out")

        # Must not crash, returns empty list and logs error
        assert items == []
        assert len(web_source.last_errors) > 0
        assert any("error" in e.lower() for e in web_source.last_errors)
