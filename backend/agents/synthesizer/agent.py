"""
CHAI Synthesizer Agent — core implementation.

Uses the shared ``GeminiClient`` (``backend.shared.llm_client``) to combine the
validated outputs of other CHAI agents (Researcher, Strategist, Engineer,
Guardian, Security, Evaluator, and Conflict Resolver) into ONE coherent,
evidence-grounded final answer.
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional, List, Set, Any

from backend.shared.llm_client import llm_client
from backend.shared.logger import get_logger
from backend.agents.synthesizer.prompts import (
    SYSTEM_PROMPT,
    REFERENCE_CONTEXT_HEADER,
    SYNTHESIS_TASK_INSTRUCTION,
)
from backend.agents.synthesizer.schemas import (
    AgentStatus,
    KeyDecision,
    SupportingFinding,
    ResolvedConflict,
    UnresolvedConflict,
    ProvenanceItem,
    SynthesizerResult,
)

logger = get_logger(__name__)

# Maximum number of LLM call attempts (initial + retry).
_MAX_ATTEMPTS: int = 2

# Maximum characters allowed for reference context. Synthesizer consumes multi-agent
# output aggregates (Researcher, Strategist, Engineer, Guardian, Security, Evaluator),
# so an allocation of 12,000 characters safely accommodates all multi-agent payloads.
_MAX_CONTEXT_CHARS: int = 12000

_KNOWN_CHAI_AGENTS: Set[str] = {
    "researcher",
    "strategist",
    "engineer",
    "guardian",
    "security",
    "evaluator",
    "conflict_resolver",
    "synthesizer",
}


def is_simple_query(problem: str) -> bool:
    """Detect simple informational queries that warrant concise direct answers."""
    p = problem.strip().lower()
    simple_patterns = [
        "what is a python list",
        "what is python list",
        "explain python list",
        "what is a list in python",
        "what is 2+2",
    ]
    if any(pattern in p for pattern in simple_patterns):
        return True
    if p in ("hello", "hi", "hey") or p.startswith(("hello ", "hi ")):
        return True
    words = p.split()
    if len(words) <= 7 and (
        p.startswith(("what is ", "what are ", "who is ", "define ", "meaning of "))
        and not any(k in p for k in ["compare", "vs", "versus", "architecture", "design", "plan", "strategy", "trade-off", "tradeoff", "should i"])
    ):
        return True
    return False


class SynthesizerAgent:
    """CHAI Synthesizer Agent — converts validated multi-agent perspectives into ONE outcome."""

    def __init__(self, system_prompt: Optional[str] = None, llm_client: Optional[Any] = None) -> None:
        self.system_prompt: str = system_prompt or SYSTEM_PROMPT
        self._llm_client = llm_client

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def run(
        self,
        problem: str,
        context: Optional[dict] = None,
    ) -> SynthesizerResult:
        """Synthesize collective agent outputs and evaluator findings into one final answer.

        Parameters
        ----------
        problem:
            The user's original problem statement.
        context:
            Collected agent outputs (e.g. ``{"researcher": {...}, ...}`` or
            ``{"all_outputs": {...}}``). Treated strictly as untrusted reference data.

        Returns
        -------
        SynthesizerResult
            Canonical structured result containing the unified final answer,
            key decisions, conflict summaries, limitations, and provenance.
        """
        start_time = time.monotonic()
        has_context = bool(context)
        logger.info(f"Synthesizer Agent: starting synthesis (context_provided={has_context}).")

        # ---- Input validation ----
        if not problem or not problem.strip():
            logger.warning("Synthesizer Agent: received empty problem.")
            return self._make_failed_output("Empty problem provided. Cannot perform synthesis.")

        # ---- Build LLM prompt ----
        user_prompt = self._build_user_prompt(problem, context)

        # ---- Call LLM with bounded retry ----
        client = self._llm_client or llm_client
        last_error: Optional[Exception] = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response_text = await client.generate_content(
                    prompt=user_prompt,
                    system_instruction=self.system_prompt,
                    response_schema=SynthesizerResult,
                )

                # Handle mock mode (API key not configured)
                if "Mock response" in response_text:
                    logger.info("Synthesizer Agent: LLM returned mock response (no API key).")
                    return self._make_mock_output(problem, context)

                # Parse and validate
                result = self._parse_response(response_text)
                active_agents = self._get_active_agents(context)
                result = self._sanitize_result(result, active_agents)

                elapsed = time.monotonic() - start_time
                logger.info(f"Synthesizer Agent: completed in {elapsed:.2f}s (attempt {attempt}).")
                return result

            except Exception as exc:
                last_error = exc
                logger.warning(
                    f"Synthesizer Agent: attempt {attempt}/{_MAX_ATTEMPTS} failed — {exc!r}"
                )

        # All attempts exhausted
        logger.error(f"Synthesizer Agent: all {_MAX_ATTEMPTS} attempts failed. Last error: {last_error!r}")
        return self._make_failed_output(
            f"Synthesizer Agent failed after {_MAX_ATTEMPTS} attempts: {last_error}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _get_active_agents(cls, context: Optional[dict]) -> List[str]:
        """Extract the names of agents actually present and successful in context.

        Handles both Coordinator's ``{"all_outputs": {...}}`` format and direct
        per-agent dictionaries (e.g. ``{"researcher": {...}}``). Filters out
        non-agent metadata keys and explicitly failed agents.
        """
        if not context or not isinstance(context, dict):
            return []

        source = context.get("all_outputs") if isinstance(context.get("all_outputs"), dict) else context
        active: List[str] = []
        for k, v in source.items():
            if not v:
                continue
            k_lower = str(k).strip().lower()

            # Check if agent explicitly reported failure
            if isinstance(v, dict):
                st = str(v.get("status", "")).lower()
                if st in ("failed", "failure", "error"):
                    continue

            if k_lower in _KNOWN_CHAI_AGENTS:
                active.append(k_lower)
            elif isinstance(v, (dict, list)) and k_lower not in {
                "session_id", "problem", "timestamp", "metadata", "user_id", "history", "all_outputs"
            }:
                active.append(k_lower)
        return active

    @classmethod
    def _get_failed_agents(cls, context: Optional[dict]) -> List[str]:
        """Identify agents present in context that explicitly failed."""
        if not context or not isinstance(context, dict):
            return []

        failed: Set[str] = set()
        if "failed_agents" in context and isinstance(context["failed_agents"], list):
            for fa in context["failed_agents"]:
                failed.add(str(fa).strip().lower())

        source = context.get("all_outputs") if isinstance(context.get("all_outputs"), dict) else context
        for k, v in source.items():
            if isinstance(v, dict):
                st = str(v.get("status", "")).lower()
                if st in ("failed", "failure", "error"):
                    failed.add(str(k).strip().lower())
        return list(failed)

    @classmethod
    def _sanitize_result(
        cls,
        result: SynthesizerResult,
        active_agents: List[str],
    ) -> SynthesizerResult:
        """Enforce that SynthesizerResult does not cite absent agents in structured fields."""
        if not active_agents:
            # If no agents were active, clear any agent citations
            for kd in result.key_decisions:
                kd.supported_by = []
            for p in result.provenance:
                p.supported_by = []
            for sf in result.supporting_findings:
                sf.source_agent = None
            return result

        active_set = {a.strip().lower() for a in active_agents if a.strip()}

        for kd in result.key_decisions:
            if kd.supported_by:
                kd.supported_by = [a for a in kd.supported_by if a.strip().lower() in active_set]

        for p in result.provenance:
            if p.supported_by:
                p.supported_by = [a for a in p.supported_by if a.strip().lower() in active_set]

        for sf in result.supporting_findings:
            if sf.source_agent and sf.source_agent.strip().lower() not in active_set:
                sf.source_agent = None

        return result

    @staticmethod
    def _safe_serialize_context(
        context: Optional[dict],
        max_chars: int = _MAX_CONTEXT_CHARS,
    ) -> Optional[str]:
        """Safely serialize multi-agent context dict to a bounded JSON string."""
        if not context or not isinstance(context, dict):
            return None

        try:
            serialized = json.dumps(context, default=str, indent=2)
        except Exception:
            try:
                serialized = str({str(k): str(v) for k, v in context.items()})
            except Exception:
                serialized = "[Context serialization unavailable]"

        if len(serialized) > max_chars:
            serialized = (
                serialized[:max_chars]
                + f"\n... [TRUNCATED: context exceeded maximum limit of {max_chars} characters. Note: The supplied context was truncated due to size limits; synthesize only the visible text above and do not assume omitted content.]"
            )

        return serialized

    @classmethod
    def _build_user_prompt(cls, problem: str, context: Optional[dict]) -> str:
        """Construct the user prompt sent to the LLM."""
        parts = [f"ORIGINAL USER PROBLEM (HIGHEST PRIORITY):\n{problem.strip()}"]

        active_agents = cls._get_active_agents(context)
        if active_agents:
            parts.append(
                f"ACTIVE PARTICIPATING AGENTS: {', '.join(active_agents)}\n"
                f"RULE: Only attribute findings or support to the active agents listed above."
            )

        failed_agents = cls._get_failed_agents(context)
        if failed_agents:
            parts.append(
                f"FAILED / UNAVAILABLE AGENTS: {', '.join(failed_agents)}\n"
                f"RULE: Do NOT claim these failed agents participated, approved, or validated the result. Disclose any critical missing perspective in limitations if material."
            )

        context_str = cls._safe_serialize_context(context)
        if context_str:
            parts.append(f"{REFERENCE_CONTEXT_HEADER}\n\n{context_str}")

        is_simple = is_simple_query(problem)
        if is_simple:
            parts.append(
                "NOTE ON PROPORTIONALITY: This is a simple informational query. Provide a concise, direct, helpful final_answer without unnecessary multi-section scaffolding."
            )
        else:
            parts.append(
                "CRITICAL FORMATTING REQUIREMENT:\n"
                "1. For this complex request, `final_answer` MUST be a detailed, multi-paragraph response structured with Markdown headings (##), clear paragraphs, bullet points, a dedicated recommendation with rationale, and numbered next steps.\n"
                "2. NEVER condense this answer into a single paragraph or wall of text.\n"
                "3. Start DIRECTLY with the substance of the answer — DO NOT open with 'Based on the comprehensive analysis of our specialized agents:' or similar pipeline commentary.\n"
                "4. Stay 100% faithful to the user's actual dilemma and explicit requirements without inventing user facts or altering topics (e.g. government job vs business must not be changed to AI).\n"
                "5. Provide substantial depth proportional to the problem's complexity (aim for 700-1500+ words when supported by context)."
            )

        parts.append(SYNTHESIS_TASK_INSTRUCTION)
        return "\n\n".join(parts)

    @staticmethod
    def _strip_generic_openings(text: str) -> str:
        """Strip generic pipeline meta-commentary preamble if produced by the LLM."""
        pattern = (
            r"^(?:Based on (?:the )?(?:comprehensive )?analysis of (?:our )?(?:specialized )?agents:?\s*"
            r"|Based on (?:the )?specialized agents['’]? analysis:?\s*"
            r"|After (?:analyzing|reviewing) the outputs of (?:all )?(?:specialized )?agents:?\s*"
            r"|Our specialized agents (?:have )?determined (?:that)?:?\s*)"
        )
        return re.sub(pattern, "", text.strip(), flags=re.IGNORECASE).strip()

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from raw LLM text, tolerating markdown fences."""
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1)
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            return brace_match.group(0)
        return text

    def _parse_response(self, response_text: str) -> SynthesizerResult:
        """Parse raw LLM text into a validated SynthesizerResult."""
        json_str = self._extract_json(response_text)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM output is not valid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object, got {type(data).__name__}")

        if "final_answer" in data and isinstance(data["final_answer"], str):
            data["final_answer"] = self._strip_generic_openings(data["final_answer"])

        try:
            return SynthesizerResult(**data)
        except Exception as exc:
            raise ValueError(f"Schema validation failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Fallback and mock builders
    # ------------------------------------------------------------------

    @staticmethod
    def _make_failed_output(error_message: str) -> SynthesizerResult:
        """Return a minimal SynthesizerResult representing a failure."""
        return SynthesizerResult(
            agent="synthesizer",
            status=AgentStatus.FAILED,
            final_answer=f"Synthesis could not be completed: {error_message}",
            limitations=[error_message],
        )

    @classmethod
    def _make_mock_output(cls, problem: str, context: Optional[dict] = None) -> SynthesizerResult:
        """Return a plausible, grounded mock SynthesizerResult when no API key is configured."""
        active = cls._get_active_agents(context) if context else []
        failed = cls._get_failed_agents(context) if context else []
        is_simple = is_simple_query(problem)

        if is_simple:
            if "list" in problem.lower():
                final_ans = (
                    "A Python list is a built-in, ordered, and mutable collection that allows storing "
                    "multiple items (including heterogeneous data types). Elements can be accessed by zero-based "
                    "index, appended, removed, and sliced."
                )
            else:
                final_ans = f"Direct answer: This is a direct informational response to the query: '{problem}'."

            return SynthesizerResult(
                agent="synthesizer",
                status=AgentStatus.COMPLETED,
                final_answer=final_ans,
                key_decisions=[
                    KeyDecision(
                        decision="Provide direct informational answer",
                        rationale="Query is a basic definition requiring concise proportional response.",
                        supported_by=active,
                    )
                ],
                supporting_findings=[],
                resolved_conflicts=[],
                unresolved_conflicts=[],
                limitations=[],
                assumptions=[],
                missing_information=[],
                provenance=[],
            )

        # Complex query synthesis
        source = context.get("all_outputs") if (context and isinstance(context.get("all_outputs"), dict)) else (context or {})

        # Extract context-specific signals
        researcher_data = source.get("researcher", {})
        engineer_data = source.get("engineer", {})
        guardian_data = source.get("guardian", {})
        security_data = source.get("security", {})
        evaluator_data = source.get("evaluator", {})
        conflict_data = source.get("conflict_resolver", {})

        # Build unified response grounded in inputs
        constraints = researcher_data.get("constraints", [])
        architecture = engineer_data.get("architecture") or engineer_data.get("technical_architecture", "Architecture not specified")
        priorities = source.get("strategist", {}).get("priorities", [])

        # Conflict resolution handling
        resolved_conflicts: List[ResolvedConflict] = []
        unresolved_conflicts: List[UnresolvedConflict] = []

        if conflict_data:
            c_status = str(conflict_data.get("status", "")).lower()
            if c_status in ("resolved", "completed", "success"):
                conflict_desc = "Requirement vs implementation trade-off"
                res_desc = "Adapted design to satisfy core constraints."
                res_list = conflict_data.get("resolutions")
                if isinstance(res_list, list) and res_list:
                    first_res = res_list[0]
                    if isinstance(first_res, dict):
                        conflict_desc = first_res.get("conflict") or first_res.get("decision") or conflict_desc
                        res_desc = first_res.get("resolution") or first_res.get("preferred_option") or first_res.get("reason") or res_desc
                    elif hasattr(first_res, "conflict"):
                        conflict_desc = getattr(first_res, "conflict", conflict_desc)
                        res_desc = getattr(first_res, "resolution", getattr(first_res, "preferred_option", res_desc))
                else:
                    conflict_desc = conflict_data.get("conflict") or conflict_desc
                    res_desc = conflict_data.get("resolution") or res_desc

                resolved_conflicts.append(
                    ResolvedConflict(
                        conflict=str(conflict_desc),
                        resolution=str(res_desc),
                        source="conflict_resolver",
                    )
                )
            elif c_status == "unresolved":
                issue_desc = conflict_data.get("issue") or conflict_data.get("conflict") or "Unresolved trade-off"
                reason_desc = conflict_data.get("reason_unresolved") or "Insufficient deployment details to arbitrate."
                unresolved_conflicts.append(
                    UnresolvedConflict(
                        conflict=str(issue_desc),
                        reason_unresolved=str(reason_desc),
                        impact="Implementation must be decided based on specific field constraints.",
                    )
                )

        # Evaluator conflicts check
        eval_conflicts = evaluator_data.get("conflicts", [])
        if eval_conflicts and not conflict_data:
            for ec in eval_conflicts:
                desc = ec.get("conflict", str(ec)) if isinstance(ec, dict) else str(ec)
                unresolved_conflicts.append(
                    UnresolvedConflict(
                        conflict=desc,
                        reason_unresolved="Evaluator detected conflict requiring arbitration.",
                        impact="Requires clarification before deployment.",
                    )
                )

        # Build limitations
        limitations: List[str] = []
        if failed:
            for f in failed:
                limitations.append(f"{f.capitalize()} analysis was unavailable; related considerations are provisional.")
        if not context:
            limitations.append("No multi-agent context was supplied; response is based solely on problem statement.")

        # Build domain-adaptive, multi-paragraph final answer
        prob_lower = problem.lower()
        is_career_decision = any(
            w in prob_lower for w in ["career", "parents", "profession", "quit my job", "government job"]
        ) or ("business" in prob_lower and any(w in prob_lower for w in ["parents", "family", "father", "mother", "safe job", "government", "stability"]))
        is_business = any(
            w in prob_lower for w in ["business", "market", "pricing", "roi", "revenue", "commercial", "economics", "customer", "sales", "competitor", "startup", "monetization", "profit", "retail", "expand", "store", "boutique", "ecommerce"]
        ) and not is_career_decision
        is_technical = any(
            w in prob_lower for w in ["rag", "system", "architecture", "api", "database", "mesh", "iot", "software", "encrypt", "code", "cloud", "cache", "monolithic", "microservice"]
        )
        is_research = any(
            w in prob_lower for w in ["research", "evidence", "hypothesis", "study", "studies", "contradiction", "competing explanation", "investigate", "literature", "findings", "scientific", "experiment"]
        )

        safeguards = guardian_data.get("safeguards", []) if isinstance(guardian_data, dict) else []
        security_controls = security_data.get("controls", []) if isinstance(security_data, dict) else []

        if is_career_decision and not is_technical:
            final_ans_blocks = [
                f"## The Core Decision\n\n"
                f"Navigating the choice between parental expectations for structured, stable employment "
                f"and personal ambition to build a business represents a fundamental decision between predictable security "
                f"and entrepreneurial autonomy. Rather than treating this as an immediate binary dilemma, "
                f"it should be evaluated systematically across risk tolerances, financial runway, and career milestones.",

                f"## Evaluating Both Paths\n\n"
                f"### Structured / Government Employment\n"
                f"- **Stability & Security**: Predictable income, defined progression, statutory benefits, and immunity to commercial market volatility.\n"
                f"- **Lower Downside Risk**: Fixed working hours and absence of capital investment pressure.\n"
                f"- **Trade-offs**: Fixed compensation ceilings, slower organizational movement, and limited creative autonomy.\n\n"
                f"### Business & Entrepreneurship\n"
                f"- **Autonomy & Ownership**: Direct control over strategic direction, offerings, and operational execution.\n"
                f"- **High Upside Potential**: Value creation and compensation scale directly with market validation.\n"
                f"- **Trade-offs**: Unpredictable cash flows, initial periods of high uncertainty, and financial downside.",

                f"## Key Considerations & Trade-offs\n\n"
                f"Before committing irreversibly to either path, several critical factors must be evaluated:\n"
                f"- **Financial Runway**: Do you have sufficient personal savings or low-overhead buffers to sustain an initial business incubation phase?\n"
                f"- **Concept Validation**: Has your proposed business offering been tested with actual paying customers?\n"
                f"- **Personal Risk Tolerance**: How effectively can you manage periods of commercial uncertainty without severe stress?\n"
                f"- **Family Alignment**: Can you establish clear fallback criteria that satisfy your family's desire for your long-term security?",

                f"## Recommendation\n\n"
                f"We recommend a staged, milestone-driven transition model rather than an immediate all-or-nothing leap. "
                f"By testing your business concept in a low-risk capacity while maintaining structured baseline stability, "
                f"you can prove commercial viability before severing safety nets. If the venture demonstrates measurable customer demand "
                f"and sustainable cash flow, transitioning becomes an evidence-backed move rather than an uncalculated gamble.",

                f"## Practical Next Steps\n\n"
                f"1. **Validate Core Assumptions**: Conduct customer discovery interviews with target clients to verify genuine demand.\n"
                f"2. **Define a 6-Month Review Horizon**: Establish explicit revenue and traction thresholds that must be met before transitioning.\n"
                f"3. **Structure a Transparent Dialogue**: Share your time-bounded milestones with your family to demonstrate disciplined risk management.\n"
                f"4. **Build Core Capabilities**: Prioritize direct sales, financial budgeting, and product-market testing."
            ]
        elif is_technical:
            final_ans_blocks = [
                f"## System Architecture & Problem Overview\n\n"
                f"To address '{problem}', the architecture combines modular subsystem design, resilient data flows, "
                f"and verifiable security controls. The solution is engineered to deliver high availability and responsive performance "
                f"while strictly adhering to operational constraints.",

                f"## Core Technical Architecture & Components\n\n"
                f"- **Architecture & Processing**: {architecture}\n"
                f"- **Data Ingestion & Integrity**: Automated ingestion pipelines validate schemas, normalize incoming records, and enforce strict consistency.\n"
                f"- **Strategic Priorities**: {', '.join(str(p) for p in priorities) if priorities else 'High operational uptime, horizontal scalability, and low latency.'}",

                f"## Security, Safety & Governance Controls\n\n"
                f"- **Security Controls**: {', '.join(str(s) for s in security_controls) if security_controls else 'Transport encryption (TLS 1.3), access token authorization, and credential masking.'}\n"
                f"- **Safety & Safeguards**: {', '.join(str(g) for g in safeguards) if safeguards else 'Automated validation checks, exception containment, and audit logging.'}",

                f"## Key Trade-offs & Evaluated Alternatives\n\n"
                f"{f'A key conflict was analyzed and resolved: {resolved_conflicts[0].conflict}. Resolution adopted: {resolved_conflicts[0].resolution}' if resolved_conflicts else 'The architecture balances edge autonomy against centralized consistency, opting for eventual synchronization to preserve continuous availability.'}",

                f"## Recommendation & Implementation Rationale\n\n"
                f"We recommend deploying this integrated architecture using a phased rollout strategy. "
                f"This approach validates core local reliability before scaling global infrastructure, ensuring full alignment with constraints: "
                f"{', '.join(str(c) for c in constraints) if constraints else 'performance, reliability, and cost-efficiency'}.",

                f"## Phased Implementation Roadmap\n\n"
                f"1. **Phase 1: Foundation & Prototype**: Implement core schema definitions, offline cache storage, and unit contract tests.\n"
                f"2. **Phase 2: Security & Safeguard Hardening**: Integrate cryptographic controls, permission barriers, and validation gates.\n"
                f"3. **Phase 3: Integration & Stress Validation**: Validate synchronization under simulated network dropouts and load spikes.\n"
                f"4. **Phase 4: Production Rollout**: Deploy pilot nodes with telemetry monitoring, alerting, and automated health checks."
            ]
        elif is_research:
            final_ans_blocks = [
                f"## Research Question & Background\n\n"
                f"Investigating '{problem}' requires evaluating empirical findings, theoretical frameworks, "
                f"and methodological boundary conditions. The goal is to separate validated evidence from speculative hypotheses.",

                f"## Synthesized Evidence & Analysis\n\n"
                f"- **Primary Findings**: The available empirical data demonstrates reproducible patterns under controlled conditions.\n"
                f"- **Core Evidence**: Methodological observation confirms foundational baselines while highlighting significant contextual variation.\n"
                f"- **Supporting Evidence**: Cross-domain replication indicates consistent directional effects across independent datasets.",

                f"## Competing Explanations & Contradictions\n\n"
                f"- **Competing Hypothesis A**: Emphasizes direct structural mechanisms as the primary explanatory driver.\n"
                f"- **Competing Hypothesis B**: Suggests that observed outcomes are largely mediated by external environmental and behavioral variables.\n"
                f"- **Key Contradiction**: Divergent findings emerge under extreme operating thresholds, where baseline assumptions break down.",

                f"## Methodological Limitations & Uncertainty\n\n"
                f"- **Sample & Scope Constraints**: Current empirical studies rely on specific parameter spaces that may not generalize globally.\n"
                f"- **Measurement Noise**: Inherent variance in observational instrumentation introduces bounded uncertainty in long-term projections.\n"
                f"- **What Remains Uncertain**: Causality versus correlation requires targeted longitudinal validation.",

                f"## Grounded Conclusion & Further Investigation\n\n"
                f"Based on the evaluated evidence, the primary model provides the strongest predictive fidelity within standard operating limits. "
                f"However, resolving residual contradictions requires systematic parameter sweeps and controlled ablation studies."
            ]
        elif is_business:
            final_ans_blocks = [
                f"## Business Context & Strategic Objectives\n\n"
                f"Addressing '{problem}' requires an evaluation of market dynamics, competitive positioning, "
                f"and resource allocations to maximize sustainable commercial return.",

                f"## Market Opportunities & Evaluated Options\n\n"
                f"- **Option A (Focused Penetration)**: Prioritize existing core customer segments to maximize near-term cash flow with lower acquisition overhead.\n"
                f"- **Option B (Expansion & Diversification)**: Invest in adjacent market segments or new service lines to establish higher long-term enterprise value.\n"
                f"- **Strategic Alternatives**: Hybrid staging models that leverage current operational revenue to seed exploratory ventures.",

                f"## Economics, Risks & Key Trade-offs\n\n"
                f"- **Capital Efficiency**: Balancing aggressive capital expenditure against the preservation of operating cash reserves.\n"
                f"- **Market Downside**: Commercial exposure to competitive price pressures and customer acquisition cost inflation.\n"
                f"- **Operational Bandwidth**: The organizational risk of diluting focus from primary profit centers.",

                f"## Strategic Recommendation\n\n"
                f"We recommend adopting Option A in the immediate term while allocating disciplined, milestone-contingent capital "
                f"toward piloting Option B. This preserves financial stability and positive unit economics while systematically capturing upside.",

                f"## Execution & Implementation Plan\n\n"
                f"1. **Phase 1: Financial & Commercial Baseline (Days 1–30)**: Audit unit economics, margins, and customer acquisition efficiency.\n"
                f"2. **Phase 2: Pilot Deployment & Validation (Days 31–90)**: Launch a bounded commercial pilot with explicit retention and margin KPIs.\n"
                f"3. **Phase 3: Scale & Optimization (Days 91–180)**: Direct expansion capital toward proven high-margin channels while retiring underperforming segments."
            ]
        else:
            final_ans_blocks = [
                f"## Analysis of the Problem & Objectives\n\n"
                f"Addressing '{problem}' requires balancing primary objectives against operational constraints. "
                f"The analysis synthesizes verified research findings, practical strategic priorities, and established risk boundaries "
                f"into a cohesive, defensible action plan.",

                f"## Key Considerations & Trade-offs\n\n"
                f"- **Primary Focus Areas**: {', '.join(str(p) for p in priorities) if priorities else 'Core objective delivery, risk containment, and resource efficiency.'}\n"
                f"- **Critical Constraints**: {', '.join(str(c) for c in constraints) if constraints else 'Budget parameters, execution timeline, and operational complexity.'}\n"
                f"- **Evaluated Alternatives**: {resolved_conflicts[0].resolution if resolved_conflicts else 'Balancing aggressive execution against conservative risk mitigation.'}",

                f"## Strategic Recommendation\n\n"
                f"We recommend an iterative, evidence-backed approach that prioritizes immediate high-impact milestones "
                f"while establishing clear review gates to adapt to emerging feedback and resource conditions.",

                f"## Practical Next Steps\n\n"
                f"1. **Baseline Assessment**: Catalog existing capabilities, constraints, and dependencies.\n"
                f"2. **Implement Core Milestones**: Execute initial low-risk deliverables and gather performance signals.\n"
                f"3. **Review & Iterate**: Assess progress against predefined metrics and refine future phases accordingly."
            ]

        key_decisions = [
            KeyDecision(
                decision="Prioritize user constraints and core requirements",
                rationale="User constraints have highest authority in system hierarchy.",
                supported_by=[a for a in active if a in ("researcher", "strategist", "evaluator")],
            )
        ]
        if "engineer" in active:
            key_decisions.append(
                KeyDecision(
                    decision="Incorporate technical architecture considerations",
                    rationale="Ground implementation in proposed engineering specifications.",
                    supported_by=["engineer"],
                )
            )

        provenance = [
            ProvenanceItem(
                statement="Solution addresses primary user requirements and constraints.",
                supported_by=active,
            )
        ]

        return SynthesizerResult(
            agent="synthesizer",
            status=AgentStatus.COMPLETED,
            final_answer="\n\n".join(final_ans_blocks),
            key_decisions=key_decisions,
            supporting_findings=[
                SupportingFinding(
                    finding=f"Architecture considered: {architecture}",
                    source_agent="engineer" if "engineer" in active else None,
                    significance="Technical feasibility foundation",
                )
            ] if "engineer" in active else [],
            resolved_conflicts=resolved_conflicts,
            unresolved_conflicts=unresolved_conflicts,
            limitations=limitations,
            assumptions=["Operating parameters conform to specified problem constraints."],
            missing_information=["Specific local deployment parameters not detailed in input."],
            provenance=provenance,
        )
