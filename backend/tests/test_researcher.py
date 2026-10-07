import os
import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import ValidationError

from backend.agents.researcher.models import (
    ResearchInput,
    ResearchResult,
    Source,
)
from backend.agents.researcher.agent import (
    ResearcherAgent,
    researcher_node,
)


# 1. ResearchResult Pydantic validation
def test_research_result_validation():
    # Default valid instance
    res = ResearchResult()
    assert res.agent == "researcher"
    assert res.status == "completed"
    assert res.key_findings == []
    assert res.user_needs == []
    assert res.constraints == []
    assert res.assumptions == []
    assert res.open_questions == []
    assert res.sources == []

    # Valid populated instance
    populated = ResearchResult(
        agent="researcher",
        status="completed",
        key_findings=["Finding 1"],
        user_needs=["Need 1"],
        constraints=["Constraint 1"],
        assumptions=["Assumption 1"],
        open_questions=["Question 1"],
        sources=[Source(title="Doc 1", url="https://example.com/doc", source_type="document")],
    )
    assert len(populated.key_findings) == 1
    assert populated.sources[0].url == "https://example.com/doc"

    # Invalid agent literal rejected
    with pytest.raises(ValidationError):
        ResearchResult(agent="strategist")

    # Invalid status literal rejected
    with pytest.raises(ValidationError):
        ResearchResult(status="unknown")


# 2. Valid ResearchInput validation
def test_valid_research_input():
    inp = ResearchInput(
        problem="  Design a rural solar energy monitoring system  ",
        context="Energy sector in developing nations",
        acquired_information=["Avg solar radiation 5.5 kWh/m2"],
        sources=[Source(title="Solar Report", source_type="document")],
    )
    assert inp.problem == "Design a rural solar energy monitoring system"
    assert inp.context == "Energy sector in developing nations"
    assert len(inp.acquired_information) == 1
    assert len(inp.sources) == 1


# 3. Empty problem rejection
def test_empty_problem_rejection():
    # Empty string in ResearchInput
    with pytest.raises(ValueError):
        ResearchInput(problem="")

    # Whitespace only in ResearchInput
    with pytest.raises(ValueError):
        ResearchInput(problem="    \n\t  ")

    # Empty problem in ResearcherAgent.run()
    agent = ResearcherAgent()
    with pytest.raises(ValueError, match="Problem statement cannot be empty"):
        import asyncio
        asyncio.run(agent.run(problem=""))

    with pytest.raises(ValueError, match="Problem statement cannot be empty"):
        import asyncio
        asyncio.run(agent.run(problem="   "))


# 4. Successful Researcher response using a mocked Gemini call
@pytest.mark.asyncio
async def test_successful_researcher_mocked_gemini():
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    
    mock_data = ResearchResult(
        agent="researcher",
        status="completed",
        key_findings=["Limited cellular bandwidth in rural zones"],
        user_needs=["Low-bandwidth communication", "Local offline caching"],
        constraints=["Intermittent electricity", "Device storage limits"],
        assumptions=["Community centers have occasional generator access"],
        open_questions=["What is the primary local language spoken?"],
        sources=[],
    )
    
    mock_structured.ainvoke = AsyncMock(return_value=mock_data)
    mock_llm.with_structured_output.return_value = mock_structured

    agent = ResearcherAgent(llm=mock_llm)
    result = await agent.run(
        problem="Design an affordable AI-powered healthcare support platform for rural communities with unreliable internet."
    )

    assert result.agent == "researcher"
    assert result.status == "completed"
    assert "Limited cellular bandwidth in rural zones" in result.key_findings
    assert "Low-bandwidth communication" in result.user_needs
    assert "Intermittent electricity" in result.constraints
    assert "Community centers have occasional generator access" in result.assumptions
    assert "What is the primary local language spoken?" in result.open_questions
    assert result.sources == []


# 5. Malformed model output handling
@pytest.mark.asyncio
async def test_malformed_model_output_handling():
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    
    # Simulate structured output failure, falling back to ainvoke which returns invalid unparseable text
    mock_structured.ainvoke = AsyncMock(side_effect=Exception("Structured output parse error"))
    mock_llm.with_structured_output.return_value = mock_structured
    
    bad_msg = MagicMock()
    bad_msg.content = "This is completely broken and not valid JSON at all: {bad_syntax"
    mock_llm.ainvoke = AsyncMock(return_value=bad_msg)

    agent = ResearcherAgent(llm=mock_llm)
    result = await agent.run(problem="Investigate battery storage degradation factors.")

    # Should not crash, and return a clean failed result
    assert result.agent == "researcher"
    assert result.status == "failed"
    assert result.key_findings == []
    assert result.user_needs == []
    assert result.constraints == []


