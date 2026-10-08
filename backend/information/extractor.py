"""
Deterministic HTML content extractor for the Information Acquisition Layer.
"""
from typing import Optional, List
from bs4 import BeautifulSoup, Comment

from backend.information.models import ExtractedContent
from backend.shared.logger import get_logger

logger = get_logger(__name__)

# Tags representing boilerplate or non-content elements to strip out
DISCARD_TAGS = {
    "script",
    "style",
    "noscript",
    "nav",
    "footer",
    "header",
    "aside",
    "svg",
    "iframe",
    "form",
    "button",
    "input",
    "select",
    "textarea",
    "menu",
    "canvas",
}


class ContentExtractor:
    """
    Extracts article title, headings, and readable body text from HTML.
    Eliminates noise elements and preserves document structure deterministically.
    """

    def extract(self, html: str, fallback_url: Optional[str] = None) -> ExtractedContent:
        """
        Parses raw HTML and extracts clean text and title.

        Args:
            html: Raw HTML string.
            fallback_url: Optional URL to derive fallback title.

        Returns:
            ExtractedContent model.
        """
        if not html or not html.strip():
            return ExtractedContent(title="", text="", headings=[])

        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as e:
            logger.warning(f"ContentExtractor: HTML parsing exception: {e}")
            return ExtractedContent(title="", text=html[:500], headings=[])

        # 1. Extract Page Title
        title = ""
        title_tag = soup.find("title")
        if title_tag and title_tag.get_text(strip=True):
            title = title_tag.get_text(strip=True)

        if not title:
            # Check og:title meta tag
            og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
            if og_title and og_title.get("content"):
                title = str(og_title.get("content")).strip()

        if not title:
            # Check first h1
            h1 = soup.find("h1")
            if h1 and h1.get_text(strip=True):
                title = h1.get_text(strip=True)

        # 2. Remove unwanted tags and comments
        for tag in soup.find_all(DISCARD_TAGS):
            tag.decompose()

        for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
            comment.extract()

        # 3. Locate Main Content Container
        main_container = (
            soup.find("article")
            or soup.find("main")
            or soup.find(attrs={"role": "main"})
            or soup.find(id=lambda i: i and "content" in i.lower())
            or soup.body
            or soup
        )

        # 4. Extract headings and block elements
        headings: List[str] = []
        for h in main_container.find_all(["h1", "h2", "h3", "h4"]):
            h_text = h.get_text(strip=True)
            if h_text and h_text not in headings:
                headings.append(h_text)

        # 5. Extract structured text preserving paragraph breaks
        blocks: List[str] = []
        for element in main_container.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote"]):
            text = element.get_text(strip=True)
            if not text:
                continue

            tag_name = element.name.lower()
            if tag_name in ("h1", "h2", "h3", "h4"):
                blocks.append(f"\n## {text}\n")
            elif tag_name == "li":
                blocks.append(f"- {text}")
            else:
                blocks.append(text)

        if blocks:
            extracted_text = "\n".join(blocks)
        else:
            # Fallback to get_text if specific tags are absent
            extracted_text = main_container.get_text(separator="\n", strip=True)

        return ExtractedContent(
            title=title,
            text=extracted_text,
            headings=headings,
        )


__all__ = ["ContentExtractor", "DISCARD_TAGS"]
