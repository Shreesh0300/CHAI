import os
import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import ValidationError

from backend.agents.researcher.models import ResearchResult
from backend.agents.strategist.models import StrategyResult
from backend.agents.security.models import (
    SecurityInput,
    SecurityResult,
)
from backend.agents.security.agent import (
    SecurityAgent,
    security_node,
)
from backend.agents.security.prompts import (
    SYSTEM_PROMPT,
    build_security_prompt,
)
from backend.agents.security.tools import (
    normalize_severity,
    categorize_threat,
    clean_security_findings,
)


# 1. SecurityInput validation
def test_security_input_validation():
    # Problem alone
    inp = SecurityInput(problem="  Design secure telehealth app  ")
    assert inp.problem == "Design secure telehealth app"
    assert inp.context is None
    assert inp.research is None
    assert inp.strategy is None
    assert inp.engineering is None

    # Empty problem rejected
    with pytest.raises(ValueError, match="Problem statement cannot be empty"):
        SecurityInput(problem="")

    with pytest.raises(ValueError, match="Problem statement cannot be empty"):
        SecurityInput(problem="   \t\n  ")

    # Problem with research and strategy
    research = ResearchResult(
        key_findings=["Insecure mobile devices used"],
        constraints=["Low bandwidth"],
    )
    strategy = StrategyResult(
        strategy="Offline-first deployment",
        priorities=["Local DB sync"],
    )
    full_inp = SecurityInput(
        problem="Rural hospital triage system",
        research=research,
        strategy=strategy,
        engineering={"database": "SQLite"},
    )
    assert full_inp.problem == "Rural hospital triage system"
    assert full_inp.research.key_findings == ["Insecure mobile devices used"]
    assert full_inp.strategy.strategy == "Offline-first deployment"
    assert full_inp.engineering == {"database": "SQLite"}


# 2. SecurityResult defaults
def test_security_result_defaults():
    res = SecurityResult()
    assert res.agent == "security"
    assert res.status == "completed"
    assert res.security_summary == ""
    assert res.attack_surfaces == []
    assert res.threats == []
    assert res.authentication_risks == []
    assert res.authorization_risks == []
    assert res.data_privacy_risks == []
    assert res.api_security_risks == []
    assert res.prompt_injection_risks == []
    assert res.secret_exposure_risks == []
    assert res.severity_levels == []
    assert res.mitigations == []
    assert res.security_assumptions == []
    assert res.limitations == []


# 3. SecurityResult validation
def test_security_result_validation():
    populated = SecurityResult(
        agent="security",
        status="completed",
        security_summary="Moderate risk profile due to mobile client exposure.",
        attack_surfaces=["Public API gateway", "Mobile offline cache"],
        threats=["Data tampering in transit", "Insecure local storage"],
        authentication_risks=["Weak session expiration on shared devices"],
        authorization_risks=["Horizontal privilege escalation between patients"],
        data_privacy_risks=["PII leakage in crash analytics"],
        api_security_risks=["Lack of IP rate limiting on login endpoint"],
        prompt_injection_risks=["Indirect injection via patient health intake notes"],
        secret_exposure_risks=["Hardcoded JWT signing key in mobile bundle"],
        severity_levels=["High", "Medium"],
        mitigations=["Enforce SQLCipher for offline cache", "Implement mTLS"],
        security_assumptions=["TLS 1.3 is enforced at gateway"],
        limitations=["Physical device theft not fully modeled"],
    )
    assert populated.agent == "security"
    assert len(populated.attack_surfaces) == 2
    assert len(populated.mitigations) == 2

    # Invalid agent literal rejected
    with pytest.raises(ValidationError):
        SecurityResult(agent="strategist")

    # Invalid status literal rejected
    with pytest.raises(ValidationError):
        SecurityResult(status="in_progress")


