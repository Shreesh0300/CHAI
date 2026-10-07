import pytest
from unittest.mock import AsyncMock
from pydantic import BaseModel
from backend.core.coordinator import Coordinator
from backend.core.schemas import SolveRequest


class DummyAgentOutput(BaseModel):
    status: str = "completed"
    strategy: str = "Strategy overview"
    strategy_overview: str = "Strategy overview"
    technical_architecture: str = "Architecture overview"
    architecture_overview: str = "Architecture overview"
    security_summary: str = "Security summary"
    overall_assessment: str = "Evaluation summary"
    source_references: list = ["Source 1"]
    sources: list = ["Source 1"]
    limitations: list = ["Limitation 1"]


class DummyFailedOutput(BaseModel):
    status: str = "failed"
    error: str = "Agent failed"


def build_mock_coordinator(agent_states: dict = None) -> Coordinator:
    """Build a Coordinator instance with mocked agents."""
    c = Coordinator()
    states = agent_states or {}
    for agent_name in ["researcher", "strategist", "engineer", "guardian", "security", "evaluator"]:
        agent = getattr(c, agent_name)
        state = states.get(agent_name, True)
        if state is True:
            agent.run = AsyncMock(return_value=DummyAgentOutput())
        elif state is False:
            agent.run = AsyncMock(return_value=DummyFailedOutput())
        elif isinstance(state, Exception):
            agent.run = AsyncMock(side_effect=state)
        else:
            agent.run = AsyncMock(return_value=DummyAgentOutput())
    return c


@pytest.mark.asyncio
async def test_all_agents_successful():
    coordinator = build_mock_coordinator({a: True for a in ["researcher", "strategist", "engineer", "guardian", "security", "evaluator"]})
    request = SolveRequest(problem="Analyze distributed systems design")
    response = await coordinator.process_request(request)

    assert response.request_status == "completed"
    assert len(response.selected_agents) == 6
    assert len(response.agent_execution_statuses) == 6
    assert all(s.status == "success" for s in response.agent_execution_statuses)


@pytest.mark.asyncio
async def test_one_agent_failed():
    states = {a: True for a in ["researcher", "strategist", "engineer", "guardian", "security", "evaluator"]}
    states["security"] = False
    coordinator = build_mock_coordinator(states)

    request = SolveRequest(problem="Analyze security posture")
    response = await coordinator.process_request(request)

    assert response.request_status == "partial"
    status_map = {s.agent_name: s.status for s in response.agent_execution_statuses}
    assert status_map["security"] == "failed"
    assert status_map["engineer"] == "success"


@pytest.mark.asyncio
async def test_multiple_agents_failed():
    states = {a: True for a in ["researcher", "strategist", "engineer", "guardian", "security", "evaluator"]}
    states["researcher"] = Exception("Network timeout connecting to search provider")
    states["strategist"] = False
    coordinator = build_mock_coordinator(states)

    request = SolveRequest(problem="Evaluate business strategy and tech stack")
    response = await coordinator.process_request(request)

    assert response.request_status == "partial"
    status_map = {s.agent_name: s.status for s in response.agent_execution_statuses}
    assert status_map["researcher"] == "failed"
    assert status_map["strategist"] == "failed"
    assert status_map["engineer"] == "success"


@pytest.mark.asyncio
async def test_all_agents_failed():
    states = {a: False for a in ["researcher", "strategist", "engineer", "guardian", "security", "evaluator"]}
    states["guardian"] = Exception("Guardian service unavailable")
    coordinator = build_mock_coordinator(states)

    request = SolveRequest(problem="High risk medical deployment")
    response = await coordinator.process_request(request)

    assert response.request_status == "failed"
    assert len(response.agent_execution_statuses) == 6
    assert all(s.status == "failed" for s in response.agent_execution_statuses)


@pytest.mark.asyncio
async def test_partial_execution_all_selected_succeed():
    coordinator = build_mock_coordinator({"engineer": True, "guardian": True})
    request = SolveRequest(problem="Check engineering and safety", selected_agents=["engineer", "guardian"])
    response = await coordinator.process_request(request)

    assert response.request_status == "completed"
    assert response.selected_agents == ["engineer", "guardian"]
    assert len(response.agent_execution_statuses) == 2
    assert all(s.status == "success" for s in response.agent_execution_statuses)


@pytest.mark.asyncio
async def test_partial_execution_mixed_success_and_failure():
    coordinator = build_mock_coordinator({"engineer": True, "guardian": False})
    request = SolveRequest(problem="Check engineering and safety", selected_agents=["engineer", "guardian"])
    response = await coordinator.process_request(request)

    assert response.request_status == "partial"
    assert response.selected_agents == ["engineer", "guardian"]
    status_map = {s.agent_name: s.status for s in response.agent_execution_statuses}
    assert status_map["engineer"] == "success"
    assert status_map["guardian"] == "failed"


@pytest.mark.asyncio
async def test_partial_execution_all_selected_fail():
    coordinator = build_mock_coordinator({"engineer": False, "guardian": False})
    request = SolveRequest(problem="Check engineering and safety", selected_agents=["engineer", "guardian"])
    response = await coordinator.process_request(request)

    assert response.request_status == "failed"
    assert response.selected_agents == ["engineer", "guardian"]
    assert all(s.status == "failed" for s in response.agent_execution_statuses)


@pytest.mark.asyncio
async def test_simple_query_behavior():
    coordinator = build_mock_coordinator()
    request = SolveRequest(problem="What is a Python list?")
    response = await coordinator.process_request(request)

    assert response.request_status == "completed"
    assert response.selected_agents == []
    assert response.agent_execution_statuses == []
    assert "Direct response" in response.final_synthesized_answer


@pytest.mark.asyncio
async def test_direct_query_with_no_agents_selected():
    coordinator = build_mock_coordinator()
    request = SolveRequest(problem="Direct factual query", selected_agents=[])
    response = await coordinator.process_request(request)

    assert response.request_status == "completed"
    assert response.selected_agents == []
    assert response.agent_execution_statuses == []
    assert "Direct response" in response.final_synthesized_answer
