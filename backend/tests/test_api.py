from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "chai-backend"}

def test_solve_endpoint(monkeypatch):
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    payload = {"problem": "Test problem"}
    response = client.post("/api/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["request_status"] == "completed"
    assert "Based on the comprehensive analysis" in data["final_synthesized_answer"]
    assert len(data["selected_agents"]) == 6