# 4. Correct agent identifier and status handling
def test_agent_identifier_and_status():
    res_completed = SecurityResult(status="completed")
    assert res_completed.agent == "security"
    assert res_completed.status == "completed"

    res_failed = SecurityResult(status="failed")
    assert res_failed.agent == "security"
    assert res_failed.status == "failed"


# 5. Prompt generation and relevant security instructions
def test_prompt_generation_and_instructions():
    research = ResearchResult(
        key_findings=["Nurses share community tablets"],
        constraints=["Intermittent network"],
    )
    strategy = StrategyResult(
        strategy="Store-and-forward offline architecture",
        priorities=["Local sync queue"],
    )

    prompt = build_security_prompt(
        problem="Design secure patient records app",
        context="Rural health network",
        research=research,
        strategy=strategy,
        engineering={"auth": "JWT with refresh token"},
    )

    # Asserts problem and context are in prompt
    assert "Design secure patient records app" in prompt
    assert "Rural health network" in prompt

    # Asserts upstream research and strategy are woven into prompt
    assert "Nurses share community tablets" in prompt
    assert "Store-and-forward offline architecture" in prompt
    assert "JWT with refresh token" in prompt

    # Asserts core defensive security instructions exist
    assert "attack surfaces" in prompt.lower()
    assert "authentication" in prompt.lower()
    assert "mitigations" in prompt.lower()

    # Asserts SYSTEM_PROMPT contains defensive guidelines
    assert "defensive technical security architect" in SYSTEM_PROMPT.lower()
    assert "never provide exploit instructions" in SYSTEM_PROMPT.lower()
    assert "100% secure" in SYSTEM_PROMPT


# 6. Missing optional context is handled gracefully
@pytest.mark.asyncio
async def test_missing_optional_context_handled():
    mock_llm = MagicMock()
    mock_structured = MagicMock()

    mock_data = SecurityResult(
        agent="security",
        status="completed",
        security_summary="Baseline security evaluation.",
        attack_surfaces=["Public API endpoint"],
        threats=["Credential stuffing"],
        mitigations=["Rate limiting and MFA"],
    )
    mock_structured.ainvoke = AsyncMock(return_value=mock_data)
    mock_llm.with_structured_output.return_value = mock_structured

    agent = SecurityAgent(llm=mock_llm)
    # Run with problem alone, omitting all optional parameters
    result = await agent.run(problem="Design customer portal")

    assert result.status == "completed"
    assert result.agent == "security"
    assert "Baseline security evaluation." in result.security_summary
    assert len(result.attack_surfaces) == 1


# 7. Successful mocked LLM execution
@pytest.mark.asyncio
async def test_successful_mocked_llm_execution():
    mock_llm = MagicMock()
    mock_structured = MagicMock()

    mock_result = SecurityResult(
        agent="security",
        status="completed",
        security_summary="Analysis completed: High risk of prompt injection and local data leakage.",
        attack_surfaces=["Web UI chat interface", "Sync API"],
        threats=["Prompt injection into LLM pipeline", "Insecure direct object reference (IDOR)"],
        authentication_risks=["No brute-force protection"],
        authorization_risks=["Missing object-level authorization on medical records API"],
        data_privacy_risks=["Sensitive health data stored in plain SQLite on client"],
        api_security_risks=["Unauthenticated telemetry endpoint"],
        prompt_injection_risks=["Indirect injection from untrusted medical document uploads"],
        secret_exposure_risks=["Client bundle contains development API tokens"],
        severity_levels=["Critical: IDOR on patient records", "High: Local SQLite unencrypted"],
        mitigations=[
            "Implement SQLCipher database encryption",
            "Introduce strict server-side RBAC checks on /records/{id}",
            "Sanitize input text before model inference",
        ],
        security_assumptions=["TLS termination happens at Cloudflare edge"],
        limitations=["Physical side-channel hardware attacks out of scope"],
    )

    mock_structured.ainvoke = AsyncMock(return_value=mock_result)
    mock_llm.with_structured_output.return_value = mock_structured

    agent = SecurityAgent(llm=mock_llm)
    result = await agent.run(
        problem="Design offline medical intake app",
        context="Healthcare domain",
    )

    assert result.agent == "security"
    assert result.status == "completed"
    assert len(result.attack_surfaces) == 2
    assert len(result.threats) == 2
    assert len(result.mitigations) == 3
    assert "SQLCipher" in result.mitigations[0]


