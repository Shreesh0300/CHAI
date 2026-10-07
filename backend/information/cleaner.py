"""
Text cleaning and normalization utilities for extracted web content.
"""
import html
import re
import unicodedata

DEFAULT_MAX_CHARS = 10_000


class TextCleaner:
    """
    Normalizes and cleans extracted text while preserving faithful source content.
    Prevents unbounded context consumption via configurable character caps.
    """

    def __init__(self, max_chars: int = DEFAULT_MAX_CHARS):
        self.max_chars = max_chars

    def clean(self, raw_text: str) -> str:
        """
        Cleans and normalizes text extracted from HTML.

        Args:
            raw_text: Dirty or unformatted extracted text.

        Returns:
            Normalized, cleanly formatted text within max_chars.
        """
        if not raw_text:
            return ""

        # 1. Unescape HTML entities (&amp;, &nbsp;, &gt;, etc.)
        text = html.unescape(raw_text)

        # 2. Normalize Unicode characters (compatibility decomposition followed by canonical composition)
        text = unicodedata.normalize("NFKC", text)

        # 3. Replace non-breaking spaces and exotic whitespace with standard spaces
        text = text.replace("\xa0", " ").replace("\u200b", "")

        # 4. Collapse inline whitespace (tabs, consecutive spaces) to a single space
        text = re.sub(r"[ \t]+", " ", text)

        # 5. Remove leading/trailing spaces per line and filter blank lines
        lines = [line.strip() for line in text.splitlines()]
        cleaned_lines = [line for line in lines if line]

        # 6. Reconstruct with standard paragraph breaks (max 2 consecutive newlines)
        joined_text = "\n\n".join(cleaned_lines)
        joined_text = re.sub(r"\n{3,}", "\n\n", joined_text).strip()

        # 7. Bound maximum character length to protect downstream LLM context window
        if len(joined_text) > self.max_chars:
            cutoff = joined_text[: self.max_chars]
            # Try to truncate at a natural sentence or word boundary
            last_period = cutoff.rfind(".")
            if last_period > self.max_chars * 0.8:
                truncated = cutoff[: last_period + 1]
            else:
                last_space = cutoff.rfind(" ")
                truncated = cutoff[:last_space] if last_space > 0 else cutoff

            joined_text = f"{truncated.strip()}\n\n[Content truncated at {self.max_chars} character limit]"

        return joined_text


__all__ = ["TextCleaner", "DEFAULT_MAX_CHARS"]
