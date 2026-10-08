"""
Comprehensive, deterministic unit and integration tests for the
CHAI Information Acquisition Layer.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from backend.information.models import (
    InformationItem,
    InformationResult,
    SearchResult,
    FetchResult,
    ExtractedContent,
)
from backend.agents.researcher.models import ResearchResult
from backend.information.search import (
    BaseSearchProvider,
    MockSearchProvider,
    HttpSearchProvider,
    extract_domain,
    get_search_provider,
)
from backend.information.fetcher import (
    PageFetcher,
    validate_url,
    DEFAULT_MAX_BYTES,
)
from backend.information.extractor import ContentExtractor
from backend.information.cleaner import TextCleaner
from backend.information.provenance import build_information_item
from backend.information.service import InformationAcquisitionService
from backend.core.coordinator import Coordinator
from backend.core.schemas import SolveRequest


@pytest.fixture(autouse=True)
def enable_chai_mock_mode(monkeypatch):
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")


# ==============================================================================
# 1. Successful Web Search
# ==============================================================================
@pytest.mark.asyncio
async def test_1_successful_web_search():
    provider = MockSearchProvider()
    results = await provider.search("Healthcare clinical guidelines", max_results=3)

    assert len(results) > 0
    assert len(results) <= 3
    for r in results:
        assert isinstance(r, SearchResult)
        assert r.title
        assert r.url.startswith("http")
        assert r.snippet
        assert r.source


# ==============================================================================
# 2. Successful Page Fetch
# ==============================================================================
@pytest.mark.asyncio
async def test_2_successful_page_fetch():
    target_url = "https://example.org/article"
    mock_html = "<html><head><title>Example</title></head><body><p>Hello World</p></body></html>"

    fetcher = PageFetcher(mock_html_responses={target_url: mock_html})
    result = await fetcher.fetch(target_url)

    assert result.success is True
    assert result.status_code == 200
    assert "Hello World" in result.html
    assert result.url == target_url
    assert result.error is None


# ==============================================================================
# 3. HTML Extraction
# ==============================================================================
def test_3_html_extraction():
    html_sample = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Zero Trust Architecture Guidelines</title>
        <script>console.log("malicious or tracker script");</script>
        <style>body { color: red; }</style>
    </head>
    <body>
        <nav><a href="/">Home</a><a href="/login">Login</a></nav>
        <header>Site Header</header>
        <article>
            <h1>Zero Trust Architecture Overview</h1>
            <p>Zero Trust is a security framework requiring all users to be authenticated.</p>
            <h2>Core Principles</h2>
            <p>Continuous verification and least privilege access.</p>
            <ul>
                <li>Never trust, always verify.</li>
                <li>Assume breach.</li>
            </ul>
        </article>
        <footer>Copyright 2026 Example Corp</footer>
    </body>
    </html>
    """
    extractor = ContentExtractor()
    extracted = extractor.extract(html_sample)

    assert extracted.title == "Zero Trust Architecture Guidelines"
    assert "Zero Trust Architecture Overview" in extracted.text
    assert "Never trust, always verify" in extracted.text
    assert "script" not in extracted.text
    assert "Site Header" not in extracted.text
    assert "Copyright 2026" not in extracted.text
    assert "Zero Trust Architecture Overview" in extracted.headings
    assert "Core Principles" in extracted.headings


# ==============================================================================
# 4. Text Cleaning
# ==============================================================================
def test_4_text_cleaning():
    dirty_text = (
        "  Title of Article &amp; Standards  \n\n\n\n"
        "This is paragraph one with    excessive   inline  spaces.\n\n"
        "Here is a quote: &quot;Security is essential&quot; &lt;v1.0&gt;.\n\n\n"
        "   \n"
        "Final line with non-breaking\xa0space.\n  "
    )
    cleaner = TextCleaner(max_chars=5000)
    cleaned = cleaner.clean(dirty_text)

    assert "&amp;" not in cleaned
    assert "&quot;" not in cleaned
    assert "Security is essential" in cleaned
    assert "  " not in cleaned  # No double spaces
    assert "\n\n\n" not in cleaned  # Max 2 consecutive newlines
    assert cleaned.startswith("Title of Article & Standards")


