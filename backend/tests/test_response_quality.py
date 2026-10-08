"""
Response Quality, Length, and Language Verification Tests for CHAI.

Covers:
- TEST 1: "What is the full form of ISRO?" (concise, direct, no headings, no agent language)
- TEST 2: "What is Python?" (short answer, no unnecessary sections)
- TEST 3: "What is API?" (approx 1-3 sentences)
- TEST 4: "Tell me about the song Se Te Nota." (concise, natural English, handles title ambiguity naturally, no report)
- TEST 5: "Explain binary search." (short educational explanation)
- TEST 6: "Explain binary search with examples, complexity, edge cases and Python implementation." (detailed answer)
- TEST 7: "Design a secure healthcare RAG architecture." (detailed structured response)
- TEST 8: "My parents want me to take a government job, but I want to pursue AI. What should I do?" (thoughtful personal/career guidance, no irrelevant tech/security sections)
- TEST 9: "Give me a comprehensive comparison of PostgreSQL and MongoDB for a production multi-tenant AI SaaS." (detailed structured comparison)
- TEST 10: "Who invented the telephone?" (concise answer, no research report)
"""
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.coordinator import Coordinator
from backend.core.schemas import SolveRequest
from backend.synthesis.response_formatter import (
    format_user_facing_response,
    remove_forbidden_agent_language,
    remove_boilerplate_preambles,
    handle_ambiguity_naturally,
)


FORBIDDEN_PHRASES = [
    "based on the comprehensive analysis of our specialized agents",
    "according to the agents",
    "our researcher agent found",
    "the strategist recommends",
    "the guardian determined",
    "the evaluator concluded",
    "the security agent noted",
    "agent consensus",
    "multi-agent analysis indicates",
]


@pytest.fixture(autouse=True)
def enable_chai_mock_mode(monkeypatch):
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")


# ==============================================================================
# Unit Tests for Response Formatter Subsystems
# ==============================================================================

def test_remove_forbidden_agent_language():
    bad_text = (
        "Based on the comprehensive analysis of our specialized agents:\n\n"
        "Our Researcher agent found that ISRO was founded in 1969. "
        "The Strategist recommends space expansion. "
        "Multi-agent analysis indicates significant mission success."
    )
    cleaned = remove_forbidden_agent_language(bad_text)
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in cleaned.lower()
    assert "ISRO was founded in 1969" in cleaned


def test_remove_boilerplate_preambles():
    sample1 = "The question asks about Python lists. A Python list is an ordered mutable sequence."
    assert remove_boilerplate_preambles(sample1) == "A Python list is an ordered mutable sequence."

    sample2 = "Direct response provided for: What is API?\nAPI is Application Programming Interface."
    assert "Direct response provided for:" not in remove_boilerplate_preambles(sample2)


def test_handle_ambiguity_naturally_song():
    over_researched = (
        "## Executive Summary\n"
        "The query 'sete nota' is ambiguous.\n\n"
        "## Candidate Songs\n"
        "1. Se Te Nota by Lele Pons & Guaynaa (2020)\n"
        "2. Se Te Nota by Piper Pimienta\n\n"
        "## Linguistic Alternative\n"
        "It translates to 'It shows on you'.\n\n"
        "## Sources\n"
        "1. Billboard\n"
    )
    res = handle_ambiguity_naturally("tell me about this song sete nota", over_researched)
    assert "Do you mean 'Se Te Nota' by Lele Pons and Guaynaa?" in res
    assert "## Candidate Songs" not in res
    assert "## Linguistic Alternative" not in res
    assert "## Executive Summary" not in res


# ==============================================================================
# End-to-End Coordinator Regression Tests (Section 22)
# ==============================================================================

@pytest.mark.asyncio
async def test_1_isro_full_form():
    """TEST 1: 'What is the full form of ISRO?' -> concise, direct, grammatically correct, no headings, no agent language."""
    coordinator = Coordinator()
    req = SolveRequest(problem="What is the full form of ISRO?")
    resp = await coordinator.process_request(req)

    ans = resp.final_answer
    assert ans is not None and len(ans) > 0
    # Concise & direct
    assert "Indian Space Research Organisation" in ans
    assert "ISRO" in ans
    # No markdown headings
    assert "#" not in ans
    # No forbidden agent language
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in ans.lower()
    # Length proportional (1-4 sentences)
    sentences = [s for s in ans.split(".") if s.strip()]
    assert len(sentences) <= 4


@pytest.mark.asyncio
async def test_2_what_is_python():
    """TEST 2: 'What is Python?' -> short answer, no unnecessary sections."""
    coordinator = Coordinator()
    req = SolveRequest(problem="What is Python?")
    resp = await coordinator.process_request(req)

    ans = resp.final_answer
    assert ans is not None and len(ans) > 0
    assert "Python" in ans
    assert "programming language" in ans.lower()
    # No unnecessary headings or sections
    assert "##" not in ans
    assert "Executive Summary" not in ans
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in ans.lower()
    sentences = [s for s in ans.split(".") if s.strip()]
    assert len(sentences) <= 4


