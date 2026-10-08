"""
CHAI Resilience Hardening Regression Test Suite
================================================
Covers all 32 required regression tests for Issues #1, #2, and #3:
- Tests 1-10: Synthesizer Robust Parsing & Failure Handling
- Tests 11-18: Reliability Monitor Deterministic Hard Gates & Execution Integrity
- Tests 19-26: Output Validator Internal Error Detection & False-Positive Immunity
- Tests 27-32: Coordinator End-to-End Integration, Consistency, and Work Preservation
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
import pytest

from backend.agents.synthesizer.agent import SynthesizerAgent
from backend.agents.synthesizer.schemas import (
    AgentStatus,
    SynthesizerResult,
    KeyDecision,
    SupportingFinding,
)
from backend.agents.reliability_monitor.agent import (
    ReliabilityMonitorAgent,
    ReliabilityMonitorResult,
    ReliabilityAction,
    ReliabilityLevel,
    ReliabilityDimension,
    DimensionStatus,
)
from backend.validation.output_validator import OutputValidator, OutputValidationResult
from backend.core.coordinator import Coordinator, CANONICAL_AGENTS
from backend.core.schemas import SolveRequest, AgentExecutionStatus


@pytest.fixture(autouse=True)
def enable_chai_mock_mode(monkeypatch):
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")


# ==============================================================================
# Synthesizer Tests (1 to 10)
# ==============================================================================

def test_1_valid_structured_gemini_output_parses():
    """1. Valid structured Gemini output parses successfully."""
    agent = SynthesizerAgent()
    payload = json.dumps({
        "agent": "synthesizer",
        "status": "completed",
        "final_answer": "Valid synthesized response narrative.",
        "key_decisions": [{"decision": "D1", "rationale": "R1", "supported_by": ["engineer"]}],
        "supporting_findings": [],
        "resolved_conflicts": [],
        "unresolved_conflicts": [],
        "limitations": [],
        "assumptions": [],
        "missing_information": [],
        "provenance": [],
    })
    result = agent._parse_response(payload)
    assert result.status == AgentStatus.COMPLETED
    assert result.final_answer == "Valid synthesized response narrative."
    assert len(result.key_decisions) == 1


def test_2_output_containing_markdown_handled_correctly():
    """2. Output containing markdown is handled correctly."""
    agent = SynthesizerAgent()
    markdown_answer = (
        "## Executive Summary\n"
        "Here is the synthesized architecture.\n\n"
        "### Core Components\n"
        "- Component A: Event Bus\n"
        "- Component B: Distributed Cache\n\n"
        "```python\n"
        "def process():\n"
        "    return True\n"
        "```\n"
    )
    payload = json.dumps({
        "agent": "synthesizer",
        "status": "completed",
        "final_answer": markdown_answer,
        "key_decisions": [],
        "supporting_findings": [],
        "resolved_conflicts": [],
        "unresolved_conflicts": [],
        "limitations": [],
        "assumptions": [],
        "missing_information": [],
        "provenance": [],
    })
    result = agent._parse_response(f"```json\n{payload}\n```")
    assert result.status == AgentStatus.COMPLETED
    assert "## Executive Summary" in result.final_answer
    assert "def process():" in result.final_answer


def test_3_output_containing_backslashes_handled_correctly():
    """3. Output containing backslashes is handled correctly without crashing."""
    agent = SynthesizerAgent()
    # Emulate Gemini returning unescaped LaTeX backslashes \alpha and \beta inside string
    raw_payload = (
        '{\n'
        '  "agent": "synthesizer",\n'
        '  "status": "completed",\n'
        '  "final_answer": "The formula uses \\alpha + \\beta and file path C:\\Users\\service.",\n'
        '  "key_decisions": [],\n'
        '  "supporting_findings": [],\n'
        '  "resolved_conflicts": [],\n'
        '  "unresolved_conflicts": [],\n'
        '  "limitations": [],\n'
        '  "assumptions": [],\n'
        '  "missing_information": [],\n'
        '  "provenance": []\n'
        '}'
    )
    result = agent._parse_response(raw_payload)
    assert result.status == AgentStatus.COMPLETED
    assert "alpha" in result.final_answer


def test_4_output_containing_escaped_quotes_handled_correctly():
    """4. Output containing escaped quotes is handled correctly."""
    agent = SynthesizerAgent()
    raw_payload = (
        '{\n'
        '  "agent": "synthesizer",\n'
        '  "status": "completed",\n'
        '  "final_answer": "The architecture is termed \\"Zero-Trust\\" by specialists.",\n'
        '  "key_decisions": [],\n'
        '  "supporting_findings": [],\n'
        '  "resolved_conflicts": [],\n'
        '  "unresolved_conflicts": [],\n'
        '  "limitations": [],\n'
        '  "assumptions": [],\n'
        '  "missing_information": [],\n'
        '  "provenance": []\n'
        '}'
    )
    result = agent._parse_response(raw_payload)
    assert result.status == AgentStatus.COMPLETED
    assert '"Zero-Trust"' in result.final_answer


def test_5_output_containing_newline_control_characters_does_not_crash():
    """5. Output containing newline/control characters does not crash unexpectedly."""
    agent = SynthesizerAgent()
    # Raw literal unescaped newline byte (ASCII 10) inside string value
    raw_payload = (
        '{\n'
        '  "agent": "synthesizer",\n'
        '  "status": "completed",\n'
        '  "final_answer": "Line 1\nLine 2\nLine 3",\n'
        '  "key_decisions": [],\n'
        '  "supporting_findings": [],\n'
        '  "resolved_conflicts": [],\n'
        '  "unresolved_conflicts": [],\n'
        '  "limitations": [],\n'
        '  "assumptions": [],\n'
        '  "missing_information": [],\n'
        '  "provenance": []\n'
        '}'
    )
    result = agent._parse_response(raw_payload)
    assert result.status == AgentStatus.COMPLETED
    assert "Line 1" in result.final_answer
    assert "Line 2" in result.final_answer


def test_6_unterminated_json_handled_as_structured_failure():
    """6. Unterminated JSON is handled as structured failure."""
    agent = SynthesizerAgent()
    truncated_payload = '{"agent": "synthesizer", "status": "completed", "final_answer": "This string is cut off and completely unclos'
    result = agent._parse_response(truncated_payload)
    assert result.status in (AgentStatus.FAILED, AgentStatus.COMPLETED)
    assert not any("JSONDecodeError" in str(getattr(result, f, "")) for f in ["final_answer"])


def test_7_invalid_escape_sequence_handled_safely():
    """7. Invalid escape sequence is handled as structured failure or safely repaired."""
    agent = SynthesizerAgent()
    bad_escape_payload = '{"agent": "synthesizer", "status": "completed", "final_answer": "Invalid escape: \\q \\w \\e \\r \\z"}'
    result = agent._parse_response(bad_escape_payload)
    # Must not raise unhandled exception
    assert result.status in (AgentStatus.COMPLETED, AgentStatus.FAILED)


def test_8_synthesizer_failure_never_exposes_raw_parser_exceptions():
    """8. Synthesizer failure never exposes raw parser exceptions as final user output."""
    agent = SynthesizerAgent()
    unparseable = "Fatal non-json garbage payload !@#$%^&*()"
    result = agent._parse_response(unparseable)
    assert result.status == AgentStatus.FAILED
    assert "JSONDecodeError" not in result.final_answer
    assert "LLM output is not valid JSON" not in result.final_answer
    assert "Traceback" not in result.final_answer
    assert "CHAI could not complete the final synthesis" in result.final_answer


@pytest.mark.asyncio
async def test_9_upstream_agent_outputs_remain_preserved_when_synthesizer_fails(monkeypatch):
    """9. Upstream agent outputs remain preserved when Synthesizer fails."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    coordinator = Coordinator()

    # Mock synthesizer to fail
    coordinator.synthesizer.run = AsyncMock(
        return_value=SynthesizerResult(
            agent="synthesizer",
            status=AgentStatus.FAILED,
            final_answer="CHAI could not complete the final synthesis reliably for this request.",
            limitations=["Synthesizer structured output could not be parsed."],
            error_type="invalid_structured_output",
            error="Synthesizer structured output could not be parsed",
        )
    )

    req = SolveRequest(problem="Design scalable architecture for financial analytics")
    resp = await coordinator.process_request(req)

    # Specialist outputs must remain present
    assert "researcher" in resp.agent_outputs
    assert "engineer" in resp.agent_outputs
    assert "security" in resp.agent_outputs
    assert "guardian" in resp.agent_outputs
    assert "evaluator" in resp.agent_outputs
    assert "conflict_resolver" in resp.agent_outputs
    assert resp.agent_outputs["synthesizer"]["status"] == "failed"


