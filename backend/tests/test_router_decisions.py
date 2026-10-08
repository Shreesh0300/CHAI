"""
Automated tests for CHAI Router Decision Gate and Domain-Aware Dispatch.
Covers Section 12 tests (TEST 1 to TEST 10) and full lifecycle coordinator behavior.
"""
import pytest
from unittest.mock import AsyncMock, patch
from pydantic import ValidationError

from backend.core.router import (
    route_request,
    is_simple_query,
    Router,
    ROUTE_SIMPLE,
    ROUTE_COMPLEX,
)
from backend.core.schemas import RouteDecision, SolveRequest
from backend.core.coordinator import Coordinator, CANONICAL_AGENTS
from backend.agents.researcher.models import ResearchResult
from backend.agents.strategist.models import StrategyResult
from backend.agents.guardian.schemas import GuardianOutput, GuardianResult
from backend.agents.evaluator.schemas import EvaluatorOutput, EvaluatorResult


@pytest.fixture(autouse=True)
def enable_chai_mock_mode(monkeypatch):
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")


# ==============================================================================
# SECTION 12: SPECIFICATION TESTS (TEST 1 - TEST 10)
# ==============================================================================

def test_1_what_is_python():
    """TEST 1: 'What is Python?' -> route = simple"""
    decision = route_request("What is Python?")
    assert decision.route == ROUTE_SIMPLE
    assert decision.complexity in ("low", "simple")
    assert decision.confidence >= 0.90
    assert decision.requires_multi_agent_reasoning is False
    assert decision.requires_external_information is False
    assert decision.required_agents == []
    assert is_simple_query("What is Python?") is True


def test_2_explain_binary_search():
    """TEST 2: 'Explain binary search.' -> route = simple"""
    decision = route_request("Explain binary search.")
    assert decision.route == ROUTE_SIMPLE
    assert decision.complexity in ("low", "simple")
    assert decision.confidence >= 0.90
    assert decision.requires_multi_agent_reasoning is False
    assert decision.requires_external_information is False
    assert decision.required_agents == []
    assert is_simple_query("Explain binary search.") is True


def test_3_who_invented_the_telephone():
    """TEST 3: 'Who invented the telephone?' -> route = simple"""
    decision = route_request("Who invented the telephone?")
    assert decision.route == ROUTE_SIMPLE
    assert decision.complexity in ("low", "simple")
    assert decision.confidence >= 0.90
    assert decision.requires_multi_agent_reasoning is False
    assert decision.requires_external_information is False
    assert decision.required_agents == []
    assert is_simple_query("Who invented the telephone?") is True


def test_4_design_secure_multi_agent_healthcare_rag():
    """TEST 4: 'Design a secure multi-agent healthcare RAG system.' -> route = complex"""
    query = "Design a secure multi-agent healthcare RAG system."
    decision = route_request(query)
    assert decision.route == ROUTE_COMPLEX
    assert decision.complexity in ("high", "complex")
    assert decision.confidence >= 0.90
    assert decision.requires_multi_agent_reasoning is True
    assert decision.requires_external_information is True
    assert "engineer" in decision.required_agents
    assert "security" in decision.required_agents
    assert is_simple_query(query) is False


def test_5_compare_postgresql_and_mongodb_scalable():
    """TEST 5: 'Compare PostgreSQL and MongoDB for a scalable multi-tenant AI SaaS.' -> route = complex"""
    query = "Compare PostgreSQL and MongoDB for a scalable multi-tenant AI SaaS."
    decision = route_request(query)
    assert decision.route == ROUTE_COMPLEX
    assert decision.complexity in ("high", "complex")
    assert decision.confidence >= 0.90
    assert decision.requires_multi_agent_reasoning is True
    assert decision.requires_external_information is True
    assert is_simple_query(query) is False


def test_6_personal_career_dilemma():
    """
    TEST 6:
    Input: 'My parents want me to take a government job, but I want to pursue AI. I am financially dependent on them. What should I do?'
    Expected:
    route = complex
    Expected relevant agents should NOT automatically include Engineer/Security.
    """
    query = "My parents want me to take a government job, but I want to pursue AI. I am financially dependent on them. What should I do?"
    decision = route_request(query)
    assert decision.route == ROUTE_COMPLEX
    assert decision.complexity in ("high", "complex")
    assert decision.domain == "personal_career"
    assert decision.requires_multi_agent_reasoning is True
    assert decision.requires_external_information is False  # User-specific context; no irrelevant external API calls

    # Critical requirement: Engineer and Security must NOT be included
    assert "engineer" not in decision.required_agents
    assert "security" not in decision.required_agents

    # Relevant reasoning agents must be present
    assert "researcher" in decision.required_agents
    assert "strategist" in decision.required_agents
    assert "guardian" in decision.required_agents
    assert "evaluator" in decision.required_agents


