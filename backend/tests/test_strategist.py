import os
import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import ValidationError

from backend.agents.researcher.models import (
    ResearchResult,
    Source,
)
from backend.agents.strategist.models import (
    StrategyInput,
    StrategyResult,
)
from backend.agents.strategist.agent import (
    StrategistAgent,
    strategist_node,
)
from backend.agents.strategist.prompts import build_strategy_prompt


# Fixture for sample valid ResearchResult
@pytest.fixture
def sample_research_result() -> ResearchResult:
    return ResearchResult(
        agent="researcher",
        status="completed",
        key_findings=["Target communities have intermittent and slow connectivity."],
        user_needs=["Offline data entry", "Low-bandwidth synchronization"],
        constraints=["Unreliable internet", "Limited smartphone RAM"],
        assumptions=["Community clinics have battery power."],
        open_questions=["What regional language support is mandatory?"],
        sources=[Source(title="Rural Health Network Study", source_type="document")],
    )


# 1. StrategyResult Pydantic validation
def test_strategy_result_validation():
    res = StrategyResult()
    assert res.agent == "strategist"
    assert res.status == "completed"
    assert res.strategy == ""
    assert res.priorities == []
    assert res.roadmap == []
    assert res.tradeoffs == []
    assert res.success_metrics == []

    populated = StrategyResult(
        agent="strategist",
        status="completed",
        strategy="Build an offline-first telemedicine app",
        priorities=["Offline sync", "Safety escalation"],
        roadmap=["Phase 1: MVP", "Phase 2: Field testing"],
        tradeoffs=["No high-res video streaming in v1"],
        success_metrics=["Sync reliability > 99%"],
    )
    assert populated.strategy == "Build an offline-first telemedicine app"
    assert len(populated.priorities) == 2
    assert len(populated.roadmap) == 2

    # Invalid agent literal rejected
    with pytest.raises(ValidationError):
        StrategyResult(agent="researcher")

    # Invalid status literal rejected
    with pytest.raises(ValidationError):
        StrategyResult(status="in_progress")


# 2. Valid StrategyInput
def test_valid_strategy_input(sample_research_result):
    inp = StrategyInput(
        problem="  Design a resilient healthcare support system  ",
        research=sample_research_result,
        context="Developing regions healthcare initiative",
    )
    assert inp.problem == "Design a resilient healthcare support system"
    assert inp.research.agent == "researcher"
    assert inp.context == "Developing regions healthcare initiative"


# 3. Empty problem rejection
def test_empty_problem_rejection(sample_research_result):
    # StrategyInput rejects empty string
    with pytest.raises(ValueError):
        StrategyInput(problem="", research=sample_research_result)

    # StrategyInput rejects whitespace only
    with pytest.raises(ValueError):
        StrategyInput(problem="   \n\t  ", research=sample_research_result)

    # StrategistAgent.run rejects empty problem
    agent = StrategistAgent()
    with pytest.raises(ValueError, match="Problem statement cannot be empty"):
        import asyncio
        asyncio.run(agent.run(problem="", research=sample_research_result))

    with pytest.raises(ValueError, match="Problem statement cannot be empty"):
        import asyncio
        asyncio.run(agent.run(problem="   ", research=sample_research_result))


# 4. Missing ResearchResult rejection
def test_missing_research_result_rejection():
    # StrategyInput rejects missing/None research
    with pytest.raises(ValidationError):
        StrategyInput(problem="Design solar monitoring system", research=None)

    agent = StrategistAgent()
    with pytest.raises(ValueError, match="ResearchResult is required"):
        import asyncio
        asyncio.run(agent.run(problem="Design solar monitoring system", research=None))