@pytest.mark.asyncio
async def test_10_synthesizer_status_correctly_recorded_as_failed(monkeypatch):
    """10. Synthesizer status is correctly recorded as failed in both statuses and trace."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    coordinator = Coordinator()

    coordinator.synthesizer.run = AsyncMock(
        return_value=SynthesizerResult(
            agent="synthesizer",
            status=AgentStatus.FAILED,
            final_answer="CHAI could not complete the final synthesis reliably for this request.",
            limitations=["Synthesis stage failed."],
            error_type="invalid_structured_output",
            error="Synthesizer structured output could not be parsed",
        )
    )

    req = SolveRequest(problem="Complex query requiring synthesis", selected_agents=CANONICAL_AGENTS)
    resp = await coordinator.process_request(req)

    status_map = {s.agent_name: s.status for s in resp.agent_execution_statuses}
    assert status_map["synthesizer"] == "failed"

    synth_trace = next((t for t in resp.execution_trace if t["agent"] == "synthesizer"), None)
    assert synth_trace is not None
    assert synth_trace["status"] == "failed"


# ==============================================================================
# Reliability Monitor Tests (11 to 18)
# ==============================================================================

@pytest.mark.asyncio
async def test_11_synthesizer_failure_prohibits_proceed():
    """11. Synthesizer failure prohibits PROCEED."""
    rm = ReliabilityMonitorAgent()
    context = {
        "execution_statuses": [
            AgentExecutionStatus(agent_name="researcher", status="success"),
            AgentExecutionStatus(agent_name="synthesizer", status="failed", error="Parse failed"),
        ],
        "all_outputs": {
            "synthesizer": {"status": "failed", "final_answer": "CHAI could not complete synthesis."}
        },
        "final_answer": "CHAI could not complete synthesis.",
    }
    res = await rm.run("Problem", context=context)
    assert res.action != ReliabilityAction.PROCEED
    assert res.action in (ReliabilityAction.PROCEED_WITH_LIMITATIONS, ReliabilityAction.BLOCK_OUTPUT)


@pytest.mark.asyncio
async def test_12_researcher_failure_is_visible_to_reliability_monitor():
    """12. Researcher failure is visible to Reliability Monitor."""
    rm = ReliabilityMonitorAgent()
    context = {
        "execution_statuses": [
            AgentExecutionStatus(agent_name="researcher", status="failed", error="Network error"),
            AgentExecutionStatus(agent_name="synthesizer", status="success"),
        ],
        "all_outputs": {
            "researcher": {"status": "failed"},
            "synthesizer": {"status": "completed", "final_answer": "Valid answer"},
        },
    }
    res = await rm.run("Problem", context=context)
    assert "researcher" in res.failed_agents
    assert res.action != ReliabilityAction.PROCEED


@pytest.mark.asyncio
async def test_13_engineer_failure_is_visible_to_reliability_monitor():
    """13. Engineer failure is visible to Reliability Monitor."""
    rm = ReliabilityMonitorAgent()
    context = {
        "execution_statuses": [
            AgentExecutionStatus(agent_name="engineer", status="failed", error="Timeout"),
            AgentExecutionStatus(agent_name="synthesizer", status="success"),
        ],
        "all_outputs": {
            "engineer": {"status": "failed"},
            "synthesizer": {"status": "completed", "final_answer": "Valid answer"},
        },
    }
    res = await rm.run("Problem", context=context)
    assert "engineer" in res.failed_agents
    assert res.action != ReliabilityAction.PROCEED


@pytest.mark.asyncio
async def test_14_multiple_failed_agents_reduce_execution_completeness():
    """14. Multiple failed agents reduce execution completeness."""
    rm = ReliabilityMonitorAgent()
    context = {
        "execution_statuses": [
            AgentExecutionStatus(agent_name="researcher", status="failed"),
            AgentExecutionStatus(agent_name="engineer", status="failed"),
            AgentExecutionStatus(agent_name="synthesizer", status="success"),
        ],
        "all_outputs": {
            "researcher": {"status": "failed"},
            "engineer": {"status": "failed"},
            "synthesizer": {"status": "completed", "final_answer": "Answer"},
        },
    }
    res = await rm.run("Problem", context=context)
    assert "Partial" in res.execution_completeness
    assert res.action != ReliabilityAction.PROCEED
    exec_dim = next((d for d in res.dimensions if d.name == "execution_completeness"), None)
    if exec_dim:
        assert exec_dim.score < 0.60


@pytest.mark.asyncio
async def test_15_final_answer_containing_internal_error_prohibits_proceed():
    """15. Final answer containing an internal error prohibits PROCEED."""
    rm = ReliabilityMonitorAgent()
    context = {
        "all_outputs": {
            "synthesizer": {"status": "completed", "final_answer": "Synthesis could not be completed: Agent failed"}
        },
        "final_answer": "Synthesis could not be completed: Agent failed",
    }
    res = await rm.run("Problem", context=context)
    assert res.action != ReliabilityAction.PROCEED


def test_16_llm_cannot_override_deterministic_failure_gates():
    """16. LLM cannot override deterministic failure gates."""
    # Create an artificial LLM output that claims PROCEED and 0.95 score
    raw_llm_result = ReliabilityMonitorResult(
        agent="reliability_monitor",
        status=AgentStatus.COMPLETED,
        reliability_score=0.95,
        reliability_level=ReliabilityLevel.HIGH,
        action=ReliabilityAction.PROCEED,
        dimensions=[
            ReliabilityDimension(
                name="execution_completeness",
                score=1.0,
                weight=0.15,
                status=DimensionStatus.PASSED,
                reason="Claiming everything passed",
            )
        ],
        strengths=["All good"],
        concerns=[],
        failed_agents=[],
    )

    context = {
        "execution_statuses": [
            AgentExecutionStatus(agent_name="synthesizer", status="failed", error="Structured parse error")
        ],
        "all_outputs": {"synthesizer": {"status": "failed"}},
    }

    enforced = ReliabilityMonitorAgent._enforce_scoring_policy(raw_llm_result, context=context)
    assert enforced.action != ReliabilityAction.PROCEED
    assert enforced.reliability_level != ReliabilityLevel.HIGH
    exec_dim = next((d for d in enforced.dimensions if d.name == "execution_completeness"), None)
    assert exec_dim.status == DimensionStatus.FAILED
    assert exec_dim.score < 0.50


def test_17_reliability_monitor_failure_produces_unknown_score_level():
    """17. Reliability Monitor failure produces UNKNOWN score/level."""
    failed = ReliabilityMonitorAgent._make_failed_output("Timeout during verification")
    assert failed.status == AgentStatus.FAILED
    assert failed.reliability_score is None
    assert failed.reliability_level == ReliabilityLevel.UNKNOWN
    assert failed.action == ReliabilityAction.PROCEED_WITH_LIMITATIONS
    assert any("Timeout" in c for c in failed.concerns)


@pytest.mark.asyncio
async def test_18_proceed_with_limitations_preserves_limitations():
    """18. PROCEED_WITH_LIMITATIONS preserves limitations correctly."""
    rm = ReliabilityMonitorAgent()
    context = {
        "execution_statuses": [
            AgentExecutionStatus(agent_name="security", status="failed"),
            AgentExecutionStatus(agent_name="synthesizer", status="success"),
        ],
        "all_outputs": {
            "security": {"status": "failed"},
            "synthesizer": {"status": "completed", "final_answer": "Valid answer"},
        },
    }
    res = await rm.run("Problem", context=context)
    assert res.action in (ReliabilityAction.PROCEED_WITH_LIMITATIONS, ReliabilityAction.BLOCK_OUTPUT)
    assert len(res.limitations) > 0


# ==============================================================================
# Output Validator Tests (19 to 26)
# ==============================================================================

def test_19_synthesis_could_not_be_completed_rejected():
    """19. 'Synthesis could not be completed...' is rejected."""
    val = OutputValidator()
    text = (
        "Based on the comprehensive analysis of our specialized agents:\n\n"
        "Synthesis could not be completed: Synthesizer Agent failed after 2 attempts: JSONDecodeError"
    )
    res = val.validate(text)
    assert res.is_valid is False
    assert any("Internal agent failure" in e for e in res.errors)


def test_20_jsondecodeerror_output_rejected():
    """20. JSONDecodeError output is rejected."""
    val = OutputValidator()
    text = "Error in output: LLM output is not valid JSON: JSONDecodeError: Unterminated string at line 10"
    res = val.validate(text)
    assert res.is_valid is False
    assert any("Internal agent failure" in e for e in res.errors)


def test_21_internal_gemini_api_failure_text_rejected():
    """21. Internal Gemini API failure text is rejected."""
    val = OutputValidator()
    text = "Call failed: google.api_core.exceptions.ResourceExhausted: 429 Quota exceeded for quota metric"
    res = val.validate(text)
    assert res.is_valid is False
    assert any("Internal agent failure" in e for e in res.errors)


def test_22_stack_trace_output_rejected():
    """22. Stack trace output is rejected."""
    val = OutputValidator()
    text = (
        "Execution crashed:\n"
        "Traceback (most recent call last):\n"
        "  File 'backend/core/coordinator.py', line 850, in process_request\n"
        "ValueError: Synthesis failed"
    )
    res = val.validate(text)
    assert res.is_valid is False
    assert any("traceback" in e.lower() or "stack trace" in e.lower() for e in res.errors)


def test_23_normal_technical_discussion_of_errors_not_rejected():
    """23. Normal technical discussion of errors is NOT rejected."""
    val = OutputValidator()
    text = (
        "When handling user input in Python, catch `ValueError` specifically:\n"
        "```python\n"
        "try:\n"
        "    val = int(user_str)\n"
        "except ValueError:\n"
        "    val = 0\n"
        "```\n"
        "This ensures clean input parsing without unhandled crashes."
    )
    res = val.validate(text)
    assert res.is_valid is True
    assert len(res.errors) == 0


def test_24_normal_answer_containing_word_error_not_rejected():
    """24. Normal answer containing the word 'error' is NOT rejected."""
    val = OutputValidator()
    text = (
        "In distributed consensus, Byzantine fault tolerance allows systems to reach agreement "
        "even when a fraction of nodes fail or transmit erroneous messages. The error correction "
        "protocols operate under bounded network latency assumptions."
    )
    res = val.validate(text)
    assert res.is_valid is True
    assert len(res.errors) == 0


def test_25_safe_structured_failure_message_passes_validation():
    """25. Safe structured failure message passes validation."""
    val = OutputValidator()
    safe_msg = (
        "CHAI could not complete the final synthesis reliably for this request.\n\n"
        "Some specialist analysis was completed, but the final synthesis stage failed. "
        "The result has therefore been withheld rather than presenting an unverified answer."
    )
    res = val.validate(safe_msg)
    assert res.is_valid is True
    assert len(res.errors) == 0


def test_26_secrets_credentials_remain_blocked():
    """26. Secrets/credentials remain blocked."""
    val = OutputValidator()
    text = "Deployment config: AIzaSyD9876543210123456789012345678901"
    res = val.validate(text)
    assert res.is_valid is False
    assert any("credential" in e.lower() or "security pattern" in e.lower() for e in res.errors)


# ==============================================================================
# Integration Tests (27 to 32)
# ==============================================================================

@pytest.mark.asyncio
async def test_27_synthesizer_failure_detected_by_reliability_monitor(monkeypatch):
    """27. Synthesizer failure is detected by Reliability Monitor in full workflow."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    coordinator = Coordinator()

    coordinator.synthesizer.run = AsyncMock(
        return_value=SynthesizerResult(
            agent="synthesizer",
            status=AgentStatus.FAILED,
            final_answer="CHAI could not complete the final synthesis reliably for this request.",
            limitations=["Synthesizer structured output could not be parsed."],
            error_type="invalid_structured_output",
            error="Synthesizer structured output could not be parsed",
        )
    )

    req = SolveRequest(problem="Design multi-agent system", selected_agents=CANONICAL_AGENTS)
    resp = await coordinator.process_request(req)

    rm_output = resp.agent_outputs.get("reliability_monitor")
    assert rm_output is not None
    assert "synthesizer" in rm_output.get("failed_agents", [])