@pytest.mark.asyncio
async def test_3_what_is_api():
    """TEST 3: 'What is API?' -> approximately 1-3 sentences."""
    coordinator = Coordinator()
    req = SolveRequest(problem="What is API?")
    resp = await coordinator.process_request(req)

    ans = resp.final_answer
    assert ans is not None and len(ans) > 0
    assert "Application Programming Interface" in ans or "interface" in ans.lower()
    assert "#" not in ans
    sentences = [s for s in ans.split(".") if s.strip()]
    assert 1 <= len(sentences) <= 4
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in ans.lower()


@pytest.mark.asyncio
async def test_4_tell_me_about_song_se_te_nota():
    """TEST 4: 'Tell me about the song Se Te Nota.' -> concise, natural English, handle ambiguity naturally, no huge report."""
    mock_synth = AsyncMock()
    mock_synth.synthesize = AsyncMock(return_value={
        "status": "completed",
        "final_answer": (
            "## Executive Summary\n"
            "Query matches Latin pop track.\n\n"
            "## Candidate Songs\n"
            "Candidate 1: Lele Pons and Guaynaa (2020).\n\n"
            "## Linguistic Alternative\n"
            "Spanish phrase meaning it shows.\n\n"
            "## Sources\n"
            "1. Music database"
        )
    })
    coordinator = Coordinator(synthesizer=mock_synth)
    req = SolveRequest(problem="Tell me about the song Se Te Nota.")
    resp = await coordinator.process_request(req)

    ans = resp.final_answer
    assert ans is not None and len(ans) > 0
    # Natural ambiguity handling without massive bureaucratic report
    assert "Se Te Nota" in ans
    assert "Lele Pons" in ans
    assert "Guaynaa" in ans
    assert "## Candidate Songs" not in ans
    assert "## Linguistic Alternative" not in ans
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in ans.lower()


@pytest.mark.asyncio
async def test_5_explain_binary_search():
    """TEST 5: 'Explain binary search.' -> short educational explanation."""
    coordinator = Coordinator()
    req = SolveRequest(problem="Explain binary search.")
    resp = await coordinator.process_request(req)

    ans = resp.final_answer
    assert ans is not None and len(ans) > 0
    assert "binary search" in ans.lower()
    assert any(term in ans.lower() for term in ("sorted", "middle", "log n", "half"))
    # Educational: moderate explanation, no enterprise multi-agent template
    assert "## Executive Summary" not in ans
    assert "## Strategic Thesis" not in ans
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in ans.lower()


@pytest.mark.asyncio
async def test_6_explain_binary_search_with_implementation():
    """TEST 6: 'Explain binary search with examples, complexity, edge cases and Python implementation.' -> detailed answer."""
    mock_synth = AsyncMock()
    mock_synth.synthesize = AsyncMock(return_value={
        "status": "completed",
        "final_answer": (
            "## Algorithm Overview\n"
            "Binary search finds an element in a sorted array by repeatedly dividing the search interval in half.\n\n"
            "## Python Implementation\n"
            "```python\n"
            "def binary_search(arr, target):\n"
            "    low, high = 0, len(arr) - 1\n"
            "    while low <= high:\n"
            "        mid = (low + high) // 2\n"
            "        if arr[mid] == target:\n"
            "            return mid\n"
            "        elif arr[mid] < target:\n"
            "            low = mid + 1\n"
            "        else:\n"
            "            high = mid - 1\n"
            "    return -1\n"
            "```\n\n"
            "## Complexity Analysis\n"
            "- Time Complexity: O(log n)\n"
            "- Space Complexity: O(1)\n\n"
            "## Edge Cases\n"
            "- Empty list\n"
            "- Target not present\n"
            "- Single element list"
        )
    })
    coordinator = Coordinator(synthesizer=mock_synth)
    req = SolveRequest(problem="Explain binary search with examples, complexity, edge cases and Python implementation.")
    resp = await coordinator.process_request(req)

    ans = resp.final_answer
    assert ans is not None and len(ans) > 0
    # Detailed structured response is preserved
    assert "O(log n)" in ans
    assert "def binary_search" in ans
    assert "Edge Cases" in ans
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in ans.lower()


@pytest.mark.asyncio
async def test_7_design_secure_healthcare_rag():
    """TEST 7: 'Design a secure healthcare RAG architecture.' -> detailed structured response."""
    mock_synth = AsyncMock()
    mock_synth.synthesize = AsyncMock(return_value={
        "status": "completed",
        "final_answer": (
            "## Executive Summary\n"
            "This architecture delivers an enterprise-grade, HIPAA-compliant Retrieval-Augmented Generation platform.\n\n"
            "## Architecture & System Design\n"
            "Multi-tier architecture with clinical vector store and role-based gateway.\n\n"
            "## Security & Privacy Controls\n"
            "Strict AES-256 encryption at rest, TLS 1.3 in transit, and de-identification pipelines.\n\n"
            "## Phased Implementation Roadmap\n"
            "Phase 1: Ingestion & RBAC. Phase 2: Vector search. Phase 3: Clinical audit logging."
        )
    })
    coordinator = Coordinator(synthesizer=mock_synth)
    req = SolveRequest(problem="Design a secure healthcare RAG architecture.")
    resp = await coordinator.process_request(req)

    ans = resp.final_answer
    assert ans is not None and len(ans) > 0
    # Rich technical structure retained
    assert "## Executive Summary" in ans
    assert "## Architecture & System Design" in ans
    assert "## Security & Privacy Controls" in ans
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in ans.lower()