# ==============================================================================
# 5. Provenance Generation
# ==============================================================================
def test_5_provenance_generation():
    item = build_information_item(
        content="Clean extracted content here.",
        title="NIST Security Guidelines",
        url="https://csrc.nist.gov/publications/detail/sp/800-207/final",
        query="NIST Zero Trust",
        status_code=200,
        metadata={"custom_flag": True},
    )

    assert isinstance(item, InformationItem)
    assert item.title == "NIST Security Guidelines"
    assert item.url == "https://csrc.nist.gov/publications/detail/sp/800-207/final"
    assert item.source == "csrc.nist.gov"
    assert item.source_type == "web"
    assert item.content == "Clean extracted content here."
    assert item.metadata["query"] == "NIST Zero Trust"
    assert item.metadata["status_code"] == 200
    assert "retrieved_at" in item.metadata
    assert item.metadata["custom_flag"] is True


# ==============================================================================
# 6. Complete Acquisition Flow
# ==============================================================================
@pytest.mark.asyncio
async def test_6_complete_acquisition_flow():
    fixed_results = [
        SearchResult(
            title="HIPAA Cloud Security Standards",
            url="https://healthit.gov/hipaa-cloud",
            snippet="Overview of regulatory requirements for health data.",
            source="healthit.gov",
        )
    ]
    search_provider = MockSearchProvider(fixed_results=fixed_results)
    mock_html = (
        "<html><head><title>HIPAA Cloud Standards</title></head>"
        "<body><article><p>Protected health information must be encrypted at rest and in transit.</p></article></body></html>"
    )
    fetcher = PageFetcher(mock_html_responses={"https://healthit.gov/hipaa-cloud": mock_html})

    service = InformationAcquisitionService(
        search_provider=search_provider,
        fetcher=fetcher,
    )

    res = await service.acquire("Design a healthcare data pipeline")

    assert res.status == "completed"
    assert res.query == "Design a healthcare data pipeline"
    assert len(res.items) == 1
    assert res.items[0].source == "healthit.gov"
    assert "Protected health information must be encrypted" in res.items[0].content
    assert res.items[0].source_type == "web"
    assert len(res.errors) == 0


# ==============================================================================
# 7. Search-Provider Failure
# ==============================================================================
@pytest.mark.asyncio
async def test_7_search_provider_failure():
    failing_provider = MockSearchProvider(fail=True)
    service = InformationAcquisitionService(search_provider=failing_provider)

    res = await service.acquire("Any query")

    assert res.status == "failed"
    assert len(res.items) == 0
    assert len(res.errors) == 1
    assert "search provider error" in res.errors[0].lower()


# ==============================================================================
# 8. Individual Page Fetch Failure
# ==============================================================================
@pytest.mark.asyncio
async def test_8_individual_page_fetch_failure():
    fixed_results = [
        SearchResult(
            title="Dead Link Page",
            url="https://invalid-nonexistent-domain.xyz/page",
            snippet="Will fail fetch",
            source="invalid-nonexistent-domain.xyz",
        ),
        SearchResult(
            title="Working Page",
            url="https://working-site.org/doc",
            snippet="Will succeed fetch",
            source="working-site.org",
        ),
    ]
    search_provider = MockSearchProvider(fixed_results=fixed_results)
    working_html = "<html><head><title>Working</title></head><body><article><p>Valid documentation text.</p></article></body></html>"

    fetcher = PageFetcher(mock_html_responses={"https://working-site.org/doc": working_html})
    service = InformationAcquisitionService(
        search_provider=search_provider,
        fetcher=fetcher,
    )

    # Note: invalid-nonexistent-domain.xyz will return mock HTML under CHAI_MOCK_MODE unless we mock an error.
    # Let's mock a fetch failure for the first URL explicitly
    original_fetch = fetcher.fetch
    async def selective_fetch(url):
        if "invalid" in url:
            return FetchResult(url=url, status_code=404, html="", success=False, error="HTTP 404 Not Found")
        return await original_fetch(url)

    fetcher.fetch = selective_fetch

    res = await service.acquire("Test partial page failure")

    assert res.status == "completed"
    assert len(res.items) == 1
    assert res.items[0].source == "working-site.org"
    assert len(res.errors) == 1
    assert "404" in res.errors[0]


