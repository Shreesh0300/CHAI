"""
Multilingual NLP Layer for CHAI.

Supports canonical ISO-style short language codes:
  - 'en': English
  - 'hi': Hindi
  - 'kn': Kannada

Provides:
  1. Canonical language constants and mapping.
  2. Fast, resilient script-based language detection.
  3. Non-destructive text normalization preserving Kannada/Hindi scripts,
     code snippets, URLs, numbers, and technical identifiers.
"""

import re
import unicodedata
from typing import Optional, Dict
from pydantic import BaseModel, Field

SUPPORTED_LANGUAGES = ["en", "hi", "kn", "sa"]
DEFAULT_LANGUAGE = "en"

LANGUAGE_NAMES: Dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "kn": "Kannada",
    "sa": "Sanskrit",
}

CANONICAL_LANGUAGE_MAP: Dict[str, str] = {
    "en": "en",
    "english": "en",
    "en-us": "en",
    "en-gb": "en",
    "hi": "hi",
    "hindi": "hi",
    "hin": "hi",
    "kn": "kn",
    "kannada": "kn",
    "kan": "kn",
    "sa": "sa",
    "sanskrit": "sa",
    "san": "sa",
    "sa-in": "sa",
}


class LanguageDetectionResult(BaseModel):
    """Structured result returned by the language detector."""
    language: str = Field(..., description="Canonical language code: 'en', 'hi', or 'kn'")
    confidence: Optional[float] = Field(default=None, description="Calibrated detection confidence or None")


def canonicalize_language(lang_input: Optional[str]) -> Optional[str]:
    """
    Normalizes human-readable names or varying cases to canonical 'en', 'hi', or 'kn'.
    Returns None if unsupported or invalid.
    """
    if not lang_input:
        return None
    cleaned = lang_input.strip().lower()
    return CANONICAL_LANGUAGE_MAP.get(cleaned)


def detect_language(text: Optional[str]) -> LanguageDetectionResult:
    """
    Detects whether the input text is Kannada ('kn'), Hindi ('hi'), or English ('en').

    Uses Unicode script boundaries for 100% deterministic, instant script classification:
      - Kannada block: U+0C80 - U+0CFF
      - Devanagari block (Hindi): U+0900 - U+097F
      - Latin/ASCII (English): a-zA-Z

    Falls back safely to 'en' with confidence=None if text is empty or ambiguous.
    """
    if not text or not text.strip():
        return LanguageDetectionResult(language=DEFAULT_LANGUAGE, confidence=None)

    kn_chars = sum(1 for c in text if "\u0c80" <= c <= "\u0cff")
    hi_chars = sum(1 for c in text if "\u0900" <= c <= "\u097f")
    en_chars = sum(1 for c in text if "a" <= c.lower() <= "z")

    total_script_chars = kn_chars + hi_chars + en_chars

    # 1. Kannada script dominance
    if kn_chars > 0 and kn_chars >= hi_chars:
        conf = round(kn_chars / max(1, total_script_chars), 2) if total_script_chars else None
        return LanguageDetectionResult(language="kn", confidence=conf)

    # 2. Devanagari script dominance (Hindi or Sanskrit)
    if hi_chars > 0 and hi_chars > kn_chars:
        conf = round(hi_chars / max(1, total_script_chars), 2) if total_script_chars else None
        # Check for distinctive Sanskrit markers (e.g., visarga, halanta-m endings, classic terms)
        sanskrit_patterns = [
            r"नमस्कारम्",
            r"परीक्षणम्",
            r"इदं",
            r"इदम्",
            r"अस्ति",
            r"भवति",
            r"नमः",
            r"सर्वम्",
            r"एवम्",
            r"म\u094d\b",  # words ending in म्
            r"\u0903\b",   # words ending in visarga ः
        ]
        is_sanskrit = any(re.search(pat, text) for pat in sanskrit_patterns)
        detected_code = "sa" if is_sanskrit else "hi"
        return LanguageDetectionResult(language=detected_code, confidence=conf)

    # 3. Latin / English dominance
    if en_chars > 0:
        conf = round(en_chars / max(1, total_script_chars), 2) if total_script_chars else None
        return LanguageDetectionResult(language="en", confidence=conf)

    # 4. Safe fallback to default language
    return LanguageDetectionResult(language=DEFAULT_LANGUAGE, confidence=None)


def normalize_text(text: Optional[str]) -> str:
    """
    Cleans unnecessary whitespace while strictly preserving:
      - Indian language scripts (Kannada, Devanagari)
      - Technical terms, library names, APIs, and product names
      - Code blocks, functions, and backticks
      - URLs and paths
      - Numbers and punctuation

    Does NOT translate or transliterate text.
    """
    if not text:
        return ""

    # Normalize unicode to standard NFC form (composes characters accurately)
    normalized = unicodedata.normalize("NFC", text)

    # Remove non-printable control characters except standard whitespace \n, \t, \r
    cleaned_chars = [
        c for c in normalized
        if c in ("\n", "\t", "\r") or not unicodedata.category(c).startswith("C")
    ]
    cleaned = "".join(cleaned_chars)

    # Collapse multiple inline spaces and tabs while preserving newlines
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in cleaned.splitlines()]
    result = "\n".join(line for line in lines if line)

    return result or text.strip()
