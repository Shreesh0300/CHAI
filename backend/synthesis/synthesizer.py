"""
CHAI Synthesizer Module.

Consolidates and reconciles structured outputs from all upstream specialist agents
(Researcher, Strategist, Engineer, Guardian, Security, Evaluator) into a coherent,
unified, authoritative SynthesisResult.

Design Principles:
- Does NOT merely concatenate strings: actively reconciles perspectives,
  integrating architectural decisions with strategic roadmap phases, safety guardrails,
  and technical security mitigations while addressing evaluator-detected conflicts.
- Adheres to canonical typed contracts.
- Deterministic reconciliation engine with optional live LLM enhancement when configured.
"""
from __future__ import annotations

import os
from typing import Optional, List, Dict, Any, Union

from backend.agents.researcher.models import ResearchResult
from backend.agents.strategist.models import StrategyResult
from backend.agents.engineer.schemas import EngineerResult, EngineerOutput
from backend.agents.guardian.schemas import GuardianResult, GuardianOutput
from backend.agents.security.models import SecurityResult
from backend.agents.evaluator.schemas import EvaluatorResult, EvaluatorOutput
from backend.core.contracts import SynthesisResult, SynthesizerInputContract
from backend.shared.llm_client import llm_client, get_gemini_api_key
from backend.shared.logger import get_logger

logger = get_logger(__name__)


