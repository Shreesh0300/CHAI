"""
CHAI Conflict Resolver Agent — core implementation.

Uses the shared ``GeminiClient`` (``backend.shared.llm_client``) to arbitrate
cross-agent disagreements detected by Evaluator and specialized agents.
Returns a canonical ``ConflictResolutionResult`` (or ``ConflictResolverOutput``).

Design principles:
- Reuses the shared project singleton ``llm_client``.
- Anti-prompt-injection isolation for untrusted multi-agent context.
- Bounded context serialization (12k limit).
- Bounded retry logic (max 2 attempts).
- Tolerant JSON parsing supporting markdown fences and surrounding commentary.
- Graceful degradation returning ``status=failed`` rather than crashing the pipeline.
- Principled decision hierarchy prioritizing user requirements and safety/security.
- Transparent preservation of unresolved conflicts and missing information.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional, Set

from backend.shared.llm_client import llm_client
from backend.shared.logger import get_logger
from backend.agents.conflict_resolver.prompts import (
    SYSTEM_PROMPT,
    REFERENCE_CONTEXT_HEADER,
    RESOLUTION_TASK_INSTRUCTION,
)
from backend.agents.conflict_resolver.schemas import (
    AgentStatus,
    Resolution,
    UnresolvedConflictItem,
    ProvenanceItem,
    ConflictResolutionResult,
    ConflictResolverOutput,
)

logger = get_logger(__name__)

# Maximum number of LLM call attempts (initial + retry).
_MAX_ATTEMPTS: int = 2

# Maximum characters allowed for reference context.
_MAX_CONTEXT_CHARS: int = 12000

# Canonical CHAI agent names known across the system.
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


class ConflictResolverAgent:
    """CHAI Conflict Resolver Agent — multi-agent arbitration and trade-off specialist."""

    def __init__(self, system_prompt: Optional[str] = None) -> None:
        self.system_prompt: str = system_prompt or SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def run(
        self,
        problem: str,
        context: Optional[dict] = None,
    ) -> ConflictResolutionResult:
        """Arbitrate cross-agent conflicts against the user's problem and constraints.

        Parameters
        ----------
        problem:
            The user's original problem statement.
        context:
            Collected agent outputs and Evaluator findings (e.g. ``{"all_outputs": {...}}``
            or direct per-agent dicts). Treated strictly as untrusted reference data.

        Returns
        -------
        ConflictResolutionResult
            Canonical structured result containing resolutions, unresolved conflicts,
            decision basis, assumptions, and missing information.
        """
        start_time = time.monotonic()
        has_context = bool(context)
        logger.info(f"Conflict Resolver Agent: starting arbitration (context_provided={has_context}).")

        # ---- Input validation ----
        if not problem or not problem.strip():
            logger.warning("Conflict Resolver Agent: received empty problem.")
            return self._make_failed_output("Empty problem provided. Cannot perform conflict resolution.")

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
                    logger.info("Conflict Resolver Agent: LLM returned mock response (no API key).")
                    return self._make_mock_output(problem, context)

                # Parse and validate
                result = self._parse_response(response_text)
                active_agents = self._get_active_agents(context)
                result = self._sanitize_result(result, active_agents)

                elapsed = time.monotonic() - start_time
                logger.info(f"Conflict Resolver Agent: completed in {elapsed:.2f}s (attempt {attempt}).")
                return result

            except Exception as exc:
                last_error = exc
                logger.warning(
                    f"Conflict Resolver Agent: attempt {attempt}/{_MAX_ATTEMPTS} failed — {exc!r}"
                )

        # All attempts exhausted
        logger.error(
            f"Conflict Resolver Agent: all {_MAX_ATTEMPTS} attempts failed. Last error: {last_error!r}"
        )
        return self._make_failed_output(
            f"Conflict Resolver Agent failed after {_MAX_ATTEMPTS} attempts: {last_error}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _get_active_agents(cls, context: Optional[dict]) -> List[str]:
        """Extract the names of agents actually present in the context.

        Handles both Coordinator's ``{"all_outputs": {...}}`` format and direct
        per-agent dictionaries (e.g. ``{"evaluator": {...}}``).
        """
        if not context or not isinstance(context, dict):
            return []

        source = context.get("all_outputs") if isinstance(context.get("all_outputs"), dict) else context
        active: List[str] = []
        for k, v in source.items():
            if not v:
                continue
            k_lower = str(k).strip().lower()
            if k_lower in _KNOWN_CHAI_AGENTS:
                active.append(str(k))
            elif isinstance(v, (dict, list)) and k_lower not in {
                "session_id",
                "problem",
                "timestamp",
                "metadata",
                "user_id",
                "history",
                "all_outputs",
            }:
                active.append(str(k))
        return active

    @classmethod
    def _sanitize_result(
        cls,
        result: ConflictResolutionResult,
        active_agents: List[str],
    ) -> ConflictResolutionResult:
        """Enforce that ConflictResolutionResult does not cite absent agents.

        Filters ``supporting_agents`` and ``provenance`` to only allow agents
        actually present in ``active_agents``.
        """
        if not active_agents:
            return result

        active_set = {a.strip().lower() for a in active_agents if a.strip()}
        if not active_set:
            return result

        for r in result.resolutions:
            if r.supporting_agents:
                r.supporting_agents = [
                    a for a in r.supporting_agents if a.strip().lower() in active_set
                ]

        for p in result.provenance:
            if p.supported_by:
                p.supported_by = [
                    a for a in p.supported_by if a.strip().lower() in active_set
                ]

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
        - Non-JSON-serializable objects are converted safely via ``str``.
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
                + f"\n... [TRUNCATED: context exceeded maximum limit of {max_chars} characters. Note: The supplied context was truncated due to size limits; arbitrate only based on the visible text above and do not assume omitted content.]"
            )

        return serialized

    @classmethod
    def _build_user_prompt(cls, problem: str, context: Optional[dict]) -> str:
        """Construct the user-facing prompt sent to the LLM.

        Clearly separates:
        1. Original user problem (explicitly labeled)
        2. Active participating agents list (preventing hallucinated absent agents)
        3. Reference context from other CHAI agents (untrusted reference data)
        4. Actual Conflict Resolver arbitration task
        """
        parts = [f"PROBLEM:\n{problem.strip()}"]

        active_agents = cls._get_active_agents(context)
        if active_agents:
            parts.append(
                f"ACTIVE AGENTS PRESENT IN CONTEXT: {', '.join(active_agents)}\n"
                f"CRITICAL RULE: Arbitrate ONLY among the active agents listed above. Do NOT reference, cite, or invent findings or agreement for absent agents unless they are explicitly in this active list."
            )

        context_str = cls._safe_serialize_context(context)
        if context_str:
            parts.append(f"{REFERENCE_CONTEXT_HEADER}\n\n{context_str}")

        parts.append(RESOLUTION_TASK_INSTRUCTION)
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

    def _parse_response(self, response_text: str) -> ConflictResolutionResult:
        """Parse raw LLM text into a validated ``ConflictResolutionResult``."""
        json_str = self._extract_json(response_text)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM output is not valid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object, got {type(data).__name__}")

        try:
            return ConflictResolutionResult(**data)
        except Exception as exc:
            raise ValueError(f"Schema validation failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Fallback & Mock builders
    # ------------------------------------------------------------------

    @staticmethod
    def _make_failed_output(error_message: str) -> ConflictResolutionResult:
        """Return a structured failure result adhering to the required schema."""
        return ConflictResolutionResult(
            agent="conflict_resolver",
            status=AgentStatus.FAILED,
            resolutions=[],
            unresolved_conflicts=[],
            decision_basis=[],
            assumptions=[],
            missing_information=[],
            limitations=[error_message],
            conflicts_considered=[],
            provenance=[],
        )

    @classmethod
    def _make_mock_output(
        cls,
        problem: str,
        context: Optional[dict] = None,
    ) -> ConflictResolutionResult:
        """Return a deterministic, grounded mock result when no API key is set."""
        active = cls._get_active_agents(context) if context else []
        source = (
            context.get("all_outputs")
            if (context and isinstance(context.get("all_outputs"), dict))
            else (context or {})
        )

        evaluator_data = source.get("evaluator", {})
        eval_conflicts = evaluator_data.get("conflicts", []) or evaluator_data.get("detected_contradictions", [])

        # Check if context contains explicit conflicts or if Evaluator reports none
        has_eval_conflicts = bool(eval_conflicts)
        prob_lower = problem.lower()

        # If no multi-agent context or evaluator reported no conflicts:
        if not context or (evaluator_data and not has_eval_conflicts):
            return ConflictResolutionResult(
                agent="conflict_resolver",
                status=AgentStatus.COMPLETED,
                resolutions=[],
                unresolved_conflicts=[],
                decision_basis=["No material cross-agent conflicts detected for the problem."],
                assumptions=["Individual recommendations are mutually compatible."],
                missing_information=[],
                limitations=["No conflicts required arbitration."],
                conflicts_considered=[],
                provenance=[],
            )

        # Build grounded resolutions based on evaluated conflicts
        resolutions: List[Resolution] = []
        unresolved: List[UnresolvedConflictItem] = []
        considered: List[str] = []

        # Technical conflict: Database (PostgreSQL vs MongoDB)
        if any("database" in str(c).lower() or "postgres" in str(c).lower() or "mongo" in str(c).lower() for c in eval_conflicts) or ("postgres" in prob_lower or "mongo" in prob_lower or "database" in prob_lower):
            conflict_title = "Database selection: Relational vs Document Store"
            considered.append(conflict_title)
            # Check user requirement in problem
            if "transaction" in prob_lower or "relational" in prob_lower or "acid" in prob_lower:
                pref = "PostgreSQL"
                reason = "Explicit user requirement for transactional consistency outweighs development speed."
            else:
                pref = "PostgreSQL"
                reason = "Structured relational consistency and access controls provide stronger long-term integrity."
            resolutions.append(
                Resolution(
                    conflict=conflict_title,
                    decision=f"Prefer {pref}",
                    preferred_option=pref,
                    reason=reason,
                    decision_basis=[
                        "Prioritized explicit user transactional integrity requirements over initial setup speed.",
                        "Preserved structured access control boundaries.",
                    ],
                    supporting_agents=[a for a in ["engineer", "security"] if a in active] or active[:1],
                )
            )

        # Technical / Architectural conflict: Cloud vs Edge/Offline
        if any("offline" in str(c).lower() or "connectivity" in str(c).lower() or "cloud" in str(c).lower() for c in eval_conflicts) or ("offline" in prob_lower or "intermittent" in prob_lower or "rural" in prob_lower):
            conflict_title = "Deployment architecture: Cloud-first vs Edge-first offline caching"
            considered.append(conflict_title)
            resolutions.append(
                Resolution(
                    conflict=conflict_title,
                    decision="Prefer edge-first local deployment with asynchronous cloud sync",
                    preferred_option="Edge-first local architecture",
                    reason="Explicit user constraint for unreliable/offline connectivity takes precedence over persistent cloud services.",
                    decision_basis=[
                        "Explicit user constraint requires resilience during intermittent connectivity.",
                        "Guardian identified safety risk if triage is unavailable offline.",
                    ],
                    supporting_agents=[a for a in ["researcher", "guardian", "engineer"] if a in active] or active[:1],
                )
            )

        # Safety / Guardian conflict
        if any("safety" in str(c).lower() or "guardian" in str(c).lower() or "oversight" in str(c).lower() for c in eval_conflicts):
            conflict_title = "Automated recommendations vs clinician oversight"
            considered.append(conflict_title)
            resolutions.append(
                Resolution(
                    conflict=conflict_title,
                    decision="Require mandatory clinician oversight before executing critical actions",
                    preferred_option="Clinician oversight workflow",
                    reason="Safety and ethical risk mitigation overrides autonomous operational speed.",
                    decision_basis=[
                        "Guardian identified critical risk in unmonitored decision execution.",
                        "Safety guardrails take precedence over automation convenience.",
                    ],
                    supporting_agents=[a for a in ["guardian"] if a in active] or active[:1],
                )
            )

        # Security conflict: API keys or secrets
        if any("security" in str(c).lower() or "secret" in str(c).lower() or "credential" in str(c).lower() for c in eval_conflicts):
            conflict_title = "Client-side convenience vs backend secrets isolation"
            considered.append(conflict_title)
            resolutions.append(
                Resolution(
                    conflict=conflict_title,
                    decision="Isolate all credentials in backend vault services",
                    preferred_option="Backend secrets vault",
                    reason="Security risk of secret exposure overrides developer convenience.",
                    decision_basis=[
                        "Security constraint strictly prohibits client-side API key exposure.",
                    ],
                    supporting_agents=[a for a in ["security"] if a in active] or active[:1],
                )
            )

        # Unresolved conflict: missing information (e.g. data sensitivity or deployment budget)
        if any("unspecified" in str(c).lower() or "missing" in str(c).lower() or "sensitivity" in str(c).lower() for c in eval_conflicts) or "compliance" in prob_lower:
            conflict_title = "Data residency and hosting compliance requirements"
            considered.append(conflict_title)
            unresolved.append(
                UnresolvedConflictItem(
                    conflict=conflict_title,
                    reason="Regulatory data jurisdiction and privacy sensitivity classification are not specified in problem.",
                    missing_information=[
                        "Applicable privacy regulations (e.g. HIPAA, GDPR, local health privacy)",
                        "Specific deployment country or regional jurisdiction",
                    ],
                    impact="Cannot determine whether public cloud hosting complies with local statutory obligations.",
                )
            )

        # Fallback if eval_conflicts exists but none matched our specific keywords
        if not resolutions and not unresolved and has_eval_conflicts:
            first_c = eval_conflicts[0]
            c_desc = first_c.get("conflict", str(first_c)) if isinstance(first_c, dict) else str(first_c)
            conflict_title = f"Arbitration: {c_desc}"
            considered.append(conflict_title)
            resolutions.append(
                Resolution(
                    conflict=conflict_title,
                    decision="Adopt balanced approach adhering to core constraints",
                    preferred_option="Constraint-aligned compromise",
                    reason="Arbitrated by prioritizing explicit user requirements and safety boundaries.",
                    decision_basis=["User requirements and core constraints prioritized."],
                    supporting_agents=active[:2] if len(active) >= 2 else active,
                )
            )

        return ConflictResolutionResult(
            agent="conflict_resolver",
            status=AgentStatus.COMPLETED,
            resolutions=resolutions,
            unresolved_conflicts=unresolved,
            decision_basis=[
                "Explicit user constraints take precedence over specialist preferences.",
                "Safety and security boundaries strictly maintained.",
                "Unresolved conflicts identified where critical data is missing.",
            ],
            assumptions=["Operating assumptions validated against problem constraints."],
            missing_information=[u.missing_information[0] for u in unresolved if u.missing_information] or [],
            limitations=["Arbitration grounded in available multi-agent context."],
            conflicts_considered=considered,
            provenance=[
                ProvenanceItem(
                    statement=f"Arbitrated {len(resolutions)} conflict(s) based on user constraints.",
                    supported_by=active,
                )
            ],
        )
