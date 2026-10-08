"""
Test Suite for CHAI Agent Workflow and Shared Output Contracts.

Verifies:
1. ResearchResult → Strategist contract
2. StrategyResult → Engineer contract
3. EngineerResult → Guardian contract
4. EngineerResult → Security contract
5. All previous results → Evaluator contract
6. All previous results → Synthesizer contract
7. Typed state is authoritative
8. agent_outputs remains derived and consistent
9. Malformed agent output is rejected
10. Simple query bypasses specialized agents
11. Researcher failure hard-stops the complex pipeline
12. Complete complex workflow executes in exact sequential order
13. Final synthesis is validated by OutputValidator
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import ValidationError

from backend.agents.researcher.models import ResearchResult, Source
from backend.agents.strategist.models import StrategyResult
from backend.agents.engineer.schemas import EngineerResult, EngineerOutput, AgentStatus as EngStatus
from backend.agents.guardian.schemas import GuardianResult, GuardianOutput, AgentStatus as GuardStatus
from backend.agents.security.models import SecurityResult
from backend.agents.evaluator.schemas import EvaluatorResult, EvaluatorOutput, AgentStatus as EvalStatus
from backend.agents.conflict_resolver.schemas import ConflictResolutionResult, AgentStatus as CRStatus
from backend.agents.reliability_monitor.schemas import ReliabilityMonitorResult, ReliabilityAction, ReliabilityLevel, AgentStatus as RMStatus
from backend.core.contracts import (
    AgentResult,
    ResearcherInputContract,
    StrategistInputContract,
    EngineerInputContract,
    GuardianInputContract,
    SecurityInputContract,
    EvaluatorInputContract,
    SynthesizerInputContract,
    SynthesisResult,
    ValidationResult,
)
from backend.core.state import (
    CHAIState,
    create_initial_state,
    register_agent_result,
    get_canonical_agent_result,
)
from backend.core.workflow import build_chai_workflow
from backend.core.coordinator import Coordinator
from backend.core.schemas import SolveRequest
from backend.synthesis.synthesizer import Synthesizer
from backend.validation.output_validator import OutputValidator


# ---------------------------------------------------------------------------
# Test Fixtures & Sample Outputs
# ---------------------------------------------------------------------------

def sample_research_result() -> ResearchResult:
    return ResearchResult(
        agent="researcher",
        status="completed",
        key_findings=["Distributed ledger requires sub-second finality."],
        user_needs=["High throughput transaction settlement."],
        constraints=["Regulatory compliance with PCI-DSS."],
        assumptions=["Network nodes have reliable NTP synchronization."],
        open_questions=["What is the peak transactions per second requirement?"],
        sources=[Source(title="Fintech Spec 2026", url="https://example.com/spec", source_type="web")],
    )


def sample_strategy_result() -> StrategyResult:
    return StrategyResult(
        agent="strategist",
        status="completed",
        strategy="Adopt a hybrid consensus mechanism with zero-knowledge rollups.",
        priorities=["Deploy testnet validator nodes", "Audit smart contract primitives"],
        roadmap=["Phase 1: Architecture blueprint", "Phase 2: Testnet deployment"],
        tradeoffs=["Higher latency on Layer 1 for cheaper Layer 2 settlement"],
        success_metrics=["Sub-500ms block confirmation time"],
    )


def sample_engineer_output() -> EngineerOutput:
    eng_res = EngineerResult(
        problem_understanding="High scale fintech settlement engine",
        architecture=None,
        status=EngStatus.COMPLETED,
    )
    return EngineerOutput.from_engineer_result(eng_res)


def sample_guardian_output() -> GuardianOutput:
    guard_res = GuardianResult(
        safety_assessment="Financial risk assessment with anti-money laundering controls",
        status=GuardStatus.COMPLETED,
    )
    return GuardianOutput.from_guardian_result(guard_res)


def sample_security_result() -> SecurityResult:
    return SecurityResult(
        agent="security",
        status="completed",
        security_summary="Hardware security module (HSM) key management required.",
        threats=["Key compromise during validator signing", "Sybil attacks on p2p layer"],
        mitigations=["Enforce threshold signature schemes (TSS)", "Mutual TLS for RPC channels"],
    )


def sample_evaluator_output() -> EvaluatorOutput:
    eval_res = EvaluatorResult(
        agent="evaluator",
        status=EvalStatus.COMPLETED,
        overall_assessment="Strategy and Engineering are aligned; Security mitigations must be applied to Phase 1.",
        detected_contradictions=[],
    )
    return EvaluatorOutput.from_evaluator_result(eval_res)


# ==============================================================================
# 1. ResearchResult → Strategist Contract
# ==============================================================================

def test_1_research_result_to_strategist_contract():
    res = sample_research_result()
    contract = StrategistInputContract(
        problem="Build a financial transaction engine",
        research=res,
        context="Fintech domain",
    )
    assert contract.problem == "Build a financial transaction engine"
    assert contract.research.agent == "researcher"
    assert "Distributed ledger requires sub-second finality." in contract.research.key_findings
    assert len(contract.research.sources) == 1

    # Empty problem must fail validation
    with pytest.raises(ValidationError):
        StrategistInputContract(problem="   ", research=res)


# ==============================================================================
# 2. StrategyResult → Engineer Contract
# ==============================================================================

def test_2_strategy_result_to_engineer_contract():
    res = sample_research_result()
    strat = sample_strategy_result()
    contract = EngineerInputContract(
        problem="Build a financial transaction engine",
        research=res,
        strategy=strat,
        context={"upstream": True},
    )
    assert contract.strategy.strategy.startswith("Adopt a hybrid consensus")
    assert "Phase 1: Architecture blueprint" in contract.strategy.roadmap
    assert contract.research.status == "completed"

    with pytest.raises(ValidationError):
        EngineerInputContract(problem="", strategy=strat)


# ==============================================================================
# 3. EngineerResult → Guardian Contract
# ==============================================================================

def test_3_engineer_result_to_guardian_contract():
    res = sample_research_result()
    strat = sample_strategy_result()
    eng = sample_engineer_output()

    contract = GuardianInputContract(
        problem="Build a financial transaction engine",
        research=res,
        strategy=strat,
        engineering=eng,
    )
    assert contract.engineering is not None
    assert contract.problem == "Build a financial transaction engine"


# ==============================================================================
# 4. EngineerResult → Security Contract
# ==============================================================================

def test_4_engineer_result_to_security_contract():
    res = sample_research_result()
    strat = sample_strategy_result()
    eng = sample_engineer_output()

    contract = SecurityInputContract(
        problem="Build a financial transaction engine",
        research=res,
        strategy=strat,
        engineering=eng,
        context="High assurance banking",
    )
    assert contract.problem == "Build a financial transaction engine"
    assert contract.context == "High assurance banking"


# ==============================================================================
# 5. All Previous Results → Evaluator Contract
# ==============================================================================

def test_5_all_previous_results_to_evaluator_contract():
    contract = EvaluatorInputContract(
        problem="Build a financial transaction engine",
        research=sample_research_result(),
        strategy=sample_strategy_result(),
        engineering=sample_engineer_output(),
        guardian=sample_guardian_output(),
        security=sample_security_result(),
    )
    assert contract.security.agent == "security"
    assert len(contract.security.threats) == 2
    assert contract.research.agent == "researcher"


# ==============================================================================
# 6. All Previous Results → Synthesizer Contract
# ==============================================================================

@pytest.mark.asyncio
async def test_6_all_previous_results_to_synthesizer_contract():
    synth = Synthesizer()
    res = sample_research_result()
    strat = sample_strategy_result()
    eng = sample_engineer_output()
    guard = sample_guardian_output()
    sec = sample_security_result()
    ev = sample_evaluator_output()

    input_contract = SynthesizerInputContract(
        problem="Build a financial transaction engine",
        research=res,
        strategy=strat,
        engineering=eng,
        guardian=guard,
        security=sec,
        evaluator=ev,
        sources=["https://example.com/spec"],
        conflicts=["Latency vs decentralization tradeoff"],
    )

    result = await synth.synthesize(
        problem=input_contract.problem,
        research=input_contract.research,
        strategy=input_contract.strategy,
        engineering=input_contract.engineering,
        guardian=input_contract.guardian,
        security=input_contract.security,
        evaluator=input_contract.evaluator,
        sources=input_contract.sources,
        conflicts=input_contract.conflicts,
    )

    assert isinstance(result, SynthesisResult)
    assert result.agent == "synthesizer"
    assert result.status == "completed"
    assert len(result.summary) > 0
    assert len(result.reconciled_solution) > 0
    assert "Based on the comprehensive analysis of our specialized agents:" in result.final_text
    assert "Strategic Thesis:" in result.final_text
    assert "Cybersecurity & Protection:" in result.final_text
    assert "https://example.com/spec" in result.sources


# ==============================================================================
# 7. Typed State is Authoritative
# ==============================================================================

def test_7_typed_state_is_authoritative():
    state = create_initial_state("Test problem")
    res = sample_research_result()
    strat = sample_strategy_result()

    updates = register_agent_result(state, "researcher", res)
    state.update(updates)

    updates_strat = register_agent_result(state, "strategist", strat)
    state.update(updates_strat)

    # Canonical typed key is authoritative
    assert state["research_result"] is res
    assert isinstance(state["research_result"], ResearchResult)
    assert state["strategy_result"] is strat
    assert isinstance(state["strategy_result"], StrategyResult)

    # get_canonical_agent_result retrieves the typed object
    assert get_canonical_agent_result(state, "researcher") is res
    assert get_canonical_agent_result(state, "strategist") is strat


# ==============================================================================
# 8. agent_outputs Remains Derived and Consistent
# ==============================================================================

def test_8_agent_outputs_remains_derived_and_consistent():
    state = create_initial_state("Test problem")
    res = sample_research_result()

    updates = register_agent_result(state, "researcher", res)
    state.update(updates)

    # agent_outputs is derived from model_dump()
    assert "researcher" in state["agent_outputs"]
    serialized = state["agent_outputs"]["researcher"]
    assert isinstance(serialized, dict)
    assert serialized["agent"] == "researcher"
    assert serialized["key_findings"] == res.key_findings

    # Both representations reflect the exact same state without split-brain
    assert state["research_result"].key_findings == state["agent_outputs"]["researcher"]["key_findings"]


# ==============================================================================
# 9. Malformed Agent Output is Rejected by Validation
# ==============================================================================

def test_9_malformed_agent_output_is_rejected():
    # Attempting to validate invalid data into ResearchResult fails
    with pytest.raises(ValidationError):
        ResearchResult.model_validate({"agent": "unknown_agent", "status": "invalid_status"})

    # Attempting to validate invalid data into StrategyResult fails
    with pytest.raises(ValidationError):
        StrategyResult.model_validate({"agent": "not_strategist", "status": "wrong"})

    # Validator identifies empty or null output
    val = OutputValidator()
    result = val.validate(None)
    assert result.is_valid is False
    assert result.status == "failed"


# ==============================================================================
# 10. Simple Query Bypasses Specialized Agents
# ==============================================================================

@pytest.mark.asyncio
async def test_10_simple_query_bypasses_specialized_agents():
    res_mock = AsyncMock()
    strat_mock = AsyncMock()
    eng_mock = AsyncMock()
    guard_mock = AsyncMock()
    sec_mock = AsyncMock()
    eval_mock = AsyncMock()
    synth_mock = AsyncMock()
    val_mock = MagicMock()

    coordinator = Coordinator(
        researcher=res_mock,
        strategist=strat_mock,
        engineer=eng_mock,
        guardian=guard_mock,
        security=sec_mock,
        evaluator=eval_mock,
        synthesizer=synth_mock,
        output_validator=val_mock,
    )

    response = await coordinator.process_request(SolveRequest(problem="What is Python?"))

    assert response.route == "simple"
    assert response.request_status == "completed"
    assert response.selected_agents == []

    # None of the specialized agents or synthesizer were invoked
    res_mock.run.assert_not_called()
    strat_mock.run.assert_not_called()
    eng_mock.run.assert_not_called()
    guard_mock.run.assert_not_called()
    sec_mock.run.assert_not_called()
    eval_mock.run.assert_not_called()
    synth_mock.synthesize.assert_not_called()
    val_mock.validate.assert_not_called()


# ==============================================================================
# 11. Researcher Failure Hard-Stops the Complex Pipeline
# ==============================================================================

@pytest.mark.asyncio
async def test_11_researcher_failure_hard_stops_complex_pipeline():
    res_mock = AsyncMock()
    res_mock.run = AsyncMock(side_effect=RuntimeError("Web indexing cluster timeout"))

    strat_mock = AsyncMock()
    eng_mock = AsyncMock()
    guard_mock = AsyncMock()
    sec_mock = AsyncMock()
    eval_mock = AsyncMock()
    synth_mock = AsyncMock()
    val_mock = MagicMock()

    coordinator = Coordinator(
        researcher=res_mock,
        strategist=strat_mock,
        engineer=eng_mock,
        guardian=guard_mock,
        security=sec_mock,
        evaluator=eval_mock,
        synthesizer=synth_mock,
        output_validator=val_mock,
    )

    response = await coordinator.process_request(
        SolveRequest(problem="Architect a multi-datacenter consensus engine")
    )

    assert response.route == "complex"
    assert response.request_status == "failed"
    assert response.selected_agents == ["researcher"]

    # Downstream agents were NOT executed
    strat_mock.run.assert_not_called()
    eng_mock.run.assert_not_called()
    guard_mock.run.assert_not_called()
    sec_mock.run.assert_not_called()
    eval_mock.run.assert_not_called()
    synth_mock.synthesize.assert_not_called()
    val_mock.validate.assert_not_called()


# ==============================================================================
# 12. Complete Complex Workflow Executes in Exact Order
# ==============================================================================

@pytest.mark.asyncio
async def test_12_complete_complex_workflow_executes_in_exact_order():
    call_order = []

    async def mock_info(*args, **kwargs):
        call_order.append("information_acquisition")
        from backend.information.models import InformationResult
        return InformationResult(status="completed", query="Test", items=[])

    async def mock_res(*args, **kwargs):
        call_order.append("researcher")
        return sample_research_result()

    async def mock_strat(*args, **kwargs):
        call_order.append("strategist")
        return sample_strategy_result()

    async def mock_eng(*args, **kwargs):
        call_order.append("engineer")
        return sample_engineer_output()

    async def mock_guard(*args, **kwargs):
        call_order.append("guardian")
        return sample_guardian_output()

    async def mock_sec(*args, **kwargs):
        call_order.append("security")
        return sample_security_result()

    async def mock_eval(*args, **kwargs):
        call_order.append("evaluator")
        return sample_evaluator_output()

    async def mock_synth(*args, **kwargs):
        call_order.append("synthesizer")
        return SynthesisResult(
            agent="synthesizer",
            status="completed",
            summary="Test summary",
            reconciled_solution="Test solution",
            final_text="Based on the comprehensive analysis of our specialized agents:\n\nTest final text",
        )

    def mock_val(*args, **kwargs):
        call_order.append("output_validator")
        return ValidationResult(
            agent="output_validator",
            status="completed",
            is_valid=True,
            sanitized_text="Based on the comprehensive analysis of our specialized agents:\n\nTest final text",
        )

    info_service = MagicMock()
    info_service.acquire = AsyncMock(side_effect=mock_info)

    mock_cr = AsyncMock()
    mock_cr.run = AsyncMock(return_value=ConflictResolutionResult(
        agent="conflict_resolver",
        status=CRStatus.COMPLETED,
        resolutions=[],
        unresolved_conflicts=[],
        decision_basis=[],
        assumptions=[],
        missing_information=[],
        limitations=[],
        conflicts_considered=[],
        provenance=[],
    ))

    mock_rm = AsyncMock()
    mock_rm.run = AsyncMock(return_value=ReliabilityMonitorResult(
        agent="reliability_monitor",
        status=RMStatus.COMPLETED,
        reliability_score=0.95,
        reliability_level=ReliabilityLevel.HIGH,
        action=ReliabilityAction.PROCEED,
        concerns=[],
        limitations=[],
    ))

    coordinator = Coordinator(
        information_acquisition=info_service,
        researcher=AsyncMock(run=mock_res),
        strategist=AsyncMock(run=mock_strat),
        engineer=AsyncMock(run=mock_eng),
        guardian=AsyncMock(run=mock_guard),
        security=AsyncMock(run=mock_sec),
        evaluator=AsyncMock(run=mock_eval),
        conflict_resolver=mock_cr,
        synthesizer=AsyncMock(synthesize=mock_synth),
        reliability_monitor=mock_rm,
        output_validator=MagicMock(validate=mock_val),
    )

    response = await coordinator.process_request(
        SolveRequest(problem="Architect a fault-tolerant edge IoT mesh with end-to-end encryption")
    )

    assert response.route == "complex"
    assert response.request_status == "completed"

    expected_order = [
        "information_acquisition",
        "researcher",
        "strategist",
        "engineer",
        "guardian",
        "security",
        "evaluator",
        "synthesizer",
        "output_validator",
    ]
    assert call_order == expected_order


# ==============================================================================
# 13. Final Synthesis is Validated by OutputValidator
# ==============================================================================

def test_13_final_synthesis_is_validated():
    validator = OutputValidator()

    synth_res = SynthesisResult(
        agent="synthesizer",
        status="completed",
        summary="Clear summary of the architecture",
        reconciled_solution="Reconciled solution across strategy and engineering",
        final_text="Based on the comprehensive analysis of our specialized agents:\n\nFull validated synthesis.",
    )

    val_res = validator.validate(synth_res)
    assert isinstance(val_res, ValidationResult)
    assert val_res.agent == "output_validator"
    assert val_res.is_valid is True
    assert len(val_res.issues) == 0
    assert "Full validated synthesis" in val_res.sanitized_text

    # Sensitive token masking check
    leaky_synth = SynthesisResult(
        agent="synthesizer",
        status="completed",
        summary="Leaky summary",
        final_text="System uses sk-123456789012345678901234567890 for API calls.",
    )
    leaky_val = validator.validate(leaky_synth)
    assert leaky_val.is_valid is False
    assert "[REDACTED_SECRET]" in leaky_val.sanitized_text
    assert "sk-" not in leaky_val.sanitized_text