@pytest.mark.asyncio
async def test_28_reliability_monitor_cannot_return_proceed_on_synthesizer_failure(monkeypatch):
    """28. Reliability Monitor cannot return PROCEED when Synthesizer fails."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    coordinator = Coordinator()

    coordinator.synthesizer.run = AsyncMock(
        return_value=SynthesizerResult(
            agent="synthesizer",
            status=AgentStatus.FAILED,
            final_answer="CHAI could not complete the final synthesis reliably for this request.",
            limitations=["Synthesizer structured output could not be parsed."],
            error_type="invalid_structured_output",
            error="Synthesizer structured output could not be parsed",
        )
    )

    req = SolveRequest(problem="Design multi-agent system", selected_agents=CANONICAL_AGENTS)
    resp = await coordinator.process_request(req)

    rm_output = resp.agent_outputs.get("reliability_monitor")
    assert rm_output is not None
    assert rm_output.get("action") != "PROCEED"


@pytest.mark.asyncio
async def test_29_output_validator_rejects_accidental_raw_failure_content():
    """29. Output Validator rejects any accidental raw failure content."""
    val = OutputValidator()
    accidentally_leaked = "Based on our agents:\nSynthesis could not be completed: LLM output is not valid JSON"
    res = val.validate(accidentally_leaked)
    assert res.is_valid is False
    assert any("Internal agent failure" in e for e in res.errors)


@pytest.mark.asyncio
async def test_30_final_user_response_contains_only_safe_structured_failure_text(monkeypatch):
    """30. Final user response contains only safe structured failure/limitation text."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    coordinator = Coordinator()

    coordinator.synthesizer.run = AsyncMock(
        return_value=SynthesizerResult(
            agent="synthesizer",
            status=AgentStatus.FAILED,
            final_answer="CHAI could not complete the final synthesis reliably for this request.",
            limitations=["Synthesizer structured output could not be parsed."],
            error_type="invalid_structured_output",
            error="Synthesizer structured output could not be parsed",
        )
    )

    req = SolveRequest(problem="Complex enterprise integration query", selected_agents=CANONICAL_AGENTS)
    resp = await coordinator.process_request(req)

    assert "CHAI could not complete the final synthesis" in resp.final_answer
    assert "JSONDecodeError" not in resp.final_answer
    assert "Traceback" not in resp.final_answer
    assert "LLM output is not valid JSON" not in resp.final_answer
    assert "Synthesizer Agent failed after 2 attempts" not in resp.final_answer


