"""
Tests for Query-Driven, Domain-Adaptive, and User-Intent-Driven Synthesis in CHAI.

Validates:
- ResponsePlan generation (domains, intent, requirements, depth, required & excluded sections).
- The 11 core benchmark regression test cases defined in Section 25:
    TEST 1: "What is Python?" (brief, direct, no report structure)
    TEST 2: "What is the full form of ISRO?" (one-two sentences, no unnecessary headings)
    TEST 3: "Tell me about the song Se Te Nota." (concise, natural English, ambiguity handled naturally, no research report)
    TEST 4: "Design a secure and scalable online learning platform for a university serving 50,000 students..." (deep technical structure)
    TEST 5: "I have a small business with limited capital and three possible directions..." (business strategy structure, no tech architecture)
    TEST 6: "Explain the competing explanations for why some students perform significantly better academically..." (evidence/research structure, causality distinctions, competing explanations, research design)
    TEST 7: "I am in college and I have two very different paths in front of me..." (personal decision framework, trade-offs, risks, opportunity costs, practical steps)
    TEST 8: "I want to improve my life significantly over the next two years..." (prioritization & sustainable life-planning structure)
    TEST 9: "Compare PostgreSQL and MongoDB for a production multi-tenant AI SaaS considering performance, hiring, ecosystem, deployment, cost and long-term maintainability." (deep comparison)
    TEST 10: "Explain binary search." (concise educational explanation)
    TEST 11: "Explain binary search with examples, complexity, edge cases and Python implementation." (detailed educational answer)
- Language quality, grammar, and no internal agent orchestration phrase leakage.
"""
import pytest
from backend.synthesis.response_planner import (
    ResponsePlan,
    plan_response,
    detect_domains,
    detect_intent,
    extract_explicit_requirements,
)
from backend.agents.synthesizer.agent import SynthesizerAgent
from backend.synthesis.response_formatter import format_user_facing_response


# ==============================================================================
# Unit Tests for ResponsePlan and Detection
# ==============================================================================

def test_response_planner_software_engineering_domain():
    query = "Design a secure and scalable online learning platform for a university serving 50,000 students"
    plan = plan_response(query)
    assert plan.domain == "software_engineering"
    assert "cybersecurity" in plan.secondary_domains or "education" in plan.secondary_domains
    assert plan.intent == "architecture_design"
    assert "Executive Summary" in plan.required_sections
    assert any("Architecture" in s for s in plan.required_sections)
    assert any("Security" in s for s in plan.required_sections)


def test_response_planner_business_strategy_domain():
    query = "I have a small business with limited capital and three possible directions: second store, online, or new product"
    plan = plan_response(query)
    assert plan.domain == "business_strategy"
    assert plan.intent == "strategy"
    assert "Situation & Strategic Constraints" in plan.required_sections
    assert "Financial & Capital Risk Analysis" in plan.required_sections
    assert "12-Month Execution Roadmap" in plan.required_sections
    # Must exclude technical software architecture sections
    assert any("Technical Architecture" in s for s in plan.excluded_sections)
    assert any("API Design" in s for s in plan.excluded_sections)
    assert any("Database Schema" in s for s in plan.excluded_sections)


def test_response_planner_science_evidence_domain():
    query = "Explain the competing explanations for why some students perform significantly better academically, including causal interpretations and research design"
    plan = plan_response(query)
    assert plan.domain == "science"
    assert plan.intent == "evidence_analysis"
    assert "Core Question & Hypotheses" in plan.required_sections
    assert "Competing Explanations" in plan.required_sections
    assert "Causal Interpretation vs. Association" in plan.required_sections
    assert "Rigorous Research Design & Testing Framework" in plan.required_sections
    assert any("Technical Architecture" in s for s in plan.excluded_sections)


def test_response_planner_personal_decision_domain():
    query = "I am in college and I have two very different paths in front of me: stable job or start a business"
    plan = plan_response(query)
    assert plan.domain in ("personal_decision", "career")
    assert plan.intent == "decision_support"
    assert "Situation & Context" in plan.required_sections
    assert "Comparative Trade-offs & Opportunity Costs" in plan.required_sections
    assert "Downside Protection & Risk Reduction" in plan.required_sections
    assert any("Technical Architecture" in s for s in plan.excluded_sections)


def test_response_planner_life_planning_domain():
    query = "I want to improve my life significantly over the next two years with sustainable habits and energy management"
    plan = plan_response(query)
    assert plan.domain == "planning"
    assert plan.intent == "prioritization"
    assert "Current Situation & Core Priorities" in plan.required_sections
    assert "Sustainable Operating Framework" in plan.required_sections
    assert "First 30 Days Action Plan" in plan.required_sections
    assert any("Technical Architecture" in s for s in plan.excluded_sections)