# 8. LLM/API failure handling
@pytest.mark.asyncio
async def test_llm_api_failure_handling():
    mock_llm = MagicMock()
    mock_llm.with_structured_output.side_effect = Exception("Google Gemini 429 Quota Exceeded")
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("Google Gemini 429 Quota Exceeded"))

    agent = SecurityAgent(llm=mock_llm)
    result = await agent.run(problem="Evaluate secure messaging gateway")

    assert result.agent == "security"
    assert result.status == "failed"
    assert result.security_summary == ""
    assert result.mitigations == []


# 9. Invalid structured output and fallback handling
@pytest.mark.asyncio
async def test_invalid_structured_output_fallback():
    mock_llm = MagicMock()
    mock_structured = MagicMock()

    # structured output raises, fallback receives completely unparseable text
    mock_structured.ainvoke = AsyncMock(side_effect=Exception("Structured output parser crashed"))
    mock_llm.with_structured_output.return_value = mock_structured

    bad_msg = MagicMock()
    bad_msg.content = "Malformed non-JSON output: <<Incompatible Format>>"
    mock_llm.ainvoke = AsyncMock(return_value=bad_msg)

    agent = SecurityAgent(llm=mock_llm)
    result = await agent.run(problem="Assess microservice mesh")

    assert result.agent == "security"
    assert result.status == "failed"


# 10. security_node returns expected state structure
@pytest.mark.asyncio
async def test_security_node_state_structure(monkeypatch):
    mock_llm = MagicMock()
    mock_structured = MagicMock()

    mock_structured.ainvoke = AsyncMock(return_value={
        "security_summary": "Architecture reviewed for technical vulnerabilities.",
        "attack_surfaces": ["REST API /v1/ingest"],
        "threats": ["Denial of Service"],
        "mitigations": ["Enforce rate limiter"],
    })
    mock_llm.with_structured_output.return_value = mock_structured

    monkeypatch.setattr(
        "backend.agents.security.agent.SecurityAgent._get_llm",
        lambda self: mock_llm,
    )

    state = {
        "problem": "Public telemetry ingestion pipeline",
        "research": {"key_findings": ["High throughput"]},
        "strategy": {"strategy": "Cloud pipeline"},
    }

    new_state = await security_node(state)
    assert "security_result" in new_state
    sec_data = new_state["security_result"]
    assert sec_data["agent"] == "security"
    assert sec_data["status"] == "completed"
    assert sec_data["security_summary"] == "Architecture reviewed for technical vulnerabilities."
    assert len(sec_data["attack_surfaces"]) == 1


# 11. Empty problem handling
def test_empty_problem_rejection():
    agent = SecurityAgent()
    with pytest.raises(ValueError, match="Problem statement cannot be empty"):
        import asyncio
        asyncio.run(agent.run(problem=""))

    with pytest.raises(ValueError, match="Problem statement cannot be empty"):
        import asyncio
        asyncio.run(agent.run(problem="   "))


# 12. No API key leakage in returned result
@pytest.mark.asyncio
async def test_no_api_key_leakage(monkeypatch):
    secret_key = "AIzaSyFakeKeySecurityTestSecret888"
    monkeypatch.setenv("GEMINI_API_KEY", secret_key)

    mock_llm = MagicMock()
    mock_llm.with_structured_output.side_effect = Exception("Internal connection error with backend token")
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("Internal connection error with backend token"))

    agent = SecurityAgent(llm=mock_llm)
    result = await agent.run(problem="Check encrypted storage")

    result_json = result.model_dump_json()
    assert secret_key not in result_json
    assert result.status == "failed"