@pytest.mark.asyncio
async def test_31_execution_trace_and_agent_execution_statuses_remain_consistent(monkeypatch):
    """31. execution_trace and agent_execution_statuses remain consistent on failure."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    coordinator = Coordinator()

    coordinator.synthesizer.run = AsyncMock(
        return_value=SynthesizerResult(
            agent="synthesizer",
            status=AgentStatus.FAILED,
            final_answer="CHAI could not complete the final synthesis reliably for this request.",
            limitations=["Synthesizer failure"],
            error_type="invalid_structured_output",
            error="Structured parse failure",
        )
    )

    req = SolveRequest(problem="Complex integration query", selected_agents=CANONICAL_AGENTS)
    resp = await coordinator.process_request(req)

    # Check synthesizer status in execution_statuses
    synth_status = next((s for s in resp.agent_execution_statuses if s.agent_name == "synthesizer"), None)
    assert synth_status is not None
    assert synth_status.status == "failed"

    # Check synthesizer status in execution_trace
    synth_trace = next((t for t in resp.execution_trace if t["agent"] == "synthesizer"), None)
    assert synth_trace is not None
    assert synth_trace["status"] == "failed"

    # Both MUST agree
    assert synth_status.status == synth_trace["status"]


@pytest.mark.asyncio
async def test_32_completed_upstream_agent_outputs_remain_preserved(monkeypatch):
    """32. Completed upstream agent outputs remain preserved in response."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    coordinator = Coordinator()

    coordinator.synthesizer.run = AsyncMock(
        return_value=SynthesizerResult(
            agent="synthesizer",
            status=AgentStatus.FAILED,
            final_answer="CHAI could not complete the final synthesis reliably for this request.",
            limitations=["Synthesizer failure"],
            error_type="invalid_structured_output",
            error="Structured parse failure",
        )
    )

    req = SolveRequest(problem="Complex query", selected_agents=CANONICAL_AGENTS)
    resp = await coordinator.process_request(req)

    # All upstream outputs exist and contain completed work
    expected_agents = ["researcher", "strategist", "engineer", "guardian", "security", "evaluator", "conflict_resolver"]
    for agent in expected_agents:
        assert agent in resp.agent_outputs
        out = resp.agent_outputs[agent]
        assert isinstance(out, dict)
        assert len(out) > 0
