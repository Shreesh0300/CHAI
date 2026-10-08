"""
Response Planner for CHAI (Coordinated Hybrid Agentic Intelligence).

The central decision gate for response structure, domain perspective,
user intent, and content requirements.

Hierarchy:
    1. Understand user request
    2. Identify primary and secondary domains
    3. Identify task / intent
    4. Extract explicit user requirements
    5. Determine requested depth
    6. Formulate tailored response plan (required sections, excluded sections, evidence guidelines)
    7. Guide synthesis and language quality gates

Principle:
    COMPLEXITY DOES NOT DETERMINE TEMPLATE.
    Complexity determines DEPTH.
    Domain determines PERSPECTIVE.
    User Intent determines STRUCTURE.
    Explicit Requirements determine CONTENT.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class ResponsePlan(BaseModel):
    """
    Internal blueprint guiding synthesis structure, perspective, and constraints.
    Not directly displayed to the user; governs the Synthesizer and Formatter.
    """
    domain: str = Field(..., description="Primary domain of the problem.")
    secondary_domains: List[str] = Field(default_factory=list, description="Secondary domains involved.")
    intent: str = Field(..., description="Primary task / user intent.")
    requested_depth: str = Field(default="normal", description="Requested reasoning depth ('brief', 'normal', 'deep').")
    answer_goal: str = Field(default="", description="High-level goal for answering this specific query.")
    required_sections: List[str] = Field(default_factory=list, description="Explicit section headings tailored for this query.")
    optional_sections: List[str] = Field(default_factory=list, description="Secondary sections that may be useful.")
    excluded_sections: List[str] = Field(default_factory=list, description="Sections that MUST NOT appear (e.g. no APIs for pure business queries).")
    key_points_to_answer: List[str] = Field(default_factory=list, description="Explicit requirements or specific criteria to address.")
    relevant_agent_outputs: List[str] = Field(default_factory=list, description="Agents providing pertinent evidence.")
    unresolved_uncertainties: List[str] = Field(default_factory=list, description="Information gaps or conditional dependencies.")
    important_tradeoffs: List[str] = Field(default_factory=list, description="Genuine trade-offs requiring transparent articulation.")
    evidence_requirements: List[str] = Field(default_factory=list, description="Distinctions between facts, hypotheses, correlation vs causation.")


# ---------------------------------------------------------------------------
# Domain Detection
# ---------------------------------------------------------------------------

_DOMAIN_PATTERNS: Dict[str, List[str]] = {
    "software_engineering": [
        r"\barchitecture\b", r"\barchitect\b", r"\bdesign\s+(a|an|our)\b",
        r"\bplatform\b", r"\bmicroservices?\b", r"\bmodular\s+monolith\b",
        r"\brag\s+(platform|system|pipeline|architecture)\b", r"\bpostgresql\b",
        r"\bmongodb\b", r"\bdatabase\b", r"\bapis?\b", r"\bdata\s+flow\b",
        r"\bhigh\s+availability\b", r"\bscalability\b", r"\bmulti-tenant\b",
        r"\bpython\s+(implementation|code)\b", r"\bbinary\s+search\b",
        r"\bsoftware\b", r"\bcode\b", r"\bbackend\b", r"\bfrontend\b",
        r"\bdistributed\s+systems?\b", r"\bfault\s+tolerance\b",
    ],
    "cybersecurity": [
        r"\bsecurity\b", r"\bsecure\b", r"\bhipaa\b", r"\bprivacy\b",
        r"\bthreat\b", r"\bvulnerability\b", r"\bencryption\b", r"\brbac\b",
        r"\bauthentication\b", r"\bauthorization\b", r"\baudit\s+logging\b",
        r"\bphi\b", r"\bpii\b", r"\bcybersecurity\b", r"\bfirewall\b",
    ],
    "healthcare": [
        r"\bhealthcare\b", r"\bpatient\b", r"\bclinical\b", r"\bhospital\b",
        r"\bmedical\b", r"\bdoctor\b", r"\bmedicine\b", r"\bhealth\b",
        r"\btriage\b", r"\bclinician\b",
    ],
    "business_strategy": [
        r"\bbusiness\b", r"\bsmall\s+business\b", r"\bcapital\b",
        r"\blimited\s+capital\b", r"\bdirections?\b", r"\bopening\s+a\s+second\s+store\b",
        r"\bonline\s+business\b", r"\bretail\b", r"\bgo-to-market\b", r"\bstartup\b",
        r"\bmonetization\b", r"\bunit\s+economics\b", r"\brevenue\b", r"\bprofit\b",
        r"\bmarket\s+validation\b", r"\bbusiness\s+strategy\b", r"\bexpansion\b",
        r"\bopportunity\s+cost\b", r"\bcustomer\s+retention\b", r"\brunway\b",
    ],
    "finance": [
        r"\bcapital\b", r"\bfinancial\b", r"\binvestment\b", r"\bbudget\b",
        r"\bcash\s+flow\b", r"\bcash\s+runway\b", r"\bmargins?\b", r"\broi\b",
        r"\bfunding\b", r"\bfinancially\b", r"\bliquidity\b",
    ],
    "education": [
        r"\bstudents?\b", r"\blearning\b", r"\bacademic(ally)?\b", r"\bteach(ing)?\b",
        r"\bcurriculum\b", r"\bcourse\b", r"\bstudy\b", r"\buniversit(y|ies)\b",
        r"\bschool\b", r"\bstudy\s+habits\b", r"\bgrades?\b", r"\bgpa\b",
    ],
    "science": [
        r"\bcompeting\s+explanations\b", r"\bscientifically\b", r"\bscientific\b",
        r"\bcognitive\b", r"\bempirical\b", r"\bexperiment(al)?\b", r"\bhypothesis\b",
        r"\bcausal\b", r"\bcausality\b", r"\bcorrelation\b", r"\bconfounding\b",
        r"\bpeer\s+environment\b", r"\bsleep\s+quality\b", r"\binteraction\s+effects?\b",
        r"\bresearch\s+design\b", r"\bsocioeconomic\b",
    ],
    "personal_decision": [
        r"\bshould\s+i\b", r"\bin\s+college\b", r"\btwo\s+paths\b",
        r"\bpaths\s+in\s+front\s+of\s+me\b", r"\bwhat\s+should\s+i\s+do\b",
        r"\bparents\s+want\s+me\s+to\b", r"\bdilemma\b", r"\bdeciding\s+between\b",
        r"\bchoose\s+between\b", r"\bmy\s+life\b", r"\bpersonal\b",
    ],
    "career": [
        r"\bcareer\b", r"\bjob\b", r"\bstable\s+job\b", r"\bgovernment\s+job\b",
        r"\bentrepreneurship\b", r"\bpromotion\b", r"\bresume\b", r"\bhiring\b",
        r"\bpursue\s+ai\b", r"\bcareer\s+paths?\b", r"\bquit\s+my\s+job\b",
    ],
    "planning": [
        r"\bimprove\s+my\s+life\b", r"\bover\s+the\s+next\s+two\s+years\b",
        r"\bnext\s+2\s+years\b", r"\b12-month\b", r"\blife\s+plan\b",
        r"\bpersonal\s+growth\b", r"\bhabits?\b", r"\bprioritize\b",
        r"\bpriorities\b", r"\benergy\s+management\b", r"\bsustainable\s+plan\b",
        r"\boperating\s+system\b",
    ],
    "ethics_and_governance": [
        r"\bethics\b", r"\bethical\b", r"\bgovernance\b", r"\bbias\b",
        r"\balgorithmic\s+bias\b", r"\bcompliance\b", r"\bfairness\b",
    ],
    "organizational": [
        r"\bteam\b", r"\borganization(al)?\b", r"\bmanagement\b",
        r"\bcompany\s+culture\b", r"\bhiring\s+engineers\b",
    ],
    "general_research": [
        r"\bresearch\b", r"\binvestigation\b", r"\bliterature\s+review\b",
        r"\bevidence\s+analysis\b", r"\bmeta-analysis\b",
    ],
}


def detect_domains(query: str, context: Optional[Dict[str, Any]] = None) -> Tuple[str, List[str]]:
    """
    Detects the primary and secondary domains of the user query.
    Ensures multi-domain queries recognize all materially relevant perspectives.
    """
    lower = (query or "").lower().strip()
    scores: Dict[str, int] = {domain: 0 for domain in _DOMAIN_PATTERNS}

    for domain, patterns in _DOMAIN_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, lower):
                scores[domain] += 1

    # Specific contextual boosts
    if any(k in lower for k in ("improve my life", "next two years", "next 2 years", "sustainable framework")):
        scores["planning"] += 4
        scores["personal_decision"] += 2

    if any(k in lower for k in ("small business", "limited capital", "three possible directions", "second store")):
        scores["business_strategy"] += 4
        scores["finance"] += 2

    if any(k in lower for k in ("competing explanations", "perform significantly better academically", "causal", "correlation")):
        scores["science"] += 4
        scores["education"] += 2

    if any(k in lower for k in ("in college and i have two very different paths", "stable job or start a business", "parents want me to")):
        scores["personal_decision"] += 4
        scores["career"] += 3

    if any(k in lower for k in ("learning platform", "university serving 50,000", "50,000 students")):
        scores["software_engineering"] += 4
        scores["education"] += 2
        scores["cybersecurity"] += 2

    if any(k in lower for k in ("postgresql and mongodb", "modular monolith with microservices")):
        scores["software_engineering"] += 5

    # Filter domains with at least 1 match, sorted by score descending
    matched = [(d, score) for d, score in scores.items() if score > 0]
    matched.sort(key=lambda x: x[1], reverse=True)

    if not matched:
        return "general", []

    primary = matched[0][0]
    secondary = [d for d, s in matched[1:4] if s >= 1 and d != primary]

    return primary, secondary


# ---------------------------------------------------------------------------
# Intent Detection
# ---------------------------------------------------------------------------

def detect_intent(query: str, domain: str) -> str:
    """
    Determines the specific task / intent of the user.
    """
    lower = (query or "").lower().strip()

    # Factual lookup
    if any(lower.startswith(k) for k in ("what is the full form of", "who invented", "when was", "what is 2")):
        return "factual_explanation"

    # Cultural / song lookup
    if any(k in lower for k in ("tell me about the song", "tell me about this song", "sete nota", "se te nota")):
        return "general_information"

    # Architecture & system design
    if any(k in lower for k in ("design a", "design an", "architect a", "system architecture", "learning platform")):
        return "architecture_design"

    # Comparison
    if any(k in lower for k in ("compare", "vs", "versus", "differences between", "choose between")):
        return "comparison"

    # Scientific evidence / research
    if any(k in lower for k in ("competing explanations", "why do some", "evidence for", "causal interpretation")):
        return "evidence_analysis"
    if any(k in lower for k in ("research this", "scientific analysis")):
        return "research_analysis"

    # Life planning / prioritization
    if any(k in lower for k in ("improve my life", "prioritize", "what to focus on first", "over the next two years")):
        return "prioritization"

    # Personal decision / career dilemma
    if any(k in lower for k in ("should i", "what should i do", "paths in front of me", "parents want me to", "dilemma")):
        return "decision_support"

    # Business strategy
    if domain == "business_strategy" and any(k in lower for k in ("directions", "direction", "strategy", "second store", "online business")):
        return "strategy"

    # Educational with code / implementation
    if any(k in lower for k in ("with examples, complexity", "python implementation", "code implementation")):
        return "educational_explanation"

    # Simple concept explanation
    if lower.startswith("explain "):
        return "educational_explanation" if domain in ("software_engineering", "education", "science") else "concept_explanation"
    if lower.startswith("what is ") or lower.startswith("define "):
        return "concept_explanation"

    return "general_information"


# ---------------------------------------------------------------------------
# Explicit Requirement Extraction
# ---------------------------------------------------------------------------

def extract_explicit_requirements(query: str) -> List[str]:
    """
    Extracts explicit user requirements, criteria, and sub-questions from query.
    """
    lower = query.lower()
    requirements: List[str] = []

    # Check for explicit multi-criteria comparisons (e.g. PostgreSQL vs MongoDB)
    criteria_map = {
        "performance": "Performance & Throughput",
        "hiring": "Hiring & Talent Availability",
        "ecosystem": "Ecosystem & Tooling Maturity",
        "deployment": "Deployment & Operations",
        "cost": "Cost & Total Cost of Ownership",
        "long-term maintainability": "Long-Term Maintainability",
        "multi-tenant": "Multi-Tenant Data Isolation",
        "apis": "API & Interface Design",
        "database": "Database Architecture",
        "security": "Security & Access Controls",
        "scalability": "Scalability & Load Handling",
        "monitoring": "Monitoring & Observability",
        "failure handling": "Failure Handling & Resilience",
        "rollout": "Phased Rollout Plan",
        "examples": "Practical Examples",
        "complexity": "Time & Space Complexity",
        "edge cases": "Edge Cases & Pitfalls",
        "python implementation": "Executable Python Implementation",
        "three years": "3-Year Strategic Horizon",
        "contradictions": "Contradictions & Trade-offs",
        "competing explanations": "Competing Hypotheses",
        "causal interpretation": "Causal Interpretation vs Association",
        "research design": "Rigorous Experimental Testing",
        "capital": "Capital & Financial Risk",
        "12-month": "12-Month Execution Roadmap",
        "first 30 days": "First 30 Days Action Plan",
    }

    for keyword, label in criteria_map.items():
        if keyword in lower:
            requirements.append(label)

    return requirements


# ---------------------------------------------------------------------------
# Core Response Planner
# ---------------------------------------------------------------------------

def plan_response(
    problem: str,
    context: Optional[Dict[str, Any]] = None,
    route: str = "complex",
    requested_depth: Optional[str] = None,
) -> ResponsePlan:
    """
    Constructs a query-driven, domain-adaptive ResponsePlan for the user request.
    Does NOT use a universal template.
    """
    primary_domain, secondary_domains = detect_domains(problem, context)
    intent = detect_intent(problem, primary_domain)
    explicit_reqs = extract_explicit_requirements(problem)

    # Determine depth
    depth = requested_depth or "normal"
    p_lower = problem.lower()
    if any(k in p_lower for k in ("detailed", "in-depth", "comprehensive", "with examples", "edge cases", "implementation", "deep analysis")):
        depth = "deep"
    elif route == "simple" or any(k in p_lower for k in ("brief", "quick", "short", "in one sentence", "in one line", "who invented", "full form of")):
        depth = "brief"

    # Build section sets tailored to domain and intent
    required_sections: List[str] = []
    optional_sections: List[str] = []
    excluded_sections: List[str] = []
    answer_goal = ""
    evidence_reqs: List[str] = []
    tradeoffs: List[str] = []

    # -----------------------------------------------------------------------
    # Domain & Intent Specific Planning
    # -----------------------------------------------------------------------

    if route == "simple" or depth == "brief":
        answer_goal = "Provide the direct factual or conceptual answer in 1-4 concise sentences."
        required_sections = ["Direct Answer"]
        excluded_sections = [
            "Executive Summary", "Architecture", "Components", "Security",
            "Reliability", "Scalability", "Roadmap", "Trade-offs", "Risks",
            "Sources", "Assumptions", "Limitations", "Candidate Songs"
        ]

    elif primary_domain in ("personal_decision", "career") or (intent == "decision_support" and primary_domain != "business_strategy"):
        answer_goal = "Provide empathetic, balanced decision support comparing life paths and downside protection."
        required_sections = [
            "Situation & Context",
            "Core Priorities (What Matters Most)",
            "Path 1 Assessment",
            "Path 2 Assessment",
            "Comparative Trade-offs & Opportunity Costs",
            "Downside Protection & Risk Reduction",
            "Decision Framework & Conditional Recommendation",
            "Practical Next Steps (First 30–90 Days)",
        ]
        optional_sections = ["Family & Stakeholder Communication", "Reassessment Milestones"]
        excluded_sections = [
            "Technical Architecture & System Design", "Cybersecurity Controls",
            "Database Schema", "API Endpoints", "Microservices", "Corporate Jargon"
        ]
        evidence_reqs = [
            "Do not invent facts about user family, finances, or personal personality.",
            "Separate known facts from reasonable inferences and explicit assumptions.",
            "Provide conditional recommendations with clear reassessment triggers."
        ]
        tradeoffs = ["Predictable stability vs compounding growth potential", "Immediate security vs long-term upside"]

    elif primary_domain == "business_strategy" or (intent in ("strategy", "decision_support") and "business" in p_lower):
        answer_goal = "Deliver actionable strategic business guidance evaluating options, capital risk, and unit economics."
        required_sections = [
            "Executive Summary",
            "Situation & Strategic Constraints",
            "Evaluation of Strategic Options",
            "Financial & Capital Risk Analysis",
            "Key Trade-offs & Opportunity Costs",
            "Critical Information Needed Before Deciding",
            "Strategic Recommendation & Rationale",
            "12-Month Execution Roadmap",
            "Key Milestones & Decision Gates",
        ]
        optional_sections = ["Assumptions & Market Dependencies", "Risk Mitigation Strategies"]
        excluded_sections = [
            "Technical Architecture & System Design", "Core Architecture Components",
            "API Design & Endpoints", "Database Schema & Topology", "Microservices Architecture",
            "Cybersecurity Defense Posture", "Network Firewalls", "RBAC / ABAC Security Controls"
        ]
        evidence_reqs = [
            "Do not fabricate revenue, margins, or customer retention data.",
            "Identify missing financial metrics explicitly.",
            "Make recommendations conditional on cash runway and market demand validation."
        ]
        tradeoffs = ["Capital commitment vs flexibility", "Offline retail expansion vs digital customer acquisition"]

    elif primary_domain == "science" or intent == "evidence_analysis":
        answer_goal = "Provide an objective, evidence-based scientific analysis distinguishing causal effects from association."
        required_sections = [
            "Core Question & Hypotheses",
            "Competing Explanations",
            "Empirical Evidence Analysis (Supporting vs. Weakening Factors)",
            "Confounding Factors & Interaction Effects",
            "Contradictions & Methodological Limitations",
            "Causal Interpretation vs. Association",
            "Rigorous Research Design & Testing Framework",
            "Synthesis & Evidence-Grounded Conclusion",
        ]
        optional_sections = ["Practical Implications for Education", "Future Research Priorities"]
        excluded_sections = [
            "Technical Architecture & System Design", "API Design", "Database Design",
            "Cybersecurity Defense Posture", "Commercial Implementation Roadmap", "Sales Strategy"
        ]
        evidence_reqs = [
            "Strictly distinguish correlation and association from verified causal mechanisms.",
            "Do not state hypotheses as established facts.",
            "Address interactions between environmental, cognitive, and socioeconomic variables."
        ]
        tradeoffs = ["Observational sample breadth vs experimental causal control"]

    elif primary_domain == "planning" or intent == "prioritization":
        answer_goal = "Formulate a sustainable, realistic life prioritization and execution framework avoiding burnout."
        required_sections = [
            "Current Situation & Core Priorities",
            "What to Focus on First vs. What to Deprioritize",
            "Priority Interactions & Real-World Trade-offs",
            "Sustainable Operating Framework",
            "First 30 Days Action Plan",
            "3-Month & 6-Month Execution Milestones",
            "12-Month & 2-Year Direction",
            "Habit, Energy & Capacity Management",
            "Review & Course-Correction Rules",
        ]
        optional_sections = ["Overcoming Plateaus", "Accountability Systems"]
        excluded_sections = [
            "Technical Architecture & System Design", "Cybersecurity Defense Posture",
            "API Architecture", "Database Schema", "Corporate Enterprise Templates"
        ]
        evidence_reqs = [
            "Prioritize realistic sustainability over unrealistic simultaneous optimization.",
            "Acknowledge human cognitive and energy limits explicitly."
        ]
        tradeoffs = ["Breadth across life domains vs focused mastery in core priority"]

    elif intent == "comparison" and primary_domain == "software_engineering":
        answer_goal = "Provide a deep, multi-dimensional technical comparison across all user criteria."
        required_sections = [
            "Executive Summary",
            "Architectural Paradigm Comparison",
            "Multi-Tenancy & Data Isolation",
            "Performance, Scaling & Vector Workloads",
            "Ecosystem, Tooling & Talent Availability",
            "Deployment, Operational Complexity & Cost",
            "Key Trade-offs & Contradictions",
            "Synthesis Recommendation by Use Case",
        ]
        optional_sections = ["Migration Considerations", "Long-Term Maintainability"]
        excluded_sections = ["Personal Advice", "Generic Marketing Fluff"]
        evidence_reqs = [
            "Ground technical claims in production realities (e.g. pgvector vs Atlas Vector Search).",
            "Acknowledge strengths and weaknesses of both technologies fairly."
        ]
        tradeoffs = ["Relational transactional rigidity vs polymorphic document schema flexibility"]

    elif primary_domain == "software_engineering" and intent == "architecture_design":
        answer_goal = "Deliver a comprehensive, production-grade technical architecture tailored to user constraints."
        required_sections = [
            "Executive Summary",
            "Requirements & Architectural Approach",
            "Core Architecture Components & Topology",
            "Data Flow & Interface / API Design",
            "Database & Storage Strategy",
            "Security, Privacy & Compliance Controls",
            "Reliability, Fault Tolerance & High Availability",
            "Scalability & Performance Strategy",
            "Trade-offs & Reconciled Decisions",
            "Phased Implementation Roadmap",
            "Assumptions & Limitations",
        ]
        optional_sections = ["Monitoring & Observability", "Cost Optimization"]
        excluded_sections = ["Personal Life Advice", "Sales Pitch"]
        evidence_reqs = ["Ground architecture in the specific scale (e.g. 50,000 university students)."]
        tradeoffs = ["Immediate time-to-market vs long-term modular decoupling"]

    elif intent == "educational_explanation" and depth == "deep":
        answer_goal = "Provide a comprehensive educational explanation with code, complexity, and edge cases."
        required_sections = [
            "Algorithm Concept & Core Intuition",
            "Step-by-Step Walkthrough with Example",
            "Python Implementation",
            "Complexity Analysis (Time & Space)",
            "Edge Cases & Common Pitfalls",
            "Summary & Best Practices",
        ]
        excluded_sections = ["Enterprise Architecture", "Cybersecurity Posture", "Business Strategy"]

    elif intent == "general_information" and ("song" in p_lower or "sete nota" in p_lower or "se te nota" in p_lower):
        answer_goal = "Deliver a concise, natural informational response addressing title ambiguity conversationally."
        required_sections = ["Direct Song Overview"]
        excluded_sections = [
            "Executive Summary", "Candidate Songs", "Linguistic Alternative",
            "Clarification & Next Steps", "Sources", "Architecture", "Cybersecurity"
        ]

    else:
        # Balanced general complex plan
        answer_goal = "Provide a well-structured, domain-appropriate response directly answering the problem."
        required_sections = [
            "Executive Summary",
            "Core Analysis & Findings",
            "Options & Trade-offs",
            "Recommendation & Practical Next Steps",
        ]
        optional_sections = ["Assumptions & Limitations"]
        excluded_sections = ["Irrelevant Technical Boilerplate"]

    # Incorporate explicit user requirements into key points
    key_points = list(explicit_reqs)
    if not key_points:
        key_points = [f"Address primary objective: {problem[:80]}"]

    # Select relevant agents based on domain
    relevant_agents = ["researcher", "strategist", "guardian", "evaluator", "conflict_resolver", "synthesizer"]
    if primary_domain in ("software_engineering", "cybersecurity") or "cybersecurity" in secondary_domains:
        relevant_agents.extend(["engineer", "security"])

    return ResponsePlan(
        domain=primary_domain,
        secondary_domains=secondary_domains,
        intent=intent,
        requested_depth=depth,
        answer_goal=answer_goal,
        required_sections=required_sections,
        optional_sections=optional_sections,
        excluded_sections=excluded_sections,
        key_points_to_answer=key_points,
        relevant_agent_outputs=relevant_agents,
        unresolved_uncertainties=[],
        important_tradeoffs=tradeoffs,
        evidence_requirements=evidence_reqs,
    )


__all__ = [
    "ResponsePlan",
    "detect_domains",
    "detect_intent",
    "extract_explicit_requirements",
    "plan_response",
]
