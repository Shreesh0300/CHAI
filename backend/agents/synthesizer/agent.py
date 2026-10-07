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
from typing import Optional, List, Set

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
        "hello",
        "hi",
    ]
    return any(pattern in p for pattern in simple_patterns)


class SynthesizerAgent:
    """CHAI Synthesizer Agent — converts validated multi-agent perspectives into ONE outcome."""

    def __init__(self, system_prompt: Optional[str] = None) -> None:
        self.system_prompt: str = system_prompt or SYSTEM_PROMPT

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
        last_error: Optional[Exception] = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response_text = await llm_client.generate_content(
                    prompt=user_prompt,
                    system_instruction=self.system_prompt,
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

        source = context.get("all_outputs") if isinstance(context.get("all_outputs"), dict) else context
        failed: List[str] = []
        for k, v in source.items():
            if isinstance(v, dict):
                st = str(v.get("status", "")).lower()
                if st in ("failed", "failure", "error"):
                    failed.append(str(k).strip().lower())
        return failed

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

        parts.append(SYNTHESIS_TASK_INSTRUCTION)
        return "\n\n".join(parts)

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
            c_status = conflict_data.get("status", "").lower()
            if c_status in ("resolved", "completed", "success"):
                resolved_conflicts.append(
                    ResolvedConflict(
                        conflict=conflict_data.get("conflict", "Requirement vs implementation trade-off"),
                        resolution=conflict_data.get("resolution", "Adapted design to satisfy core constraints."),
                        source="conflict_resolver",
                    )
                )
            elif c_status == "unresolved":
                unresolved_conflicts.append(
                    UnresolvedConflict(
                        conflict=conflict_data.get("issue") or conflict_data.get("conflict", "Unresolved trade-off"),
                        reason_unresolved=conflict_data.get("reason_unresolved", "Insufficient deployment details to arbitrate."),
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

        # Build final unified answer
        answer_parts = [
            f"Recommended Solution for '{problem}':\n"
            f"Deploy an integrated, resilient solution addressing the primary requirements."
        ]
        if constraints:
            answer_parts.append(f"Core Constraints: {', '.join(str(c) for c in constraints)}.")
        if priorities:
            answer_parts.append(f"Strategic Focus: {', '.join(str(p) for p in priorities)}.")
        if resolved_conflicts:
            answer_parts.append(f"Reconciled Approach: {resolved_conflicts[0].resolution}")
        if unresolved_conflicts:
            answer_parts.append(f"Unresolved Consideration: {unresolved_conflicts[0].conflict} ({unresolved_conflicts[0].reason_unresolved})")

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
            final_answer="\n\n".join(answer_parts),
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
