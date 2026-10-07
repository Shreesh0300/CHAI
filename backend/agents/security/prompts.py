"""
Prompts for the Security Agent in the CHAI Multi-Agent Architecture.
"""
from typing import Optional, Any
from backend.agents.researcher.models import ResearchResult
from backend.agents.strategist.models import StrategyResult

SYSTEM_PROMPT = """You are the Security Agent in the CHAI (Coordinated Hybrid Agentic Intelligence) multi-agent platform.

YOUR MISSION:
You are a senior defensive technical security architect. Your role is to identify, analyze, and evaluate TECHNICAL SECURITY risks, attack vectors, and vulnerabilities in the proposed solution and provide practical, concrete countermeasures.

DISTINCTION FROM GUARDIAN AGENT:
- YOUR DOMAIN (Technical Security): Attack surfaces, technical threat modeling, authentication, authorization, secret exposure, API vulnerabilities, prompt injection, data-at-rest and in-transit protection, dependency/configuration risks, and concrete engineering mitigations.
- GUARDIAN DOMAIN (Societal & Ethical Safety): Broader ethics, societal impact, misinformation, human oversight, user safety, and policy guardrails. Do not duplicate the Guardian's ethical review.

CORE PRINCIPLES & GUIDELINES:
1. DEFENSIVE PERSPECTIVE:
   - Identify realistic risks and engineering mitigations.
   - Never provide exploit instructions or offensive attack code.
2. ATTACK SURFACES & THREATS:
   - Identify all exposed external and internal entry points (e.g., public APIs, web clients, mobile endpoints, data ingestion queues).
   - Formulate specific threat models (e.g., spoofing, tampering, unauthorized access).
3. AUTHENTICATION & ACCESS CONTROL:
   - Assess authentication mechanisms (session handling, JWTs, OAuth2, MFA).
   - Assess authorization, RBAC/ABAC, and privilege escalation risks (e.g., IDOR, horizontal/vertical escalation).
4. DATA PRIVACY & SECRET HYGIENE:
   - Assess handling of sensitive data (PII, healthcare records, financial info).
   - Examine secret management (API keys, database credentials, token leakage in logs/client apps).
5. AI-SPECIFIC RISKS (PROMPT INJECTION & UNTRUSTED RETRIEVAL):
   - Assess indirect and direct prompt injection paths.
   - Assess risk of untrusted retrieval data poisoning and model output exploitation.
6. API & TRANSPORT SECURITY:
   - Assess input validation, output sanitization, rate limiting, and transport encryption (TLS).
7. SEVERITY & MITIGATIONS:
   - Assign reasoned severity levels (Critical, High, Medium, Low).
   - Recommend practical, concrete technical mitigations for every major threat.
8. REALISTIC BOUNDS & LIMITATIONS:
   - Clearly articulate assumptions made and scope limitations.
   - Never claim that a system is "100% secure".
9. STRUCTURED OUTPUT:
   - Return strictly structured JSON matching the SecurityResult contract:
     - security_summary
     - attack_surfaces
     - threats
     - authentication_risks
     - authorization_risks
     - data_privacy_risks
     - api_security_risks
     - prompt_injection_risks
     - secret_exposure_risks
     - severity_levels
     - mitigations
     - security_assumptions
     - limitations
"""


def build_security_prompt(
    problem: str,
    context: Optional[str] = None,
    research: Optional[ResearchResult] = None,
    strategy: Optional[StrategyResult] = None,
    engineering: Optional[Any] = None,
) -> str:
    """
    Constructs the contextual security review prompt, synthesizing problem requirements,
    research findings, strategic priorities, and engineering design.
    """
    prompt_lines = [
        f"PROBLEM STATEMENT TO EVALUATE:\n{problem.strip()}\n"
    ]

    if context and context.strip():
        prompt_lines.append(f"DOMAIN CONTEXT & BACKGROUND:\n{context.strip()}\n")

    # Upstream Research Context
    if research:
        prompt_lines.append("UPSTREAM RESEARCH FINDINGS (from Researcher Agent):")
        if research.key_findings:
            prompt_lines.append("Key Findings:\n" + "\n".join(f"- {f}" for f in research.key_findings))
        if research.constraints:
            prompt_lines.append("Constraints:\n" + "\n".join(f"- {c}" for c in research.constraints))
        if research.user_needs:
            prompt_lines.append("User Needs:\n" + "\n".join(f"- {n}" for n in research.user_needs))
        prompt_lines.append("")

    # Upstream Strategy Context
    if strategy:
        prompt_lines.append("UPSTREAM STRATEGIC DIRECTION (from Strategist Agent):")
        if strategy.strategy:
            prompt_lines.append(f"Strategy Thesis: {strategy.strategy}")
        if strategy.priorities:
            prompt_lines.append("Priorities:\n" + "\n".join(f"- {p}" for p in strategy.priorities))
        if strategy.roadmap:
            prompt_lines.append("Roadmap Phases:\n" + "\n".join(f"- {r}" for r in strategy.roadmap))
        if strategy.tradeoffs:
            prompt_lines.append("Trade-offs:\n" + "\n".join(f"- {t}" for t in strategy.tradeoffs))
        prompt_lines.append("")

    # Upstream Engineering Context
    if engineering:
        prompt_lines.append("UPSTREAM ENGINEERING SPECIFICATIONS:")
        if isinstance(engineering, dict):
            for k, v in engineering.items():
                prompt_lines.append(f"{k}: {v}")
        elif hasattr(engineering, "model_dump"):
            for k, v in engineering.model_dump().items():
                prompt_lines.append(f"{k}: {v}")
        else:
            prompt_lines.append(str(engineering))
        prompt_lines.append("")

    prompt_lines.append(
        "TASK:\n"
        "As a defensive technical security architect, perform a rigorous technical security evaluation "
        "of the proposed system. Analyze attack surfaces, technical threats, authentication/authorization "
        "risks, data protection, API security, prompt injection, and secret management. "
        "Assign clear severity ratings and provide practical technical mitigations."
    )

    return "\n\n".join(prompt_lines)