def test_response_planner_explicit_requirements_extraction():
    query = "Compare PostgreSQL and MongoDB for a production multi-tenant AI SaaS considering performance, hiring, ecosystem, deployment, cost and long-term maintainability."
    reqs = extract_explicit_requirements(query)
    assert "Performance & Throughput" in reqs
    assert "Hiring & Talent Availability" in reqs
    assert "Ecosystem & Tooling Maturity" in reqs
    assert "Deployment & Operations" in reqs
    assert "Cost & Total Cost of Ownership" in reqs
    assert "Long-Term Maintainability" in reqs


# ==============================================================================
# The 11 Benchmark Test Cases from Section 25
# ==============================================================================

@pytest.mark.asyncio
async def test_case_1_what_is_python(monkeypatch):
    """TEST 1: 'What is Python?' -> brief, direct, no report structure."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    agent = SynthesizerAgent()
    query = "What is Python?"
    res = await agent.run(query)

    assert "python" in res.final_answer.lower()
    assert "programming language" in res.final_answer.lower()
    # No report structure or headings
    assert "## Executive Summary" not in res.final_answer
    assert "## Technical Architecture" not in res.final_answer
    assert len(res.final_answer.splitlines()) < 5

    formatted = format_user_facing_response(query, res.final_answer, route="simple", requested_depth="brief")
    assert "#" not in formatted
    assert "Based on the comprehensive analysis" not in formatted


@pytest.mark.asyncio
async def test_case_2_isro_full_form(monkeypatch):
    """TEST 2: 'What is the full form of ISRO?' -> one or two sentences, no unnecessary headings."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    agent = SynthesizerAgent()
    query = "What is the full form of ISRO?"
    res = await agent.run(query)

    assert "Indian Space Research Organisation" in res.final_answer
    assert "##" not in res.final_answer
    assert len(res.final_answer.splitlines()) <= 3

    formatted = format_user_facing_response(query, res.final_answer, route="simple", requested_depth="brief")
    assert "Indian Space Research Organisation" in formatted
    assert "#" not in formatted


@pytest.mark.asyncio
async def test_case_3_se_te_nota_song(monkeypatch):
    """TEST 3: 'Tell me about the song Se Te Nota.' -> concise, natural English, ambiguity handled naturally, no research report."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    agent = SynthesizerAgent()
    query = "Tell me about the song Se Te Nota."
    res = await agent.run(query)

    assert "Se Te Nota" in res.final_answer
    assert "Lele Pons" in res.final_answer or "Guaynaa" in res.final_answer
    # Must NOT produce an exhaustive multi-candidate report
    assert "## Executive Summary" not in res.final_answer
    assert "## Technical Architecture" not in res.final_answer

    formatted = format_user_facing_response(query, res.final_answer, route="complex", requested_depth="normal")
    assert "Se Te Nota" in formatted
    assert "## Executive Summary" not in formatted


@pytest.mark.asyncio
async def test_case_4_university_platform_50000_students(monkeypatch):
    """TEST 4: 'Design a secure and scalable online learning platform for a university serving 50,000 students...' -> deep technical structure."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    agent = SynthesizerAgent()
    query = "Design a secure and scalable online learning platform for a university serving 50,000 students with privacy, high availability, and failure resilience."
    res = await agent.run(query)

    # Must contain full technical engineering sections
    assert "## Executive Summary" in res.final_answer
    assert "## Recommended Solution & Strategy" in res.final_answer
    assert "## Technical Architecture & System Design" in res.final_answer
    assert "## Security, Privacy & Safety Guardrails" in res.final_answer
    assert "## Trade-offs & Reconciled Decisions" in res.final_answer
    assert "## Risks & Mitigations" in res.final_answer
    assert "## Implementation Roadmap" in res.final_answer
    assert len(res.final_answer.splitlines()) > 20


