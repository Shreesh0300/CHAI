"""
Test Suite for Multi-Source Information Acquisition Layer in CHAI.

Covers:
1. Web source returns InformationItem (source_type='web')
2. API source successfully parses JSON (source_type='api')
3. API source handles HTTP failure safely without crashing
4. Model source returns structured Gemini knowledge (source_type='model')
5. Model source failure does not crash acquisition
6. Multiple sources combine into one normalized InformationResult
7. Source provenance is preserved across all source types
8. source_type is correct and verified
9. Unverified model knowledge is explicitly marked verified=False
10. One failed source does not remove successful sources (error isolation)
11. Coordinator and Researcher remain source-agnostic
12. RAG placeholder interface functions without requiring vector database
13. Selective source filtering operates deterministically
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import httpx

from backend.information.models import InformationItem, InformationResult, SearchResult
from backend.information.source import (
    SOURCE_TYPE_WEB,
    SOURCE_TYPE_API,
    SOURCE_TYPE_MODEL,
    SOURCE_TYPE_RAG,
)
from backend.information.web_source import WebAcquisitionSource
from backend.information.api_source import APIAcquisitionSource
from backend.information.model_source import ModelKnowledgeSource, ModelKnowledgeResponse
from backend.information.rag_source import RAGInformationSource
from backend.information.service import InformationAcquisitionService
from backend.core.coordinator import Coordinator
from backend.core.schemas import SolveRequest


# ==============================================================================
# 1. Web Source Returns InformationItem
# ==============================================================================

@pytest.mark.asyncio
async def test_1_web_source_returns_information_item():
    mock_search = MagicMock()
    mock_search.search = AsyncMock(return_value=[
        SearchResult(title="Decentralized Identity", url="https://w3c.org/did", snippet="W3C DID Specification")
    ])

    mock_fetcher = MagicMock()
    mock_fetcher.fetch = AsyncMock(return_value=MagicMock(
        success=True,
        html="<html><body><h1>Decentralized Identity</h1><p>W3C global standard for decentralized identifiers.</p></body></html>",
        status_code=200,
    ))

    web_source = WebAcquisitionSource(search_provider=mock_search, fetcher=mock_fetcher)
    items = await web_source.acquire(query="Decentralized Identity")

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, InformationItem)
    assert item.source_type == SOURCE_TYPE_WEB
    assert item.url == "https://w3c.org/did"
    assert "Decentralized" in item.title
    assert "W3C global standard" in item.content


# ==============================================================================
# 2. API Source Successfully Parses JSON
# ==============================================================================

@pytest.mark.asyncio
async def test_2_api_source_successfully_parses_json(monkeypatch):
    monkeypatch.delenv("CHAI_MOCK_MODE", raising=False)

    fake_json = {
        "amount": 1.0,
        "base": "USD",
        "date": "2026-04-01",
        "rates": {"EUR": 0.92, "GBP": 0.79, "JPY": 154.2},
    }

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.content = json.dumps(fake_json).encode("utf-8")
    mock_response.json = MagicMock(return_value=fake_json)

    api_source = APIAcquisitionSource(api_url="https://api.frankfurter.app/latest?from=USD")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        items = await api_source.acquire(query="Current exchange benchmarks")

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, InformationItem)
    assert item.source_type == SOURCE_TYPE_API
    assert "Exchange Rates Reference" in item.content
    assert "EUR: 0.92" in item.content
    assert item.source == "api.frankfurter.app"
    assert item.metadata["status_code"] == 200
    assert item.metadata["source_category"] == "structured_api"


# ==============================================================================
# 3. API Source Handles HTTP Failure Safely
# ==============================================================================

@pytest.mark.asyncio
async def test_3_api_source_handles_http_failure_safely(monkeypatch):
    monkeypatch.delenv("CHAI_MOCK_MODE", raising=False)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 503
    mock_response.content = b"Service Unavailable"

    api_source = APIAcquisitionSource(api_url="https://api.frankfurter.app/latest?from=USD")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        items = await api_source.acquire(query="Exchange rates")

    assert items == []
    assert len(api_source.last_errors) == 1
    assert "503" in api_source.last_errors[0]


# ==============================================================================
# 4. Model Source Returns Structured Gemini Knowledge
# ==============================================================================

@pytest.mark.asyncio
async def test_4_model_source_returns_structured_gemini_knowledge(monkeypatch):
    monkeypatch.delenv("CHAI_MOCK_MODE", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key")

    mock_llm_json = json.dumps({
        "knowledge": [
            "RAFT consensus requires odd number of nodes for quorum.",
            "Network partitions require quorum loss detection.",
        ],
        "assumptions": ["Asynchronous network with bounded message delays."],
        "limitations": ["Assumes non-Byzantine crash-recovery model."],
        "suggested_areas_to_verify": ["Empirical heartbeat timeout in wide-area network."],
    })

    mock_client = MagicMock()
    mock_client.generate_content = AsyncMock(return_value=mock_llm_json)

    source = ModelKnowledgeSource(model_name="gemini-3.8-flash", client=mock_client)
    items = await source.acquire(query="Explain RAFT consensus failure modes")

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, InformationItem)
    assert item.source_type == SOURCE_TYPE_MODEL
    assert "RAFT consensus requires odd number" in item.content
    assert item.url is None
    assert item.source == "gemini-3.8-flash"
    assert item.metadata["provider"] == "gemini"
    assert item.metadata["verified"] is False
    assert item.metadata["source_category"] == "model_knowledge"


# ==============================================================================
# 5. Model Source Failure Does Not Crash Acquisition
# ==============================================================================

@pytest.mark.asyncio
async def test_5_model_source_failure_does_not_crash_acquisition(monkeypatch):
    monkeypatch.delenv("CHAI_MOCK_MODE", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key")

    mock_client = MagicMock()
    mock_client.generate_content = AsyncMock(side_effect=RuntimeError("Google GenAI 429 Quota Exceeded"))

    source = ModelKnowledgeSource(client=mock_client)
    items = await source.acquire(query="Distributed consensus")

    assert items == []
    assert len(source.last_errors) == 1
    assert "Model knowledge acquisition failed" in source.last_errors[0]


# ==============================================================================
# 6. Multiple Sources Combine into One InformationResult
# ==============================================================================

@pytest.mark.asyncio
async def test_6_multiple_sources_combine_into_one_information_result():
    # Web item
    mock_web = MagicMock()
    mock_web.source_type = SOURCE_TYPE_WEB
    mock_web.last_errors = []
    mock_web.acquire = AsyncMock(return_value=[
        InformationItem(
            content="Web page analysis of quantum encryption.",
            title="Quantum Safe Cryptography",
            url="https://nist.gov/pqc",
            source="nist.gov",
            source_type=SOURCE_TYPE_WEB,
        )
    ])

    # API item
    mock_api = MagicMock()
    mock_api.source_type = SOURCE_TYPE_API
    mock_api.last_errors = []
    mock_api.acquire = AsyncMock(return_value=[
        InformationItem(
            content="Foreign exchange rate metrics: EUR: 0.92, USD: 1.0.",
            title="API Data: frankfurter.app",
            url="https://api.frankfurter.app/latest",
            source="frankfurter.app",
            source_type=SOURCE_TYPE_API,
        )
    ])

    # Model item
    mock_model = MagicMock()
    mock_model.source_type = SOURCE_TYPE_MODEL
    mock_model.last_errors = []
    mock_model.acquire = AsyncMock(return_value=[
        InformationItem(
            content="Theoretical principles of post-quantum lattice cryptography.",
            title="Model Knowledge: Post-Quantum",
            url=None,
            source="gemini-3.8-flash",
            source_type=SOURCE_TYPE_MODEL,
            metadata={"verified": False, "source_category": "model_knowledge"},
        )
    ])

    service = InformationAcquisitionService(
        sources=[mock_web, mock_api, mock_model]
    )

    result = await service.acquire(query="Implement post-quantum secure payment gateway")

    assert isinstance(result, InformationResult)
    assert result.status == "completed"
    assert len(result.items) == 3

    types = {item.source_type for item in result.items}
    assert types == {SOURCE_TYPE_WEB, SOURCE_TYPE_API, SOURCE_TYPE_MODEL}
    assert result.metadata["sources_used"] == [SOURCE_TYPE_WEB, SOURCE_TYPE_API, SOURCE_TYPE_MODEL]


# ==============================================================================
# 7. Source Provenance is Preserved
# ==============================================================================

@pytest.mark.asyncio
async def test_7_source_provenance_is_preserved():
    mock_web = MagicMock()
    mock_web.source_type = SOURCE_TYPE_WEB
    mock_web.acquire = AsyncMock(return_value=[
        InformationItem(
            content="Web content",
            title="Web Title",
            url="https://example.com/page",
            source="example.com",
            source_type=SOURCE_TYPE_WEB,
            metadata={"retrieved_at": "2026-04-01T00:00:00Z"},
        )
    ])

    mock_api = MagicMock()
    mock_api.source_type = SOURCE_TYPE_API
    mock_api.acquire = AsyncMock(return_value=[
        InformationItem(
            content="API content",
            title="API Data: api.example.com",
            url="https://api.example.com/data",
            source="api.example.com",
            source_type=SOURCE_TYPE_API,
            metadata={"endpoint": "https://api.example.com/data"},
        )
    ])

    service = InformationAcquisitionService(sources=[mock_web, mock_api])
    res = await service.acquire(query="Test query")

    assert len(res.items) == 2
    web_item = next(i for i in res.items if i.source_type == "web")
    api_item = next(i for i in res.items if i.source_type == "api")

    assert web_item.url == "https://example.com/page"
    assert web_item.source == "example.com"
    assert api_item.url == "https://api.example.com/data"
    assert api_item.source == "api.example.com"


# ==============================================================================
# 8. source_type is Correct Across Items
# ==============================================================================

@pytest.mark.asyncio
async def test_8_source_type_is_correct():
    item_web = InformationItem(content="C1", source="s1", source_type="web")
    item_api = InformationItem(content="C2", source="s2", source_type="api")
    item_model = InformationItem(content="C3", source="s3", source_type="model")
    item_rag = InformationItem(content="C4", source="s4", source_type="rag")

    assert item_web.source_type == "web"
    assert item_api.source_type == "api"
    assert item_model.source_type == "model"
    assert item_rag.source_type == "rag"


# ==============================================================================
# 9. Unverified Model Knowledge Marked as Such
# ==============================================================================

@pytest.mark.asyncio
async def test_9_unverified_model_knowledge_marked_as_such(monkeypatch):
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    model_source = ModelKnowledgeSource()
    items = await model_source.acquire(query="Distributed transactions")

    assert len(items) == 1
    item = items[0]
    assert item.source_type == SOURCE_TYPE_MODEL
    assert item.metadata["verified"] is False
    assert item.metadata["source_category"] == "model_knowledge"
    assert item.metadata["provider"] == "gemini"


# ==============================================================================
# 10. One Failed Source Does Not Remove Successful Sources
# ==============================================================================

@pytest.mark.asyncio
async def test_10_one_failed_source_does_not_remove_successful_sources():
    # Web throws
    failing_web = MagicMock()
    failing_web.source_type = SOURCE_TYPE_WEB
    failing_web.acquire = AsyncMock(side_effect=RuntimeError("DNS resolution failed"))

    # API succeeds
    working_api = MagicMock()
    working_api.source_type = SOURCE_TYPE_API
    working_api.last_errors = []
    working_api.acquire = AsyncMock(return_value=[
        InformationItem(content="Live API payload", source="api.com", source_type=SOURCE_TYPE_API)
    ])

    # Model succeeds
    working_model = MagicMock()
    working_model.source_type = SOURCE_TYPE_MODEL
    working_model.last_errors = []
    working_model.acquire = AsyncMock(return_value=[
        InformationItem(content="Theoretical model knowledge", source="gemini", source_type=SOURCE_TYPE_MODEL, metadata={"verified": False})
    ])

    service = InformationAcquisitionService(sources=[failing_web, working_api, working_model])
    result = await service.acquire(query="Resilience test query")

    assert result.status == "completed"
    assert len(result.items) == 2
    types = {i.source_type for i in result.items}
    assert types == {SOURCE_TYPE_API, SOURCE_TYPE_MODEL}
    assert len(result.errors) >= 1
    assert any("Web acquisition source failed" in err for err in result.errors)


# ==============================================================================
# 11. Coordinator and Researcher Remain Source-Agnostic
# ==============================================================================

@pytest.mark.asyncio
async def test_11_coordinator_remains_source_agnostic(monkeypatch):
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")

    mock_info = AsyncMock()
    mock_info.acquire = AsyncMock(return_value=InformationResult(
        status="completed",
        query="Design a payment processing microservice",
        items=[
            InformationItem(content="Web guide on payments", source="stripe.com", source_type="web"),
            InformationItem(content="API FX rates", source="frankfurter.app", source_type="api"),
            InformationItem(content="Model principles", source="gemini", source_type="model", metadata={"verified": False}),
        ]
    ))

    coordinator = Coordinator(information_acquisition=mock_info)
    response = await coordinator.process_request(
        SolveRequest(problem="Design a payment processing microservice with multi-currency support")
    )

    assert response.route == "complex"
    assert response.request_status == "completed"
    # Acquired information preserved in response
    assert len(response.acquired_information) == 3
    source_types = [item["source_type"] for item in response.acquired_information]
    assert "web" in source_types
    assert "api" in source_types
    assert "model" in source_types


# ==============================================================================
# 12. RAG Placeholder Interface Operates Without Requiring Vector Database
# ==============================================================================

@pytest.mark.asyncio
async def test_12_rag_placeholder_does_not_require_vector_db():
    rag = RAGInformationSource()
    assert rag.source_type == SOURCE_TYPE_RAG
    assert rag.is_available() is False

    with pytest.raises(NotImplementedError) as exc_info:
        await rag.acquire(query="Enterprise proprietary policy documents")

    assert "future architectural milestone" in str(exc_info.value)


# ==============================================================================
# 13. Selective Source Filtering Operates Deterministically
# ==============================================================================

@pytest.mark.asyncio
async def test_13_deterministic_source_selection():
    mock_web = MagicMock()
    mock_web.source_type = SOURCE_TYPE_WEB
    mock_web.acquire = AsyncMock(return_value=[
        InformationItem(content="Web content", source="web", source_type=SOURCE_TYPE_WEB)
    ])

    mock_api = MagicMock()
    mock_api.source_type = SOURCE_TYPE_API
    mock_api.acquire = AsyncMock(return_value=[
        InformationItem(content="API content", source="api", source_type=SOURCE_TYPE_API)
    ])

    service = InformationAcquisitionService(sources=[mock_web, mock_api])

    # Request only API source
    res = await service.acquire(query="Filter test", source_types=["api"])
    assert len(res.items) == 1
    assert res.items[0].source_type == SOURCE_TYPE_API
    mock_api.acquire.assert_called_once()
    mock_web.acquire.assert_not_called()