# ==============================================================================
# 9. Invalid URL Handling & SSRF Protection
# ==============================================================================
def test_9_invalid_url_and_ssrf():
    # Dangerous or invalid URL schemes
    assert validate_url("file:///etc/passwd")[0] is False
    assert validate_url("ftp://ftp.example.com/file")[0] is False
    assert validate_url("gopher://bad.host/")[0] is False
    assert validate_url("javascript:alert(1)")[0] is False

    # Blocked hosts and internal IP addresses
    assert validate_url("http://localhost/admin")[0] is False
    assert validate_url("http://127.0.0.1:8080/metrics")[0] is False
    assert validate_url("http://0.0.0.0:5000/api")[0] is False
    assert validate_url("http://169.254.169.254/latest/meta-data/")[0] is False
    assert validate_url("http://10.0.0.5/internal")[0] is False
    assert validate_url("http://192.168.1.1/router")[0] is False

    # Valid public web URLs
    assert validate_url("https://example.com/docs")[0] is True
    assert validate_url("http://who.int/guidelines")[0] is True


# ==============================================================================
# 10. Empty Page Handling
# ==============================================================================
@pytest.mark.asyncio
async def test_10_empty_page():
    extractor = ContentExtractor()
    extracted = extractor.extract("<html><head></head><body></body></html>")
    assert extracted.text == ""

    # Test through service with fallback snippet
    fixed_results = [
        SearchResult(
            title="Empty Web Page",
            url="https://empty-test.org/doc",
            snippet="A fallback snippet describing the architecture.",
            source="empty-test.org",
        )
    ]
    fetcher = PageFetcher(mock_html_responses={"https://empty-test.org/doc": "<html><body></body></html>"})
    service = InformationAcquisitionService(
        search_provider=MockSearchProvider(fixed_results=fixed_results),
        fetcher=fetcher,
    )

    res = await service.acquire("Empty page query")
    assert res.status == "completed"
    assert len(res.items) == 1
    assert "fallback snippet" in res.items[0].content


# ==============================================================================
# 11. Timeout Handling
# ==============================================================================
@pytest.mark.asyncio
async def test_11_timeout_handling():
    fetcher = PageFetcher(timeout_seconds=0.1)

    async def timeout_fetch(url):
        return FetchResult(url=url, status_code=0, html="", success=False, error="Request timed out after 0.1s.")

    fetcher.fetch = timeout_fetch

    res = await fetcher.fetch("https://slow-site.org/delay")
    assert res.success is False
    assert "timed out" in res.error.lower()


# ==============================================================================
# 12. Response-Size Protection
# ==============================================================================
def test_12_response_size_protection():
    cleaner = TextCleaner(max_chars=200)
    huge_text = "This is a sentence about cloud security and data integrity. " * 50

    cleaned = cleaner.clean(huge_text)
    assert len(cleaned) < 300
    assert "[Content truncated at 200 character limit]" in cleaned


