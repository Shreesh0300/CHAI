"""
Deterministic helper utilities for the Security Agent.
Provides minimal classification, severity normalization, and finding validation
without introducing heavy external security scanners or third-party dependencies.
"""
from typing import List
from backend.shared.logger import get_logger

logger = get_logger(__name__)

SEVERITY_ORDER = ["Critical", "High", "Medium", "Low", "Informational"]


def normalize_severity(level: str) -> str:
    """
    Normalizes severity strings into standardized ratings:
    Critical, High, Medium, Low, or Informational.
    """
    clean = (level or "").strip().lower()
    if "crit" in clean:
        return "Critical"
    elif "high" in clean:
        return "High"
    elif "med" in clean or "mod" in clean:
        return "Medium"
    elif "low" in clean:
        return "Low"
    elif "info" in clean:
        return "Informational"
    return "Medium"


def categorize_threat(threat_description: str) -> str:
    """
    Basic deterministic categorization of security threat descriptions.
    """
    desc = threat_description.lower()
    if any(k in desc for k in ["prompt", "injection", "jailbreak"]):
        return "Prompt Injection"
    elif any(k in desc for k in ["auth", "token", "jwt", "session", "password", "login"]):
        return "Authentication"
    elif any(k in desc for k in ["role", "permission", "privilege", "idor", "rbac"]):
        return "Authorization"
    elif any(k in desc for k in ["secret", "api key", "credential", "env"]):
        return "Secret Exposure"
    elif any(k in desc for k in ["api", "endpoint", "rate limit", "ddos"]):
        return "API Security"
    elif any(k in desc for k in ["pii", "privacy", "leak", "gdpr", "hipaa", "data"]):
        return "Data Privacy"
    return "General Infrastructure"


def clean_security_findings(findings: List[str]) -> List[str]:
    """
    Deduplicates and strips whitespace from a list of security findings.
    """
    seen = set()
    cleaned = []
    for f in findings:
        item = f.strip()
        if item and item not in seen:
            seen.add(item)
            cleaned.append(item)
    return cleaned
