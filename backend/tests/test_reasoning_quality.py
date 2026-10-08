"""
Regression tests for CHAI targeted reasoning quality fixes.

Covers:
A. Missing numeric information (no invented "5-10 hours/week")
B. Business decision (options compared, assumptions identified, conditional recommendations, no universal heuristics)
C. Personal life planning (interacting systems, not rigid sequential ordering)
D. Conflicting recommendations (explicit position_a, position_b, why_they_differ, resolution, rationale)
E. No conflict ("No material conflict detected" rather than fabricated disagreement)
F. Unsupported claim detection (Evaluator & Reliability Monitor severity classification & corrections)
G. Synthesizer faithfulness (assumptions not converted into facts, conditional recommendations)
H. Debug observability (banners printed when enabled, sensitive tokens/keys redacted)
"""
import os
import pytest
from unittest.mock import patch, MagicMock

from backend.agents.researcher.models import ResearchResult, Source
from backend.agents.researcher.agent import ResearcherAgent
from backend.agents.strategist.models import StrategyResult
from backend.agents.strategist.agent import StrategistAgent
from backend.agents.evaluator.schemas import EvaluatorResult, EvaluatorOutput, UnsupportedClaimItem, ConflictItem
from backend.agents.evaluator.agent import EvaluatorAgent
from backend.agents.conflict_resolver.schemas import Resolution, ConflictResolutionResult
from backend.agents.conflict_resolver.agent import ConflictResolverAgent
from backend.agents.reliability_monitor.schemas import ReliabilityMonitorResult, UnsupportedClaimFinding
from backend.agents.reliability_monitor.agent import ReliabilityMonitorAgent
from backend.agents.synthesizer.schemas import SynthesizerResult, KeyDecision, ResolvedConflict
from backend.agents.synthesizer.agent import SynthesizerAgent
from backend.shared.debug_observability import (
    is_debug_agent_outputs_enabled,
    sanitize_debug_payload,
    format_debug_payload,
    log_debug_agent_output,
    REDACTED,
)


# =====================================================================
# Test A: Missing numeric information (no invented "5-10 hours/week")
# =====================================================================

@pytest.mark.asyncio
async def test_missing_numeric_info_researcher_does_not_invent_hours():
    """When problem does not specify weekly capacity, Researcher must not invent hours."""
    with patch.dict(os.environ, {"CHAI_MOCK_MODE": "true"}):
        agent = ResearcherAgent()
        res = await agent.run(problem="Help me plan my career development and skill building.")
        
        # Check all findings, constraints, assumptions, and open questions
        combined_text = " ".join(res.key_findings + res.constraints + res.assumptions + res.open_questions)
        assert "5-10" not in combined_text
        assert "5–10" not in combined_text
        # Unknown capacity should be represented in open questions, not invented as fact
        assert any("capacity" in q.lower() or "scope" in q.lower() for q in res.open_questions)


@pytest.mark.asyncio
async def test_missing_numeric_info_strategist_adapts_to_unknown_hours():
    """Strategist notes time capacity as dependency/unknown without inventing fixed hours."""
    with patch.dict(os.environ, {"CHAI_MOCK_MODE": "true"}):
        agent = StrategistAgent()
        research = ResearchResult(
            agent="researcher",
            status="completed",
            key_findings=["User seeks data science transition roadmap"],
            open_questions=["User weekly time availability and current math background"],
        )
        strat = await agent.run(
            problem="Plan my learning roadmap for transitioning into data science.",
            research=research,
        )
        
        combined_text = " ".join(strat.priorities + strat.roadmap + strat.dependencies_and_unknowns)
        assert "5-10" not in combined_text
        assert "5–10" not in combined_text
        # Explicitly records that user capacity is an unknown dependency
        assert any("capacity" in d.lower() or "bandwidth" in d.lower() for d in strat.dependencies_and_unknowns)


# =====================================================================
# Test B: Business decision discipline
# =====================================================================