@pytest.mark.asyncio
async def test_8_career_dilemma_parents_vs_ai():
    """TEST 8: 'My parents want me to take a government job, but I want to pursue AI. What should I do?' -> personal/career structure, no irrelevant tech sections."""
    mock_synth = AsyncMock()
    mock_synth.synthesize = AsyncMock(return_value={
        "status": "completed",
        "final_answer": (
            "## Situation Analysis\n"
            "Balancing familial stability expectations with long-term aspirations in artificial intelligence.\n\n"
            "## Career Assessment\n"
            "- Government Role: High job security, predictable hours, societal prestige.\n"
            "- AI Career: Rapid innovation, higher earning potential, higher market variability.\n\n"
            "## Cybersecurity & Protection\n"
            "MFA and network firewall configuration.\n\n"
            "## Strategic Action Plan\n"
            "1. Discuss mutual priorities with family.\n"
            "2. Consider a hybrid milestone approach.\n"
            "3. Build demonstrable AI projects while managing risk."
        )
    })
    coordinator = Coordinator(synthesizer=mock_synth)
    req = SolveRequest(problem="My parents want me to take a government job, but I want to pursue AI. What should I do?")
    resp = await coordinator.process_request(req)

    ans = resp.final_answer
    assert ans is not None and len(ans) > 0
    # Thoughtful career structure preserved
    assert "Situation Analysis" in ans
    assert "Strategic Action Plan" in ans
    # Irrelevant technical cybersecurity section stripped
    assert "Cybersecurity & Protection" not in ans
    assert "network firewall configuration" not in ans
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in ans.lower()


@pytest.mark.asyncio
async def test_9_comprehensive_comparison_postgresql_mongodb():
    """TEST 9: 'Give me a comprehensive comparison of PostgreSQL and MongoDB for a production multi-tenant AI SaaS.' -> detailed structured comparison."""
    mock_synth = AsyncMock()
    mock_synth.synthesize = AsyncMock(return_value={
        "status": "completed",
        "final_answer": (
            "## Executive Summary\n"
            "Both databases can power a production multi-tenant AI SaaS, with PostgreSQL favoring relational integrity and MongoDB favoring flexible document schemas.\n\n"
            "## Multi-Tenancy Architecture\n"
            "PostgreSQL offers row-level security (RLS) and schema-per-tenant isolation. MongoDB supports database-per-tenant or document tenancy keys.\n\n"
            "## AI & Vector Capabilities\n"
            "PostgreSQL leverages pgvector, whereas MongoDB utilizes Atlas Vector Search.\n\n"
            "## Recommendation & Trade-offs\n"
            "Choose PostgreSQL if structured transactions and RLS are paramount. Choose MongoDB if document flexibility across polymorphic models is the driver."
        )
    })
    coordinator = Coordinator(synthesizer=mock_synth)
    req = SolveRequest(problem="Give me a comprehensive comparison of PostgreSQL and MongoDB for a production multi-tenant AI SaaS.")
    resp = await coordinator.process_request(req)

    ans = resp.final_answer
    assert ans is not None and len(ans) > 0
    assert "PostgreSQL" in ans
    assert "MongoDB" in ans
    assert "Multi-Tenancy" in ans
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in ans.lower()


@pytest.mark.asyncio
async def test_10_who_invented_the_telephone():
    """TEST 10: 'Who invented the telephone?' -> concise answer, no research report."""
    coordinator = Coordinator()
    req = SolveRequest(problem="Who invented the telephone?")
    resp = await coordinator.process_request(req)

    ans = resp.final_answer
    assert ans is not None and len(ans) > 0
    assert "Alexander Graham Bell" in ans or "Bell" in ans
    # Concise: no report headings
    assert "#" not in ans
    sentences = [s for s in ans.split(".") if s.strip()]
    assert len(sentences) <= 4
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in ans.lower()


# ==============================================================================
# Live HTTP API Solve Endpoint Verification
# ==============================================================================

def test_api_solve_simple_response_quality():
    """Ensures POST /api/solve returns clean, proportional final_answer without internal agent text."""
    client = TestClient(app)
    response = client.post("/api/solve", json={"problem": "What is the full form of ISRO?"})
    assert response.status_code == 200
    data = response.json()
    assert data["route"] == "simple"
    assert "Indian Space Research Organisation" in data["final_answer"]
    assert "#" not in data["final_answer"]
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in data["final_answer"].lower()