@pytest.mark.asyncio
async def test_case_5_small_business_capital_directions(monkeypatch):
    """TEST 5: 'I have a small business with limited capital and three possible directions...' -> business strategy structure, no tech architecture."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    agent = SynthesizerAgent()
    query = "I have a small business with limited capital and three possible directions: expand my physical store, launch an online store, or develop a new product line."
    res = await agent.run(query)

    # Must contain business strategy structure
    assert "## Executive Summary" in res.final_answer
    assert "## Situation & Strategic Constraints" in res.final_answer
    assert "## Evaluation of the Three Strategic Options" in res.final_answer
    assert "## Financial & Capital Risk Analysis" in res.final_answer
    assert "## Key Trade-offs & Opportunity Costs" in res.final_answer
    assert "## Critical Information Needed Before Deciding" in res.final_answer
    assert "## Strategic Recommendation & Rationale" in res.final_answer
    assert "## 12-Month Execution Roadmap" in res.final_answer
    assert "## Key Milestones & Decision Gates" in res.final_answer

    # Must strictly NOT contain technical software architecture sections
    assert "## Technical Architecture & System Design" not in res.final_answer
    assert "## Core Architecture Components" not in res.final_answer
    assert "API Design" not in res.final_answer
    assert "Database Schema" not in res.final_answer
    assert "Microservices Architecture" not in res.final_answer
    assert "Cybersecurity Defense Posture" not in res.final_answer

    # User-facing format verification
    formatted = format_user_facing_response(query, res.final_answer, route="complex", domain="business_strategy", requested_depth="deep")
    assert "## Evaluation of the Three Strategic Options" in formatted
    assert "## Technical Architecture" not in formatted


@pytest.mark.asyncio
async def test_case_6_academic_performance_evidence_analysis(monkeypatch):
    """TEST 6: 'Explain the competing explanations for why some students perform significantly better academically...' -> evidence/research structure, causality distinctions, competing explanations, research design."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    agent = SynthesizerAgent()
    query = "Explain the competing explanations for why some students perform significantly better academically, including study habits, motivation, sleep, and socioeconomic background."
    res = await agent.run(query)

    # Must contain research/evidence structure
    assert "## Core Question & Competing Hypotheses" in res.final_answer
    assert "## Competing Explanations" in res.final_answer
    assert "## Empirical Evidence Analysis" in res.final_answer
    assert "## Confounding Factors & Interaction Effects" in res.final_answer
    assert "## Contradictions & Methodological Limitations" in res.final_answer
    assert "## Causal Interpretation vs. Association" in res.final_answer
    assert "## Rigorous Research Design & Testing Framework" in res.final_answer
    assert "## Synthesis & Evidence-Grounded Conclusion" in res.final_answer

    # Must explicitly differentiate causality from correlation
    assert "association" in res.final_answer.lower()
    assert "causal" in res.final_answer.lower()

    # Must NOT have software architecture or IT security sections
    assert "## Technical Architecture" not in res.final_answer
    assert "## Security, Privacy & Safety Guardrails" not in res.final_answer
    assert "API Design" not in res.final_answer


@pytest.mark.asyncio
async def test_case_7_college_two_paths_career(monkeypatch):
    """TEST 7: 'I am in college and I have two very different paths in front of me...' -> personal decision framework, trade-offs, risks, opportunity costs, practical steps."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    agent = SynthesizerAgent()
    query = "I am in college and I have two very different paths in front of me: take a stable corporate job or pursue full-time entrepreneurship."
    res = await agent.run(query)

    # Must contain personal decision structure
    assert "## Situation & Context" in res.final_answer
    assert "## Core Priorities (What Matters Most)" in res.final_answer
    assert "## Path 1 Assessment: Stable Employment" in res.final_answer
    assert "## Path 2 Assessment: Entrepreneurship" in res.final_answer
    assert "## Comparative Trade-offs & Opportunity Costs" in res.final_answer
    assert "## Downside Protection & Risk Reduction" in res.final_answer
    assert "## Decision Framework & Conditional Recommendation" in res.final_answer
    assert "## Practical Next Steps" in res.final_answer

    # Must NOT contain software engineering architecture
    assert "## Technical Architecture" not in res.final_answer
    assert "Database" not in res.final_answer
    assert "API Endpoints" not in res.final_answer


@pytest.mark.asyncio
async def test_case_8_improve_life_two_years(monkeypatch):
    """TEST 8: 'I want to improve my life significantly over the next two years...' -> prioritization and sustainable life-planning structure."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    agent = SynthesizerAgent()
    query = "I want to improve my life significantly over the next two years. What should I prioritize, what should I avoid, and how do I build a sustainable operating system?"
    res = await agent.run(query)

    # Must contain life planning structure
    assert "## Current Situation & Core Priorities" in res.final_answer
    assert "## What to Focus on First vs. What to Deprioritize" in res.final_answer
    assert "## Priority Interactions & Real-World Trade-offs" in res.final_answer
    assert "## Sustainable Operating Framework" in res.final_answer
    assert "## First 30 Days Action Plan" in res.final_answer
    assert "## 3-Month & 6-Month Execution Milestones" in res.final_answer
    assert "## 12-Month & 2-Year Direction" in res.final_answer
    assert "## Habit, Energy & Capacity Management" in res.final_answer
    assert "## Review & Course-Correction Rules" in res.final_answer

    # Must NOT contain software technical architecture
    assert "## Technical Architecture" not in res.final_answer
    assert "Cybersecurity Defense Posture" not in res.final_answer
    assert "Database Schema" not in res.final_answer