def test_7_what_is_2_plus_2():
    """TEST 7: 'What is 2 + 2?' -> route = simple"""
    decision = route_request("What is 2 + 2?")
    assert decision.route == ROUTE_SIMPLE
    assert decision.complexity in ("low", "simple")
    assert decision.requires_multi_agent_reasoning is False
    assert decision.requires_external_information is False
    assert decision.required_agents == []
    assert is_simple_query("What is 2 + 2?") is True


def test_8_detailed_economic_risks_ai_startup():
    """TEST 8: 'Give me a detailed research-backed analysis of the economic risks of launching an AI startup.' -> route = complex"""
    query = "Give me a detailed research-backed analysis of the economic risks of launching an AI startup."
    decision = route_request(query)
    assert decision.route == ROUTE_COMPLEX
    assert decision.complexity in ("high", "complex")
    assert decision.domain == "business_strategy"
    assert decision.requires_multi_agent_reasoning is True
    assert decision.requires_external_information is True
    assert decision.requested_depth == "deep"
    assert is_simple_query(query) is False
    # Business strategy does not inject engineer or security automatically
    assert "engineer" not in decision.required_agents
    assert "security" not in decision.required_agents


def test_9_is_python_better_than_java():
    """
    TEST 9: 'Is Python better than Java?' -> route = simple (deterministic broad comparison)
    """
    query = "Is Python better than Java?"
    decision = route_request(query)
    assert decision.route == ROUTE_SIMPLE
    assert decision.complexity in ("low", "simple")
    assert decision.requires_multi_agent_reasoning is False
    assert is_simple_query(query) is True


def test_10_compare_python_and_java_production_saas():
    """
    TEST 10:
    Input: 'Compare Python and Java for our production AI SaaS considering performance, hiring, ecosystem, deployment, cost and long-term maintainability.'
    Expected: route = complex
    """
    query = (
        "Compare Python and Java for our production AI SaaS considering performance, "
        "hiring, ecosystem, deployment, cost and long-term maintainability."
    )
    decision = route_request(query)
    assert decision.route == ROUTE_COMPLEX
    assert decision.complexity in ("high", "complex")
    assert decision.requires_multi_agent_reasoning is True
    assert decision.requires_external_information is True
    assert "engineer" in decision.required_agents
    assert is_simple_query(query) is False


# ==============================================================================
# SECTION 5 & OTHER COMPLEXITY CRITERIA TESTS
# ==============================================================================

@pytest.mark.parametrize("simple_q", [
    "What is recursion?",
    "Explain recursion.",
    "What is a database?",
    "Convert 10 km to meters.",
    "Give me the definition of machine learning.",
    "define polymorphism",
    "What is HTTP?",
])
def test_additional_simple_queries(simple_q):
    """Verifies additional factual definitions from Section 5 route as simple."""
    decision = route_request(simple_q)
    assert decision.route == ROUTE_SIMPLE
    assert decision.complexity in ("low", "simple")
    assert decision.required_agents == []


@pytest.mark.parametrize("complex_q", [
    "Design a scalable healthcare RAG system.",
    "Should I choose AI or a government job considering my financial situation?",
    "Design a secure multi-agent architecture.",
    "Create a detailed business strategy for launching an AI startup.",
    "Analyze the risks and trade-offs of using autonomous AI agents in healthcare.",
    "Give me a research-backed comparison of these technologies.",
    "Should I quit my job?",
])
def test_additional_complex_queries(complex_q):
    """Verifies architectural, trade-off, and consequential decision queries route as complex."""
    decision = route_request(complex_q)
    assert decision.route == ROUTE_COMPLEX
    assert decision.complexity in ("high", "complex")
    assert decision.requires_multi_agent_reasoning is True