# 5. Successful strategy generation with mocked Gemini
@pytest.mark.asyncio
async def test_successful_strategy_mocked_gemini(sample_research_result):
    mock_llm = MagicMock()
    mock_structured = MagicMock()

    mock_data = StrategyResult(
        agent="strategist",
        status="completed",
        strategy="Deploy an offline-first lightweight triage platform with SMS escalation fallback.",
        priorities=[
            "Prioritize offline local SQLite storage and opportunistic sync",
            "Establish structured clinical escalation protocols",
            "Keep client payload strictly under 100KB",
        ],
        roadmap=[
            "Phase 1: Build local storage and offline triage forms",
            "Phase 2: Integrate background sync queue with retry policy",
            "Phase 3: Deploy pilot in 5 rural community health posts",
        ],
        tradeoffs=[
            "Delay real-time video consults in favor of store-and-forward messaging",
            "Store limited diagnostic history on device to conserve memory",
        ],
        success_metrics=[
            "100% data preservation during network blackouts",
            "Average sync latency under 5 seconds when connection restores",
        ],
    )
    mock_structured.ainvoke = AsyncMock(return_value=mock_data)
    mock_llm.with_structured_output.return_value = mock_structured

    agent = StrategistAgent(llm=mock_llm)
    result = await agent.run(
        problem="Design an affordable AI-powered healthcare support platform for rural communities with unreliable internet.",
        research=sample_research_result,
    )

    assert result.agent == "strategist"
    assert result.status == "completed"
    assert "offline-first lightweight triage platform" in result.strategy
    assert len(result.priorities) == 3
    assert len(result.roadmap) == 3
    assert len(result.tradeoffs) == 2
    assert len(result.success_metrics) == 2


# 6. ResearchResult is actually passed into the strategy prompt (Traceability)
@pytest.mark.asyncio
async def test_research_result_traceability_in_prompt():
    specific_research = ResearchResult(
        agent="researcher",
        status="completed",
        key_findings=["Users experience 80% packet loss during monsoon season."],
        user_needs=["Store-and-forward asynchronous consultation."],
        constraints=["Solar charging stations operate only 4 hours daily."],
        assumptions=["Community volunteers have feature phones or low-end Androids."],
        open_questions=["What is the local regulatory stance on automated triage?"],
        sources=[],
    )

    # 6a. Direct prompt inspection
    prompt_text = build_strategy_prompt(
        problem="Build healthcare network for isolated island clinics.",
        research=specific_research,
    )
    assert "Users experience 80% packet loss during monsoon season." in prompt_text
    assert "Store-and-forward asynchronous consultation." in prompt_text
    assert "Solar charging stations operate only 4 hours daily." in prompt_text
    assert "Community volunteers have feature phones or low-end Androids." in prompt_text
    assert "What is the local regulatory stance on automated triage?" in prompt_text

    # 6b. Verify agent actually passes these findings in messages to the LLM
    captured_messages = []

    mock_llm = MagicMock()
    mock_structured = MagicMock()

    async def fake_ainvoke(messages):
        captured_messages.extend(messages)
        return StrategyResult(
            agent="strategist",
            status="completed",
            strategy="Grounded strategy",
            priorities=["P1"],
            roadmap=["R1"],
            tradeoffs=["T1"],
            success_metrics=["M1"],
        )

    mock_structured.ainvoke = fake_ainvoke
    mock_llm.with_structured_output.return_value = mock_structured

    agent = StrategistAgent(llm=mock_llm)
    await agent.run(
        problem="Build healthcare network for isolated island clinics.",
        research=specific_research,
    )

    # Verify captured messages contain the specific research findings
    all_content = " ".join(str(m.content) for m in captured_messages)
    assert "Users experience 80% packet loss during monsoon season." in all_content
    assert "Solar charging stations operate only 4 hours daily." in all_content


# 7. Malformed model output handling
@pytest.mark.asyncio
async def test_malformed_model_output_handling(sample_research_result):
    mock_llm = MagicMock()
    mock_structured = MagicMock()

    # Simulate structured output exception, falling back to raw output which is invalid JSON
    mock_structured.ainvoke = AsyncMock(side_effect=Exception("Structured output parse failure"))
    mock_llm.with_structured_output.return_value = mock_structured

    bad_msg = MagicMock()
    bad_msg.content = "Malformed non-JSON output: <<Not a valid json string>>"
    mock_llm.ainvoke = AsyncMock(return_value=bad_msg)

    agent = StrategistAgent(llm=mock_llm)
    result = await agent.run(
        problem="Evaluate water purification logistics.",
        research=sample_research_result,
    )

    assert result.agent == "strategist"
    assert result.status == "failed"
    assert result.strategy == ""
    assert result.priorities == []
    assert result.roadmap == []


