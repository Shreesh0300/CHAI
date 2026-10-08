"""
CHAI Reliability Monitor Agent — core implementation.

Uses the shared ``GeminiClient`` (``backend.shared.llm_client``) to evaluate
the reasoning quality, trust level, and defensibility of the synthesized CHAI
outcome based on observable workflow signals.

Design principles:
- Reuses the shared project singleton ``llm_client``.
- Anti-prompt-injection isolation for untrusted multi-agent context.
- Bounded context serialization (12k limit).
- Bounded retry logic (max 2 attempts).
- Explainable, deterministic dimension scoring and threshold evaluation.
- Proportional gate actions: PROCEED, PROCEED_WITH_LIMITATIONS, REQUEST_MORE_INFORMATION, BLOCK_OUTPUT.
- Does NOT act as an omniscient truth oracle.
- Does NOT rewrite final answers or resolve conflicts.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional, Set

from backend.shared.llm_client import llm_client
from backend.shared.logger import get_logger
from backend.agents.reliability_monitor.prompts import (
    SYSTEM_PROMPT,
    REFERENCE_CONTEXT_HEADER,
    MONITOR_TASK_INSTRUCTION,
)
from backend.agents.reliability_monitor.schemas import (
    AgentStatus,
    ReliabilityLevel,
    ReliabilityAction,
    DimensionStatus,
    ReliabilityDimension,
    UnsupportedClaimFinding,
    ReliabilityMonitorResult,
    ReliabilityMonitorOutput,
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
    "reliability_monitor",
}

# Standard dimension weights summing to 1.00
DIMENSION_WEIGHTS: Dict[str, float] = {
    "execution_completeness": 0.15,
    "evidence_grounding": 0.20,
    "internal_consistency": 0.15,
    "conflict_resolution": 0.15,
    "provenance_quality": 0.10,
    "assumption_transparency": 0.05,
    "information_completeness": 0.10,
    "overconfidence": 0.10,
}


class ReliabilityMonitorAgent:
    """CHAI Reliability Monitor Agent — reasoning-quality and trust-assessment checkpoint."""

    def __init__(self, system_prompt: Optional[str] = None) -> None:
        self.system_prompt: str = system_prompt or SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def run(
        self,
        problem: str,
        context: Optional[dict] = None,
    ) -> ReliabilityMonitorResult:
        """Assess the reliability of the CHAI workflow outcome.

        Parameters
        ----------
        problem:
            The user's original problem statement.
        context:
            Collected workflow state, agent outputs, evaluator findings,
            conflict resolutions, and the synthesized final answer.

        Returns
        -------
        ReliabilityMonitorResult
            Canonical structured assessment with explainable score, qualitative level,
            evaluated dimensions, concerns, and gate action.
        """
        start_time = time.monotonic()
        has_context = bool(context)
        logger.info(f"Reliability Monitor Agent: starting assessment (context_provided={has_context}).")

        # ---- Input validation ----
        if not problem or not problem.strip():
            logger.warning("Reliability Monitor Agent: received empty problem.")
            return self._make_failed_output("Empty problem provided. Cannot perform reliability monitoring.")

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
                    logger.info("Reliability Monitor Agent: LLM returned mock response (no API key).")
                    return self._make_mock_output(problem, context)

                # Parse and validate
                result = self._parse_response(response_text)
                result = self._enforce_scoring_policy(result, context=context)

                elapsed = time.monotonic() - start_time
                logger.info(f"Reliability Monitor Agent: completed in {elapsed:.2f}s (attempt {attempt}).")
                return result

            except Exception as exc:
                last_error = exc
                logger.warning(
                    f"Reliability Monitor Agent: attempt {attempt}/{_MAX_ATTEMPTS} failed — {exc!r}"
                )

        # All attempts exhausted
        logger.error(
            f"Reliability Monitor Agent: all {_MAX_ATTEMPTS} attempts failed. Last error: {last_error!r}"
        )
        return self._make_failed_output(
            f"Reliability Monitor Agent failed after {_MAX_ATTEMPTS} attempts: {last_error}",
            context=context,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _get_active_agents(cls, context: Optional[dict]) -> List[str]:
        """Extract the names of agents actually present in the context."""
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
                "execution_statuses",
                "agent_execution_statuses",
            }:
                active.append(str(k))
        return active

    @staticmethod
    def _safe_serialize_context(
        context: Optional[dict],
        max_chars: int = _MAX_CONTEXT_CHARS,
    ) -> Optional[str]:
        """Safely serialize workflow context dict to a bounded JSON string."""
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
                + f"\n... [TRUNCATED: context exceeded maximum limit of {max_chars} characters. Note: The supplied workflow context was truncated due to size limits; evaluate reliability only based on visible text above and do not assume omitted content.]"
            )

        return serialized

    @classmethod
    def _extract_execution_metadata(cls, context: Optional[dict]) -> dict:
        """Extract explicit workflow execution state, statuses, and final answer health."""
        metadata = {
            "executed_agents": [],
            "successful_agents": [],
            "failed_agents": [],
            "synthesizer_succeeded": True,
            "synthesizer_status": "completed",
            "final_answer_has_internal_error": False,
            "critical_agents_failed": [],
        }
        if not context or not isinstance(context, dict):
            return metadata

        statuses = context.get("execution_statuses") or context.get("agent_execution_statuses") or []
        all_outputs = context.get("all_outputs") if isinstance(context.get("all_outputs"), dict) else context

        # 1. Parse from execution_statuses
        for s in statuses:
            name = getattr(s, "agent_name", None) or (s.get("agent_name") if isinstance(s, dict) else None)
            stat = getattr(s, "status", None) or (s.get("status") if isinstance(s, dict) else None)
            if not name:
                continue
            name_str = str(name).strip().lower()
            stat_str = str(stat).strip().lower()

            if name_str not in metadata["executed_agents"]:
                metadata["executed_agents"].append(name_str)

            if stat_str in ("success", "completed"):
                if name_str not in metadata["successful_agents"]:
                    metadata["successful_agents"].append(name_str)
            elif stat_str in ("failed", "failure", "error"):
                if name_str not in metadata["failed_agents"]:
                    metadata["failed_agents"].append(name_str)

        # 2. Cross-reference with all_outputs dict
        for k, v in all_outputs.items():
            if not v or not isinstance(v, dict):
                continue
            k_lower = str(k).strip().lower()
            if k_lower in _KNOWN_CHAI_AGENTS:
                if k_lower not in metadata["executed_agents"]:
                    metadata["executed_agents"].append(k_lower)
                v_stat = str(v.get("status", "")).strip().lower()
                if v_stat in ("failed", "failure", "error"):
                    if k_lower not in metadata["failed_agents"]:
                        metadata["failed_agents"].append(k_lower)
                    if k_lower in metadata["successful_agents"]:
                        metadata["successful_agents"].remove(k_lower)
                elif v_stat in ("completed", "success"):
                    if k_lower not in metadata["successful_agents"] and k_lower not in metadata["failed_agents"]:
                        metadata["successful_agents"].append(k_lower)

        # 3. Check Synthesizer Status specifically
        synth_data = all_outputs.get("synthesizer") if isinstance(all_outputs, dict) else None
        if synth_data and isinstance(synth_data, dict):
            s_stat = str(synth_data.get("status", "")).strip().lower()
            metadata["synthesizer_status"] = s_stat
            if s_stat in ("failed", "failure", "error") or "synthesizer" in metadata["failed_agents"]:
                metadata["synthesizer_succeeded"] = False
        elif "synthesizer" in metadata["failed_agents"]:
            metadata["synthesizer_succeeded"] = False
            metadata["synthesizer_status"] = "failed"

        # 4. Check Final Answer for internal error signatures
        final_answer = (
            context.get("final_answer")
            or (synth_data.get("final_answer", "") if synth_data else "")
        )
        if final_answer and isinstance(final_answer, str):
            error_signatures = [
                "synthesis could not be completed",
                "synthesizer agent failed",
                "llm output is not valid json",
                "jsondecodeerror",
                "validationerror",
                "traceback (most recent call last)",
                "returned failed status",
                "resource_exhausted",
                "quota exceeded",
            ]
            fa_lower = final_answer.lower()
            if any(sig in fa_lower for sig in error_signatures):
                metadata["final_answer_has_internal_error"] = True
                metadata["synthesizer_succeeded"] = False

        # 5. Identify critical failed agents
        critical_names = {"researcher", "engineer", "guardian", "security", "synthesizer"}
        metadata["critical_agents_failed"] = [a for a in metadata["failed_agents"] if a in critical_names]

        return metadata

    @classmethod
    def _build_user_prompt(cls, problem: str, context: Optional[dict]) -> str:
        """Construct the prompt sent to the LLM."""
        parts = [f"PROBLEM:\n{problem.strip()}"]

        meta = cls._extract_execution_metadata(context)
        active_agents = meta["successful_agents"]
        failed_agents = meta["failed_agents"]

        if active_agents:
            parts.append(f"SUCCESSFUL WORKFLOW AGENTS: {', '.join(active_agents)}")

        if failed_agents:
            parts.append(
                f"FAILED WORKFLOW AGENTS: {', '.join(failed_agents)}\n"
                f"RULE: Because agent(s) failed, execution_completeness must NOT be 1.0, and action MUST NOT be PROCEED."
            )

        if not meta["synthesizer_succeeded"]:
            parts.append(
                f"SYNTHESIZER STATUS: FAILED ({meta['synthesizer_status']})\n"
                f"RULE: Synthesizer failed. You must NOT award execution_completeness = 1.0 and you must NOT issue PROCEED."
            )

        context_str = cls._safe_serialize_context(context)
        if context_str:
            parts.append(f"{REFERENCE_CONTEXT_HEADER}\n\n{context_str}")

        parts.append(MONITOR_TASK_INSTRUCTION)
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

    def _parse_response(self, response_text: str) -> ReliabilityMonitorResult:
        """Parse raw LLM text into a validated ``ReliabilityMonitorResult``."""
        json_str = self._extract_json(response_text)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM output is not valid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object, got {type(data).__name__}")

        try:
            return ReliabilityMonitorResult(**data)
        except Exception as exc:
            raise ValueError(f"Schema validation failed: {exc}") from exc

    @classmethod
    def _enforce_scoring_policy(
        cls,
        result: ReliabilityMonitorResult,
        context: Optional[dict] = None,
    ) -> ReliabilityMonitorResult:
        """Verify that dimension scores compute the aggregate score and align with levels and actions.
        Enforces deterministic safety and execution integrity gates that the LLM cannot override.
        """
        meta = cls._extract_execution_metadata(context)
        failed_agents = meta["failed_agents"]
        synthesizer_succeeded = meta["synthesizer_succeeded"]
        final_answer_has_error = meta["final_answer_has_internal_error"]
        critical_failed = meta["critical_agents_failed"]

        # Ensure failed_agents list in result reflects actual execution state
        for fa in failed_agents:
            if fa not in result.failed_agents:
                result.failed_agents.append(fa)

        # -------------------------------------------------------------
        # Hard Gate 1: Execution Completeness Dimension
        # -------------------------------------------------------------
        exec_dim = next((d for d in result.dimensions if d.name == "execution_completeness"), None)
        if failed_agents or not synthesizer_succeeded:
            if exec_dim:
                if not synthesizer_succeeded:
                    exec_dim.score = min(exec_dim.score, 0.35)
                    exec_dim.status = DimensionStatus.FAILED
                    exec_dim.reason = "Synthesizer failed to produce a verified structured synthesis."
                elif len(failed_agents) >= 2 or critical_failed:
                    exec_dim.score = min(exec_dim.score, 0.45)
                    exec_dim.status = DimensionStatus.FAILED
                    exec_dim.reason = f"Critical or multiple workflow agent(s) [{', '.join(failed_agents)}] failed."
                else:
                    exec_dim.score = min(exec_dim.score, 0.65)
                    exec_dim.status = DimensionStatus.WARNING
                    exec_dim.reason = f"Workflow agent(s) [{', '.join(failed_agents)}] failed during execution."
            result.execution_completeness = f"Partial ({len(failed_agents) or 1} failed)"
        elif exec_dim and not failed_agents:
            result.execution_completeness = "Complete"

        # -------------------------------------------------------------
        # Dimension Weighted Score Recomputation
        # -------------------------------------------------------------
        if result.dimensions:
            weighted_sum = sum(
                d.score * DIMENSION_WEIGHTS.get(d.name, d.weight) for d in result.dimensions
            )
            total_weight = sum(DIMENSION_WEIGHTS.get(d.name, d.weight) for d in result.dimensions)
            normalized_score = round(weighted_sum / total_weight, 2) if total_weight > 0 else 0.5
            result.reliability_score = normalized_score

        has_critical_failure = any(d.status == DimensionStatus.FAILED for d in result.dimensions)

        # -------------------------------------------------------------
        # Reliability Level Alignment
        # -------------------------------------------------------------
        if result.reliability_score is not None:
            if result.reliability_score >= 0.80 and not has_critical_failure and not result.unresolved_conflicts and synthesizer_succeeded and not critical_failed:
                result.reliability_level = ReliabilityLevel.HIGH
            elif result.reliability_score >= 0.55 and not (has_critical_failure and result.reliability_score < 0.60):
                result.reliability_level = ReliabilityLevel.MEDIUM
            else:
                result.reliability_level = ReliabilityLevel.LOW

        # -------------------------------------------------------------
        # DETERMINISTIC HARD GATES: Action Constraints
        # The LLM must NEVER override these deterministic gates.
        # -------------------------------------------------------------
        # Gate A: Synthesizer Failure / Internal Error in Final Answer
        if not synthesizer_succeeded or final_answer_has_error:
            if result.action == ReliabilityAction.PROCEED:
                result.action = ReliabilityAction.PROCEED_WITH_LIMITATIONS
            if "Synthesizer stage failed to complete successfully." not in result.concerns:
                result.concerns.append("Synthesizer stage failed to complete successfully.")
            if "Synthesis could not be verified; specialist outputs preserved." not in result.limitations:
                result.limitations.append("Synthesis could not be verified; specialist outputs preserved.")

        # Gate B: Critical Agent Failure or Multiple Agent Failures
        if len(failed_agents) >= 2 or (critical_failed and not synthesizer_succeeded):
            if result.action == ReliabilityAction.PROCEED:
                result.action = ReliabilityAction.PROCEED_WITH_LIMITATIONS
            c_msg = f"Multiple or critical agents failed [{', '.join(failed_agents)}]; PROCEED prohibited."
            if c_msg not in result.concerns:
                result.concerns.append(c_msg)
        elif failed_agents and result.action == ReliabilityAction.PROCEED:
            result.action = ReliabilityAction.PROCEED_WITH_LIMITATIONS
            f_msg = f"Agent(s) [{', '.join(failed_agents)}] failed; delivering with limitations."
            if f_msg not in result.concerns:
                result.concerns.append(f_msg)

        # Gate C: Severe Failure (< 0.45 score or critical security failure)
        if result.reliability_score is not None and result.reliability_score < 0.45:
            if "security" in failed_agents:
                result.action = ReliabilityAction.BLOCK_OUTPUT

        # Gate D: Unresolved Conflicts
        if result.unresolved_conflicts and result.action == ReliabilityAction.PROCEED:
            result.action = ReliabilityAction.PROCEED_WITH_LIMITATIONS

        return result

    # ------------------------------------------------------------------
    # Fallback & Mock builders
    # ------------------------------------------------------------------

    @classmethod
    def _make_failed_output(
        cls,
        error_message: str,
        context: Optional[dict] = None,
    ) -> ReliabilityMonitorResult:
        """Return a structured failure result adhering to the required schema."""
        meta = cls._extract_execution_metadata(context) if context else {"failed_agents": []}
        failed_list = meta.get("failed_agents", [])
        return ReliabilityMonitorResult(
            agent="reliability_monitor",
            status=AgentStatus.FAILED,
            reliability_score=None,
            reliability_level=ReliabilityLevel.UNKNOWN,
            action=ReliabilityAction.PROCEED_WITH_LIMITATIONS,
            concerns=[error_message],
            failed_agents=failed_list,
            execution_completeness=f"Partial ({len(failed_list)} failed)" if failed_list else None,
            limitations=["Reliability monitoring could not be completed; proceed with caution."],
        )

    @classmethod
    def _make_mock_output(
        cls,
        problem: str,
        context: Optional[dict] = None,
    ) -> ReliabilityMonitorResult:
        """Return a deterministic, explainable mock result when no API key is configured."""
        source = (
            context.get("all_outputs")
            if (context and isinstance(context.get("all_outputs"), dict))
            else (context or {})
        )

        final_answer = (
            context.get("final_answer")
            or source.get("synthesizer", {}).get("final_answer", "")
            if context
            else ""
        )
        prob_lower = problem.lower()
        active = cls._get_active_agents(context) if context else []

        # Track failed agents from context
        failed_agents: List[str] = []
        if context:
            statuses = context.get("execution_statuses") or context.get("agent_execution_statuses") or []
            for s in statuses:
                s_name = getattr(s, "agent_name", None) or (s.get("agent_name") if isinstance(s, dict) else None)
                s_stat = getattr(s, "status", None) or (s.get("status") if isinstance(s, dict) else None)
                if s_name and str(s_stat).lower() in ("failed", "failure", "error"):
                    failed_agents.append(str(s_name))

            for k, v in source.items():
                if isinstance(v, dict):
                    v_stat = str(v.get("status", "")).lower()
                    if v_stat == "failed" and k not in failed_agents:
                        failed_agents.append(str(k))

        # Check evaluator and conflict resolver
        eval_data = source.get("evaluator", {})
        eval_conflicts = eval_data.get("conflicts", []) or eval_data.get("detected_contradictions", [])
        cr_data = source.get("conflict_resolver", {})
        unresolved_cr = cr_data.get("unresolved_conflicts", [])
        synth_data = source.get("synthesizer", {})

        dimensions: List[ReliabilityDimension] = []
        concerns: List[str] = []
        strengths: List[str] = []
        unsupported_claims: List[UnsupportedClaimFinding] = []
        evidence_gaps: List[str] = []
        missing_info: List[str] = list(cr_data.get("missing_information", []))
        overconfidence = False

        # -------------------------------------------------------------
        # 1. Execution Completeness
        # -------------------------------------------------------------
        if not failed_agents:
            dim_exec = ReliabilityDimension(
                name="execution_completeness",
                score=1.0,
                weight=DIMENSION_WEIGHTS["execution_completeness"],
                status=DimensionStatus.PASSED,
                reason="All scheduled workflow agents executed successfully.",
                evidence=f"Active agents: {', '.join(active)}" if active else "Workflow executed.",
            )
            strengths.append("Complete execution across workflow agents.")
        else:
            # Check relevance of failed agents
            is_security_relevant = any(w in prob_lower for w in ["security", "auth", "secret", "password", "token", "encrypt"])
            is_health_relevant = any(w in prob_lower for w in ["health", "medical", "clinic", "triage", "patient", "safety"])

            if "security" in failed_agents and is_security_relevant:
                dim_exec = ReliabilityDimension(
                    name="execution_completeness",
                    score=0.35,
                    weight=DIMENSION_WEIGHTS["execution_completeness"],
                    status=DimensionStatus.FAILED,
                    reason="Security agent failed during a security-sensitive task.",
                    evidence="Security agent failure in authentication/confidentiality context.",
                )
                concerns.append("Security analysis was unavailable for a security-sensitive request.")
            elif "guardian" in failed_agents and is_health_relevant:
                dim_exec = ReliabilityDimension(
                    name="execution_completeness",
                    score=0.30,
                    weight=DIMENSION_WEIGHTS["execution_completeness"],
                    status=DimensionStatus.FAILED,
                    reason="Guardian safety agent failed during a safety-critical task.",
                    evidence="Guardian agent failure in health/triage context.",
                )
                concerns.append("Guardian safety guardrails were unavailable for a safety-critical domain.")
            else:
                dim_exec = ReliabilityDimension(
                    name="execution_completeness",
                    score=0.75,
                    weight=DIMENSION_WEIGHTS["execution_completeness"],
                    status=DimensionStatus.WARNING,
                    reason=f"Agent(s) [{', '.join(failed_agents)}] failed, but domain impact is moderate/low.",
                    evidence=f"Failed agents: {', '.join(failed_agents)}.",
                )
                concerns.append(f"Agent(s) {', '.join(failed_agents)} unavailable; secondary considerations are provisional.")
        dimensions.append(dim_exec)

        # -------------------------------------------------------------
        # 2. Evidence Grounding
        # -------------------------------------------------------------
        # Detect ungrounded statistics or fabricated metrics in final answer
        if "40% cheaper" in final_answer or "30% faster" in final_answer or "unsupported" in final_answer.lower():
            dim_ev = ReliabilityDimension(
                name="evidence_grounding",
                score=0.50,
                weight=DIMENSION_WEIGHTS["evidence_grounding"],
                status=DimensionStatus.WARNING,
                reason="Synthesized answer contains numerical claims or metrics lacking supporting agent findings.",
                evidence="Unsupported percentage metric detected in final answer.",
            )
            unsupported_claims.append(
                UnsupportedClaimFinding(
                    claim="Numerical metric assertion in final answer",
                    reason="No participating agent findings provide empirical benchmarking for this figure.",
                    severity="medium",
                )
            )
            concerns.append("Final answer includes quantitative claims unsupported by agent findings.")
        else:
            dim_ev = ReliabilityDimension(
                name="evidence_grounding",
                score=0.95,
                weight=DIMENSION_WEIGHTS["evidence_grounding"],
                status=DimensionStatus.PASSED,
                reason="Core conclusions are grounded in specialist findings.",
                evidence="Recommendations correspond to documented agent positions.",
            )
            strengths.append("High degree of evidentiary grounding across recommendations.")
        dimensions.append(dim_ev)

        # -------------------------------------------------------------
        # 3. Internal Consistency & False Consensus
        # -------------------------------------------------------------
        if ("all agents agree" in final_answer.lower() or "complete alignment" in final_answer.lower()) and eval_conflicts:
            dim_const = ReliabilityDimension(
                name="internal_consistency",
                score=0.40,
                weight=DIMENSION_WEIGHTS["internal_consistency"],
                status=DimensionStatus.FAILED,
                reason="Final answer claims unanimous consensus despite documented agent disagreements.",
                evidence="Synthesizer claims full agreement while Evaluator recorded conflicts.",
            )
            concerns.append("False consensus: final answer asserts complete agreement despite documented conflicts.")
        else:
            dim_const = ReliabilityDimension(
                name="internal_consistency",
                score=0.95,
                weight=DIMENSION_WEIGHTS["internal_consistency"],
                status=DimensionStatus.PASSED,
                reason="No internal contradictions or false consensus detected.",
                evidence=None,
            )
        dimensions.append(dim_const)

        # -------------------------------------------------------------
        # 4. Conflict Resolution
        # -------------------------------------------------------------
        unresolved_list: List[str] = []
        if unresolved_cr:
            for u in unresolved_cr:
                desc = u.get("conflict", str(u)) if isinstance(u, dict) else str(u)
                unresolved_list.append(desc)
            dim_cr = ReliabilityDimension(
                name="conflict_resolution",
                score=0.55,
                weight=DIMENSION_WEIGHTS["conflict_resolution"],
                status=DimensionStatus.WARNING,
                reason=f"{len(unresolved_list)} conflict(s) remain unresolved due to missing data.",
                evidence=f"Unresolved: {', '.join(unresolved_list)}",
            )
            concerns.append(f"Unresolved conflict: {unresolved_list[0]}")
        elif eval_conflicts and not cr_data:
            dim_cr = ReliabilityDimension(
                name="conflict_resolution",
                score=0.50,
                weight=DIMENSION_WEIGHTS["conflict_resolution"],
                status=DimensionStatus.WARNING,
                reason="Evaluator detected conflicts but Conflict Resolver did not execute.",
                evidence="Missing conflict arbitration step.",
            )
            concerns.append("Evaluator-detected conflicts lack formal Conflict Resolver arbitration.")
        else:
            dim_cr = ReliabilityDimension(
                name="conflict_resolution",
                score=1.0,
                weight=DIMENSION_WEIGHTS["conflict_resolution"],
                status=DimensionStatus.PASSED,
                reason="No unmitigated conflicts; all disagreements were arbitrated.",
                evidence=None,
            )
            strengths.append("Conflicts were successfully arbitrated and reconciled.")
        dimensions.append(dim_cr)

        # -------------------------------------------------------------
        # 5. Provenance Quality
        # -------------------------------------------------------------
        provenance_present = bool(synth_data.get("provenance") or synth_data.get("supporting_findings"))
        if provenance_present or active:
            dim_prov = ReliabilityDimension(
                name="provenance_quality",
                score=0.90,
                weight=DIMENSION_WEIGHTS["provenance_quality"],
                status=DimensionStatus.PASSED,
                reason="Key conclusions maintain traceability to contributing specialists.",
                evidence="Traceability items present.",
            )
        else:
            dim_prov = ReliabilityDimension(
                name="provenance_quality",
                score=0.60,
                weight=DIMENSION_WEIGHTS["provenance_quality"],
                status=DimensionStatus.WARNING,
                reason="Provenance traceability is sparse or absent.",
                evidence="No provenance mappings found in context.",
            )
            concerns.append("Conclusions lack explicit provenance attribution.")
        dimensions.append(dim_prov)

        # -------------------------------------------------------------
        # 6. Assumption Transparency
        # -------------------------------------------------------------
        dim_assump = ReliabilityDimension(
            name="assumption_transparency",
            score=0.90,
            weight=DIMENSION_WEIGHTS["assumption_transparency"],
            status=DimensionStatus.PASSED,
            reason="Operational assumptions are transparently stated in workflow findings.",
            evidence=None,
        )
        dimensions.append(dim_assump)

        # -------------------------------------------------------------
        # 7. Information Completeness
        # -------------------------------------------------------------
        if any(w in prob_lower for w in ["unknown", "compliance", "unspecified"]) or missing_info:
            if not missing_info:
                missing_info.append("Target compliance jurisdiction or data classification")
            dim_info = ReliabilityDimension(
                name="information_completeness",
                score=0.50,
                weight=DIMENSION_WEIGHTS["information_completeness"],
                status=DimensionStatus.WARNING,
                reason="Material information gaps prevent unconditional recommendation.",
                evidence=f"Missing: {', '.join(missing_info)}",
            )
            concerns.append(f"Missing information: {missing_info[0]}")
        else:
            dim_info = ReliabilityDimension(
                name="information_completeness",
                score=0.95,
                weight=DIMENSION_WEIGHTS["information_completeness"],
                status=DimensionStatus.PASSED,
                reason="Available context is adequate for the requested decision scope.",
                evidence=None,
            )
        dimensions.append(dim_info)

        # -------------------------------------------------------------
        # 8. Overconfidence Detection
        # -------------------------------------------------------------
        has_absolute_words = any(w in final_answer.lower() for w in ["unquestionably", "definitely the best", "guaranteed to succeed"])
        if has_absolute_words and (unresolved_list or missing_info or failed_agents):
            overconfidence = True
            dim_over = ReliabilityDimension(
                name="overconfidence",
                score=0.40,
                weight=DIMENSION_WEIGHTS["overconfidence"],
                status=DimensionStatus.FAILED,
                reason="Final answer uses absolute certainty assertions despite unresolved trade-offs or incomplete context.",
                evidence="Absolute phrasing ('unquestionably' / 'definitely the best') detected.",
            )
            concerns.append("Overconfidence: categorical language used despite unresolved trade-offs.")
        else:
            dim_over = ReliabilityDimension(
                name="overconfidence",
                score=0.95,
                weight=DIMENSION_WEIGHTS["overconfidence"],
                status=DimensionStatus.PASSED,
                reason="Tone is measured and calibrated to available evidence.",
                evidence=None,
            )
        dimensions.append(dim_over)

        # -------------------------------------------------------------
        # Aggregate Score, Level, and Gate Action
        # -------------------------------------------------------------
        weighted_score = sum(d.score * d.weight for d in dimensions)
        score = round(weighted_score, 2)

        has_failed_dim = any(d.status == DimensionStatus.FAILED for d in dimensions)

        if score >= 0.80 and not has_failed_dim and not unresolved_list and not missing_info:
            level = ReliabilityLevel.HIGH
            action = ReliabilityAction.PROCEED
            rec = "Output is well-supported and verified. Proceed with delivery."
        elif score >= 0.55 and not (has_failed_dim and score < 0.60):
            level = ReliabilityLevel.MEDIUM
            if missing_info and (len(missing_info) >= 2 or any("jurisdiction" in m.lower() or "compliance" in m.lower() for m in missing_info)):
                action = ReliabilityAction.REQUEST_MORE_INFORMATION
                rec = "Request clarification from user on critical missing variables before finalizing architecture."
            elif unresolved_list:
                action = ReliabilityAction.PROCEED_WITH_LIMITATIONS
                rec = "Deliver output with explicit disclosure of unresolved trade-offs."
            else:
                action = ReliabilityAction.PROCEED_WITH_LIMITATIONS
                rec = "Deliver output with explicit caveats and limitation disclosure."
        else:
            level = ReliabilityLevel.LOW
            if score < 0.45 or (has_failed_dim and "security" in failed_agents):
                action = ReliabilityAction.BLOCK_OUTPUT
                rec = "Block delivery: severe reliability or safety/security failure."
            elif missing_info:
                action = ReliabilityAction.REQUEST_MORE_INFORMATION
                rec = "Missing information critically impedes reliable decision. Request additional context."
            else:
                action = ReliabilityAction.PROCEED_WITH_LIMITATIONS
                rec = "Deliver output with prominent warnings regarding low reliability."

        mock_res = ReliabilityMonitorResult(
            agent="reliability_monitor",
            status=AgentStatus.COMPLETED,
            reliability_score=score,
            reliability_level=level,
            action=action,
            dimensions=dimensions,
            strengths=strengths,
            concerns=concerns,
            failed_agents=failed_agents,
            unresolved_conflicts=unresolved_list,
            unsupported_claims=unsupported_claims,
            evidence_gaps=evidence_gaps,
            assumptions=["Operating parameters evaluated against visible workflow context."],
            missing_information=missing_info,
            provenance_quality="High" if provenance_present else "Moderate",
            execution_completeness="Complete" if not failed_agents else f"Partial ({len(failed_agents)} failed)",
            overconfidence_detected=overconfidence,
            limitations=[
                "Reliability assessment grounded strictly in observable workflow telemetry.",
            ],
            recommendation=rec,
        )
        return cls._enforce_scoring_policy(mock_res, context=context)