@pytest.mark.asyncio
async def test_business_decision_options_and_conditional_recommendations():
    """Business decision must evaluate options, criteria, and provide conditional recommendations."""
    with patch.dict(os.environ, {"CHAI_MOCK_MODE": "true"}):
        agent = StrategistAgent()
        research = ResearchResult(
            agent="researcher",
            status="completed",
            key_findings=["Boutique has stable existing retail foot traffic"],
            open_questions=["Digital customer acquisition cost and local competitor margins"],
        )
        strat = await agent.run(
            problem="Should our retail boutique expand online, open a second store, or optimize the existing location?",
            research=research,
        )
        
        assert len(strat.options) >= 2
        assert len(strat.decision_criteria) >= 1
        assert len(strat.conditional_triggers) >= 1
        # Recommendation is conditional on capacity / verified demand
        assert any("if" in c.lower() for c in strat.conditional_triggers)


@pytest.mark.asyncio
async def test_business_decision_no_universal_ltv_cac_rule_in_synthesizer():
    """Synthesizer handles business decisions without claiming arbitrary LTV:CAC 3:1 as a universal law."""
    agent = SynthesizerAgent()
    context = {
        "researcher": {"key_findings": ["Retail boutique operating with stable foot traffic"]},
        "strategist": {
            "strategy": "Option A: Optimize store while piloting online sales conditionally",
            "options": ["Option A: In-store optimization", "Option B: Online launch"],
            "conditional_triggers": ["Expand online IF unit economics and CAC are sustainable"],
        },
    }
    with patch.dict(os.environ, {"CHAI_MOCK_MODE": "true"}):
        synth = await agent.run(
            problem="Should our retail boutique expand online, open a second store, or optimize the existing location?",
            context=context,
        )
        # Should not assert a rigid universal "must maintain 3:1 LTV:CAC" as fact
        assert "must maintain 3:1" not in synth.final_answer.lower()
        assert "3:1 ltv:cac is required" not in synth.final_answer.lower()
        # Should evaluate options conditionally
        assert "option a" in synth.final_answer.lower() or "option b" in synth.final_answer.lower()


# =====================================================================
# Test C: Personal life planning (interacting systems)
# =====================================================================

def test_personal_life_planning_no_rigid_sequence_in_prompts():
    """Verify system prompts explicitly require interacting systems rather than rigid sequences."""
    from backend.agents.strategist.prompts import SYSTEM_PROMPT as STRAT_PROMPT
    from backend.agents.synthesizer.prompts import SYSTEM_PROMPT as SYNTH_PROMPT
    
    assert "INTERACTING SYSTEMS" in STRAT_PROMPT
    assert "rigid sequence" in STRAT_PROMPT.lower()
    assert "INTERACTING SYSTEMS" in SYNTH_PROMPT
    assert "non-negotiable prerequisite" in SYNTH_PROMPT.lower()


# =====================================================================
# Test D: Conflicting recommendations
# =====================================================================

@pytest.mark.asyncio
async def test_conflicting_recommendations_explicit_resolution():
    """Conflict Resolver explicitly records position_a, position_b, why_they_differ, resolution, and rationale."""
    with patch.dict(os.environ, {"CHAI_MOCK_MODE": "true"}):
        agent = ConflictResolverAgent()
        context = {
            "evaluator": {
                "conflicts": [
                    {
                        "conflict": "Database selection: Relational vs Document Store",
                        "agents_involved": ["engineer", "strategist"],
                    }
                ]
            },
            "all_outputs": {
                "engineer": {"database": "PostgreSQL"},
                "strategist": {"database": "MongoDB"},
            }
        }
        res = await agent.run(
            problem="Choose database architecture for our medical records service requiring transactions.",
            context=context,
        )
        
        assert len(res.resolutions) >= 1
        r0 = res.resolutions[0]
        assert r0.position_a is not None
        assert r0.position_b is not None
        assert r0.why_they_differ is not None
        assert r0.rationale is not None
        assert "CONFLICT:" in r0.resolution
        assert "POSITION A:" in r0.resolution
        assert "POSITION B:" in r0.resolution
        assert "RESOLUTION:" in r0.resolution


# =====================================================================
# Test E: No conflict detected
# =====================================================================

@pytest.mark.asyncio
async def test_no_conflict_detected_returns_explicit_message():
    """When no conflicts exist, Conflict Resolver explicitly states 'No material conflict detected.'"""
    with patch.dict(os.environ, {"CHAI_MOCK_MODE": "true"}):
        agent = ConflictResolverAgent()
        context = {
            "evaluator": {"conflicts": []},
            "all_outputs": {
                "researcher": {"status": "completed"},
                "engineer": {"status": "completed"},
            }
        }
        res = await agent.run(
            problem="Build a basic contact form.",
            context=context,
        )
        
        assert len(res.resolutions) == 0
        assert "No material conflict detected." in res.decision_basis
        assert res.resolution == "No material conflict detected."


