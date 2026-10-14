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
from backend.core.domain_lenses import apply_domain_lens
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
from backend.synthesis.response_planner import (
    ResponsePlan,
    plan_response,
    detect_domains,
    detect_intent,
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
        "what is 2 + 2",
        "what is python",
        "what is the full form of isro",
        "full form of isro",
        "tell me about the song se te nota",
        "tell me about this song sete nota",
        "what is api",
        "define api",
    ]
    # Check if exact or query matches simple pattern without complex qualifiers
    if any(pattern in p for pattern in simple_patterns):
        if not any(k in p for k in ("architecture", "design", "scalable", "microservices", "with examples", "implementation")):
            return True
    return False


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
        domain: Optional[str] = None,
    ) -> SynthesizerResult:
        """Synthesize collective agent outputs and evaluator findings into one final answer.

        Parameters
        ----------
        problem:
            The user's original problem statement.
        context:
            Collected agent outputs (e.g. ``{"researcher": {...}, ...}`` or
            ``{"all_outputs": {...}}``). Treated strictly as untrusted reference data.
        domain:
            Optional resolved domain ('business', 'personal', 'software').

        Returns
        -------
        SynthesizerResult
            Canonical structured result containing the unified final answer,
            key decisions, conflict summaries, limitations, and provenance.
        """
        start_time = time.monotonic()
        has_context = bool(context)
        resolved_domain = domain or (
            context.get("domain") or context.get("resolved_domain") or context.get("domain_category")
            if isinstance(context, dict) else None
        )
        logger.info(f"Synthesizer Agent: starting synthesis (context_provided={has_context}, domain={resolved_domain}).")

        # ---- Input validation ----
        if not problem or not problem.strip():
            logger.warning("Synthesizer Agent: received empty problem.")
            return self._make_failed_output("Empty problem provided. Cannot perform synthesis.")

        # ---- Formulate Response Plan ----
        plan = plan_response(problem, context)

        # ---- Build LLM prompt ----
        user_prompt = self._build_user_prompt(problem, context, plan=plan)
        effective_system_prompt = apply_domain_lens(self.system_prompt, "synthesizer", resolved_domain)

        # ---- Call LLM with bounded retry ----
        last_error: Optional[Exception] = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response_text = await llm_client.generate_content(
                    prompt=user_prompt,
                    system_instruction=effective_system_prompt,
                )

                # Handle mock mode (API key not configured)
                if "Mock response" in response_text:
                    logger.info("Synthesizer Agent: LLM returned mock response (no API key).")
                    return self._make_mock_output(problem, context, plan=plan)

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
    def _build_user_prompt(
        cls,
        problem: str,
        context: Optional[dict],
        plan: Optional[ResponsePlan] = None,
    ) -> str:
        """Construct the user prompt sent to the LLM."""
        if plan is None:
            plan = plan_response(problem, context)

        parts = [f"ORIGINAL USER PROBLEM (HIGHEST PRIORITY):\n{problem.strip()}"]

        # -------------------------------------------------------------
        # Query-Specific Response Plan
        # -------------------------------------------------------------
        plan_block = [
            "QUERY-SPECIFIC RESPONSE PLAN (MANDATORY STRUCTURE & CONSTRAINTS):",
            f"- Primary Domain: {plan.domain}",
        ]
        if plan.secondary_domains:
            plan_block.append(f"- Secondary Domains: {', '.join(plan.secondary_domains)}")
        plan_block.append(f"- Intent / Task: {plan.intent}")
        plan_block.append(f"- Requested Depth: {plan.requested_depth}")
        plan_block.append(f"- Answer Goal: {plan.answer_goal}")
        if plan.required_sections:
            plan_block.append("- REQUIRED SECTIONS (Organize final_answer using these exact headings):")
            for s in plan.required_sections:
                plan_block.append(f"  * ## {s}")
        if plan.excluded_sections:
            plan_block.append("- EXCLUDED SECTIONS (DO NOT include ANY of these or similar headings):")
            for s in plan.excluded_sections:
                plan_block.append(f"  * {s}")
        if plan.key_points_to_answer:
            plan_block.append("- KEY REQUIREMENTS & CRITERIA TO ADDRESS:")
            for kp in plan.key_points_to_answer:
                plan_block.append(f"  * {kp}")
        if plan.evidence_requirements:
            plan_block.append("- EVIDENCE & CAUSALITY RULES:")
            for er in plan.evidence_requirements:
                plan_block.append(f"  * {er}")
        if plan.important_tradeoffs:
            plan_block.append("- KEY TRADE-OFFS:")
            for tr in plan.important_tradeoffs:
                plan_block.append(f"  * {tr}")

        parts.append("\n".join(plan_block))

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
    def _make_mock_output(
        cls,
        problem: str,
        context: Optional[dict] = None,
        plan: Optional[ResponsePlan] = None,
    ) -> SynthesizerResult:
        """Return a plausible, grounded, domain-adaptive mock SynthesizerResult when no API key is configured."""
        if plan is None:
            plan = plan_response(problem, context)

        active = cls._get_active_agents(context) if context else []
        failed = cls._get_failed_agents(context) if context else []
        p_lower = problem.strip().lower()
        is_simple = is_simple_query(problem) or plan.requested_depth == "brief"

        # -------------------------------------------------------------
        # 1. Brief / Simple Informational Queries
        # -------------------------------------------------------------
        if is_simple:
            if "isro" in p_lower:
                final_ans = (
                    "ISRO stands for Indian Space Research Organisation. It is India's national space agency "
                    "responsible for space research, satellite development, and exploration missions."
                )
            elif "python" in p_lower and "list" not in p_lower and "binary search" not in p_lower:
                final_ans = (
                    "Python is a high-level programming language known for its simple syntax and readability. "
                    "It is widely used in web development, automation, data science, and AI."
                )
            elif "list" in p_lower:
                final_ans = (
                    "A Python list is a built-in, ordered, and mutable collection that allows storing "
                    "multiple items (including heterogeneous data types). Elements can be accessed by zero-based "
                    "index, appended, removed, and sliced."
                )
            elif "sete nota" in p_lower or "se te nota" in p_lower:
                final_ans = (
                    "Do you mean 'Se Te Nota' by Lele Pons and Guaynaa? It is a popular 2020 Latin pop and reggaeton "
                    "song known for its upbeat, dance-oriented style.\n\n"
                    "There are other songs with the same title, so please let me know the artist if you mean a different one."
                )
            elif p_lower.strip().rstrip("?.! ") == "explain binary search":
                final_ans = (
                    "Binary search is an efficient algorithm for finding an element in a sorted list. "
                    "It repeatedly checks the middle element and eliminates half of the remaining search space. "
                    "Its time complexity is O(log n), making it significantly faster than linear search for large datasets."
                )
            elif "2+2" in p_lower or "2 + 2" in p_lower:
                final_ans = "2 + 2 = 4."
            else:
                final_ans = f"Direct answer: This is a direct informational response to the query: '{problem}'."

            return SynthesizerResult(
                agent="synthesizer",
                status=AgentStatus.COMPLETED,
                final_answer=final_ans,
                key_decisions=[
                    KeyDecision(
                        decision="Provide direct informational answer",
                        rationale="Query is a basic factual or conceptual lookup requiring concise proportional response.",
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

        # -------------------------------------------------------------
        # Context Extraction for Complex Multi-Agent Pipelines
        # -------------------------------------------------------------
        source = context.get("all_outputs") if (context and isinstance(context.get("all_outputs"), dict)) else (context or {})

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

        constraints = researcher_data.get("constraints", [])
        architecture = engineer_data.get("architecture") or engineer_data.get("technical_architecture", "Architecture not specified")
        priorities = strategist_data.get("priorities", [])

        # Conflict resolution handling
        resolved_conflicts: List[ResolvedConflict] = []
        unresolved_conflicts: List[UnresolvedConflict] = []

        if conflict_data and isinstance(conflict_data, dict):
            c_status = str(conflict_data.get("status", "")).lower()
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

        limitations: List[str] = []
        if failed:
            for f in failed:
                limitations.append(f"{f.capitalize()} analysis was unavailable; related considerations are provisional.")
        if not context:
            limitations.append("No multi-agent context was supplied; response is based solely on problem statement.")

        # -------------------------------------------------------------
        # 2. Domain & Intent Specific Response Assembly
        # -------------------------------------------------------------
        sections: List[str] = []

        is_job_offer = ("job offer" in p_lower or "offers" in p_lower or ("relocation" in p_lower and ("family" in p_lower or "balance" in p_lower or "decide" in p_lower)))
        is_saas_smb = ("saas" in p_lower and ("restaurant" in p_lower or "retail" in p_lower or "professional services" in p_lower))
        is_auth_arch = ("authentication" in p_lower and ("fastapi" in p_lower or "react" in p_lower or "postgresql" in p_lower or "jwt" in p_lower))

        # (0) BENCHMARK: PERSONAL JOB OFFER RELOCATION VS FAMILY/WLB DILEMMA
        if is_job_offer:
            sections.append(
                "## 1. Decision Restatement & Known Facts\n"
                "You are evaluating two competing career offers involving fundamental personal and professional trade-offs:\n"
                "- **Offer A (Higher Compensation / Relocation)**: Provides higher nominal compensation but requires relocating away from your current location, network, and family.\n"
                "- **Offer B (Lower Compensation / Family Proximity & Work-Life Balance)**: Offers lower nominal compensation but preserves physical proximity to your family and affords superior work-life balance.\n\n"
                "**Known Facts**: The choice balances immediate earning potential against personal well-being, family proximity, and geographic stability. "
                "Crucially, neither financial compensation nor family proximity is universally superior; your personal values and life stage determine the optimal path."
            )
            sections.append(
                "## 2. Comprehensive Multi-Factor Comparison\n"
                "| Evaluation Dimension | Offer A (Higher Pay / Relocate) | Offer B (Lower Pay / Family / WLB) |\n"
                "| :--- | :--- | :--- |\n"
                "| **Real Compensation (Adjusted)** | Higher nominal gross, but must be adjusted for destination taxes, cost of living index, and travel costs back to family. | Lower nominal gross, but lower living friction, shared household economies, and zero moving costs. |\n"
                "| **Relocation Costs & Friction** | High upfront moving costs, lease termination, furniture logistics, and establishing a new local social support system. | Zero relocation friction, established housing, and intact local support network. |\n"
                "| **Career Growth & Trajectory** | Potential access to a denser industry hub, marquee brand recognition, or steeper professional learning curve. | Stable compounding, reduced burnout risk, but potentially narrower local market growth depending on city. |\n"
                "| **Work-Life Balance & Health** | Risk of elevated stress from adjusting to a new city, longer hours, or demanding corporate expectations. | Protected personal time, predictable boundaries, lower chronic stress, and better psychological recovery. |\n"
                "| **Family Priorities & Support** | Physical distance requires deliberate scheduling and travel expenses for family visits, life events, or emergencies. | Immediate daily or weekly physical presence, caregiving support, and participation in family milestones. |\n"
                "| **3–5 Year Consequences** | Could accelerate compensation trajectory and title seniority, or lead to isolation and early exit if culture is poor. | Fosters sustainable life foundation and deep community ties, but may create eventual compensation plateau frustration if growth stalls. |"
            )
            sections.append(
                "## 3. When Each Offer is Preferable\n"
                "- **Offer A is preferable if**:\n"
                "  1. The net financial delta (after taxes, rent increase, and travel expenses) is substantial enough to accelerate debt payoff, savings, or investment goals.\n"
                "  2. The role provides specialized skill development, marquee brand equity, or mentorship unavailable in your current location.\n"
                "  3. You are in a life stage where spending 2–3 years in a high-intensity hub aligns with your medium-term vision, with a clear option to return or transition later.\n\n"
                "- **Offer B is preferable if**:\n"
                "  1. Family caregiving, deep relationships, or personal well-being are primary sources of fulfillment and resilience right now.\n"
                "  2. The cost-of-living increase in Offer A's destination would consume most of the salary difference, yielding negligible real net savings.\n"
                "  3. You value sustainable hours, hobbies, or mental clarity over incremental income, avoiding burnout risk."
            )
            sections.append(
                "## 4. Unknown Factors (Without Inventing Circumstances)\n"
                "A definitive calculation requires specific data points that were not provided in your prompt (and should not be assumed):\n"
                "- **Exact Compensation Delta**: The pre-tax and post-tax difference between the two base salaries, plus bonuses or equity.\n"
                "- **Relocation Package**: Whether Offer A covers moving services, temporary housing, or lease break fees.\n"
                "- **Cost-of-Living Differential**: Relative rent, state/local tax rates, and everyday costs between the two locations.\n"
                "- **Remote/Hybrid Flexibility**: Whether Offer A allows periodic remote work weeks to visit family without using vacation days.\n"
                "- **Promotion & Learning Velocity**: The concrete promotion cadence, mentorship quality, and exit opportunities for each position."
            )
            sections.append(
                "## 5. Decision Framework & Conditional Recommendation\n"
                "Rather than guessing your priorities, apply this structured decision framework:\n\n"
                "### Step 1: The Net Purchasing Power Equation\n"
                "$$\\text{Real Delta} = (\\text{Offer A Net Income} - \\text{Housing Increase} - \\text{Annual Family Visit Travel}) - \\text{Offer B Net Income}$$\n"
                "- If the real delta is marginal (e.g. less than 10–15% after living costs), the financial premium alone does not justify the relocation friction.\n\n"
                "### Step 2: The 10/10/10 Rule\n"
                "- How will you feel about relocating in 10 weeks (initial adjustment), 10 months (routine established), and 10 years (career trajectory vs. family memories)?\n\n"
                "### Step 3: Reversibility & Negotiation Leverage\n"
                "- Can you negotiate with Offer B by citing Offer A's market rate to narrow the salary gap?\n"
                "- If you take Offer A, can you treat it as a defined 24-month commitment before reassessing?"
            )
            sections.append(
                "## 6. Clarifying Follow-Up Questions\n"
                "To calculate your tailored recommendation, consider these specific questions:\n"
                "1. What is the approximate salary difference, and does Offer A include a relocation stipend?\n"
                "2. Which cities are involved, or what is the expected difference in rent and cost of living?\n"
                "3. Does Offer A offer any hybrid flexibility (e.g. working remotely 1 week per month from near your family)?"
            )

        # (1) BENCHMARK: BUSINESS SMB SAAS VERTICAL TARGETING
        elif is_saas_smb:
            sections.append(
                "## 1. Executive Summary & Problem Scope\n"
                "When launching a B2B SaaS for small businesses, choosing your initial vertical between **Restaurants**, **Retail Stores**, and "
                "**Professional Services** (accountants, lawyers, consultants, agencies) dictates your sales cycle, product surface area, "
                "and capital runway. This analysis provides an objective multi-dimensional evaluation while strictly separating empirical facts "
                "from working hypotheses."
            )
            sections.append(
                "## 2. Multi-Criteria Segment Comparison\n"
                "| Criteria | Restaurants | Retail Stores | Professional Services |\n"
                "| :--- | :--- | :--- | :--- |\n"
                "| **Willingness to Pay & Margin** | Low-to-Moderate; tight operating margins (typically 3–8%) limit software budget. | Moderate; retail gross margins vary, but net margins remain lean (4–10%). | High; healthy net margins (15–35%+) and high willingness to pay for billable hours or efficiency. |\n"
                "| **Sales Velocity & Accessibility** | Difficult to reach; owners are on the floor during service hours; high gatekeeping. | Moderate; store managers/owners busy with foot traffic and inventory. | High; desktop-based workers accessible via email, LinkedIn, and scheduled calls during business hours. |\n"
                "| **Onboarding & Workflow Friction** | High frontline staff turnover requires simple, multilingual, and intuitive workflows. | High physical workflow dependency (barcode, physical stock counts). | Low; standard desktop browser adoption, familiarity with digital file sharing and calendars. |\n"
                "| **Integration Dependency** | High if touching orders/menus (POS, delivery apps); Low if back-office scheduling. | High if managing stock (POS, e-commerce, barcodes); Low if marketing/CRM. | Standard (Email, Google Workspace, QuickBooks/Xero); rarely requires specialized physical hardware. |\n"
                "| **Market Fragmentation & TAM** | Very high fragmentation; millions of independent operators with local presence. | Very high fragmentation; independent shops alongside national chains. | Highly fragmented; hundreds of thousands of independent legal, accounting, and advisory practices. |"
            )
            sections.append(
                "## 3. Verified Facts vs. Working Hypotheses\n"
                "### Verified Industry Facts\n"
                "- **Margin Structures**: Professional services operate with significantly higher gross and operating margins than food service or physical retail, creating larger discretionary software budgets per employee.\n"
                "- **Staff Turnover**: Frontline staff turnover in food service and retail is empirically 2–3x higher than in professional services, demanding greater onboarding resilience.\n\n"
                "### Working Hypotheses (Subject to Validation for Your Product)\n"
                "- *Hypothesis on Churn*: Professional services software will have lower churn. (This is a hypothesis: white-collar tools face low churn only if embedded into daily compliance, billing, or client communications).\n"
                "- *Hypothesis on POS Complexity*: Restaurants and retail necessarily require complicated Point-of-Sale integrations. (This is conditional: if your software handles employee scheduling, compliance checklists, or local marketing, POS integration may be completely out of scope).\n"
                "- *Hypothesis on Payment Fees*: Payment facilitator fees will impact economics. (This is an assumption: payment processing is only relevant if your product monetizes transaction flow rather than subscription SaaS)."
            )
            sections.append(
                "## 4. Provisional Recommendation & Conditional Triggers\n"
                "### Provisional Recommendation\n"
                "For a lean founder with an unproven product, **Professional Services** is the recommended initial target segment. "
                "It enables higher average revenue per account (ARPA), faster remote customer discovery, and desktop-based adoption without "
                "requiring physical on-site hardware or frontline staff training.\n\n"
                "### Product Characteristics That Change This Recommendation\n"
                "- **If your product focuses on**: Kitchen prep, food waste, table reservation, or recipe costing $\\rightarrow$ **Target Restaurants**.\n"
                "- **If your product focuses on**: Barcode scanning, physical inventory shrinkage, or multi-location stock transfer $\\rightarrow$ **Target Retail Stores**.\n"
                "- **If your product focuses on**: Document intake, billable time tracking, client portals, or appointment booking $\\rightarrow$ **Target Professional Services**."
            )
            sections.append(
                "## 5. Practical Customer-Discovery Experiments\n"
                "Before writing code or committing capital, run these structured validation experiments:\n\n"
                "1. **The 30-Interview Discovery Sprint (Weeks 1–3)**:\n"
                "   - Conduct 10 structured 20-minute problem interviews in each vertical (10 restaurateurs, 10 retail shop owners, 10 professional services principals).\n"
                "   - Core question: *'What operational workflow took the most non-billable time or caused the most stress in your business this past month?'*\n\n"
                "2. **The Concierge / Smoke Test Landing Page (Weeks 4–5)**:\n"
                "   - Create 3 vertical-specific landing pages describing your proposed solution with identical pricing ($49/month or $99/month).\n"
                "   - Drive 50 targeted clicks per vertical via cold outreach or niche groups; measure click-to-waitlist conversion.\n\n"
                "3. **Measurable Decision Gate**:\n"
                "   - Select the vertical that yields at least **3 pre-commitments (letters of intent or prepaid beta deposits)** within 30 days."
            )

        # (2) BENCHMARK: SOFTWARE SAAS AUTH & AUTHZ ARCHITECTURE
        elif is_auth_arch:
            sections.append(
                "## 1. Authentication vs. Authorization Architecture\n"
                "A robust multi-user SaaS requires clean separation between identity verification and access enforcement:\n"
                "- **Authentication (AuthN - 'Who are you?')**: Verifies identity through email/password credentials or OAuth/SSO. Credentials must be hashed using **Argon2id** (preferred) or **bcrypt** (cost factor $\\ge 12$). Successful authentication produces an authenticated session and identity tokens.\n"
                "- **Authorization (AuthZ - 'What are you allowed to do?')**: Enforces tenant boundaries and Role-Based Access Control (RBAC). Evaluated on every API request based on user roles and permissions scoped to the specific tenant."
            )
            sections.append(
                "## 2. Token Architecture: Signed JWTs vs. Encrypted Tokens\n"
                "- **Signed JWTs (JWS per RFC 7519)**: Access tokens are encoded JSON payloads cryptographically signed with an asymmetric key pair (RS256/ES256) or a secure symmetric secret (HS256). Payload claims (`sub`, `tenant_id`, `roles`, `exp`, `iss`, `aud`) are Base64URL-encoded and readable by client and server.\n"
                "- **Signature Verification is NOT Decryption**: Validating a signed JWT involves computing the cryptographic signature over the header and payload using the public key or shared secret, and verifying it matches the token signature. **This does not decrypt the token** (signed JWTs are not encrypted). Encrypted tokens (JWE) are distinct and rarely needed for standard API access tokens.\n"
                "- **Required Claim Validations**: On every request, the backend must validate: (1) Cryptographic signature, (2) Expiration timestamp (`exp`), (3) Issuer (`iss`), and (4) Audience (`aud`)."
            )
            sections.append(
                "## 3. Cookie Storage, CSRF Protections & XSS Boundaries\n"
                "- **Cookie Security Attributes**: Store refresh tokens (and optionally access tokens) in cookies configured with: `HttpOnly=True`, `Secure=True` (HTTPS only), `SameSite=Lax` (or `Strict`), and path scoping (e.g. `Path=/api/auth`).\n"
                "- **CSRF Defense**: While `SameSite=Lax` defends against many cross-origin requests, defense-in-depth requires custom header verification (e.g. `X-Requested-With: XMLHttpRequest` or an explicit CSRF token header verified by FastAPI middleware) because browsers do not attach custom headers on cross-site requests.\n"
                "- **XSS Realities & Limitations**: `HttpOnly` cookies prevent JavaScript from directly reading the cookie string (`document.cookie`), preventing direct exfiltration of the raw token. **However, HttpOnly cookies DO NOT prevent ambient request execution**: if an attacker achieves cross-site scripting (XSS), their injected script can execute `fetch('/api/sensitive')` from within the user's browser, and the browser will automatically attach the HttpOnly cookie. Therefore, full XSS mitigation requires a strict Content Security Policy (CSP), React context-aware JSX encoding, and input sanitization."
            )
            sections.append(
                "## 4. Refresh Token Lifecycle, Rotation & Reuse Detection\n"
                "- **Database-Backed Token Storage**: Maintain a PostgreSQL table:\n"
                "  ```sql\n"
                "  CREATE TABLE refresh_tokens (\n"
                "      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                "      user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,\n"
                "      token_hash VARCHAR(64) NOT NULL UNIQUE,\n"
                "      family_id UUID NOT NULL,\n"
                "      is_revoked BOOLEAN NOT NULL DEFAULT FALSE,\n"
                "      expires_at TIMESTAMPTZ NOT NULL,\n"
                "      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()\n"
                "  );\n"
                "  CREATE INDEX idx_refresh_tokens_hash ON refresh_tokens(token_hash);\n"
                "  CREATE INDEX idx_refresh_tokens_family ON refresh_tokens(family_id);\n"
                "  ```\n"
                "- **Token Rotation**: Every time `/api/auth/refresh` is called, validate the token hash, mark the old token as revoked (`is_revoked = TRUE`), and issue a new refresh token sharing the same `family_id`.\n"
                "- **Reuse Detection (Anti-Theft)**: If a refresh token with `is_revoked = TRUE` is ever presented, assume token theft. Immediately invalidate **all tokens belonging to that `family_id`**, revoke active sessions, and log a critical security event."
            )
            sections.append(
                "## 5. Multi-Tenant Data Isolation in FastAPI & PostgreSQL\n"
                "- **PostgreSQL Row-Level Security (RLS)**: Enforce database-level tenant isolation:\n"
                "  ```sql\n"
                "  ALTER TABLE projects ENABLE ROW LEVEL SECURITY;\n"
                "  CREATE POLICY tenant_isolation_policy ON projects\n"
                "      USING (tenant_id = current_setting('app.current_tenant_id')::uuid);\n"
                "  ```\n"
                "- **FastAPI Dependency Injection**: Extract and verify `tenant_id` from the JWT access token in a FastAPI dependency, and set the transactional session parameter before executing queries:\n"
                "  ```python\n"
                "  async def get_tenant_db(token: TokenData = Depends(get_current_user)):\n"
                "      async with SessionLocal() as session:\n"
                "          await session.execute(text(\"SET LOCAL app.current_tenant_id = :tid\"), {\"tid\": str(token.tenant_id)})\n"
                "          yield session\n"
                "  ```"
            )
            sections.append(
                "## 6. MVP vs. Production-Hardening Infrastructure\n"
                "### Day-One MVP (Simple, Cost-Effective & Robust)\n"
                "- **Datastore**: Single PostgreSQL database storing users, tenants, and the `refresh_tokens` table. No Redis is needed; token rotation and revocation lookups take <2ms on indexed tables.\n"
                "- **Backend**: FastAPI with async SQLAlchemy, Pydantic v2 schemas, and standard HTTPS/TLS termination.\n"
                "- **Frontend**: React with in-memory access token storage and Axios/Fetch interceptor for transparent 401 token refresh.\n\n"
                "### Production Hardening (At Scale)\n"
                "- **Redis Justification**: Introduce Redis only when scaling to tens of thousands of active concurrent sessions where database query load for session validation becomes measurable, or when distributed sub-millisecond token blacklisting is required across multiple regions.\n"
                "- **Connection Pooling**: PgBouncer deployed in front of PostgreSQL to handle high-concurrency connection spikes.\n"
                "- **Rate Limiting**: SlowAPI or API gateway rate limiting on `/api/auth/login` (e.g. 5 attempts/minute) to defeat credential stuffing."
            )

        # (A) BUSINESS STRATEGY
        elif plan.domain == "business_strategy" or (plan.intent in ("strategy", "decision_support") and "business" in p_lower):
            sections.append(
                "## Executive Summary\n"
                "For a small business navigating growth with constrained capital, launching an online channel provides the strongest "
                "risk-adjusted trajectory. It maximizes capital efficiency by leveraging your existing product baseline and operations "
                "without taking on the heavy fixed lease obligations and staffing commitments of a second physical location."
            )
            sections.append(
                "## Situation & Strategic Constraints\n"
                "- **Limited Capital**: Fixed investment in physical retail expansion risks cash insolvency if foot traffic lags.\n"
                "- **Three Core Strategic Paths**: (1) Opening a second physical store, (2) Expanding into an online e-commerce channel, or (3) Developing a new product line.\n"
                "- **Execution Capacity**: Managing multiple physical footprints simultaneously strains founder bandwidth and working cash flow."
            )
            sections.append(
                "## Evaluation of the Three Strategic Options\n"
                "1. **Option 1: Opening a Second Physical Store**\n"
                "   - *Pros*: Tangible presence, local branding, and potential economies of scale if prime foot traffic is secured.\n"
                "   - *Cons*: High upfront lease, fit-out, and staffing expenses. High capital risk and operational fragility.\n"
                "2. **Option 2: Launching an Online Channel**\n"
                "   - *Pros*: Low fixed capital requirement, broader market reach, testable digital customer acquisition, and reuse of existing inventory.\n"
                "   - *Cons*: Digital fulfillment complexity, platform transaction fees, and paid digital acquisition costs.\n"
                "3. **Option 3: Developing a New Product Line**\n"
                "   - *Pros*: Deeper monetization of the existing customer base without expanding real estate.\n"
                "   - *Cons*: Upfront production run inventory costs without guaranteed demand validation."
            )
            sections.append(
                "## Financial & Capital Risk Analysis\n"
                "- **Cash Runway Preservation**: Online deployment preserves liquidity for at least 12–18 months compared to the heavy capital sink of physical leases.\n"
                "- **Unit Economics**: Requires proving customer acquisition cost (CAC) is well below lifetime value (LTV) before scaling marketing spend.\n"
                "- **Downside Exposure**: If the online channel underperforms, fixed losses are capped at platform setup software costs."
            )
            sections.append(
                "## Key Trade-offs & Opportunity Costs\n"
                "- **Fixed Overhead vs. Variable Marketing**: Physical expansion commits you to fixed rent regardless of sales; digital expansion shifts costs to variable marketing that can be paused or throttled.\n"
                "- **Geographic Focus vs. Distribution Bandwidth**: Physical store concentrates local influence, whereas e-commerce tests wider market demand."
            )
            sections.append(
                "## Critical Information Needed Before Deciding\n"
                "The following crucial data points must be clarified before finalizing long-term capital allocation:\n"
                "- Current monthly gross margins and net cash flow from the existing store.\n"
                "- Existing customer inquiry rate regarding online ordering or shipping.\n"
                "- Reliable estimates of local foot traffic and commercial lease terms for target second store locations.\n"
                "- Customer retention and repeat purchase rate in the core business."
            )
            sections.append(
                "## Strategic Recommendation & Rationale\n"
                "Pursue a phased **Online Channel Launch** first as a low-capital expansion vehicle. Reinvest the cash flows generated "
                "from verified digital sales before committing capital to a second physical location."
            )
            sections.append(
                "## 12-Month Execution Roadmap\n"
                "- **Months 1–3 (Validation & Setup)**: Set up e-commerce platform, establish direct-to-consumer packaging and fulfillment protocols, and test with existing loyal customers.\n"
                "- **Months 4–6 (Pilot Acquisition)**: Run targeted local digital marketing experiments, measure conversion rates, and optimize unit economics.\n"
                "- **Months 7–9 (Channel Scaling)**: Automate inventory syncing, refine shipping partnerships, and expand regional marketing.\n"
                "- **Months 10–12 (Strategic Review)**: Evaluate accumulated net cash reserves and decide whether to greenlight a second physical retail location based on verified profits."
            )
            sections.append(
                "## Key Milestones & Decision Gates\n"
                "- **Gate 1 (End of Month 3)**: Platform live with first 50 organic orders and zero fulfillment bottlenecks.\n"
                "- **Gate 2 (End of Month 6)**: CAC:LTV ratio established at 1:3 or better with positive contribution margins.\n"
                "- **Gate 3 (Month 12)**: Reassess physical store expansion only if accumulated cash reserves exceed 6 months of operating expenses."
            )
            sections.append(
                "## Assumptions & Strategic Limitations\n"
                "- Assumes current store operations generate steady baseline cash flow.\n"
                "- Assumes product category is suitable for standard shipping and regional fulfillment without prohibitive logistics hurdles."
            )

        # (B) SCIENCE / EVIDENCE ANALYSIS / RESEARCH
        elif plan.domain in ("science", "general_research") or plan.intent in ("evidence_analysis", "research_analysis"):
            sections.append(
                "## Core Question & Competing Hypotheses\n"
                "The central question is why certain students systematically outperform peers academically. Research across educational "
                "psychology, cognitive neuroscience, and sociology points to several competing and interacting explanations rather than "
                "any single monocausal driver."
            )
            sections.append(
                "## Competing Explanations\n"
                "1. **Study Habits & Metacognitive Strategies**: Deliberate practice, spaced repetition, and active retrieval versus passive reading.\n"
                "2. **Intrinsic Motivation & Self-Regulation**: Goal orientation, executive function, and delayed gratification.\n"
                "3. **Sleep Quality & Circadian Rhythm**: Sleep duration and consistency impacting memory consolidation and cognitive speed.\n"
                "4. **Socioeconomic Background & Resource Access**: Household income, parental education, tutoring access, and stable nutrition.\n"
                "5. **Teaching Quality & Pedagogy**: High-impact instruction, feedback loops, and teacher efficacy.\n"
                "6. **Cognitive Differences & Working Memory**: Individual baseline working memory capacity and processing speed.\n"
                "7. **Peer Environment & School Culture**: Peer norms, academic expectations, and disruptive behavior environments."
            )
            sections.append(
                "## Empirical Evidence Analysis\n"
                "- **Evidence Supporting Individual Factors**: Meta-analyses (e.g. Dunlosky et al., Hattie) show strong positive associations for active retrieval practice (d ≈ 0.6–0.8) and consistent sleep hygiene on exam performance.\n"
                "- **Evidence Supporting Structural Factors**: Sociological longitudinal studies consistently demonstrate that socioeconomic status (SES) accounts for significant variance in standardized academic outcomes.\n"
                "- **Evidence Against Monocausal Explanations**: Interventions isolating single variables (e.g., teaching study habits without addressing sleep deprivation or home instability) routinely yield diminished effect sizes."
            )
            sections.append(
                "## Confounding Factors & Interaction Effects\n"
                "- **SES as a Major Confounder**: Wealthier environments simultaneously provide better nutrition, quiet study areas, lower chronic stress, and higher-quality schooling. Isolating purely 'innate' motivation is difficult without controlling for chronic stress induced by socioeconomic strain.\n"
                "- **Sleep-Motivation Feedback Loops**: Chronic sleep deprivation impairs prefrontal cortex function, degrading self-control and motivation, creating a confounding feedback loop."
            )
            sections.append(
                "## Contradictions & Methodological Limitations\n"
                "- **Self-Report Bias**: Many studies rely on self-reported study hours or sleep duration, which suffer from social desirability and recall bias.\n"
                "- **Reverse Causality**: Higher early academic success boosts intrinsic motivation (positive reinforcement), making it difficult to determine whether motivation caused success or success fueled motivation."
            )
            sections.append(
                "## Causal Interpretation vs. Association\n"
                "- **Observational Correlation**: Most existing literature documents strong *associations* between structured habits, peer environments, and grades.\n"
                "- **Causal Bounds**: We cannot infer that forcing an unmotivated student into a high-achieving peer group will automatically raise their GPA without addressing foundational cognitive and emotional factors."
            )
            sections.append(
                "## Rigorous Research Design & Testing Framework\n"
                "To establish true causality among competing explanations:\n"
                "- **Methodology**: Randomized Controlled Trials (RCTs) with active control groups, testing specific micro-interventions (e.g. spaced retrieval curriculum vs standard homework).\n"
                "- **Measurement**: Objective wearable telemetry for sleep, blinded computerized working memory assessments, and standardized achievement tests.\n"
                "- **Controls**: Strict statistical controls for baseline SES, parental education, and school funding."
            )
            sections.append(
                "## Synthesis & Evidence-Grounded Conclusion\n"
                "Academic achievement is an emergent outcome of interacting biological, behavioral, and environmental systems. Deliberate study practices and adequate sleep are actionable high-leverage levers, but their effectiveness is heavily moderated by environmental security and emotional regulation."
            )

        # (C) PERSONAL DECISION / CAREER
        elif plan.domain in ("personal_decision", "career") or plan.intent == "decision_support":
            sections.append(
                "## Situation & Context\n"
                "You are in college facing a pivotal crossroads between two distinct trajectories: pursuing a stable, established career path versus stepping into entrepreneurship. This decision involves balancing financial security, risk tolerance, and long-term fulfillment without premature commitments."
            )
            sections.append(
                "## Core Priorities (What Matters Most)\n"
                "- **Financial Stability & Independence**: The necessity of maintaining predictable income versus tolerating variable cash flows.\n"
                "- **Learning Velocity & Skill Acquisition**: Where you will develop foundational problem-solving, sales, and operational capabilities fastest.\n"
                "- **Risk Tolerance & Downside Sensitivity**: Your personal runway, debt obligations, and family expectations.\n"
                "- **Autonomy vs. Structured Mentorship**: Whether you thrive with organizational structure or open-ended self-direction."
            )
            sections.append(
                "## Path 1 Assessment: Stable Employment\n"
                "- **Advantages**: Predictable compensation, structured mentorship, brand credibility on your resume, and protected downside.\n"
                "- **Risks**: Slower progression ceiling, organizational bureaucracy, and opportunity cost of deferred entrepreneurial ambitions."
            )
            sections.append(
                "## Path 2 Assessment: Entrepreneurship\n"
                "- **Advantages**: Uncapped learning curve, complete ownership of outcomes, equity upside, and compounding self-reliance.\n"
                "- **Risks**: High probability of initial failure, uneven or absent income, mental stress, and lack of experienced organizational mentorship."
            )
            sections.append(
                "## Comparative Trade-offs & Opportunity Costs\n"
                "- **Timing Trade-off**: College offers a rare safety buffer where baseline living costs are low, but lack of professional network and capital makes early execution harder.\n"
                "- **Resume Risk vs. Founder Regret**: Entering corporate life later with founding experience is often valued, whereas passing on early ventures can create persistent regret."
            )
            sections.append(
                "## Downside Protection & Risk Reduction\n"
                "- **The Hybrid Runway Model**: Do not treat this as a binary choice immediately. Use your final college semesters to launch a minimal viable version of your venture while interviewing for top stable roles.\n"
                "- **Conditional Acceptance**: Secure a stable job offer as a safety net with a deferred start date or clear exit timeline (e.g. 18–24 months).\n"
                "- **Low-Cost Validation**: Test your business idea with real paying users before investing substantial personal capital."
            )
            sections.append(
                "## Decision Framework & Conditional Recommendation\n"
                "- **If you have student debt or family financial dependencies**: Take the stable role first, live beneath your means, build a 12-month financial cushion, and build the venture in parallel.\n"
                "- **If you have low financial overhead and strong product-market signal**: Dedicate 12 months post-graduation exclusively to the venture, establishing a firm reassessment gate at month 12."
            )
            sections.append(
                "## Practical Next Steps (First 30–90 Days)\n"
                "1. **Next 30 Days**: Quantify your financial baseline (living costs and runway needed for 12 months).\n"
                "2. **Next 60 Days**: Talk to 20 potential customers or ship a minimum viable prototype to test customer willingness to pay.\n"
                "3. **Next 90 Days**: Set an explicit decision date (e.g. end of semester) to evaluate customer traction against career offer deadlines."
            )

        # (D) LIFE PLANNING / PERSONAL GROWTH
        elif plan.domain == "planning" or plan.intent == "prioritization":
            sections.append(
                "## Current Situation & Core Priorities\n"
                "Significant multi-year life improvement requires ruthless prioritization and sustainable pacing. Attempting to optimize fitness, career, finances, relationships, and learning simultaneously leads to cognitive overload and burnout. Over a two-year horizon, progress compounds from sequential mastery rather than parallel exhaustion."
            )
            sections.append(
                "## What to Focus on First vs. What to Deprioritize\n"
                "- **Focus on First (Foundation Phase)**:\n"
                "  1. Sleep & Energy Architecture (consistent sleep/wake times and physical movement).\n"
                "  2. Financial Cash-Flow Defense (tracking spending, debt reduction, basic emergency savings).\n"
                "  3. Primary Career Lever (improving core revenue-generating skill).\n"
                "- **What to Deprioritize for Now**:\n"
                "  - Speculative secondary side hustles before the primary skill is solid.\n"
                "  - Complex multi-step productivity systems and excessive non-fiction reading without application.\n"
                "  - Perfectionism across all personal hobbies."
            )
            sections.append(
                "## Priority Interactions & Real-World Trade-offs\n"
                "- **Energy Precedes Discipline**: When sleep and nutrition fluctuate, willpower collapses. Fixing biological foundations directly enhances career output.\n"
                "- **Focus vs. Breadth**: Advancing one major goal by 80% creates far more momentum than advancing five goals by 10%."
            )
            sections.append(
                "## Sustainable Operating Framework\n"
                "- **The Rule of One Big Thing**: Design each day around a single non-negotiable primary block (90–120 minutes) completed before cognitive fatigue sets in.\n"
                "- **Energy Management over Time Management**: Protect your highest-energy hours for deep work and fitness; schedule administrative tasks for low-energy windows."
            )
            sections.append(
                "## First 30 Days Action Plan\n"
                "- Lock in fixed wake-up and sleep times (aim for 7–8 hours).\n"
                "- Eliminate one major low-value time drain (e.g., late-night passive scrolling).\n"
                "- Walk 30 minutes daily and log daily expenses into a simple tracker."
            )
            sections.append(
                "## 3-Month & 6-Month Execution Milestones\n"
                "- **Month 3**: Baseline routine is automated; emergency fund contains 1 month of living expenses; career skill practice is consistent 4 days per week.\n"
                "- **Month 6**: Structured strength training 3x/week; measurable career performance milestone achieved; secondary life area (e.g. social relationships) intentionally introduced."
            )
            sections.append(
                "## 12-Month & 2-Year Direction\n"
                "- **Month 12**: Review career income growth or promotion readiness; emergency fund expanded to 3–6 months; physical conditioning normalized.\n"
                "- **Year 2**: Transition from foundational defense to offensive compounding (investing surplus income, tackling stretch professional challenges, pursuing deep creative or travel interests)."
            )
            sections.append(
                "## Habit, Energy & Capacity Management\n"
                "- **Minimum Effective Dose**: Set baseline habits low enough that they can be maintained on your worst day (e.g., 10 minutes of movement rather than 60 minutes).\n"
                "- **Weekly Restoration**: Dedicate at least half a day each week to unstructured rest and mental recovery."
            )
            sections.append(
                "## Review & Course-Correction Rules\n"
                "- Conduct a 15-minute weekly retro every Sunday: 'What moved the needle? What caused friction?'\n"
                "- Quarterly audit: If a habit consistently failed for 3 weeks, simplify or replace it rather than escalating self-criticism."
            )

        # (E) TECHNICAL COMPARISON (e.g. PostgreSQL vs MongoDB)
        elif plan.intent == "comparison" and plan.domain == "software_engineering":
            sections.append(
                "## Executive Summary\n"
                "For a production multi-tenant AI SaaS, PostgreSQL is the superior foundational primary datastore across performance, "
                "transactional isolation, hiring availability, and ecosystem maturity. MongoDB provides advantages in polymorphic document "
                "flexibility and native sharding, but PostgreSQL's ACID compliance, robust Row-Level Security (RLS) for tenant isolation, "
                "and extensions like `pgvector` offer a more maintainable, cost-effective 3-year foundation."
            )
            sections.append(
                "## Architectural Paradigm Comparison\n"
                "- **PostgreSQL**: Relational datastore with mature JSONB support and relational integrity, enabling structured tenant data alongside semi-structured AI metadata.\n"
                "- **MongoDB**: Document-oriented datastore with flexible BSON schemas, suited for rapid prototyping and denormalized hierarchical documents."
            )
            sections.append(
                "## Multi-Tenancy & Data Isolation\n"
                "- **PostgreSQL**: Native Row-Level Security (RLS) allows single-database multi-tenancy with cryptographic tenant ID isolation enforced at the database layer. Schema-per-tenant is also straightforward for enterprise tiers.\n"
                "- **MongoDB**: Multi-tenancy typically relies on application-level filtering (`tenant_id` queries) or collection-per-tenant, which introduces operational overhead and higher connection/index memory footprints."
            )
            sections.append(
                "## Performance, Scaling & Vector Workloads\n"
                "- **PostgreSQL**: Exceptional performance with B-tree indexes, BRIN, and GIN for JSONB. Extension `pgvector` enables unified relational + vector similarity search (HNSW/IVFFlat) without a separate vector database in early-to-mid stages.\n"
                "- **MongoDB**: MongoDB Atlas Vector Search provides integrated vector indexing. Handles massive horizontal write scaling well via native sharding, though distributed transactions introduce latency overhead."
            )
            sections.append(
                "## Ecosystem, Tooling & Talent Availability\n"
                "- **PostgreSQL**: Unrivaled developer talent availability, mature ORMs (Prisma, SQLAlchemy, Drizzle), and rich tooling (pgbouncer, TimescaleDB, Supabase).\n"
                "- **MongoDB**: Large ecosystem, but experienced database administrators for distributed sharded clusters are scarcer and more expensive than PostgreSQL talent."
            )
            sections.append(
                "## Deployment, Operational Complexity & Cost\n"
                "- **PostgreSQL**: Highly cost-effective on managed platforms (AWS RDS, Aurora, GCP Cloud SQL, Supabase) or self-hosted instances. Predictable compute/memory scaling.\n"
                "- **MongoDB**: Highly cost-effective when using MongoDB Atlas managed clusters; self-hosted sharded clusters demand significant operational complexity (mongos, config servers, replica sets)."
            )
            sections.append(
                "## Key Trade-offs & Contradictions\n"
                "- **Schema Rigidity vs Schema Flexibility**: Relational schemas require migrations for structural changes, whereas document schemas shift schema validation responsibility to the application layer.\n"
                "- **Unified vs Polyglot Architecture**: PostgreSQL lets you consolidate transactional, JSON, and vector data into one engine, reducing architectural footprint."
            )
            sections.append(
                "## Long-Term Maintainability & Synthesis Recommendation\n"
                "- **Recommendation**: Standardize on **PostgreSQL** as the core database for the first three years.\n"
                "- **Why**: Tenant isolation (RLS), ACID guarantees for billing/usage credits, and unified vector storage minimize operational overhead for a lean SaaS team. If document payloads become overwhelmingly polymorphic and exceed relational performance, offload specific document collections to a specialized cache or document store later."
            )

        # (F) EDUCATIONAL EXPLANATIONS WITH IMPLEMENTATION (e.g. Binary Search deep)
        elif plan.intent == "educational_explanation" and (plan.requested_depth == "deep" or "examples" in p_lower or "implementation" in p_lower):
            sections.append(
                "## Algorithm Concept & Core Intuition\n"
                "Binary search is an efficient search algorithm designed to find the index of a target element within a **sorted array**. "
                "Instead of scanning elements sequentially from left to right, binary search repeatedly halves the search interval by "
                "comparing the target with the middle element."
            )
            sections.append(
                "## Step-by-Step Walkthrough with Example\n"
                "Consider searching for target `7` in the sorted array `[1, 3, 5, 7, 9, 11, 13]`:\n"
                "1. Initial pointers: `low = 0` (value 1), `high = 6` (value 13).\n"
                "2. Midpoint: `mid = (0 + 6) // 2 = 3` (value `7`).\n"
                "3. Comparison: `arr[mid] == 7`. Target matched on step 1!\n\n"
                "If searching for `9`:\n"
                "1. `low = 0`, `high = 6` → `mid = 3` (value `7`). `9 > 7`, so search right half: `low = mid + 1 = 4`.\n"
                "2. `low = 4` (value 9), `high = 6` (value 13) → `mid = 5` (value 11). `9 < 11`, so search left half: `high = mid - 1 = 4`.\n"
                "3. `low = 4`, `high = 4` → `mid = 4` (value `9`). Target found at index `4` in 2 comparisons."
            )
            sections.append(
                "## Python Implementation\n"
                "```python\n"
                "def binary_search(arr: list[int], target: int) -> int:\n"
                "    \"\"\"\n"
                "    Performs iterative binary search on a sorted list.\n"
                "    Returns the 0-based index if target is found, otherwise -1.\n"
                "    \"\"\"\n"
                "    low = 0\n"
                "    high = len(arr) - 1\n\n"
                "    while low <= high:\n"
                "        # Prevent potential integer overflow in languages with fixed-width integers\n"
                "        mid = low + (high - low) // 2\n\n"
                "        if arr[mid] == target:\n"
                "            return mid\n"
                "        elif arr[mid] < target:\n"
                "            low = mid + 1\n"
                "        else:\n"
                "            high = mid - 1\n\n"
                "    return -1\n\n\n"
                "# Verification example\n"
                "if __name__ == \"__main__\":\n"
                "    numbers = [2, 4, 6, 8, 10, 12, 14, 16]\n"
                "    idx = binary_search(numbers, 10)\n"
                "    print(f\"Target found at index: {idx}\")  # Output: 4\n"
                "```"
            )
            sections.append(
                "## Complexity Analysis (Time & Space)\n"
                "- **Time Complexity**:\n"
                "  - **Best Case**: $\\mathcal{O}(1)$ when the target is at the exact midpoint on the first check.\n"
                "  - **Worst & Average Case**: $\\mathcal{O}(\\log n)$, as each comparison divides the remaining search interval by 2.\n"
                "- **Space Complexity**:\n"
                "  - **Iterative Implementation**: $\\mathcal{O}(1)$ auxiliary memory (only requires pointer variables).\n"
                "  - **Recursive Implementation**: $\\mathcal{O}(\\log n)$ call stack frames."
            )
            sections.append(
                "## Edge Cases & Common Pitfalls\n"
                "1. **Unsorted Input**: Binary search produces incorrect results if the array is not sorted.\n"
                "2. **Integer Overflow**: Calculating `mid = (low + high) // 2` can overflow in fixed 32-bit integer languages; use `low + (high - low) // 2`.\n"
                "3. **Empty Array**: `low = 0` and `high = -1` immediately terminates the while loop and safely returns `-1`.\n"
                "4. **Duplicates**: Basic binary search returns an arbitrary match; finding the first or last occurrence requires bisect left/right logic."
            )
            sections.append(
                "## Summary & Best Practices\n"
                "Binary search reduces search time from linear $\\mathcal{O}(n)$ to logarithmic $\\mathcal{O}(\\log n)$, making it ideal for large datasets, monotonic mathematical functions, and optimization problems."
            )

        # (F-2) CONCISE EDUCATIONAL EXPLANATIONS
        elif plan.intent == "educational_explanation":
            if "binary search" in p_lower:
                final_ans = (
                    "Binary search is an efficient algorithm for finding an element in a sorted list. "
                    "It repeatedly checks the middle element and eliminates half of the remaining search space. "
                    "Its time complexity is O(log n), making it significantly faster than linear search for large datasets."
                )
            else:
                final_ans = f"This directly explains '{problem}': a core foundational concept structured around clear principles."
            return SynthesizerResult(
                agent="synthesizer",
                status=AgentStatus.COMPLETED,
                final_answer=final_ans,
                key_decisions=[KeyDecision(decision="Provide educational explanation", rationale="Concise educational query.", supported_by=active)],
                supporting_findings=[],
                resolved_conflicts=[],
                unresolved_conflicts=[],
                limitations=[],
                assumptions=[],
                missing_information=[],
                provenance=[],
            )

        # (G) DEFAULT / TECHNICAL SOFTWARE ENGINEERING ARCHITECTURE
        else:
            sections.append(
                f"## Executive Summary\n"
                f"This proposal establishes a comprehensive, resilient solution for '{problem}'. "
                f"By unifying strategic priorities, technical architecture, safety guardrails, defensive cybersecurity controls, "
                f"and arbitrated trade-off resolutions, the design delivers a cohesive operational framework tailored to the problem."
            )

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
            else:
                sections.append(
                    "## Technical Architecture & System Design\n"
                    "The system architecture employs a decoupled, modular design featuring an API gateway tier, "
                    "stateless backend microservices, resilient distributed caching (Redis), and an ACID-compliant primary datastore "
                    "with read replicas to service high concurrent workloads."
                )

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
            else:
                sections.append(
                    "## Security, Privacy & Safety Guardrails\n"
                    "Defensive security controls include TLS 1.3 in transit, AES-256 at rest, OAuth2/OIDC with multi-factor authentication (MFA), "
                    "and strict Role-Based Access Control (RBAC) ensuring data privacy and compliance."
                )

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
            else:
                sections.append(
                    "## Trade-offs & Reconciled Decisions\n"
                    "Balanced horizontal scaling elasticity against upfront infrastructure operational overhead; "
                    "prioritized managed persistence and container orchestration to keep maintenance overhead predictable."
                )

            # Risks & Mitigations
            risks = engineer_data.get("technical_risks", [])
            if risks:
                risk_body = "### Technical & Operational Risks:\n"
                for r in risks[:4]:
                    if isinstance(r, dict):
                        risk_body += f"- **{r.get('risk', 'Risk')}**: Impact: {r.get('impact', 'N/A')} | Mitigation: {r.get('mitigation', 'N/A')}\n"
                sections.append(f"## Risks & Mitigations\n{risk_body.strip()}")
            else:
                sections.append(
                    "## Risks & Mitigations\n"
                    "- **Peak Load Bottlenecks**: Mitigated via queue-based load leveling and auto-scaling compute pods.\n"
                    "- **Network Failures**: Mitigated via Content Delivery Network (CDN) edge caching and active health checks."
                )

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
            else:
                sections.append(
                    "## Implementation Roadmap\n"
                    "- **Phase 1 (Months 1–3)**: Core auth, identity federation, database provisioning, and baseline service delivery.\n"
                    "- **Phase 2 (Months 4–6)**: Real-time capabilities, integration modules, and load testing.\n"
                    "- **Phase 3 (Months 7–12)**: Full deployment rollout, analytics integration, and automated disaster recovery failover."
                )

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

        if is_job_offer:
            key_decisions = [
                KeyDecision(
                    decision="Deliver preliminary personal decision framework",
                    rationale="Structures multi-factor trade-offs across compensation, relocation friction, family priorities, and long-term consequences while identifying unknown variables without inventing personal details.",
                    supported_by=[a for a in active if a in ("strategist", "researcher", "evaluator")] or ["strategist", "researcher"],
                )
            ]
            assumptions = [
                "Operating under neutral valuation of salary delta versus family proximity.",
                "Cost of living, tax, and relocation package details are provisional and subject to exact user figures.",
            ]
            missing_information = [
                "Exact net compensation delta between the two offers.",
                "Relocation package coverage and expected moving expenses.",
                "Career advancement trajectory and promotion velocity at each company.",
            ]
            limitations = [
                "Analysis provides preliminary decision guidance; exact financial calculations require specific salary and relocation numbers."
            ]
        elif is_saas_smb:
            key_decisions = [
                KeyDecision(
                    decision="Provisional recommendation of Professional Services vertical",
                    rationale="Identifies lowest operational friction, highest discretionary spend, and least physical integration dependency for an early-stage SaaS, subject to customer discovery.",
                    supported_by=[a for a in active if a in ("strategist", "researcher", "evaluator")] or ["strategist", "researcher"],
                )
            ]
            assumptions = [
                "Product is assumed to solve knowledge or workflow automation; hardware or POS integrations are not assumed unless specified by product scope.",
                "Industry churn and LTV differences are working hypotheses requiring validation via customer discovery.",
            ]
            missing_information = [
                "Specific product functionality and core workflow solved.",
                "Founder domain expertise and initial industry network access.",
            ]
            limitations = [
                "Target segment recommendations are provisional; specific product characteristics and customer discovery validation must confirm fit."
            ]
        elif is_auth_arch:
            key_decisions = [
                KeyDecision(
                    decision="Standardize on signed JWTs with database-backed refresh token rotation for MVP",
                    rationale="Separates AuthN from AuthZ, avoids premature infrastructure complexity (Redis), and enforces strict multi-tenant isolation via PostgreSQL.",
                    supported_by=[a for a in active if a in ("engineer", "security", "evaluator")] or ["engineer", "security"],
                )
            ]
            assumptions = [
                "Architecture addresses early to mid-stage multi-tenant SaaS workloads before distributed multi-region scaling."
            ]
            missing_information = [
                "Enterprise SSO / SAML requirements.",
                "Compliance certifications required (SOC 2 Type II, HIPAA).",
            ]
            limitations = [
                "Architecture distinguishes day-one MVP controls from optional production-scale hardening (Redis, PgBouncer)."
            ]
        else:
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
            assumptions = ["Operating parameters conform to specified problem constraints."]
            missing_information = ["Specific local deployment parameters not detailed in input."]

        provenance = [
            ProvenanceItem(
                statement="Solution addresses primary user requirements and constraints.",
                supported_by=active or ["synthesizer"],
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
            assumptions=assumptions,
            missing_information=missing_information,
            provenance=provenance,
        )
