"""
CHAI Evaluator Agent — core implementation.

Uses the shared ``GeminiClient`` (``backend.shared.llm_client``) to evaluate
the collected outputs of other CHAI agents (Researcher, Strategist, Engineer,
Guardian, Security). Returns an ``EvaluatorOutput`` (backward-compatible with
the Coordinator) that embeds a canonical ``EvaluatorResult``.

Design principles:
- Reuses the shared project singleton ``llm_client``.
- Anti-prompt-injection isolation for untrusted multi-agent context.
- Bounded context serialization supporting multi-agent output aggregates (12k limit).
- Bounded retry logic (max 2 attempts).
- Tolerant JSON parsing supporting markdown fences and surrounding commentary.
- Graceful degradation returning ``status=failed`` rather than crashing the pipeline.
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional, Any

from backend.shared.llm_client import llm_client
from backend.shared.logger import get_logger
from backend.agents.evaluator.prompts import (
    SYSTEM_PROMPT,
    REFERENCE_CONTEXT_HEADER,
    EVALUATION_TASK_INSTRUCTION,
)
from backend.agents.evaluator.schemas import (
    AgentStatus,
    EvaluatorResult,
    EvaluatorOutput,
)

logger = get_logger(__name__)

# Maximum number of LLM call attempts (initial + retry).
_MAX_ATTEMPTS: int = 2

# Maximum characters allowed for reference context. Evaluator consumes multiple
# agent perspectives (Researcher, Strategist, Engineer, Guardian), so an
# allocation of 12,000 characters safely accommodates all multi-agent payloads.
_MAX_CONTEXT_CHARS: int = 12000


class EvaluatorAgent:
    """CHAI Evaluator Agent — multi-agent consistency, coverage, and quality evaluator."""

    def __init__(self, llm_client: Optional[Any] = None) -> None:
        self.system_prompt: str = SYSTEM_PROMPT
        self._llm_client = llm_client

    # ------------------------------------------------------------------
    # Public interface consumed by the Coordinator
    # ------------------------------------------------------------------

    async def run(
        self,
        problem: str,
        context: Optional[dict] = None,
    ) -> EvaluatorOutput:
        """Evaluate collective agent outputs against the user's problem.

        Parameters
        ----------
        problem:
            The user's original problem statement.
        context:
            Collected agent outputs (e.g. ``{"all_outputs": {...}}`` or direct
            per-agent dicts). Treated strictly as untrusted reference data.

        Returns
        -------
        EvaluatorOutput
            Backward-compatible model consumed by the Coordinator, exposing
            ``detected_contradictions`` while embedding the full ``EvaluatorResult``.
        """
        start_time = time.monotonic()
        has_context = bool(context)
        logger.info(f"Evaluator Agent: starting evaluation (context_provided={has_context}).")

        # ---- Input validation ----
        if not problem or not problem.strip():
            logger.warning("Evaluator Agent: received empty problem.")
            return self._make_failed_output("Empty problem provided. Cannot perform evaluation.")

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
                )

                # Handle mock mode (API key not configured)
                if "Mock response" in response_text:
                    logger.info("Evaluator Agent: LLM returned mock response (no API key).")
                    return self._make_mock_output(problem, context)

                # Parse and validate
                result = self._parse_response(response_text)
                active_agents = self._get_active_agents(context)
                result = self._sanitize_result(result, active_agents, context)

                elapsed = time.monotonic() - start_time
                logger.info(f"Evaluator Agent: completed in {elapsed:.2f}s (attempt {attempt}).")
                return EvaluatorOutput.from_evaluator_result(result)

            except Exception as exc:
                last_error = exc
                logger.warning(
                    f"Evaluator Agent: attempt {attempt}/{_MAX_ATTEMPTS} failed — {exc!r}"
                )

        # All attempts exhausted
        logger.error(f"Evaluator Agent: all {_MAX_ATTEMPTS} attempts failed. Last error: {last_error!r}")
        return self._make_failed_output(
            f"Evaluator Agent failed after {_MAX_ATTEMPTS} attempts: {last_error}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    _KNOWN_CHAI_AGENTS: set[str] = {
        "researcher",
        "strategist",
        "engineer",
        "guardian",
        "security",
        "evaluator",
        "conflict_resolver",
        "synthesizer",
    }

    @classmethod
    def _get_active_agents(cls, context: Optional[dict]) -> list[str]:
        """Extract the names of agents actually present in the context.

        Handles both Coordinator's ``{"all_outputs": {...}}`` format and direct
        per-agent dictionaries (e.g. ``{"researcher": {...}}``). Filters out
        non-agent metadata keys.
        """
        if not context or not isinstance(context, dict):
            return []

        source = context.get("all_outputs") if isinstance(context.get("all_outputs"), dict) else context
        active: list[str] = []
        for k, v in source.items():
            if not v:
                continue
            k_lower = str(k).strip().lower()
            if k_lower in cls._KNOWN_CHAI_AGENTS:
                active.append(str(k))
            elif isinstance(v, (dict, list)) and k_lower not in {
                "session_id", "problem", "timestamp", "metadata", "user_id", "history", "all_outputs"
            }:
                active.append(str(k))
        return active

    @classmethod
    def _sanitize_result(
        cls,
        result: EvaluatorResult,
        active_agents: list[str],
        context: Optional[dict] = None,
    ) -> EvaluatorResult:
        """Enforce that EvaluatorResult does not cite absent agents in structured fields
        and explicitly reports missing or failed upstream agents."""
        if active_agents:
            active_set = {a.strip().lower() for a in active_agents if a.strip()}
            for c in result.conflicts:
                if c.agents_involved:
                    c.agents_involved = [a for a in c.agents_involved if a.strip().lower() in active_set]

            for inc in result.inconsistencies:
                if inc.source_agents:
                    inc.source_agents = [a for a in inc.source_agents if a.strip().lower() in active_set]

            for u in result.unsupported_claims:
                if u.source_agent and u.source_agent.strip().lower() not in active_set:
                    u.source_agent = None

        # Check for explicitly failed upstream specialist agents
        if context and isinstance(context, dict):
            failed_agents_list: list[str] = []
            if "failed_agents" in context and isinstance(context["failed_agents"], list):
                for a in context["failed_agents"]:
                    if a and str(a).lower() not in failed_agents_list:
                        failed_agents_list.append(str(a).lower())

            source = context.get("all_outputs") if isinstance(context.get("all_outputs"), dict) else context
            for k, v in source.items():
                if isinstance(v, dict):
                    st = str(v.get("status", "")).lower()
                    if st in ("failed", "failure", "error"):
                        k_clean = str(k).lower()
                        if k_clean not in failed_agents_list:
                            failed_agents_list.append(k_clean)

            if "execution_statuses" in context and isinstance(context["execution_statuses"], list):
                for es in context["execution_statuses"]:
                    if isinstance(es, dict) and str(es.get("status", "")).lower() in ("failed", "failure", "error"):
                        an = str(es.get("agent_name", "")).lower()
                        if an and an not in failed_agents_list:
                            failed_agents_list.append(an)

            if failed_agents_list:
                result.status = AgentStatus.PARTIAL
                from backend.agents.evaluator.schemas import QualityIssueItem, RequirementCoverageItem, RequirementStatus
                for f_agent in failed_agents_list:
                    already_noted_qi = any(f_agent in q.issue.lower() for q in result.quality_issues)
                    if not already_noted_qi:
                        result.quality_issues.append(
                            QualityIssueItem(
                                issue=f"Upstream agent '{f_agent}' encountered execution failure.",
                                category="dependency",
                                impact=f"Cross-agent evaluation of {f_agent} specifications could not be verified.",
                                recommendation=f"Re-run {f_agent} agent or inspect upstream failure logs.",
                            )
                        )
                    already_noted_rc = any(f_agent in r.requirement.lower() for r in result.requirement_coverage)
                    if not already_noted_rc:
                        result.requirement_coverage.append(
                            RequirementCoverageItem(
                                requirement=f"{f_agent.capitalize()} analysis",
                                status=RequirementStatus.NOT_ADDRESSED,
                                gap=f"{f_agent.capitalize()} output was absent or encountered execution errors.",
                            )
                        )
                if "partial" not in result.overall_assessment.lower() and "degraded" not in result.overall_assessment.lower():
                    result.overall_assessment += f" Note: Upstream outputs from [{', '.join(failed_agents_list)}] encountered failures; evaluation operates in degraded mode."

        return result

    @staticmethod
    def _safe_serialize_context(
        context: Optional[dict],
        max_chars: int = _MAX_CONTEXT_CHARS,
    ) -> Optional[str]:
        """Safely serialize multi-agent context dict to a bounded JSON string.

        Guarantees:
        - None or empty context returns None.
        - Non-dict values return None.
        - Non-JSON-serializable objects (custom instances, dates, sets) are
          converted safely via ``str`` without raising exceptions.
        - Circular references or unexpected exceptions fallback cleanly.
        - Payloads exceeding ``max_chars`` are truncated with a visible notice.
        """
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
                + f"\n... [TRUNCATED: context exceeded maximum limit of {max_chars} characters. Note: The supplied context was truncated due to size limits; evaluate only the visible text above and do not assume omitted content.]"
            )

        return serialized

    @classmethod
    def _build_user_prompt(cls, problem: str, context: Optional[dict]) -> str:
        """Construct the user-facing prompt sent to the LLM.

        Clearly separates:
        1. Original user problem (explicitly labeled)
        2. Active participating agents list (preventing hallucinated absent agents)
        3. Reference context from other CHAI agents (untrusted reference data)
        4. Actual Evaluator task (with boundaries re-asserted)
        """
        parts = [f"PROBLEM:\n{problem.strip()}"]

        active_agents = cls._get_active_agents(context)
        if active_agents:
            parts.append(
                f"ACTIVE AGENTS PRESENT IN CONTEXT: {', '.join(active_agents)}\n"
                f"CRITICAL RULE: Evaluate ONLY the active agents listed above. Do NOT reference, cite, or invent findings for absent agents (such as Security, Strategist, etc.) unless they are explicitly in this active list."
            )

        context_str = cls._safe_serialize_context(context)
        if context_str:
            parts.append(f"{REFERENCE_CONTEXT_HEADER}\n\n{context_str}")

        parts.append(EVALUATION_TASK_INSTRUCTION)
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

    def _parse_response(self, response_text: str) -> EvaluatorResult:
        """Parse raw LLM text into a validated ``EvaluatorResult``."""
        json_str = self._extract_json(response_text)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM output is not valid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object, got {type(data).__name__}")

        try:
            return EvaluatorResult(**data)
        except Exception as exc:
            raise ValueError(f"Schema validation failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Fallback builders
    # ------------------------------------------------------------------

    @staticmethod
    def _make_failed_output(error_message: str) -> EvaluatorOutput:
        """Return a minimal ``EvaluatorOutput`` representing a failure."""
        result = EvaluatorResult(
            agent="evaluator",
            status=AgentStatus.FAILED,
            overall_assessment=error_message,
        )
        return EvaluatorOutput.from_evaluator_result(result)

    @classmethod
    def _make_mock_output(cls, problem: str, context: Optional[dict] = None) -> EvaluatorOutput:
        """Return a plausible mock ``EvaluatorOutput`` when no API key is set."""
        active = cls._get_active_agents(context) if context else []
        active_str = f" for active agents [{', '.join(active)}]" if active else ""
        result = EvaluatorResult(
            agent="evaluator",
            status=AgentStatus.COMPLETED,
            overall_assessment=f"[Mock] Cross-agent evaluation of: {problem}{active_str}",
            requirement_coverage=[],
            conflicts=[],
            inconsistencies=[],
            unsupported_claims=[],
            quality_issues=[],
            strengths=["[Mock] Individual agent perspectives provide preliminary viewpoints."],
            recommendations=["[Mock] Comprehensive cross-agent evaluation requires GEMINI_API_KEY."],
            assumptions=["[Mock] No live LLM available; returning placeholder evaluation data."],
            missing_information=["[Mock] Full agent outputs and GEMINI_API_KEY required for detailed conflict detection."],
        )
        result = cls._sanitize_result(result, active, context)
        return EvaluatorOutput.from_evaluator_result(result)