# 13. Deterministic security tools
def test_deterministic_security_tools():
    # normalize_severity
    assert normalize_severity("CRITICAL") == "Critical"
    assert normalize_severity("high") == "High"
    assert normalize_severity("medium") == "Medium"
    assert normalize_severity("mod") == "Medium"
    assert normalize_severity("low") == "Low"
    assert normalize_severity("info") == "Informational"
    assert normalize_severity("unknown") == "Medium"

    # categorize_threat
    assert categorize_threat("Indirect prompt injection") == "Prompt Injection"
    assert categorize_threat("JWT session hijacking") == "Authentication"
    assert categorize_threat("IDOR vertical privilege escalation") == "Authorization"
    assert categorize_threat("Exposed API key in repository") == "Secret Exposure"
    assert categorize_threat("Public endpoint rate limit bypass") == "API Security"
    assert categorize_threat("Patient PII data leakage in logs") == "Data Privacy"
    assert categorize_threat("Kernel denial of service") == "General Infrastructure"

    # clean_security_findings
    raw = [" Finding A ", "Finding A", "Finding B", "", "   "]
    assert clean_security_findings(raw) == ["Finding A", "Finding B"]


# 14. Optional real Gemini integration test (disabled by default)
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_REAL_GEMINI_TEST") != "true",
    reason="Real Gemini integration test skipped. Set RUN_REAL_GEMINI_TEST=true to execute.",
)
async def test_real_gemini_integration():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not configured for live test.")

    agent = SecurityAgent()
    result = await agent.run(
        problem="Design an affordable AI-powered healthcare support platform for rural communities with unreliable internet."
    )

    if result.status == "failed":
        pytest.skip("Live Gemini call returned failed status (verify GEMINI_API_KEY validity in .env).")

    assert result.agent == "security"
    assert result.status == "completed"
    assert len(result.attack_surfaces) > 0
    assert len(result.threats) > 0
    assert len(result.mitigations) > 0


# ==============================================================================
# 15. SEVERITY LEVELS NORMALIZATION REGRESSION TESTS
# ==============================================================================

def test_severity_levels_as_list():
    """1. severity_levels as list[str] is accepted directly."""
    res = SecurityResult(
        security_summary="Test",
        severity_levels=["Critical", "High", "Medium"],
    )
    assert res.severity_levels == ["Critical", "High", "Medium"]


def test_severity_levels_as_dict():
    """2. severity_levels as dict[str, str] is safely normalized preserving threat and severity."""
    res = SecurityResult(
        security_summary="Test",
        severity_levels={
            "IDOR / Broken Authorization": "High",
            "Rate Limiting / API Abuse": "Medium",
        },
    )
    assert len(res.severity_levels) == 2
    assert "IDOR / Broken Authorization: High" in res.severity_levels
    assert "Rate Limiting / API Abuse: Medium" in res.severity_levels


def test_severity_levels_malformed_rejected():
    """3. malformed severity_levels (e.g. non-coercible invalid types) raises validation error."""
    with pytest.raises(Exception):
        SecurityResult(
            security_summary="Test",
            severity_levels=12345,  # int not allowed
        )

    with pytest.raises(Exception):
        SecurityResult(
            security_summary="Test",
            severity_levels=[object()],  # raw arbitrary object
        )


def test_severity_levels_empty_accepted():
    """4. empty severity_levels (empty list, empty dict, or None) produces empty list."""
    res_list = SecurityResult(security_summary="Test", severity_levels=[])
    assert res_list.severity_levels == []

    res_dict = SecurityResult(security_summary="Test", severity_levels={})
    assert res_dict.severity_levels == []

    res_none = SecurityResult(security_summary="Test", severity_levels=None)
    assert res_none.severity_levels == []

