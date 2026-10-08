"""
Unit tests for Autonomous Voice Wake-Up Daemon, Voice Routes, and Domain Model Routing.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.router import route_agents_for_problem
from backend.voice.wakeup_daemon import (
    VoiceWakeupDaemon,
    extract_wake_word_and_query,
    get_voice_wakeup_daemon,
)

client = TestClient(app)


def test_wake_word_extraction_english():
    res = extract_wake_word_and_query("Hey chai what is quantum computing?")
    assert res["matched"] is True
    assert res["phrase"] in ("hey chai", "chai")
    assert "quantum computing" in res["query"]


def test_wake_word_extraction_kannada():
    res = extract_wake_word_and_query("ನಮಸ್ಕಾರ ಚಾಯ್ ಇವತ್ತಿನ ಸುದ್ದಿ ಏನು?")
    assert res["matched"] is True
    assert "ಚಾಯ್" in res["phrase"]


def test_wake_word_extraction_hindi():
    res = extract_wake_word_and_query("नमस्ते चाई मौसम कैसा है?")
    assert res["matched"] is True
    assert "चाई" in res["phrase"] or "चाय" in res["phrase"]


def test_wake_word_negative():
    res = extract_wake_word_and_query("The quick brown fox jumps over the lazy dog.")
    assert res["matched"] is False
    assert res["query"] == ""


def test_daemon_status_endpoint():
    response = client.get("/api/voice/wakeup/status")
    assert response.status_code == 200
    data = response.json()
    assert "running" in data
    assert "active" in data
    assert "wake_patterns" in data


def test_daemon_simulate_endpoint():
    response = client.post(
        "/api/voice/wakeup/simulate",
        json={"text": "Welcome back chai", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["simulated_text"] == "Welcome back chai"


def test_voice_synthesize_endpoint():
    # Audio streaming endpoint returning WAV or MP3 bytes
    response = client.get("/api/voice/synthesize?text=Hello+world&language=en")
    assert response.status_code == 200
    assert len(response.content) > 100
    assert "audio/" in response.headers.get("content-type", "")


def test_domain_model_routing():
    # 1. Business mode routes to researcher, strategist, evaluator
    biz_agents = route_agents_for_problem("Build SaaS", model="Business")
    assert "strategist" in biz_agents
    assert "researcher" in biz_agents
    assert "evaluator" in biz_agents
    assert "engineer" not in biz_agents

    # 2. Personal mode routes to researcher, guardian, strategist, evaluator
    personal_agents = route_agents_for_problem("Personal fitness plan", model="Personal")
    assert "guardian" in personal_agents
    assert "researcher" in personal_agents
    assert "strategist" in personal_agents

    # 3. Software mode routes to engineer, security, researcher, evaluator
    software_agents = route_agents_for_problem("Implement OAuth2 server", model="Software")
    assert "engineer" in software_agents
    assert "security" in software_agents

    # 4. Auto mode routes to all 6 canonical agents
    auto_agents = route_agents_for_problem("Complex enterprise system", model="Auto")
    assert len(auto_agents) == 6
