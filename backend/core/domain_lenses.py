"""
CHAI Domain Lens - Centralized Role-Specific Domain Guidance.

Each specialist agent receives a role-specific domain lens addendum appended
to its system prompt that sharpens its reasoning perspective for the resolved
domain WITHOUT changing its fundamental responsibility, core identity, or schema contracts.

DESIGN PRINCIPLES
-----------------
* Exactly ONE instance/concept of each existing agent - no duplicate classes.
* The system produces exactly one resolved domain: "business" | "personal" | "software".
* Lenses are additive (appended), never replacing base agent responsibilities.
* Base Agent Responsibility + Domain-Specific Lens + User Request + Context = Agent Output.
* Clean normalization supporting canonical keys ("business", "personal", "software")
  as well as legacy internal keys ("business_strategy", "personal_career", "software_engineering").
* Role-specific guidance across all 10 canonical CHAI agents:
    1. Researcher
    2. Strategist
    3. Engineer
    4. Guardian
    5. Security
    6. Evaluator
    7. Conflict Resolver
    8. Synthesizer
    9. Reliability Monitor
    10. Output Validator
"""

from __future__ import annotations
from typing import Optional, Dict, Any


CANONICAL_DOMAINS = ["business", "personal", "software"]


def normalize_domain(domain: Optional[str]) -> str:
    """
    Normalizes a domain string to the canonical 3 resolved domains:
    'business', 'personal', or 'software' (or 'general' if unspecified).
    """
    if not domain:
        return "general"
    d = str(domain).strip().lower()
    if d in ("business", "business_strategy", "biz", "commercial"):
        return "business"
    if d in ("personal", "personal_career", "career", "individual", "life"):
        return "personal"
    if d in ("software", "software_engineering", "engineering", "tech", "technical", "cybersecurity"):
        return "software"
    return d


def canonicalize_domain(domain: Optional[str], default: str = "business") -> str:
    """
    Enforces that a resolved domain strictly belongs to the 3 canonical domains:
    'business', 'personal', or 'software'.
    Never returns 'general'.
    """
    norm = normalize_domain(domain)
    if norm in CANONICAL_DOMAINS:
        return norm
    return default


# ---------------------------------------------------------------------------
# Role x Domain lens matrix (10 agents x 3 canonical domains)
# ---------------------------------------------------------------------------

