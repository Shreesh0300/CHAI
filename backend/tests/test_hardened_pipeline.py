"""
Hardened Pipeline and Regression Test Suite for CHAI.

Covers:
- Category A: Researcher structured contract & normalization
- Category B: Engineer structured contract & nested overview validation & smart retry
- Category C: Security structured contract & structured object coercion
- Category D: Evaluator detects missing/failed upstream outputs
- Category E: Conflict Resolver always executes in complex flow
- Category F: Reliability Monitor always executes in complex flow
- Category G: Synthesizer handles failed agents & transparent limitations
- Category H: Output Validator detects false completion / missing agent claims
- Category I: Simple query bypass
- Category J: Complex deterministic pipeline execution trace
- Category K: Gemini structured-output fallback
- Category L: Gemini 429 quota handling & error sanitization
- Category M: Information source failure isolation
- Category N: Secret / token redaction
- Category O: Truthful execution trace verification
- Bug 19: End-to-end degraded execution (Engineer & Security fail)
- Bug 20: End-to-end full success execution (All agents succeed)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError

from backend.agents.researcher.models import ResearchResult, Source
from backend.agents.engineer.schemas import EngineerResult, EngineerOutput, AIMLDesign, ArchitectureDesign, DatabaseDesign
from backend.agents.engineer.agent import EngineerAgent
from backend.agents.security.models import SecurityResult
from backend.agents.evaluator.agent import EvaluatorAgent
from backend.agents.evaluator.schemas import EvaluatorOutput, EvaluatorResult, AgentStatus
from backend.agents.synthesizer.agent import SynthesizerAgent
from backend.agents.conflict_resolver.models import ConflictResolutionResult
from backend.agents.reliability_monitor.models import ReliabilityMonitorResult, ReliabilityAction
from backend.validation.output_validator import OutputValidator, OutputValidationResult
from backend.core.coordinator import Coordinator
from backend.core.schemas import SolveRequest, FinalResponse, AgentExecutionStatus
from backend.shared.llm_client import GeminiClient, sanitize_api_keys
from backend.information.service import InformationAcquisitionService
from backend.information.models import InformationResult, InformationItem


# ------------------------------------------------------------------------------
# Category A: Researcher Structured Contract
# ------------------------------------------------------------------------------

def test_category_a_researcher_contract_normalization():
    """Model name variations must normalize to canonical 'researcher'."""
    raw = {
        "agent": "Researcher Agent",
        "status": "COMPLETED",
        "key_findings": ["Finding 1", "Finding 2"],
        "user_needs": ["Need 1"],
    }
    result = ResearchResult.model_validate(raw)
    assert result.agent == "researcher"
    assert result.status == "completed"

    raw2 = {
        "agent": "researcher_agent",
        "status": "completed",
        "key_findings": ["Finding 1"],
    }
    result2 = ResearchResult.model_validate(raw2)
    assert result2.agent == "researcher"


def test_category_a_researcher_contract_rejection():
    """Arbitrary names must be rejected, not silently accepted."""
    with pytest.raises(ValidationError):
        ResearchResult.model_validate({
            "agent": "unrelated_bot",
            "key_findings": ["Finding 1"],
        })


# ------------------------------------------------------------------------------
# Category B: Engineer Structured Contract & Retries
# ------------------------------------------------------------------------------

def test_category_b_engineer_nested_overview_coercion():
    """Nested models missing overview must gracefully synthesize default overview."""
    raw = {
        "agent": "Engineer Agent",
        "problem_understanding": "System design",
        "technical_architecture": "Microservices",
        "ai_ml_system_design": {
            # 'overview' omitted intentionally to test validator recovery
            "model_role": "LLM text processing",
        },
    }
    result = EngineerResult.model_validate(raw)
    assert result.agent == "engineer"
    assert result.ai_ml_design is not None
    assert result.ai_ml_design.overview != ""
    assert "LLM" in result.ai_ml_design.overview


@pytest.mark.asyncio
async def test_category_b_engineer_retry_on_invalid_json():
    """Engineer retries with contract reminder when LLM returns invalid JSON on attempt 1."""
    mock_llm = MagicMock()
    # Attempt 1: Malformed JSON. Attempt 2: Valid JSON
    mock_llm.generate_content = AsyncMock(side_effect=[
        "Here is the design: { not valid json",
        """{
            "agent": "engineer",
            "problem_understanding": "Secure portal",
            "technical_architecture": "Cloud-native Kubernetes architecture",
            "key_components": ["API Gateway", "Auth Service"],
            "apis_and_interfaces": ["POST /apply"],
            "data_flow_and_storage": "PostgreSQL with AES-256",
            "ai_ml_design": {"overview": "RAG pipeline on Vertex AI"},
            "infrastructure_and_deployment": "GKE multi-region",
            "implementation_phases": ["Phase 1"],
            "technical_risks_and_mitigations": ["DDoS risk -> Cloud Armor"],
            "technical_assumptions": ["High availability required"]
        }"""
    ])

    agent = EngineerAgent(llm_client=mock_llm)
    out = await agent.run("Design student admissions portal")
    assert out.engineer_result is not None
    assert out.engineer_result.agent == "engineer"
    assert mock_llm.generate_content.call_count == 2
    # Verify the retry prompt included contract correction reminder
    retry_call_prompt = mock_llm.generate_content.call_args_list[1][1]["prompt"]
    assert "CRITICAL CONTRACT CORRECTION" in retry_call_prompt


# ------------------------------------------------------------------------------
# Category C: Security Structured Contract
# ------------------------------------------------------------------------------

def test_category_c_security_contract_coercion():
    """SecurityResult must coerce 'security_agent', dict threats, and dict severities to canonical contract."""
    raw = {
        "agent": "security_agent",
        "status": "completed",
        "security_summary": "Robust zero-trust security architecture",
        "threats": [
            {"threat": "SQL Injection in admissions portal", "severity": "critical"},
            {"name": "BOLA on student records", "impact": "High risk of PII leak"},
        ],
        "severity_levels": {
            "critical": 1,
            "high": 1,
            "medium": 0,
        },
        "mitigations": ["WAF rules", "RBAC enforcement"],
    }
    result = SecurityResult.model_validate(raw)
    assert result.agent == "security"
    assert len(result.threats) == 2
    assert "SQL Injection" in result.threats[0]
    assert "critical" in result.threats[0].lower()
    assert "Critical" in result.severity_levels
    assert "High" in result.severity_levels


# ------------------------------------------------------------------------------
# Category D: Evaluator Detects Missing/Failed Upstream Outputs
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_category_d_evaluator_detects_failed_agents():
    """Evaluator must report degraded coverage and partial status when upstream agents fail."""
    mock_llm = MagicMock()
    mock_llm.generate_content = AsyncMock(return_value="""{
        "agent": "evaluator",
        "status": "completed",
        "completeness_score": 0.6,
        "consistency_score": 0.8,
        "coherence_score": 0.8,
        "overall_score": 0.7,
        "overall_assessment": "Evaluated with available agents.",
        "conflicts": [],
        "inconsistencies": [],
        "unsupported_claims": [],
        "quality_issues": [],
        "requirement_coverage": [
            {"requirement": "Admissions process", "status": "addressed", "detail": "Addressed by Researcher and Strategist"}
        ],
        "strengths": ["Clear strategy"],
        "recommendations": ["Complete engineering and security specs"],
        "assumptions": [],
        "missing_information": []
    }""")
    evaluator = EvaluatorAgent(llm_client=mock_llm)
    context = {
        "failed_agents": ["engineer", "security"],
        "execution_statuses": [
            {"agent_name": "researcher", "status": "success"},
            {"agent_name": "strategist", "status": "success"},
            {"agent_name": "engineer", "status": "failed", "error": "Schema timeout"},
            {"agent_name": "security", "status": "failed", "error": "JSON parse error"},
        ],
    }
    out = await evaluator.run("Design secure application system", context=context)
    res = out.evaluator_result
    assert res.agent == "evaluator"
    assert res.status == AgentStatus.PARTIAL
    # Must explicitly log coverage issues for failed agents
    missing_reported = [c.requirement for c in res.requirement_coverage if c.status.value in ("missing", "partial", "not_addressed")]
    assert any("engineer" in r.lower() for r in missing_reported)
    assert any("security" in r.lower() for r in missing_reported)


# ------------------------------------------------------------------------------
# Category G: Synthesizer Handles Failed Agents
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_category_g_synthesizer_marks_limitations_for_failed_agents():
    """Synthesizer must not fabricate outputs for failed agents and must mark limitations."""
    mock_llm = MagicMock()
    mock_llm.generate_content = AsyncMock(return_value="""{
        "agent": "synthesizer",
        "status": "partial",
        "final_answer": "Implementation plan operates in partial mode due to missing engineer and security specifications.",
        "key_decisions": [],
        "supporting_findings": [],
        "resolved_conflicts": [],
        "unresolved_conflicts": [],
        "limitations": ["Engineer technical architecture missing", "Security threat model missing"],
        "provenance": []
    }""")
    synth = SynthesizerAgent(llm_client=mock_llm)
    context = {
        "failed_agents": ["engineer", "security"],
        "all_outputs": {
            "researcher": {"status": "completed", "key_findings": ["Students need accessibility"]},
            "strategist": {"status": "completed", "strategy": "Phased mobile rollout"},
        },
    }
    out = await synth.run("Design student admissions portal", context=context)
    final_text = out.final_answer or ""
    # Synthesizer must acknowledge incomplete / missing inputs
    assert (
        "engineer" in final_text.lower()
        or "security" in final_text.lower()
        or "partial" in final_text.lower()
        or len(out.unresolved_conflicts) > 0
        or len(out.limitations) > 0
    )


# ------------------------------------------------------------------------------
# Category H: Output Validator Detects False Completion
# ------------------------------------------------------------------------------

def test_category_h_output_validator_detects_false_claims_of_failed_agents():
    """Output validator blocks output if text falsely asserts a failed agent verified something."""
    validator = OutputValidator()
    context = {
        "failed_agents": ["security"],
        "all_outputs": {"security": {"status": "failed"}},
    }
    candidate_answer = "The security agent verified zero-trust architecture and approved the design."
    res = validator.validate(candidate_answer, context=context)
    assert not res.is_valid
    assert any("failed agent 'security'" in err.lower() for err in res.errors)


# ------------------------------------------------------------------------------
# Category I: Simple Query Routing Bypass
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_category_i_simple_query_bypass():
    """Simple query like 'What is 2 + 2?' routes directly without running 12-stage pipeline."""
    coord = Coordinator()
    req = SolveRequest(problem="What is 2 + 2?")
    res = await coord.process_request(req)
    assert res.route in ("simple", "direct")
    assert res.request_status == "completed"
    assert len(res.agent_execution_statuses) == 0


# ------------------------------------------------------------------------------
# Category L: Gemini Quota (429) & Error Sanitization
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_category_l_gemini_429_quota_handling():
    """Gemini 429 quota exhaustion must be raised as clean sanitized RuntimeError without keys."""
    client = GeminiClient(api_key="AIzaSyDummySecretKey1234567890")
    mock_aio = MagicMock()
    mock_aio.models.generate_content = AsyncMock(
        side_effect=Exception("429 ResourceExhausted: quota exceeded for api_key=AIzaSyDummySecretKey1234567890")
    )
    client._client = MagicMock(aio=mock_aio)
    with patch.dict("os.environ", {"CHAI_MOCK_MODE": "false"}):
        with pytest.raises(RuntimeError) as exc_info:
            await client.generate("Hello world")
        err_msg = str(exc_info.value)
        assert "429" in err_msg or "quota" in err_msg.lower() or "[QUOTA_ERROR]" in err_msg
        assert "AIzaSyDummySecretKey1234567890" not in err_msg
        assert "[REDACTED_API_KEY]" in err_msg or "AIza" not in err_msg


# ------------------------------------------------------------------------------
# Category M: Information Source Failure Isolation
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_category_m_information_source_failure_isolation():
    """An individual source failure (e.g. 403 or exception) must not fail entire acquisition."""
    service = InformationAcquisitionService()
    # Mock web source failing with 403
    mock_web = AsyncMock()
    mock_web.acquire = AsyncMock(side_effect=Exception("HTTP 403 Forbidden for Medium blog"))
    mock_web.source_type = "web"

    # Mock api source succeeding
    mock_api = AsyncMock()
    mock_api.acquire = AsyncMock(return_value=[
        InformationItem(source_type="api", source="campus.api", title="Campus API", content="Auth spec", url="https://api.edu")
    ])
    mock_api.source_type = "api"

    service._sources = [mock_web, mock_api]
    result = await service.acquire("University portal")
    assert result.status == "completed"
    assert len(result.items) >= 1
    assert any(s.title == "Campus API" for s in result.items)


# ------------------------------------------------------------------------------
# Category N: Secret Redaction
# ------------------------------------------------------------------------------

def test_category_n_secret_redaction():
    text = "Error occurred connecting to https://generativelanguage.googleapis.com?key=AIzaSyA1B2C3D4E5F6G7H8I9J0"
    sanitized = sanitize_api_keys(text)
    assert "AIzaSy" not in sanitized
    assert "[REDACTED]" in sanitized


# ------------------------------------------------------------------------------
# Bug 19: End-to-End Degraded Execution Test
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bug_19_end_to_end_degraded_pipeline():
    """
    Exact scenario:
    Researcher = success
    Strategist = success
    Engineer = failure
    Guardian = success
    Security = failure
    Evaluator = success
    Conflict Resolver = success
    Synthesizer = success
    Reliability Monitor = success
    Output Validator = success

    Expected:
    - Pipeline does not crash.
    - Engineer and Security appear as failed in execution_statuses & trace.
    - Conflict Resolver and Reliability Monitor execute.
    - Final status is 'partial'.
    - Degraded notice is prepended.
    - All 12 stages appear in execution_trace.
    """
    coord = Coordinator()

    # Researcher mock
    coord.researcher.run = AsyncMock(return_value=ResearchResult(
        agent="researcher",
        status="completed",
        key_findings=["Need accessible mobile student portal"],
    ))
    # Strategist mock
    coord.strategist.run = AsyncMock(return_value=MagicMock(
        agent="strategist",
        status="completed",
        strategy="Incremental cloud migration",
        model_dump=lambda: {"agent": "strategist", "status": "completed", "strategy": "Incremental cloud migration"},
    ))
    # Engineer failure mock
    coord.engineer.run = AsyncMock(side_effect=RuntimeError("Engineer schema validation exhausted"))
    # Guardian mock
    coord.guardian.run = AsyncMock(return_value=MagicMock(
        agent="guardian",
        status="completed",
        risk_level="low",
        model_dump=lambda: {"agent": "guardian", "status": "completed", "risk_level": "low"},
    ))
    # Security failure mock
    coord.security.run = AsyncMock(side_effect=RuntimeError("Security contract failure"))
    # Evaluator mock
    coord.evaluator.run = AsyncMock(return_value=EvaluatorOutput(
        agent="evaluator",
        status=AgentStatus.PARTIAL,
        evaluator_result=EvaluatorResult(
            agent="evaluator",
            status=AgentStatus.PARTIAL,
            overall_assessment="Evaluated with degraded upstream modules (Engineer, Security failed).",
        ),
    ))

    # Conflict resolver mock
    coord.conflict_resolver.run = AsyncMock(return_value=ConflictResolutionResult(
        agent="conflict_resolver",
        status="completed",
        conflicts_identified=[],
        resolutions=[],
    ))

    # Synthesizer mock
    coord.synthesizer.run = AsyncMock(return_value=MagicMock(
        agent="synthesizer",
        status="completed",
        final_answer="The admissions portal strategy prioritizes cloud resilience and user accessibility.",
        model_dump=lambda: {
            "agent": "synthesizer",
            "status": "completed",
            "final_answer": "The admissions portal strategy prioritizes cloud resilience and user accessibility.",
        },
    ))

    # Reliability monitor mock
    coord.reliability_monitor.run = AsyncMock(return_value=ReliabilityMonitorResult(
        agent="reliability_monitor",
        reliability_score=0.65,
        action=ReliabilityAction.PROCEED_WITH_LIMITATIONS,
        concerns=["Engineering architecture and security evaluations could not be fully completed."],
    ))

    req = SolveRequest(problem="Design a secure AI-powered student application system")
    response: FinalResponse = await coord.process_request(req)

    # 1. Pipeline did not crash
    assert response is not None
    # 2. Overall status is partial
    assert response.request_status == "partial"

    # 3. Engineer and Security recorded as failed
    status_dict = {s.agent_name: s.status for s in response.agent_execution_statuses}
    assert status_dict["engineer"] == "failed"
    assert status_dict["security"] == "failed"
    assert status_dict["researcher"] == "success"
    assert status_dict["strategist"] == "success"
    assert status_dict["guardian"] == "success"
    assert status_dict["evaluator"] == "success"

    # 4. Transparency banner prepended
    assert "STATUS: PARTIAL (DEGRADED)" in response.final_answer
    assert "Failed: Engineer, Security" in response.final_answer

    # 5. Execution trace contains all 12 stages
    trace_agents = [t["agent"] for t in response.execution_trace]
    expected_stages = [
        "router",
        "information_acquisition",
        "researcher",
        "strategist",
        "engineer",
        "guardian",
        "security",
        "evaluator",
        "conflict_resolver",
        "synthesizer",
        "reliability_monitor",
        "output_validator",
    ]
    for stage in expected_stages:
        assert stage in trace_agents, f"Stage {stage} missing from execution trace: {trace_agents}"


# ------------------------------------------------------------------------------
# Bug 20: End-to-End Full Success Path Test
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bug_20_end_to_end_full_success_pipeline():
    """
    All agents succeed with valid structured outputs.
    Expected:
    - All 12 stages complete in execution_trace.
    - Status is 'completed'.
    - No degraded transparency banner required.
    """
    coord = Coordinator()

    coord.researcher.run = AsyncMock(return_value=ResearchResult(
        agent="researcher",
        status="completed",
        key_findings=["Unified admissions requirement"],
    ))
    coord.strategist.run = AsyncMock(return_value=MagicMock(
        agent="strategist",
        status="completed",
        strategy="Zero-downtime microservices strategy",
        model_dump=lambda: {"agent": "strategist", "status": "completed", "strategy": "Zero-downtime microservices strategy"},
    ))
    coord.engineer.run = AsyncMock(return_value=MagicMock(
        agent="engineer",
        status="completed",
        model_dump=lambda: {"agent": "engineer", "status": "completed", "technical_architecture": "FastAPI + Postgres"},
    ))
    coord.guardian.run = AsyncMock(return_value=MagicMock(
        agent="guardian",
        status="completed",
        risk_level="low",
        model_dump=lambda: {"agent": "guardian", "status": "completed", "risk_level": "low"},
    ))
    coord.security.run = AsyncMock(return_value=SecurityResult(
        agent="security",
        status="completed",
        security_summary="TLS 1.3, mTLS internal, OAuth2 + OIDC",
    ))
    coord.evaluator.run = AsyncMock(return_value=EvaluatorOutput(
        agent="evaluator",
        status=AgentStatus.COMPLETED,
        evaluator_result=EvaluatorResult(
            agent="evaluator",
            status=AgentStatus.COMPLETED,
            overall_assessment="Full agreement across engineering and security.",
        ),
    ))
    coord.conflict_resolver.run = AsyncMock(return_value=ConflictResolutionResult(
        agent="conflict_resolver",
        status="completed",
        conflicts_identified=[],
        resolutions=[],
    ))
    coord.synthesizer.run = AsyncMock(return_value=MagicMock(
        agent="synthesizer",
        status="completed",
        final_answer="Comprehensive, secure, and production-ready implementation plan.",
        model_dump=lambda: {
            "agent": "synthesizer",
            "status": "completed",
            "final_answer": "Comprehensive, secure, and production-ready implementation plan.",
        },
    ))
    coord.reliability_monitor.run = AsyncMock(return_value=ReliabilityMonitorResult(
        agent="reliability_monitor",
        reliability_score=0.98,
        action=ReliabilityAction.PROCEED,
    ))

    req = SolveRequest(problem="Design student admissions platform")
    response: FinalResponse = await coord.process_request(req)

    assert response.request_status == "completed"
    assert all(s.status == "success" for s in response.agent_execution_statuses)
    assert "STATUS: PARTIAL" not in response.final_answer

    trace_agents = [t["agent"] for t in response.execution_trace]
    expected_stages = [
        "router",
        "information_acquisition",
        "researcher",
        "strategist",
        "engineer",
        "guardian",
        "security",
        "evaluator",
        "conflict_resolver",
        "synthesizer",
        "reliability_monitor",
        "output_validator",
    ]
    for stage in expected_stages:
        assert stage in trace_agents


# ------------------------------------------------------------------------------
# Category E & F & J & O: Conflict Resolver & Reliability Monitor Always Execute
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_categories_e_f_j_o_zero_conflicts_still_executes_cr_and_rm():
    """
    Even when zero conflicts are detected, Conflict Resolver and Reliability Monitor
    must execute and appear in the 12-stage execution trace.
    """
    coord = Coordinator()
    # Mock evaluator with zero conflicts
    coord.evaluator.run = AsyncMock(return_value=EvaluatorOutput(
        agent="evaluator",
        status=AgentStatus.COMPLETED,
        detected_contradictions=[],
        evaluator_result=EvaluatorResult(
            agent="evaluator",
            status=AgentStatus.COMPLETED,
            overall_assessment="Evaluated architecture with zero conflicts.",
            conflicts=[],
            inconsistencies=[],
        ),
    ))

    cr_called = False
    async def mock_cr_run(problem, context=None):
        nonlocal cr_called
        cr_called = True
        return ConflictResolutionResult(
            agent="conflict_resolver",
            status="completed",
            conflicts_identified=[],
            resolutions=[],
        )
    coord.conflict_resolver.run = mock_cr_run

    rm_called = False
    async def mock_rm_run(problem, context=None):
        nonlocal rm_called
        rm_called = True
        return ReliabilityMonitorResult(
            agent="reliability_monitor",
            reliability_score=0.99,
            action=ReliabilityAction.PROCEED,
        )
    coord.reliability_monitor.run = mock_rm_run

    req = SolveRequest(problem="Analyze cloud architecture")
    response: FinalResponse = await coord.process_request(req)

    assert cr_called, "Conflict Resolver was not executed!"
    assert rm_called, "Reliability Monitor was not executed!"

    trace_agents = [t["agent"] for t in response.execution_trace]
    assert "conflict_resolver" in trace_agents
    assert "reliability_monitor" in trace_agents
    assert len(trace_agents) == 12


# ------------------------------------------------------------------------------
# Category K: Gemini Structured Output Fallback
# ------------------------------------------------------------------------------

def test_category_k_researcher_markdown_codefence_fallback():
    """Researcher agent properly parses output enclosed in markdown json fences."""
    from backend.agents.researcher.agent import ResearcherAgent
    agent = ResearcherAgent()
    markdown_wrapped = """Here is the research output:
```json
{
    "agent": "researcher",
    "status": "completed",
    "key_findings": ["Finding A", "Finding B"],
    "user_needs": ["Need A"]
}
```
Hope this helps!"""
    res = agent._parse_llm_response(markdown_wrapped, initial_sources=[])
    assert res.agent == "researcher"
    assert res.status == "completed"
    assert "Finding A" in res.key_findings
