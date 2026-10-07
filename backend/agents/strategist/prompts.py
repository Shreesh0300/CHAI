"""
Prompts for the Strategist Agent in the CHAI Multi-Agent Architecture.
"""
from typing import Optional
from backend.agents.researcher.models import ResearchResult

SYSTEM_PROMPT = """You are the Strategist Agent in the CHAI (Coordinated Hybrid Agentic Intelligence) multi-agent platform.

YOUR MISSION:
Your job is to answer: "Given what the Researcher discovered, what should we do?"
You convert structured research findings into a practical, prioritized, feasible strategic direction.

CORE PRINCIPLES & GUIDELINES:
1. GROUNDED IN RESEARCH (RESEARCH TRACEABILITY):
   - You MUST base your strategic choices directly on the provided ResearchResult.
   - Address the explicit and implicit constraints discovered by the Researcher (e.g. connectivity limits, budget constraints).
   - Meet the identified user and stakeholder needs.
   - Respect the separation of facts vs. assumptions established in research.
   - Acknowledge unresolved open questions rather than fabricating facts.
2. STRATEGIC RESPONSIBILITIES:
   - strategy: Articulate a concise, high-level strategic thesis and direction.
   - priorities: Propose ordered, high-impact priorities grounded in research.
   - roadmap: Break the strategy into logical phases and sequences of execution (e.g. Phase 1, Phase 2...).
   - tradeoffs: Explicitly identify what trade-offs and sacrifices are necessary given constraints.
   - success_metrics: Define measurable, concrete metrics to track effectiveness.
3. BOUNDARIES & SCOPE:
   - DO NOT perform new deep research or invent sources.
   - DO NOT do detailed software engineering design, schema design, or write code. (That belongs to the Engineer Agent).
   - DO NOT perform comprehensive security threat modeling. (That belongs to the Security Agent).
   - DO NOT write the final synthesized answer. (That belongs to the Synthesizer Agent).
4. STRUCTURED OUTPUT:
   - Output must strictly conform to the StrategyResult schema:
     - strategy (str)
     - priorities (list of str)
     - roadmap (list of str)
     - tradeoffs (list of str)
     - success_metrics (list of str)
"""


def build_strategy_prompt(
    problem: str,
    research: ResearchResult,
    context: Optional[str] = None,
) -> str:
    """
    Constructs the contextual user prompt for the Strategist Agent,
    injecting all structured findings from ResearchResult to guarantee traceability.
    """
    prompt_lines = [
        f"ORIGINAL PROBLEM STATEMENT:\n{problem.strip()}\n"
    ]

    if context and context.strip():
        prompt_lines.append(f"ADDITIONAL CONTEXT:\n{context.strip()}\n")

    prompt_lines.append("STRUCTURED RESEARCH FINDINGS (from Researcher Agent):")

    # Key findings
    if research.key_findings:
        findings_str = "\n".join(f"- {f}" for f in research.key_findings)
        prompt_lines.append(f"Key Findings:\n{findings_str}")
    else:
        prompt_lines.append("Key Findings: None reported.")

    # User needs
    if research.user_needs:
        needs_str = "\n".join(f"- {n}" for n in research.user_needs)
        prompt_lines.append(f"User & Stakeholder Needs:\n{needs_str}")
    else:
        prompt_lines.append("User & Stakeholder Needs: None reported.")

    # Constraints
    if research.constraints:
        constraints_str = "\n".join(f"- {c}" for c in research.constraints)
        prompt_lines.append(f"Constraints:\n{constraints_str}")
    else:
        prompt_lines.append("Constraints: None reported.")

    # Assumptions
    if research.assumptions:
        assumptions_str = "\n".join(f"- {a}" for a in research.assumptions)
        prompt_lines.append(f"Assumptions:\n{assumptions_str}")
    else:
        prompt_lines.append("Assumptions: None reported.")

    # Open questions
    if research.open_questions:
        questions_str = "\n".join(f"- {q}" for q in research.open_questions)
        prompt_lines.append(f"Open Questions:\n{questions_str}")
    else:
        prompt_lines.append("Open Questions: None reported.")

    # Sources provenance
    if research.sources:
        sources_str = "\n".join(f"- {s.title} ({s.source_type})" for s in research.sources)
        prompt_lines.append(f"Referenced Sources:\n{sources_str}")

    prompt_lines.append(
        "\nTASK: Based strictly on the above research findings and constraints, develop a clear, practical strategy with ranked priorities, phased roadmap, realistic trade-offs, and measurable success metrics."
    )

    return "\n\n".join(prompt_lines)