# =====================================================================
# Test F: Unsupported claim detection
# =====================================================================

@pytest.mark.asyncio
async def test_reliability_monitor_flags_unsupported_numbers():
    """Reliability Monitor flags injected unsupported metrics with severity and corrections."""
    with patch.dict(os.environ, {"CHAI_MOCK_MODE": "true"}):
        agent = ReliabilityMonitorAgent()
        context = {
            "final_answer": "You must commit 5-10 discretionary hours each week and achieve 40% cheaper unit economics.",
            "all_outputs": {
                "researcher": {"status": "completed"},
                "engineer": {"status": "completed"},
            }
        }
        res = await agent.run(
            problem="Design a study plan.",
            context=context,
        )
        
        assert len(res.unsupported_claims) >= 1
        claim = res.unsupported_claims[0]
        assert claim.severity in ("low", "medium", "high")
        assert len(res.recommended_corrections) >= 1
        assert any("benchmark" in c.lower() or "remove" in c.lower() for c in res.recommended_corrections)


# =====================================================================
# Test G: Synthesizer faithfulness and uncertainty
# =====================================================================

@pytest.mark.asyncio
async def test_synthesizer_faithfulness_and_no_generic_opening():
    """Synthesizer does not begin with generic meta-commentary and preserves domain depth."""
    with patch.dict(os.environ, {"CHAI_MOCK_MODE": "true"}):
        agent = SynthesizerAgent()
        res = await agent.run(
            problem="Design an offline-first inventory tracker for remote rural warehouses.",
            context={
                "researcher": {"constraints": ["Intermittent connectivity", "Low bandwidth"]},
                "engineer": {"architecture": "Edge SQLite with background queue sync"},
            }
        )
        assert not res.final_answer.startswith("Based on the comprehensive analysis of our specialized agents")
        assert not res.final_answer.startswith("After analyzing the outputs of all agents")
        assert "## " in res.final_answer
        assert len(res.final_answer.split("\n\n")) >= 3


# =====================================================================
# Test H: Debug Observability and Secret Redaction
# =====================================================================

def test_debug_observability_redaction():
    """Sanitizer masks API keys, secrets, passwords, and tokens."""
    payload = {
        "agent": "researcher",
        "api_key": "AIzaSyD-dummy_test_key_1234567890abcdef",
        "token": "secret_bearer_token",
        "db_password": "super_secret_password",
        "details": {
            "auth_header": "Bearer ghp_dummygithubtoken1234567890abcdefghij",
            "nested": "normal string",
        },
        "raw_string_with_key": "Connecting with key AIzaSyD-dummy_test_key_1234567890abcdef safely",
    }
    
    sanitized = sanitize_debug_payload(payload)
    assert sanitized["api_key"] == REDACTED
    assert sanitized["token"] == REDACTED
    assert sanitized["db_password"] == REDACTED
    assert sanitized["details"]["auth_header"] == REDACTED
    assert sanitized["details"]["nested"] == "normal string"
    assert "AIzaSyD" not in sanitized["raw_string_with_key"]
    assert REDACTED in sanitized["raw_string_with_key"]


def test_debug_observability_logging_output(capsys):
    """When enabled, log_debug_agent_output prints formatted banners."""
    with patch.dict(os.environ, {"CHAI_DEBUG_AGENT_OUTPUTS": "true"}):
        assert is_debug_agent_outputs_enabled() is True
        log_debug_agent_output("researcher output", {"finding": "Verified constraint"})
        captured = capsys.readouterr()
        assert "================ RESEARCHER OUTPUT ================" in captured.out
        assert "Verified constraint" in captured.out


def test_debug_observability_silent_when_disabled(capsys):
    """When disabled, log_debug_agent_output emits no terminal output."""
    with patch.dict(os.environ, {"CHAI_DEBUG_AGENT_OUTPUTS": "false"}):
        assert is_debug_agent_outputs_enabled() is False
        log_debug_agent_output("researcher output", {"finding": "Verified constraint"})
        captured = capsys.readouterr()
        assert captured.out == ""
