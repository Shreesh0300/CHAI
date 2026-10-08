import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from pydantic import BaseModel
from backend.main import app
from backend.api.routes import coordinator

client = TestClient(app)


@pytest.fixture(autouse=True)
def enable_chai_mock_mode(monkeypatch):
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    from backend.core.coordinator import Coordinator
    yield
    fresh = Coordinator()
    for a in ["researcher", "strategist", "engineer", "guardian", "security", "evaluator"]:
        setattr(coordinator, a, getattr(fresh, a))


class MockSuccessOutput(BaseModel):
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
    action: str = "PROCEED"
    final_answer: str = "Synthesized dummy answer"


class MockFailedOutput(BaseModel):
    status: str = "failed"
    error: str = "Agent execution failed"
    action: str = "BLOCK_OUTPUT"


def setup_mock_agents(coordinator_inst, agent_configs: dict):
    """Configure coordinator agents with success, failure, or exception mocks."""
    canonical = [
        "researcher", "strategist", "engineer", "guardian", "security", "evaluator",
        "conflict_resolver", "synthesizer", "reliability_monitor"
    ]
    for agent_name in canonical:
        agent = getattr(coordinator_inst, agent_name)
        cfg = agent_configs.get(agent_name, True)
        if cfg is True:
            agent.run = AsyncMock(return_value=MockSuccessOutput())
        elif cfg is False:
            agent.run = AsyncMock(return_value=MockFailedOutput())
        elif isinstance(cfg, Exception):
            agent.run = AsyncMock(side_effect=cfg)
        else:
            agent.run = AsyncMock(return_value=MockSuccessOutput())


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "chai-backend"}


def test_solve_endpoint(monkeypatch):
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    setup_mock_agents(coordinator, {a: True for a in [
        "researcher", "strategist", "engineer", "guardian", "security", "evaluator",
        "conflict_resolver", "synthesizer", "reliability_monitor"
    ]})
    payload = {"problem": "Test problem"}
    response = client.post("/api/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["request_status"] == "completed"
    assert "Based on the comprehensive analysis" in data["final_synthesized_answer"]
    assert len(data["selected_agents"]) in (6, 9)


def test_solve_all_agents_successful():
    setup_mock_agents(coordinator, {a: True for a in [
        "researcher", "strategist", "engineer", "guardian", "security", "evaluator",
        "conflict_resolver", "synthesizer", "reliability_monitor"
    ]})
    payload = {"problem": "Complete task with all agents"}
    response = client.post("/api/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["request_status"] == "completed"
    statuses = data["agent_execution_statuses"]
    assert len(statuses) in (6, 9)
    assert all(s["status"] == "success" for s in statuses)


def test_solve_one_agent_failed():
    configs = {a: True for a in [
        "researcher", "strategist", "engineer", "guardian", "security", "evaluator",
        "conflict_resolver", "synthesizer", "reliability_monitor"
    ]}
    configs["researcher"] = False
    setup_mock_agents(coordinator, configs)

    payload = {"problem": "One agent fails"}
    response = client.post("/api/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["request_status"] == "partial"
    statuses = {s["agent_name"]: s["status"] for s in data["agent_execution_statuses"]}
    assert statuses["researcher"] == "failed"
    assert statuses["engineer"] == "success"


def test_solve_multiple_agents_failed():
    configs = {a: True for a in [
        "researcher", "strategist", "engineer", "guardian", "security", "evaluator",
        "conflict_resolver", "synthesizer", "reliability_monitor"
    ]}
    configs["engineer"] = False
    configs["security"] = Exception("Security agent connection timed out")
    setup_mock_agents(coordinator, configs)

    payload = {"problem": "Multiple agents fail"}
    response = client.post("/api/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["request_status"] == "partial"
    statuses = {s["agent_name"]: s["status"] for s in data["agent_execution_statuses"]}
    assert statuses["engineer"] == "failed"
    assert statuses["security"] == "failed"
    assert statuses["strategist"] == "success"


def test_solve_all_agents_failed():
    configs = {a: False for a in [
        "researcher", "strategist", "engineer", "guardian", "security", "evaluator",
        "conflict_resolver", "synthesizer", "reliability_monitor"
    ]}
    setup_mock_agents(coordinator, configs)

    payload = {"problem": "All agents fail"}
    response = client.post("/api/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["request_status"] == "failed"
    statuses = data["agent_execution_statuses"]
    assert len(statuses) in (6, 9)
    assert all(s["status"] == "failed" for s in statuses)



def test_solve_partial_execution():
    # Subset of agents selected: both succeed -> completed
    configs = {"engineer": True, "guardian": True}
    setup_mock_agents(coordinator, configs)
    payload = {"problem": "Partial agent selection", "selected_agents": ["engineer", "guardian"]}
    response = client.post("/api/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["request_status"] == "completed"
    assert data["selected_agents"] == ["engineer", "guardian"]
    assert len(data["agent_execution_statuses"]) == 2

    # Subset of agents selected: one succeeds, one fails -> partial
    configs = {"engineer": True, "guardian": False}
    setup_mock_agents(coordinator, configs)
    response = client.post("/api/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["request_status"] == "partial"

    # Subset of agents selected: all fail -> failed
    configs = {"engineer": False, "guardian": False}
    setup_mock_agents(coordinator, configs)
    response = client.post("/api/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["request_status"] == "failed"


def test_solve_simple_direct_query_behavior():
    # Direct query with explicitly empty selected_agents
    payload = {"problem": "What is 2+2?", "selected_agents": []}
    response = client.post("/api/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["request_status"] == "completed"
    assert data["selected_agents"] == []
    assert data["agent_execution_statuses"] == []

    # Simple definitional query detected by is_simple_query
    payload_simple = {"problem": "What is a Python list?"}
    response_simple = client.post("/api/solve", json=payload_simple)
    assert response_simple.status_code == 200
    data_simple = response_simple.json()
    assert data_simple["request_status"] == "completed"
    assert data_simple["selected_agents"] == []
    assert data_simple["agent_execution_statuses"] == []