@pytest.mark.asyncio
async def test_case_9_postgresql_vs_mongodb_comparison(monkeypatch):
    """TEST 9: 'Compare PostgreSQL and MongoDB for a production multi-tenant AI SaaS considering performance, hiring, ecosystem, deployment, cost and long-term maintainability.' -> deep comparison."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    agent = SynthesizerAgent()
    query = (
        "Compare PostgreSQL and MongoDB for a production multi-tenant AI SaaS considering "
        "performance, hiring, ecosystem, deployment, cost and long-term maintainability."
    )
    res = await agent.run(query)

    assert "## Executive Summary" in res.final_answer
    assert "## Architectural Paradigm Comparison" in res.final_answer
    assert "## Multi-Tenancy & Data Isolation" in res.final_answer
    assert "## Performance, Scaling & Vector Workloads" in res.final_answer
    assert "## Ecosystem, Tooling & Talent Availability" in res.final_answer
    assert "## Deployment, Operational Complexity & Cost" in res.final_answer
    assert "## Key Trade-offs & Contradictions" in res.final_answer
    assert "## Long-Term Maintainability & Synthesis Recommendation" in res.final_answer
    assert "pgvector" in res.final_answer or "Atlas Vector" in res.final_answer
    assert "Row-Level Security" in res.final_answer or "RLS" in res.final_answer


@pytest.mark.asyncio
async def test_case_10_explain_binary_search_concise(monkeypatch):
    """TEST 10: 'Explain binary search.' -> concise educational explanation."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    agent = SynthesizerAgent()
    query = "Explain binary search."
    res = await agent.run(query)

    assert "binary search" in res.final_answer.lower()
    assert "sorted" in res.final_answer.lower()
    assert "o(log n)" in res.final_answer.lower()
    # Concise: should not produce a 15-section enterprise architecture
    assert "## Technical Architecture" not in res.final_answer
    assert "## Security" not in res.final_answer
    assert len(res.final_answer.splitlines()) < 8


@pytest.mark.asyncio
async def test_case_11_explain_binary_search_deep_with_code(monkeypatch):
    """TEST 11: 'Explain binary search with examples, complexity, edge cases and Python implementation.' -> detailed educational answer."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    agent = SynthesizerAgent()
    query = "Explain binary search with examples, complexity, edge cases and Python implementation."
    res = await agent.run(query)

    assert "## Algorithm Concept & Core Intuition" in res.final_answer
    assert "## Step-by-Step Walkthrough with Example" in res.final_answer
    assert "## Python Implementation" in res.final_answer
    assert "```python" in res.final_answer
    assert "def binary_search" in res.final_answer
    assert "## Complexity Analysis (Time & Space)" in res.final_answer
    assert "## Edge Cases & Common Pitfalls" in res.final_answer
    assert "## Summary & Best Practices" in res.final_answer

    # Must NOT have corporate IT architecture
    assert "## Cybersecurity Defense Posture" not in res.final_answer
    assert "## Business Strategy" not in res.final_answer


def test_user_facing_response_never_exposes_internal_agents():
    """Verify that forbidden internal agent phrases are completely eliminated from user-facing responses."""
    bad_text = (
        "Based on the comprehensive analysis of our specialized agents:\n\n"
        "Our Researcher agent found that PostgreSQL is robust.\n"
        "The Strategist recommends starting with a monolith.\n"
        "The Guardian determined that data isolation is critical.\n"
        "The Evaluator diagnosed a coverage gap.\n"
        "The Security agent noted that encryption is mandatory.\n"
        "The Engineer proposed using FastAPI.\n"
        "The Conflict Resolver determined to use batch sync.\n"
        "Agent consensus indicates agreement."
    )
    cleaned = format_user_facing_response("Design system", bad_text, route="complex")
    assert "specialized agents" not in cleaned.lower()
    assert "researcher agent" not in cleaned.lower()
    assert "the strategist recommends" not in cleaned.lower()
    assert "the guardian determined" not in cleaned.lower()
    assert "the evaluator diagnosed" not in cleaned.lower()
    assert "the security agent noted" not in cleaned.lower()
    assert "the engineer proposed" not in cleaned.lower()
    assert "the conflict resolver determined" not in cleaned.lower()
    assert "agent consensus" not in cleaned.lower()
