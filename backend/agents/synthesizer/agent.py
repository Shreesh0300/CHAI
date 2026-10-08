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
# output aggregates (Researcher, Strategist, Engineer, Guardian, Security, Evaluator, Conflict Resolver),
# so an allocation of 60,000 characters safely accommodates all multi-agent payloads without truncation.
_MAX_CONTEXT_CHARS: int = 60000

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
    if p in {"hello", "hi", "hey"}:
        return True
    simple_patterns = [
        "what is a python list",
        "what is python list",
        "explain python list",
        "what is a list in python",
        "what is 2+2",
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
                if result.status == AgentStatus.COMPLETED:
                    active_agents = self._get_active_agents(context)
                    result = self._sanitize_result(result, active_agents)

                    elapsed = time.monotonic() - start_time
                    logger.info(f"Synthesizer Agent: completed in {elapsed:.2f}s (attempt {attempt}).")
                    return result
                else:
                    logger.warning(
                        f"Synthesizer Agent: attempt {attempt}/{_MAX_ATTEMPTS} returned structured failure."
                    )
                    if attempt == _MAX_ATTEMPTS:
                        result.error = f"Synthesizer Agent failed after {_MAX_ATTEMPTS} attempts: structured output could not be parsed"
                        return result

            except Exception as exc:
                last_error = exc
                logger.warning(
                    f"Synthesizer Agent: attempt {attempt}/{_MAX_ATTEMPTS} failed — {exc!r}"
                )

        # All attempts exhausted
        logger.error(f"Synthesizer Agent: all {_MAX_ATTEMPTS} attempts failed. Last error: {last_error!r}")
        return self._make_failed_output(
            error_message=f"Synthesizer Agent failed after {_MAX_ATTEMPTS} attempts: {last_error}" if last_error else "Synthesizer structured output could not be parsed",
            error_type="llm_provider_error" if last_error else "invalid_structured_output",
            retryable=False,
        )

    async def synthesize(self, problem: str, context: Optional[dict] = None, **kwargs: Any) -> SynthesizerResult:
        """Alias for run to support polymorphic synthesize calls across workflows."""
        merged_context = dict(context) if isinstance(context, dict) else {}
        if kwargs:
            merged_context.update(kwargs)
        return await self.run(problem, context=merged_context or None)

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

        # Highlight external verified sources if available
        retrieved_sources = None
        if isinstance(context, dict):
            retrieved_sources = context.get("retrieved_sources")
            if not retrieved_sources and "all_outputs" in context and isinstance(context["all_outputs"], dict):
                r_out = context["all_outputs"].get("researcher") or {}
                if isinstance(r_out, dict):
                    retrieved_sources = r_out.get("sources") or r_out.get("source_references")
        if retrieved_sources:
            src_list = []
            for s in retrieved_sources:
                if isinstance(s, dict):
                    src_list.append(s.get("title") or s.get("url") or str(s))
                else:
                    src_list.append(str(s))
            if src_list:
                parts.append(
                    "EXTERNAL VERIFIED SOURCES (Information Acquisition & Research):\n"
                    + "\n".join(f"- {s}" for s in src_list[:12])
                    + "\nRULE: Explicitly ground factual statements in these external sources where appropriate. Preserve provenance without fabricating citations."
                )

        context_str = cls._safe_serialize_context(context)
        if context_str:
            parts.append(f"{REFERENCE_CONTEXT_HEADER}\n\n{context_str}")

        parts.append(SYNTHESIS_TASK_INSTRUCTION)
        return "\n\n".join(parts)

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract candidate JSON from raw LLM text, tolerating markdown fences and outer text."""
        stripped = text.strip()
        first_brace = stripped.find("{")
        last_brace = stripped.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return stripped[first_brace:last_brace + 1]

        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return stripped

    @staticmethod
    def _normalize_and_repair_json(text: str) -> str:
        """Normalize and repair common LLM JSON transport and encoding issues safely.

        Handles:
        1. Invalid backslash escape sequences (e.g., LaTeX \\alpha, file paths C:\\Users, regex \\d).
        2. Raw unescaped control characters inside JSON strings (e.g. literal newlines, tabs).
        3. Trailing commas before closing braces/brackets.
        """
        if not text or not text.strip():
            return text

        # Step 1: Repair invalid backslash escapes and raw control characters inside string literals.
        # Valid JSON escapes: \", \\, \/, \b, \f, \n, \r, \t, \uXXXX
        result = []
        i = 0
        n = len(text)
        in_string = False

        while i < n:
            c = text[i]

            if c == '"':
                num_backslashes = 0
                j = i - 1
                while j >= 0 and text[j] == '\\':
                    num_backslashes += 1
                    j -= 1
                if num_backslashes % 2 == 0:
                    in_string = not in_string
                result.append(c)
                i += 1
            elif in_string:
                if c == '\\':
                    if i + 1 < n:
                        next_c = text[i + 1]
                        if next_c in ('"', '\\', '/', 'b', 'f', 'n', 'r', 't'):
                            result.append('\\')
                            result.append(next_c)
                            i += 2
                        elif next_c == 'u':
                            if i + 5 < n and all(text[i + 2 + k] in "0123456789abcdefABCDEF" for k in range(4)):
                                result.append(text[i:i + 6])
                                i += 6
                            else:
                                result.append('\\\\')
                                i += 1
                        else:
                            result.append('\\\\')
                            i += 1
                    else:
                        result.append('\\\\')
                        i += 1
                elif c == '\n':
                    result.append('\\n')
                    i += 1
                elif c == '\r':
                    result.append('\\r')
                    i += 1
                elif c == '\t':
                    result.append('\\t')
                    i += 1
                elif ord(c) < 32:
                    result.append(f"\\u{ord(c):04x}")
                    i += 1
                else:
                    result.append(c)
                    i += 1
            else:
                result.append(c)
                i += 1

        cleaned = "".join(result)

        # Step 2: Remove trailing commas before } or ]
        cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)

        return cleaned

    @staticmethod
    def _attempt_repair_unterminated_json(text: str) -> Optional[dict]:
        """Attempt bounded recovery for truncated or unterminated JSON structures."""
        cleaned = text.strip()
        if not cleaned.startswith("{"):
            first_brace = cleaned.find("{")
            if first_brace != -1:
                cleaned = cleaned[first_brace:]
            else:
                return None

        in_string = False
        for i, c in enumerate(cleaned):
            if c == '"':
                num_b = 0
                j = i - 1
                while j >= 0 and cleaned[j] == '\\':
                    num_b += 1
                    j -= 1
                if num_b % 2 == 0:
                    in_string = not in_string

        recovery_candidate = cleaned
        if in_string:
            recovery_candidate += '"'

        open_curly = recovery_candidate.count("{") - recovery_candidate.count("}")
        open_square = recovery_candidate.count("[") - recovery_candidate.count("]")

        if open_square > 0:
            recovery_candidate += "]" * open_square
        if open_curly > 0:
            recovery_candidate += "}" * open_curly

        try:
            data = json.loads(recovery_candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        return None

    @staticmethod
    def _extract_fields_fallback(text: str) -> Optional[dict]:
        """Bounded fallback extraction when JSON structure cannot be restored."""
        match = re.search(
            r'"final_answer"\s*:\s*"(.*?)(?:"\s*,\s*"(?:key_decisions|supporting_findings|resolved_conflicts|unresolved_conflicts|limitations|assumptions|missing_information|provenance)"|\s*\}\s*$)',
            text,
            re.DOTALL,
        )
        if match:
            fa_text = match.group(1).replace('\\"', '"').replace('\\n', '\n')
            return {
                "agent": "synthesizer",
                "status": "completed",
                "final_answer": fa_text,
                "key_decisions": [],
                "supporting_findings": [],
                "resolved_conflicts": [],
                "unresolved_conflicts": [],
                "limitations": ["Parsed via bounded field extraction fallback."],
                "assumptions": [],
                "missing_information": [],
                "provenance": [],
            }
        return None

    def _parse_response(self, response_text: str) -> SynthesizerResult:
        """Parse raw LLM text into a validated SynthesizerResult using bounded recovery."""
        candidate = self._extract_json(response_text)

        # 1. Direct parse attempt
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return SynthesizerResult(**data)
        except Exception:
            pass

        # 2. Normalize transport / format issues (escapes, control chars, trailing commas)
        normalized = candidate
        try:
            normalized = self._normalize_and_repair_json(candidate)
            data = json.loads(normalized)
            if isinstance(data, dict):
                return SynthesizerResult(**data)
        except Exception:
            pass

        # 3. Bounded recovery attempt (unterminated strings / unclosed structures)
        try:
            data = self._attempt_repair_unterminated_json(normalized)
            if data and isinstance(data, dict):
                return SynthesizerResult(**data)
        except Exception:
            pass

        # 4. Bounded field extraction fallback
        try:
            data = self._extract_fields_fallback(response_text)
            if data and isinstance(data, dict):
                return SynthesizerResult(**data)
        except Exception:
            pass

        # 5. All recovery attempts failed -> Structured Synthesizer failure
        logger.warning("Synthesizer Agent: structured output parsing failed after all recovery attempts.")
        return self._make_failed_output(
            error_message="Synthesizer structured output could not be parsed",
            error_type="invalid_structured_output",
            retryable=False,
        )

    # ------------------------------------------------------------------
    # Fallback and mock builders
    # ------------------------------------------------------------------

    @staticmethod
    def _make_failed_output(
        error_message: str,
        error_type: str = "invalid_structured_output",
        retryable: bool = False,
    ) -> SynthesizerResult:
        """Return a minimal SynthesizerResult representing a structured failure."""
        return SynthesizerResult(
            agent="synthesizer",
            status=AgentStatus.FAILED,
            final_answer="CHAI could not complete the final synthesis reliably for this request.",
            limitations=["Synthesizer structured output could not be completed; specialist analysis preserved."],
            error_type=error_type,
            error=error_message,
            retryable=retryable,
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
        def _to_dict(val):
            if hasattr(val, "model_dump"):
                return val.model_dump()
            if isinstance(val, dict):
                return val
            return {}

        researcher_data = _to_dict(source.get("researcher"))
        engineer_data = _to_dict(source.get("engineer"))
        guardian_data = _to_dict(source.get("guardian"))
        security_data = _to_dict(source.get("security"))
        evaluator_data = _to_dict(source.get("evaluator"))
        conflict_data = _to_dict(source.get("conflict_resolver"))
        strategist_data = _to_dict(source.get("strategist"))

        # Build unified response grounded in inputs
        constraints = researcher_data.get("constraints", [])
        architecture = engineer_data.get("architecture") or engineer_data.get("technical_architecture", "Architecture not specified")
        priorities = strategist_data.get("priorities", [])

        # Conflict resolution handling
        resolved_conflicts: List[ResolvedConflict] = []
        unresolved_conflicts: List[UnresolvedConflict] = []

        if conflict_data and isinstance(conflict_data, dict):
            c_status = str(conflict_data.get("status", "")).lower()

            # 1. Process explicit resolutions list if present
            raw_resolutions = conflict_data.get("resolutions") or []
            if isinstance(raw_resolutions, list) and raw_resolutions:
                for r in raw_resolutions:
                    if isinstance(r, dict):
                        c_title = r.get("conflict") or r.get("issue")
                        c_res = r.get("resolution") or r.get("decision")
                    else:
                        c_title = getattr(r, "conflict", None)
                        c_res = getattr(r, "resolution", None) or getattr(r, "decision", None)
                    if c_title and c_res:
                        resolved_conflicts.append(
                            ResolvedConflict(
                                conflict=str(c_title),
                                resolution=str(c_res),
                                source="conflict_resolver",
                            )
                        )
            elif c_status in ("resolved", "completed", "success"):
                legacy_conf = conflict_data.get("conflict")
                legacy_res = conflict_data.get("resolution")
                if legacy_conf and legacy_res:
                    resolved_conflicts.append(
                        ResolvedConflict(
                            conflict=str(legacy_conf),
                            resolution=str(legacy_res),
                            source="conflict_resolver",
                        )
                    )

            # 2. Process explicit unresolved conflicts list if present
            raw_unresolved = conflict_data.get("unresolved_conflicts") or []
            if isinstance(raw_unresolved, list) and raw_unresolved:
                for u in raw_unresolved:
                    if isinstance(u, dict):
                        u_title = u.get("conflict") or u.get("issue")
                        u_reason = u.get("reason_unresolved") or u.get("reason")
                        u_impact = u.get("impact")
                    else:
                        u_title = getattr(u, "conflict", None)
                        u_reason = getattr(u, "reason_unresolved", None) or getattr(u, "reason", None)
                        u_impact = getattr(u, "impact", None)
                    if u_title and u_reason:
                        unresolved_conflicts.append(
                            UnresolvedConflict(
                                conflict=str(u_title),
                                reason_unresolved=str(u_reason),
                                impact=str(u_impact) if u_impact else "Implementation must be decided based on specific field constraints.",
                            )
                        )
            elif c_status == "unresolved":
                legacy_u_conf = conflict_data.get("issue") or conflict_data.get("conflict")
                legacy_u_reason = conflict_data.get("reason_unresolved") or conflict_data.get("reason")
                if legacy_u_conf and legacy_u_reason:
                    unresolved_conflicts.append(
                        UnresolvedConflict(
                            conflict=str(legacy_u_conf),
                            reason_unresolved=str(legacy_u_reason),
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

        # Build comprehensive multi-section Markdown deliverable for complex queries
        sections = [
            f"## Executive Summary\n"
            f"This proposal establishes a comprehensive, resilient solution for '{problem}'. "
            f"By unifying strategic priorities, technical architecture, safety guardrails, defensive cybersecurity controls, "
            f"and arbitrated trade-off resolutions, the design delivers a cohesive operational framework tailored to the problem."
        ]

        # Strategic priorities
        strat_summary = strategist_data.get("strategy") or strategist_data.get("strategy_overview") or ""
        if priorities or strat_summary:
            strat_body = f"{strat_summary}\n\n" if strat_summary else ""
            if priorities:
                strat_body += "### Strategic Priorities:\n" + "\n".join(f"- {p}" for p in priorities)
            sections.append(f"## Recommended Solution & Strategy\n{strat_body.strip()}")
        else:
            sections.append(
                f"## Recommended Solution & Strategy\n"
                f"The core strategy centers on a phased deployment model, balancing time-to-value, "
                f"operational reliability, and user trust. Foundational capabilities are prioritized to establish "
                f"a dependable baseline before expanding into advanced operational capabilities."
            )

        # Technical Architecture
        arch_summary = ""
        if isinstance(architecture, dict):
            arch_summary = architecture.get("overview") or str(architecture)
        elif architecture and architecture != "Architecture not specified":
            arch_summary = str(architecture)
        components = engineer_data.get("components", [])
        tech_recs = engineer_data.get("technology_recommendations", [])
        if arch_summary or components or tech_recs:
            eng_body = f"{arch_summary}\n\n" if arch_summary else ""
            if components:
                eng_body += "### Core Architecture Components:\n" + "\n".join(f"- {c}" for c in components)
            if tech_recs:
                eng_body += "\n\n### Technology Recommendations:\n"
                for tr in tech_recs[:4]:
                    if isinstance(tr, dict):
                        eng_body += f"- **{tr.get('technology', 'Tech')}**: {tr.get('purpose', '')} ({tr.get('rationale', '')})\n"
                    else:
                        eng_body += f"- {tr}\n"
            sections.append(f"## Technical Architecture & System Design\n{eng_body.strip()}")

        # Security & Safety
        sec_summary = security_data.get("security_summary") or ""
        sec_threats = security_data.get("threats") or []
        sec_mitigations = security_data.get("mitigations") or []
        guard_assessment = guardian_data.get("safety_assessment") or guardian_data.get("summary") or ""
        guard_mitigations = guardian_data.get("recommended_mitigations") or guardian_data.get("mitigations") or []

        if sec_summary or guard_assessment or sec_threats or guard_mitigations:
            sec_body = []
            if sec_summary:
                sec_body.append(f"### Cybersecurity Defense Posture\n{sec_summary}")
            if sec_threats:
                sec_body.append("Key Threat Vectors Identified:\n" + "\n".join(f"- {t}" for t in sec_threats[:4]))
            if sec_mitigations:
                sec_body.append("Security Mitigations:\n" + "\n".join(f"- {m}" for m in sec_mitigations[:4]))
            if guard_assessment:
                sec_body.append(f"### Safety, Privacy & Ethical Guardrails\n{guard_assessment}")
            if guard_mitigations:
                sec_body.append("Safety & Compliance Controls:\n" + "\n".join(f"- {gm}" for gm in guard_mitigations[:4]))
            sections.append(f"## Security, Privacy & Safety Guardrails\n" + "\n\n".join(sec_body))

        # Trade-offs & Conflict Resolutions
        if resolved_conflicts or unresolved_conflicts:
            tradeoff_body = []
            if resolved_conflicts:
                tradeoff_body.append("### Arbitrated Trade-Offs & Decisions (Conflict Resolver):")
                for rc in resolved_conflicts:
                    tradeoff_body.append(f"- **{rc.conflict}**: Reconciled as *{rc.resolution}* (Source: {rc.source}).")
            if unresolved_conflicts:
                tradeoff_body.append("### Unresolved Trade-Offs Requiring Stakeholder Decision:")
                for uc in unresolved_conflicts:
                    tradeoff_body.append(f"- **{uc.conflict}**: {uc.reason_unresolved} (Impact: {uc.impact})")
            sections.append(f"## Trade-offs & Reconciled Decisions\n" + "\n\n".join(tradeoff_body))

        # Risks & Mitigations
        risks = engineer_data.get("technical_risks", [])
        if risks:
            risk_body = "### Technical & Operational Risks:\n"
            for r in risks[:4]:
                if isinstance(r, dict):
                    risk_body += f"- **{r.get('risk', 'Risk')}**: Impact: {r.get('impact', 'N/A')} | Mitigation: {r.get('mitigation', 'N/A')}\n"
            sections.append(f"## Risks & Mitigations\n{risk_body.strip()}")

        # Implementation Roadmap
        roadmap = strategist_data.get("milestones", []) or engineer_data.get("implementation_plan", [])
        if roadmap:
            road_body = "### Phased Implementation Roadmap:\n"
            for step in roadmap[:4]:
                if isinstance(step, dict):
                    road_body += f"- **{step.get('milestone') or step.get('phase', 'Phase')}**: {step.get('description') or step.get('target', '')}\n"
                else:
                    road_body += f"- {step}\n"
            sections.append(f"## Implementation Roadmap\n{road_body.strip()}")

        # Limitations & Gaps
        if limitations:
            lim_body = "### System Boundaries & Identified Gaps:\n" + "\n".join(f"- {l}" for l in limitations)
            sections.append(f"## Limitations & Evidence Gaps\n{lim_body}")

        # Sources & Provenance
        sources = researcher_data.get("sources", []) or researcher_data.get("source_references", [])
        if sources:
            src_body = "### External References & Benchmarks:\n"
            for s in sources[:5]:
                if isinstance(s, dict):
                    src_body += f"- [{s.get('title', 'Source')}]({s.get('url', '#')})\n"
                else:
                    src_body += f"- {s}\n"
            sections.append(f"## Sources & Provenance\n{src_body.strip()}")

        final_answer_text = "\n\n".join(sections)

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
            final_answer=final_answer_text,
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