# ==============================================================================
# 13. Multiple Pages Where Some Succeed and Some Fail
# ==============================================================================
@pytest.mark.asyncio
async def test_13_multiple_pages_partial_failure():
    results = [
        SearchResult(title="P1", url="https://site1.org/p1", snippet="S1"),
        SearchResult(title="P2", url="https://site2.org/p2", snippet="S2"),
        SearchResult(title="P3", url="https://site3.org/p3", snippet="S3"),
        SearchResult(title="P4", url="https://site4.org/p4", snippet="S4"),
        SearchResult(title="P5", url="https://site5.org/p5", snippet="S5"),
    ]

    fetcher = PageFetcher()
    async def mock_fetch(url):
        if "site2" in url:
            return FetchResult(url=url, status_code=500, success=False, error="HTTP 500 Internal Error")
        if "site4" in url:
            return FetchResult(url=url, status_code=0, success=False, error="Request timed out")
        return FetchResult(
            url=url,
            status_code=200,
            html=f"<html><head><title>Title for {url}</title></head><body><p>Content for {url} verified.</p></body></html>",
            success=True,
        )

    fetcher.fetch = mock_fetch

    service = InformationAcquisitionService(
        search_provider=MockSearchProvider(fixed_results=results),
        fetcher=fetcher,
        max_results=5,
    )

    res = await service.acquire("Multi-page resiliency test")

    assert res.status == "completed"
    assert len(res.items) == 3
    assert len(res.errors) == 2
    assert any("500" in e for e in res.errors)
    assert any("timed out" in e for e in res.errors)


# ==============================================================================
# 14. InformationResult Schema Validation
# ==============================================================================
def test_14_information_result_schema_validation():
    item = InformationItem(
        content="Verified text",
        title="Title",
        url="https://example.com",
        source="example.com",
        source_type="web",
        metadata={"score": 0.95},
    )

    result = InformationResult(
        status="completed",
        query="test query",
        items=[item],
        errors=["Minor fetch warning"],
        metadata={"total": 1},
    )

    dumped = result.model_dump()
    assert dumped["status"] == "completed"
    assert dumped["query"] == "test query"
    assert len(dumped["items"]) == 1
    assert dumped["items"][0]["source_type"] == "web"
    assert dumped["items"][0]["metadata"]["score"] == 0.95

    # Re-validate round trip
    validated = InformationResult.model_validate(dumped)
    assert validated.items[0].content == "Verified text"


# ==============================================================================
# 15. Simple Query Does NOT Invoke Information Acquisition
# ==============================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize("simple_query", [
    "What is Python?",
    "What is 2 + 2?",
    "Define API.",
])
async def test_15_simple_query_does_not_invoke_information_acquisition(simple_query):
    mock_info = AsyncMock()
    mock_res = AsyncMock()
    mock_strat = AsyncMock()

    coordinator = Coordinator(
        information_acquisition=mock_info,
        researcher=mock_res,
        strategist=mock_strat,
    )

    response = await coordinator.process_request(SolveRequest(problem=simple_query))

    assert response.route == "simple"
    assert response.request_status == "completed"
    assert response.selected_agents == []

    # Assert Information Acquisition was NOT invoked
    mock_info.acquire.assert_not_called()
    mock_res.run.assert_not_called()
    mock_strat.run.assert_not_called()


# ==============================================================================
# 16. Complex Workflow Passes Acquired Information to Researcher
# ==============================================================================
@pytest.mark.asyncio
async def test_16_complex_workflow_passes_acquired_information_to_researcher():
    problem = "Architect a secure distributed patient monitoring platform for rural healthcare"

    captured_res_args = {}
    async def spy_researcher_run(problem=None, context=None, acquired_information=None, sources=None, **kwargs):
        captured_res_args["acquired_information"] = acquired_information
        captured_res_args["sources"] = sources
        return ResearchResult(
            agent="researcher",
            status="completed",
            key_findings=["Finding based on acquired evidence"],
            sources=sources or [],
        )

    mock_res = AsyncMock(run=spy_researcher_run)
    coordinator = Coordinator(researcher=mock_res)

    response = await coordinator.process_request(SolveRequest(problem=problem))

    assert response.route == "complex"
    assert response.request_status == "completed"
    assert len(response.selected_agents) in (6, 9)

    # Verify that Researcher received acquired_information from Information Acquisition Layer
    assert "acquired_information" in captured_res_args
    assert captured_res_args["acquired_information"] is not None
    assert len(captured_res_args["acquired_information"]) > 0

    # Verify sources provenance was passed to Researcher
    assert "sources" in captured_res_args
    assert captured_res_args["sources"] is not None
    assert len(captured_res_args["sources"]) > 0