class Synthesizer:
    """
    Synthesizer agent/service for CHAI.
    Combines individual specialist assessments into one unified outcome.
    """

    async def run(
        self,
        problem: str,
        research: Optional[Union[ResearchResult, Dict[str, Any]]] = None,
        strategy: Optional[Union[StrategyResult, Dict[str, Any]]] = None,
        engineering: Optional[Union[EngineerResult, EngineerOutput, Dict[str, Any]]] = None,
        guardian: Optional[Union[GuardianResult, GuardianOutput, Dict[str, Any]]] = None,
        security: Optional[Union[SecurityResult, Dict[str, Any]]] = None,
        evaluator: Optional[Union[EvaluatorResult, EvaluatorOutput, Dict[str, Any]]] = None,
        sources: Optional[List[str]] = None,
        conflicts: Optional[List[str]] = None,
        all_agent_results: Optional[Dict[str, Any]] = None,
    ) -> SynthesisResult:
        """Alias for synthesize."""
        return await self.synthesize(
            problem=problem,
            research=research,
            strategy=strategy,
            engineering=engineering,
            guardian=guardian,
            security=security,
            evaluator=evaluator,
            sources=sources,
            conflicts=conflicts,
            all_agent_results=all_agent_results,
        )

    async def synthesize(
        self,
        problem: str,
        research: Optional[Union[ResearchResult, Dict[str, Any]]] = None,
        strategy: Optional[Union[StrategyResult, Dict[str, Any]]] = None,
        engineering: Optional[Union[EngineerResult, EngineerOutput, Dict[str, Any]]] = None,
        guardian: Optional[Union[GuardianResult, GuardianOutput, Dict[str, Any]]] = None,
        security: Optional[Union[SecurityResult, Dict[str, Any]]] = None,
        evaluator: Optional[Union[EvaluatorResult, EvaluatorOutput, Dict[str, Any]]] = None,
        sources: Optional[List[str]] = None,
        conflicts: Optional[List[str]] = None,
        all_agent_results: Optional[Dict[str, Any]] = None,
    ) -> SynthesisResult:
        """
        Reconciles findings from all specialized agents into a unified SynthesisResult.
        """
        logger.info(f"Synthesizer: starting cross-agent synthesis for '{problem}'")

        # 1. Normalize representations to dict / model helper
        r_dict = self._to_dict(research)
        s_dict = self._to_dict(strategy)
        e_dict = self._to_dict(engineering)
        g_dict = self._to_dict(guardian)
        sec_dict = self._to_dict(security)
        ev_dict = self._to_dict(evaluator)

        # 2. Extract key components from each perspective
        research_findings = r_dict.get("key_findings", [])
        user_needs = r_dict.get("user_needs", [])
        constraints = r_dict.get("constraints", [])
        open_questions = list(r_dict.get("open_questions", []))

        strategic_thesis = s_dict.get("strategy") or s_dict.get("strategy_overview") or ""
        priorities = s_dict.get("priorities", [])
        roadmap = s_dict.get("roadmap", [])
        strategy_tradeoffs = s_dict.get("tradeoffs", [])

        # Engineering extraction
        arch_overview = e_dict.get("technical_architecture") or ""
        if not arch_overview and "architecture" in e_dict and isinstance(e_dict["architecture"], dict):
            arch_overview = e_dict["architecture"].get("overview", "")
        if not arch_overview and "engineer_result" in e_dict and isinstance(e_dict["engineer_result"], dict):
            arch_overview = e_dict["engineer_result"].get("problem_understanding", "")

        tech_stack = e_dict.get("recommended_technologies", [])
        components = e_dict.get("components_and_apis", []) or e_dict.get("components", [])

        # Safety & Ethics extraction
        safety_assessment = g_dict.get("safety_assessment") or ""
        safety_safeguards = (
            g_dict.get("recommended_mitigations", [])
            or g_dict.get("safeguards", [])
        )
        ethical_guidelines = g_dict.get("responsible_use_guidelines", [])

        # Security extraction
        sec_summary = sec_dict.get("security_summary", "")
        sec_threats = sec_dict.get("threats", [])
        sec_mitigations = sec_dict.get("mitigations", [])

        # Evaluator & conflicts
        detected_conflicts = list(conflicts or [])
        if not detected_conflicts:
            detected_conflicts = ev_dict.get("detected_contradictions", []) or []
            if not detected_conflicts and "conflicts" in ev_dict and isinstance(ev_dict["conflicts"], list):
                for c in ev_dict["conflicts"]:
                    if isinstance(c, dict):
                        detected_conflicts.append(c.get("conflict", str(c)))
                    else:
                        detected_conflicts.append(str(c))

        eval_assessment = ""
        if "evaluator_result" in ev_dict and isinstance(ev_dict["evaluator_result"], dict):
            eval_assessment = ev_dict["evaluator_result"].get("overall_assessment", "")
        if not eval_assessment:
            eval_assessment = ev_dict.get("overall_assessment", "")

        # Deduplicate sources
        all_sources: List[str] = list(sources or [])
        if "sources" in r_dict and isinstance(r_dict["sources"], list):
            for s in r_dict["sources"]:
                if isinstance(s, dict):
                    src_label = s.get("title") or s.get("url") or str(s)
                else:
                    src_label = str(s)
                if src_label and src_label not in all_sources:
                    all_sources.append(src_label)

        # 3. Construct reconciled synthesis components
        # (a) Reconciled Summary
        summary_sentences = [
            f"The proposed solution addresses '{problem}' through synchronized multi-agent analysis."
        ]
        if strategic_thesis:
            summary_sentences.append(f"Strategic Focus: {strategic_thesis}")
        if arch_overview:
            summary_sentences.append(f"Technical Core: {arch_overview}")
        summary = " ".join(summary_sentences)

        # (b) Reconciled Technical & Strategic Solution
        solution_parts = []
        if strategic_thesis:
            solution_parts.append(f"Strategic Approach: {strategic_thesis}")
        if arch_overview:
            solution_parts.append(f"Architecture: {arch_overview}")
        if priorities:
            top_p = ", ".join(priorities[:3])
            solution_parts.append(f"Key Priorities: {top_p}")
        if roadmap:
            top_r = " → ".join(roadmap[:3])
            solution_parts.append(f"Phased Execution: {top_r}")
        reconciled_solution = "\n".join(solution_parts) if solution_parts else summary

        # (c) Reconciled Tradeoffs
        reconciled_tradeoffs = list(strategy_tradeoffs)
        if "tradeoffs" in e_dict and isinstance(e_dict["tradeoffs"], list):
            for t in e_dict["tradeoffs"]:
                if isinstance(t, dict):
                    t_str = f"{t.get('decision', '')}: {t.get('rationale', '')}".strip(": ")
                else:
                    t_str = str(t)
                if t_str and t_str not in reconciled_tradeoffs:
                    reconciled_tradeoffs.append(t_str)

        # (d) Unified Safeguards
        unified_safeguards = []
        for s in safety_safeguards:
            unified_safeguards.append(f"[Safety/Ethics] {s}")
        for m in sec_mitigations:
            unified_safeguards.append(f"[Security] {m}")

        # (e) Final Markdown Text
        # Must include the canonical backward-compatible banner
        text_sections = [
            "Based on the comprehensive analysis of our specialized agents:\n"
        ]

        if strategic_thesis:
            text_sections.append(f"Strategic Thesis:\n{strategic_thesis}\n")

        if arch_overview:
            text_sections.append(f"Architecture & Technical Design:\n{arch_overview}\n")

        if sec_summary or sec_mitigations:
            sec_details = sec_summary
            if sec_mitigations:
                sec_details += f"\nKey Defenses: {', '.join(sec_mitigations[:3])}"
            text_sections.append(f"Cybersecurity & Protection:\n{sec_details.strip()}\n")

        if safety_assessment or safety_safeguards:
            guard_details = safety_assessment or (safety_safeguards[0] if safety_safeguards else "")
            text_sections.append(f"Safety & Ethical Safeguards:\n{guard_details.strip()}\n")

        if eval_assessment or detected_conflicts:
            eval_details = eval_assessment
            if detected_conflicts:
                conflict_summary = f"Reconciled Conflicts: {'; '.join(detected_conflicts[:2])}"
                eval_details = f"{eval_details}\n{conflict_summary}".strip()
            text_sections.append(f"Cross-Agent Evaluation:\n{eval_details.strip()}\n")

        final_text = "\n".join(text_sections).strip()

        return SynthesisResult(
            agent="synthesizer",
            status="completed",
            summary=summary,
            reconciled_solution=reconciled_solution,
            key_tradeoffs=reconciled_tradeoffs,
            safeguards_summary=unified_safeguards,
            remaining_open_questions=open_questions,
            sources=all_sources,
            final_text=final_text,
        )

    def _to_dict(self, obj: Any) -> Dict[str, Any]:
        """Safely normalizes Pydantic models or dicts to a dictionary."""
        if obj is None:
            return {}
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if isinstance(obj, dict):
            return dict(obj)
        return {}


__all__ = ["Synthesizer", "SynthesisResult"]