_LENSES: Dict[str, Dict[str, str]] = {

    "researcher": {
        "business": (
            "DOMAIN LENS — BUSINESS:\n"
            "Research customers, markets, competitors, pricing, industry dynamics, and commercial evidence.\n"
            "STRICT EVIDENCE STANDARDS:\n"
            "- Explicitly distinguish verified facts, empirical findings, and reliable benchmarks from working hypotheses or assumptions.\n"
            "- Never fabricate market sizes, competitor details, churn rates, customer lifetime value (LTV), or pricing benchmarks without verified citations.\n"
            "- Do not assume all businesses in a sector share identical needs or operating models.\n"
            "- Do not introduce unprompted technical scopes (e.g. POS integration, payment-facilitator fees) unless explicitly established by the user problem. Preserve source provenance."
        ),
        "personal": (
            "DOMAIN LENS — PERSONAL:\n"
            "Identify the user's actual decision context, known facts, constraints, options, and practical trade-offs.\n"
            "DECISION SUPPORT STANDARDS:\n"
            "- Never invent personal facts, financial circumstances, living expenses, or unstated user preferences.\n"
            "- Explicitly identify unknown factors (e.g., exact salary differential, relocation costs, commute times, growth tracks) without treating missing details as a reason to withhold research.\n"
            "- Gather comparative evaluation criteria: compensation & costs, career growth & trajectory, work-life balance, family priorities, and long-term consequences.\n"
            "- Never assume the user prioritizes income over family or vice versa."
        ),
        "software": (
            "DOMAIN LENS — SOFTWARE:\n"
            "Prioritize official documentation, RFC standards (OAuth 2.0, RFC 7519 JWT), APIs, and security best practices.\n"
            "TECHNICAL ACCURACY STANDARDS:\n"
            "- Distinguish signed JWTs (JWS) from encrypted tokens (JWE). Never describe JWT signature verification as decryption.\n"
            "- Differentiate authentication from authorization.\n"
            "- Clarify that HttpOnly cookies prevent script token theft (document.cookie), but ambient credential requests still occur under XSS unless CSRF defenses and strict CSP are in place.\n"
            "- Ground refresh token lifecycle (rotation, revocation, reuse detection) and multi-tenant data isolation patterns."
        ),
        "general": "",
    },

    "strategist": {
        "business": (
            "DOMAIN LENS — BUSINESS:\n"
            "Frame commercial strategy, positioning, unit economics, and go-to-market execution.\n"
            "EVALUATION & RECOMMENDATION STANDARDS:\n"
            "- Compare target segments or options across explicit evaluation criteria (e.g., sales velocity, willingness to pay, onboarding complexity, vertical fragmentation).\n"
            "- Clearly explain which claims are supported by evidence and which are working hypotheses.\n"
            "- Provide a provisional recommendation when reasonable, but explicitly state what product characteristics would change or reverse that recommendation.\n"
            "- Suggest practical customer-discovery experiments (e.g. 10 structured interviews per segment) and measurable validation milestones."
        ),
        "personal": (
            "DOMAIN LENS — PERSONAL:\n"
            "Evaluate personal options objectively across multiple dimensions: compensation, relocation costs, career growth, work-life balance, family priorities, and long-term consequences.\n"
            "DECISION FRAMEWORK STANDARDS:\n"
            "- Restate the decision and known facts neutrally.\n"
            "- Explain when each option is preferable without imposing unsolicited personal preferences.\n"
            "- Provide a conditional recommendation and decision framework (e.g., net financial equation, weighted scoring, or 10/10/10 rule).\n"
            "- Identify key unknowns and suggest a small number of specific follow-up questions to help the user resolve the dilemma.\n"
            "- Never ask the user to provide the strategic evaluation that CHAI should perform."
        ),
        "software": (
            "DOMAIN LENS — SOFTWARE:\n"
            "Optimize architecture decisions, implementation sequence, scalability, and maintainability.\n"
            "ENGINEERING PRAGMATISM:\n"
            "- Differentiate baseline MVP requirements from optional production-hardening infrastructure.\n"
            "- For token/session management, recommend a simple, reliable PostgreSQL-backed session or refresh token table for MVP.\n"
            "- Do not automatically mandate Redis, Kubernetes, or microservices unless distributed scale or sub-millisecond revocation at volume is justified.\n"
            "- Plan phased milestones: MVP (PostgreSQL, FastAPI, React) -> Hardening (PgBouncer, rate limiting, RLS) -> Scale (Redis, distributed caching)."
        ),
        "general": "",
    },

    "engineer": {
        "business": (
            "DOMAIN LENS — BUSINESS:\n"
            "Assess technical feasibility and MVP scope proportional to commercial constraints. Do not assume specialized integrations (like POS systems or payment facilitators) are required unless the business problem specifies them."
        ),
        "personal": (
            "DOMAIN LENS — PERSONAL:\n"
            "Apply technical reasoning only when technology or automation is explicitly requested. If non-technical, provide a concise minimal note without manufacturing irrelevant technical complexity."
        ),
        "software": (
            "DOMAIN LENS — SOFTWARE:\n"
            "Deliver rigorous, production-grade technical engineering:\n"
            "- Authentication vs Authorization: Authentication verifies identity (Argon2id/bcrypt hashed credentials); authorization enforces roles and permissions (RBAC).\n"
            "- JWT Handling: Signed JWTs (JWS) verified via cryptographic signature validation (secret or public key), issuer, audience, and expiration. Signature verification is NOT decryption.\n"
            "- Cookie & Web Security: Store tokens in HttpOnly, Secure, SameSite=Lax/Strict cookies; implement CSRF protection (Double Submit Cookie, custom header verification); note that HttpOnly mitigates token theft via script read, but ambient requests still execute under XSS unless CSP and sanitization are enforced.\n"
            "- Refresh Token Rotation & Reuse Detection: Store refresh tokens in PostgreSQL with token family IDs; upon refresh, rotate token; if a used token is presented, revoke the entire token family.\n"
            "- Multi-Tenancy: PostgreSQL Row-Level Security (RLS) or explicit tenant ID filtering.\n"
            "- Connection pooling (PgBouncer) and deployment considerations."
        ),
        "general": "",
    },

    "guardian": {
        "business": (
            "DOMAIN LENS — BUSINESS:\n"
            "Evaluate ethics, customer impact, fairness, regulation, reputational risk, and responsible "
            "business practices. Flag commercial fairness concerns, consumer transparency, and regulatory "
            "compliance exposure (consumer protection, labor, algorithmic bias)."
        ),
        "personal": (
            "DOMAIN LENS — PERSONAL:\n"
            "Prioritize autonomy, privacy, well-being, potential harm, sensitive context, and human agency. "
            "Avoid paternalism or unsolicited judgment. Flag high-stakes personal risks and preserve user discretion."
        ),
        "software": (
            "DOMAIN LENS — SOFTWARE:\n"
            "Evaluate reliability, failure modes, misuse, human oversight, safe defaults, and data handling. "
            "Focus on AI system transparency, safe failure behavior, audit logging, and data privacy by design."
        ),
        "general": "",
    },

    "security": {
        "business": (
            "DOMAIN LENS — BUSINESS:\n"
            "Focus on customer/business data, financial data, access control, vendors, integrations, "
            "and regulatory compliance (GDPR, SOC 2, PCI-DSS). Calibrate threats to commercial impact."
        ),
        "personal": (
            "DOMAIN LENS — PERSONAL:\n"
            "Protect personal information, identity, accounts, private conversations, credentials, and sensitive "
            "data. If the problem has no significant attack surface, provide a concise low-risk assessment "
            "without manufacturing artificial threats."
        ),
        "software": (
            "DOMAIN LENS — SOFTWARE:\n"
            "Evaluate authentication and authorization security controls rigorously:\n"
            "- Cryptographic precision: Signed JWTs validate cryptographic signatures using HMAC or RSA/ECDSA; never call signature verification decryption.\n"
            "- XSS Boundaries: Clearly state that HttpOnly cookies prevent JavaScript from reading tokens (document.cookie), but they DO NOT prevent an attacker executing XSS from issuing ambient authenticated requests. Mitigate via strict Content Security Policy (CSP), context-aware output encoding, and input sanitization.\n"
            "- CSRF Protections: Enforce CSRF tokens or custom headers alongside cookie-based sessions.\n"
            "- Refresh Token Reuse Detection: Ensure invalid/reused refresh tokens trigger family-wide session revocation.\n"
            "- Tenant Data Isolation: Verify database-level isolation (PostgreSQL RLS or tenant scoping) to prevent cross-tenant data leakage."
        ),
        "general": "",
    },

    "evaluator": {
        "business": (
            "DOMAIN LENS — BUSINESS:\n"
            "Evaluate commercial and strategic claims rigorously:\n"
            "- Detect and flag unsupported assertions (e.g., unsubstantiated churn rates, fabricated LTV, or unverified POS/payment dependencies).\n"
            "- Ensure working hypotheses are explicitly separated from verified market facts.\n"
            "- Verify that segment comparisons use explicit criteria and recommendations are conditional on product scope."
        ),
        "personal": (
            "DOMAIN LENS — PERSONAL:\n"
            "Evaluate personal decision guidance:\n"
            "- Ensure the analysis provides actionable preliminary guidance and does NOT ask the user to supply the strategic evaluation that CHAI should perform.\n"
            "- Flag any invented user facts, assumed financial circumstances, or biased value weightings (e.g., assuming money matters more than family).\n"
            "- Verify that unknown factors are identified as caveats/questions rather than blocking delivery."
        ),
        "software": (
            "DOMAIN LENS — SOFTWARE:\n"
            "Evaluate technical correctness and security precision:\n"
            "- Check that JWT signature verification is NEVER called decryption.\n"
            "- Check that HttpOnly cookies are not presented as total immunity against XSS.\n"
            "- Verify that CSRF defense and refresh token rotation/reuse detection are addressed.\n"
            "- Verify that infrastructure complexity (Redis, Kubernetes) is justified rather than prematurely mandated."
        ),
        "general": "",
    },

    "conflict_resolver": {
        "business": (
            "DOMAIN LENS — BUSINESS:\n"
            "Resolve disagreements using evidence, commercial constraints, unit economics, and risk-adjusted outcomes. Commercial constraints > empirical evidence > speed-to-market > cost optimization."
        ),
        "personal": (
            "DOMAIN LENS — PERSONAL:\n"
            "Resolve disagreements by prioritizing user autonomy, stated values, well-being, and balanced trade-offs. Never prioritize one unstated personal value over another."
        ),
        "software": (
            "DOMAIN LENS — SOFTWARE:\n"
            "Resolve disagreements using correctness, security integrity, reliability, and implementation feasibility. Do not sacrifice security or correctness for premature optimization."
        ),
        "general": "",
    },

    "synthesizer": {
        "business": (
            "DOMAIN LENS — BUSINESS:\n"
            "Synthesize a rigorous, business-focused deliverable:\n"
            "1. Compare segments or options using explicit multi-dimensional evaluation criteria.\n"
            "2. Clearly distinguish verified evidence and benchmarks from working hypotheses and assumptions.\n"
            "3. Avoid inventing churn rates, LTV, or unstated integration requirements (e.g., POS or payment facilitators).\n"
            "4. Provide a provisional recommendation with explicit conditions on what product characteristics would alter it.\n"
            "5. Suggest practical customer-discovery experiments (e.g., 10 structured interviews per segment) with measurable validation criteria."
        ),
        "personal": (
            "DOMAIN LENS — PERSONAL:\n"
            "Synthesize a structured personal decision guide:\n"
            "1. Restate the decision and known facts neutrally.\n"
            "2. Compare options across compensation, relocation costs, career growth, work-life balance, family priorities, and long-term consequences.\n"
            "3. Explain when each option is preferable without assuming user preferences.\n"
            "4. Identify unknown factors without inventing personal circumstances.\n"
            "5. Provide a conditional recommendation and decision framework.\n"
            "6. Conclude with focused follow-up questions (e.g., salary delta, expected relocation expenses, career trajectory) to help refine the choice."
        ),
        "software": (
            "DOMAIN LENS — SOFTWARE:\n"
            "Deliver a precise, production-grade technical architecture:\n"
            "1. Clearly separate authentication from authorization.\n"
            "2. Detail credential storage (Argon2id/bcrypt) and JWT validation (signature, issuer, audience, expiry—never call signature verification decryption).\n"
            "3. Explain cookie security attributes (HttpOnly, Secure, SameSite) along with CSRF defenses and XSS mitigations (explaining that HttpOnly cookies prevent script token theft but ambient requests still execute under XSS).\n"
            "4. Detail refresh-token rotation, revocation, and reuse detection.\n"
            "5. Multi-tenant isolation (PostgreSQL RLS or tenant scoping).\n"
            "6. Distinguish MVP architecture (PostgreSQL session storage) from optional production scaling (Redis, PgBouncer, rate limiting)."
        ),
        "general": "",
    },

    "reliability_monitor": {
        "business": (
            "DOMAIN LENS — BUSINESS:\n"
            "Strictly flag unsubstantiated churn rates, fabricated LTV metrics, and unprompted scope assumptions. Ensure provisional business guidance is delivered with explicit disclosure of assumptions rather than blocked."
        ),
        "personal": (
            "DOMAIN LENS — PERSONAL:\n"
            "Verify that no user facts or preferences are fabricated. Ensure missing personal details are framed as caveats within provisional decision guidance, NOT as a reason to withhold an answer or demand the user perform the evaluation."
        ),
        "software": (
            "DOMAIN LENS — SOFTWARE:\n"
            "Enforce strict technical accuracy: ensure JWT signature verification is never termed decryption, cookie security does not overpromise XSS immunity, and infrastructure complexity is justified."
        ),
        "general": "",
    },

    "output_validator": {
        "business": (
            "DOMAIN LENS — BUSINESS:\n"
            "Verify that the answer separates hypotheses from facts, does not assert fabricated metrics as truth, and grounds segment recommendations in explicit criteria."
        ),
        "personal": (
            "DOMAIN LENS — PERSONAL:\n"
            "Verify that the answer provides actionable preliminary guidance, maintains neutral value weightings, highlights unknowns as conditional variables, and includes focused follow-up questions."
        ),
        "software": (
            "DOMAIN LENS — SOFTWARE:\n"
            "Verify technical correctness: ensure JWT signature verification is not called decryption, cookie boundaries (CSRF/XSS) are accurate, and refresh token rotation/reuse detection is covered."
        ),
        "general": "",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_domain_lens(agent: str, domain: Optional[str]) -> str:
    """
    Return the role-specific domain lens addendum for the given agent and domain.

    Parameters
    ----------
    agent : str
        Canonical agent identifier, e.g. 'researcher', 'strategist', 'engineer',
        'guardian', 'security', 'evaluator', 'conflict_resolver', 'synthesizer',
        'reliability_monitor', 'output_validator'.
    domain : Optional[str]
        Resolved domain string, e.g. 'business', 'personal', 'software'
        (also accepts 'business_strategy', 'personal_career', 'software_engineering').

    Returns
    -------
    str
        The addendum text to append to the agent's system prompt or guidance.
        Empty string if domain is general or unspecified.
    """
    if not domain:
        return ""
    canonical_domain = normalize_domain(domain)
    agent_key = str(agent).strip().lower()
    agent_lenses = _LENSES.get(agent_key, {})
    return agent_lenses.get(canonical_domain, agent_lenses.get("general", ""))


def apply_domain_lens(base_system_prompt: str, agent: str, domain: Optional[str]) -> str:
    """
    Append the domain lens addendum to a base system prompt.

    Returns the effective system prompt with the domain lens appended (if any).
    Returns the original prompt unchanged if no lens applies.
    """
    addendum = get_domain_lens(agent=agent, domain=domain)
    if not addendum:
        return base_system_prompt
    return f"{base_system_prompt}\n\n{addendum}"


__all__ = [
    "get_domain_lens",
    "apply_domain_lens",
    "normalize_domain",
    "canonicalize_domain",
    "CANONICAL_DOMAINS",
]