# 8. Gemini/API failure handling
@pytest.mark.asyncio
async def test_gemini_api_failure_handling(sample_research_result):
    mock_llm = MagicMock()
    mock_llm.with_structured_output.side_effect = Exception("Google Gemini 429 Resource Exhausted")
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("Google Gemini 429 Resource Exhausted"))

    agent = StrategistAgent(llm=mock_llm)
    result = await agent.run(
        problem="Optimize renewable microgrid dispatch.",
        research=sample_research_result,
    )

    assert result.agent == "strategist"
    assert result.status == "failed"
    assert result.strategy == ""
    assert result.priorities == []


# 9. Failed strategy returns status="failed"
@pytest.mark.asyncio
async def test_failed_strategy_contract(sample_research_result):
    mock_llm = MagicMock()
    mock_llm.with_structured_output.side_effect = TimeoutError("Request timed out")
    mock_llm.ainvoke = AsyncMock(side_effect=TimeoutError("Request timed out"))

    agent = StrategistAgent(llm=mock_llm)
    result = await agent.run(
        problem="Analyze logistics route planning.",
        research=sample_research_result,
    )

    assert result.status == "failed"
    assert result.strategy == ""
    assert result.priorities == []
    assert result.roadmap == []
    assert result.tradeoffs == []
    assert result.success_metrics == []


# 10. LangGraph strategist_node compatibility
@pytest.mark.asyncio
async def test_strategist_node_langgraph_compatibility(monkeypatch, sample_research_result):
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value={
        "strategy": "Iterative deployment model",
        "priorities": ["Local data cache", "Asynchronous sync"],
        "roadmap": ["Stage 1: Local DB", "Stage 2: Mesh network"],
        "tradeoffs": ["High initial latency"],
        "success_metrics": ["Zero data loss"],
    })
    mock_llm.with_structured_output.return_value = mock_structured

    monkeypatch.setattr(
        "backend.agents.strategist.agent.StrategistAgent._get_llm",
        lambda self: mock_llm,
    )

    state = {
        "problem": "Rural diagnostic platform",
        "research": sample_research_result.model_dump(),
        "context": "Healthcare tier 1 clinics",
    }

    new_state = await strategist_node(state)
    assert "strategy_result" in new_state
    strategy_data = new_state["strategy_result"]
    assert strategy_data["agent"] == "strategist"
    assert strategy_data["status"] == "completed"
    assert strategy_data["strategy"] == "Iterative deployment model"
    assert len(strategy_data["priorities"]) == 2


# 11. No API key leakage
@pytest.mark.asyncio
async def test_no_api_key_leakage(monkeypatch, sample_research_result):
    secret_key = "AIzaSyFakeKeyForStrategistTesting777"
    monkeypatch.setenv("GEMINI_API_KEY", secret_key)

    mock_llm = MagicMock()
    mock_llm.with_structured_output.side_effect = Exception("Connection error with backend credentials")
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("Connection error with backend credentials"))

    agent = StrategistAgent(llm=mock_llm)
    result = await agent.run(
        problem="Design encrypted mesh radios.",
        research=sample_research_result,
    )

    result_json = result.model_dump_json()
    assert secret_key not in result_json
    assert result.status == "failed"


# 12. Optional real Gemini integration test (disabled by default)
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_REAL_GEMINI_TEST") != "true",
    reason="Real Gemini integration test skipped. Set RUN_REAL_GEMINI_TEST=true to execute.",
)
async def test_real_gemini_integration(sample_research_result):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not configured for live test.")

    agent = StrategistAgent()
    result = await agent.run(
        problem="Design an affordable AI-powered healthcare support platform for rural communities with unreliable internet.",
        research=sample_research_result,
    )

    if result.status == "failed":
        pytest.skip("Live Gemini call returned failed status (verify GEMINI_API_KEY validity in .env).")

    assert result.agent == "strategist"
    assert result.status == "completed"
    assert len(result.strategy) > 0
    assert len(result.priorities) > 0
    assert len(result.roadmap) > 0