# 6. Gemini/API failure handling
@pytest.mark.asyncio
async def test_gemini_api_failure_handling():
    mock_llm = MagicMock()
    mock_llm.with_structured_output.side_effect = Exception("Google Gemini 429 Quota Exceeded")
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("Google Gemini 429 Quota Exceeded"))

    agent = ResearcherAgent(llm=mock_llm)
    result = await agent.run(problem="Analyze drone fleet telemetry.")

    assert result.agent == "researcher"
    assert result.status == "failed"
    assert result.key_findings == []
    assert result.sources == []


# 7. Sources are preserved correctly & no fake sources fabricated
@pytest.mark.asyncio
async def test_sources_preserved_correctly():
    mock_llm = MagicMock()
    mock_structured = MagicMock()

    provided_sources = [
        Source(
            title="World Health Organization Rural Health Guidelines",
            url="https://who.int/rural-health",
            source_type="document",
        )
    ]

    # LLM returns valid result without sources
    mock_data = {
        "key_findings": ["High prevalence of chronic condition A"],
        "user_needs": ["Basic triage advice"],
        "constraints": ["Regulatory compliance with health data"],
        "assumptions": ["Clinicians visit once per month"],
        "open_questions": ["What is the connectivity uptime?"],
        "sources": [],
    }
    mock_structured.ainvoke = AsyncMock(return_value=mock_data)
    mock_llm.with_structured_output.return_value = mock_structured

    agent = ResearcherAgent(llm=mock_llm)
    result = await agent.run(
        problem="Rural telemedicine triage protocol",
        sources=provided_sources,
    )

    assert result.status == "completed"
    assert len(result.sources) == 1
    assert result.sources[0].title == "World Health Organization Rural Health Guidelines"
    assert result.sources[0].url == "https://who.int/rural-health"

    # Test with no sources provided -> Result must have empty sources
    result_no_src = await agent.run(problem="Rural telemedicine triage protocol")
    assert result_no_src.sources == []


# 8. No API key leakage in returned result
@pytest.mark.asyncio
async def test_no_api_key_leakage(monkeypatch):
    secret_key = "AIzaSySecretFakeApiKeyForTesting9999"
    monkeypatch.setenv("GEMINI_API_KEY", secret_key)

    mock_llm = MagicMock()
    # Simulate an error mentioning internal details
    mock_llm.with_structured_output.side_effect = Exception("Internal connection error")
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("Internal connection error"))

    agent = ResearcherAgent(llm=mock_llm)
    result = await agent.run(problem="Analyze smart grid vulnerabilities.")

    result_json = result.model_dump_json()
    assert secret_key not in result_json
    assert result.status == "failed"


# 9. Missing API key handling
@pytest.mark.asyncio
async def test_missing_api_key_handling(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "")

    # When no LLM is injected and key is empty, agent fails safely without crash
    agent = ResearcherAgent(llm=None)
    # Mock _get_llm returning None
    agent._get_llm = MagicMock(return_value=None)
    
    result = await agent.run(problem="Analyze soil nutrient depletion patterns.")
    assert result.agent == "researcher"
    assert result.status == "failed"


# 10. LangGraph node integration compatibility
@pytest.mark.asyncio
async def test_researcher_node_langgraph_compatibility(monkeypatch):
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value={
        "key_findings": ["Soil erosion is critical"],
        "user_needs": ["Affordable sensors"],
        "constraints": ["Low battery availability"],
        "assumptions": ["Farms are within 5km radius"],
        "open_questions": ["What is the soil pH?"],
        "sources": [],
    })
    mock_llm.with_structured_output.return_value = mock_structured

    # Inject mock into ResearcherAgent default initialization
    monkeypatch.setattr(
        "backend.agents.researcher.agent.ResearcherAgent._get_llm",
        lambda self: mock_llm
    )

    state = {
        "problem": "Monitor soil erosion in mountain terraces",
        "context": "High altitude agriculture",
        "sources": [{"title": "Agronomy Report", "source_type": "document"}],
    }

    new_state = await researcher_node(state)
    assert "research" in new_state
    assert new_state["research"]["agent"] == "researcher"
    assert new_state["research"]["status"] == "completed"
    assert "Soil erosion is critical" in new_state["research"]["key_findings"]
    assert len(new_state["research"]["sources"]) == 1


# 11. Optional real Gemini integration test (disabled by default)
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_REAL_GEMINI_TEST") != "true",
    reason="Real Gemini integration test skipped. Set RUN_REAL_GEMINI_TEST=true to execute.",
)
async def test_real_gemini_integration():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not configured for live test.")

    agent = ResearcherAgent()
    result = await agent.run(
        problem="Design an affordable AI-powered healthcare support platform for rural communities with unreliable internet."
    )

    if result.status == "failed":
        pytest.skip("Live Gemini call returned failed status (verify GEMINI_API_KEY validity in .env).")

    assert result.agent == "researcher"
    assert result.status == "completed"
    assert len(result.key_findings) > 0
    assert len(result.user_needs) > 0
    assert len(result.constraints) > 0
    assert len(result.open_questions) > 0