# ==============================================================================
# COORDINATOR INTEGRATION & TRACE CONSISTENCY TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_coordinator_simple_route_execution_and_trace():
    """Verifies that a SIMPLE query executes direct LLM and does NOT invoke specialist agents."""
    mock_res = AsyncMock()
    mock_strat = AsyncMock()
    mock_eng = AsyncMock()
    mock_guard = AsyncMock()
    mock_sec = AsyncMock()
    mock_eval = AsyncMock()
    mock_info = AsyncMock()

    coordinator = Coordinator(
        researcher=mock_res,
        strategist=mock_strat,
        engineer=mock_eng,
        guardian=mock_guard,
        security=mock_sec,
        evaluator=mock_eval,
        information_acquisition=mock_info,
    )

    req = SolveRequest(problem="What is Python?")
    resp = await coordinator.process_request(req)

    assert resp.route == "simple"
    assert resp.status == "completed"
    assert resp.selected_agents == []
    assert resp.agent_outputs == {}
    assert resp.retrieved_sources == []
    assert resp.acquired_information == []

    # Specialist agents and Information Acquisition must NOT be called
    mock_info.acquire.assert_not_called()
    mock_res.run.assert_not_called()
    mock_strat.run.assert_not_called()
    mock_eng.run.assert_not_called()
    mock_guard.run.assert_not_called()
    mock_sec.run.assert_not_called()
    mock_eval.run.assert_not_called()

    # Truthful execution trace check: only router and direct_llm
    trace_stages = [t["agent"] for t in resp.execution_trace]
    assert trace_stages == ["router", "direct_llm"]
    assert all(t["status"] == "completed" for t in resp.execution_trace)


@pytest.mark.asyncio
async def test_coordinator_complex_career_query_excludes_engineer_and_security():
    """
    Verifies that for a personal career decision, Coordinator:
    1. Executes relevant agents: Researcher, Strategist, Guardian, Evaluator, Synthesizer, etc.
    2. Does NOT execute Engineer or Security.
    3. Does NOT invoke external Information Acquisition.
    4. Records truthful execution trace.
    """
    mock_res = AsyncMock(run=AsyncMock(return_value=ResearchResult(agent="researcher", status="completed", key_findings=["AI has strong growth"])))
    mock_strat = AsyncMock(run=AsyncMock(return_value=StrategyResult(agent="strategist", status="completed", strategy="Prepare part-time AI projects while respecting family stability")))
    mock_eng = AsyncMock()
    mock_guard = AsyncMock(run=AsyncMock(return_value=GuardianOutput.from_guardian_result(GuardianResult(safety_assessment="Financial dependency is high risk without income"))))
    mock_sec = AsyncMock()
    mock_eval = AsyncMock(run=AsyncMock(return_value=EvaluatorOutput.from_evaluator_result(EvaluatorResult(agent="evaluator", status="completed", overall_assessment="Balanced approach advised"))))
    mock_info = AsyncMock()

    coordinator = Coordinator(
        researcher=mock_res,
        strategist=mock_strat,
        engineer=mock_eng,
        guardian=mock_guard,
        security=mock_sec,
        evaluator=mock_eval,
        information_acquisition=mock_info,
    )

    query = "My parents want me to take a government job, but I want to pursue AI. I am financially dependent on them. What should I do?"
    resp = await coordinator.process_request(SolveRequest(problem=query))

    assert resp.route == "complex"
    assert resp.status == "completed"

    # Engineer and Security must NOT be selected or executed
    assert "engineer" not in resp.selected_agents
    assert "security" not in resp.selected_agents
    mock_eng.run.assert_not_called()
    mock_sec.run.assert_not_called()

    # Relevant agents must be present in selected_agents
    assert "researcher" in resp.selected_agents
    assert "strategist" in resp.selected_agents
    assert "guardian" in resp.selected_agents
    assert "evaluator" in resp.selected_agents

    # Information Acquisition must be skipped (not called)
    mock_info.acquire.assert_not_called()

    # Trace must not contain engineer or security
    trace_agents = [t["agent"] for t in resp.execution_trace]
    assert "engineer" not in trace_agents
    assert "security" not in trace_agents
    assert "router" in trace_agents
    assert "researcher" in trace_agents


@pytest.mark.asyncio
async def test_coordinator_simple_direct_llm_failure_handling():
    """Verifies controlled failure handling when direct LLM encounters an exception."""
    failing_llm = AsyncMock(generate_content=AsyncMock(side_effect=RuntimeError("LLM API Quota Exceeded")))

    coordinator = Coordinator(direct_llm=failing_llm)
    req = SolveRequest(problem="What is Python?")
    resp = await coordinator.process_request(req)

    assert resp.status == "failed"
    assert resp.request_status == "failed"
    assert resp.route == "simple"
    assert resp.selected_agents == []
    assert len(resp.errors) > 0
    assert "LLM API Quota Exceeded" in resp.errors[0]

    # Trace shows failure accurately without fabricating agent steps
    direct_trace = next((t for t in resp.execution_trace if t["agent"] == "direct_llm"), None)
    assert direct_trace is not None
    assert direct_trace["status"] == "failed"
    assert "LLM API Quota Exceeded" in direct_trace["error"]
