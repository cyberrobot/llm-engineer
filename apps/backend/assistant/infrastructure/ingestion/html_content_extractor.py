import re
from collections.abc import Iterable

from bs4 import BeautifulSoup, NavigableString, Tag
from bs4.element import AttributeValueList

from assistant.application.ports.content_extractor import ContentExtractor
from assistant.domain.extracted_document import ExtractedDocument
from assistant.domain.website_document import WebsiteDocument

_SPACE = re.compile(r"\s+")
_BOILERPLATE_MARKERS = re.compile(
    r"(?:^|[-_\s])(?:cookie[-_\s](?:banner|consent|controls?|settings)|"
    r"consent[-_\s](?:banner|dialog|modal)|modal[-_\s]overlay|social[-_\s]share|"
    r"share[-_\s](?:buttons?|controls?)|sidebar[-_\s]navigation|breadcrumb)(?:$|[-_\s])",
    re.IGNORECASE,
)
_BOILERPLATE_TITLES = {
    "cookie settings",
    "privacy settings",
    "access denied",
    "not found",
    "untitled",
}
_SEMANTIC_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "blockquote", "table"}


def _normalise_inline(text: str) -> str:
    return _SPACE.sub(" ", text).strip()


def _own_text(tag: Tag) -> str:
    """Read text owned by a semantic element, excluding nested semantic blocks."""
    values: list[str] = []
    for descendant in tag.descendants:
        if not isinstance(descendant, NavigableString):
            continue
        parent = descendant.parent
        nested = False
        while isinstance(parent, Tag) and parent is not tag:
            if parent.name in _SEMANTIC_TAGS:
                nested = True
                break
            parent = parent.parent
        if not nested:
            values.append(str(descendant))
    return _normalise_inline(" ".join(values))


def _valid_title(value: str | None) -> str | None:
    if value is None:
        return None
    title = _normalise_inline(value)
    if not title or len(title) > 200 or title.casefold() in _BOILERPLATE_TITLES:
        return None
    return title


def _attribute_text(value: str | AttributeValueList | None) -> str:
    if isinstance(value, AttributeValueList):
        return " ".join(str(item) for item in value)
    return str(value or "")


class HtmlContentExtractor(ContentExtractor):
    """Extract a conservative Markdown-like semantic representation from HTML."""

    def extract(self, document: WebsiteDocument) -> ExtractedDocument | None:
        if not document.html.strip():
            return None
        soup = BeautifulSoup(document.html, "html.parser")
        title = self._extract_title(soup, document.title)
        self._remove_non_content(soup)
        root = self._content_root(soup)
        if root is None:
            return None

        blocks, headings = self._semantic_blocks(root)
        if not blocks:
            fallback = _normalise_inline(root.get_text(" ", strip=True))
            if not fallback:
                return None
            blocks = [fallback]
        return ExtractedDocument(
            source_url=document.url,
            title=title,
            headings=headings,
            text="\n\n".join(blocks),
            retrieved_at=document.retrieved_at,
        )

    @staticmethod
    def _extract_title(soup: BeautifulSoup, supplied_title: str | None) -> str | None:
        """Prefer loader, Open Graph, Twitter, HTML, then the first meaningful h1."""
        candidates: list[str | None] = [supplied_title]
        for selector in ('meta[property="og:title"]', 'meta[name="twitter:title"]'):
            metadata = soup.select_one(selector)
            candidates.append(
                _attribute_text(metadata.get("content")) if isinstance(metadata, Tag) else None
            )
        candidates.append(soup.title.get_text(" ") if soup.title else None)
        first_h1 = soup.find("h1")
        candidates.append(_own_text(first_h1) if isinstance(first_h1, Tag) else None)
        return next((title for candidate in candidates if (title := _valid_title(candidate))), None)

    @staticmethod
    def _remove_non_content(soup: BeautifulSoup) -> None:
        for element in soup.find_all(
            [
                "script",
                "style",
                "noscript",
                "template",
                "svg",
                "canvas",
                "iframe",
                "nav",
                "footer",
            ]
        ):
            element.decompose()
        for element in list(soup.find_all(True)):
            if not isinstance(element, Tag) or element.parent is None:
                continue
            hidden = element.has_attr("hidden") or element.get("aria-hidden") == "true"
            styles = str(element.get("style", "")).replace(" ", "").lower()
            hidden = hidden or "display:none" in styles or "visibility:hidden" in styles
            identifiers = " ".join(
                [_attribute_text(element.get("id")), _attribute_text(element.get("class"))]
            )
            if hidden or _BOILERPLATE_MARKERS.search(identifiers):
                element.decompose()

    @staticmethod
    def _content_root(soup: BeautifulSoup) -> Tag | None:
        for candidate in (
            soup.find("main"),
            soup.find("article"),
            soup.select_one('[role="main"]'),
            soup.select_one("#main-content, .main-content, #content, .page-content"),
            soup.body,
        ):
            if isinstance(candidate, Tag):
                return candidate
        return None

    def _semantic_blocks(self, root: Tag) -> tuple[list[str], list[str]]:
        blocks: list[str] = []
        headings: list[str] = []
        for element in root.find_all(_SEMANTIC_TAGS):
            if not isinstance(element, Tag):
                continue
            block = self._format_element(element)
            if not block:
                continue
            blocks.append(block)
            if element.name and re.fullmatch(r"h[1-6]", element.name):
                headings.append(_own_text(element))
        return blocks, headings

    def _format_element(self, element: Tag) -> str | None:
        name = element.name or ""
        if re.fullmatch(r"h[1-6]", name):
            text = _own_text(element)
            return f"{'#' * int(name[1])} {text}" if text else None
        if name == "p":
            return _own_text(element) or None
        if name == "blockquote":
            text = _own_text(element)
            return f"> {text}" if text else None
        if name in {"ul", "ol"}:
            return self._format_list(element, ordered=name == "ol")
        if name == "table":
            return self._format_table(element)
        return None

    @staticmethod
    def _format_list(element: Tag, *, ordered: bool) -> str | None:
        lines: list[str] = []
        items: Iterable[Tag] = element.find_all("li", recursive=False)
        for index, item in enumerate(items, start=1):
            text = _own_text(item)
            if text:
                lines.append(f"{index}. {text}" if ordered else f"- {text}")
        return "\n".join(lines) or None

    @staticmethod
    def _format_table(element: Tag) -> str | None:
        rows: list[str] = []
        for row in element.find_all("tr"):
            cells = [
                _normalise_inline(cell.get_text(" ", strip=True))
                for cell in row.find_all(["th", "td"])
            ]
            if any(cells):
                rows.append(" | ".join(cell for cell in cells if cell))
        return "\n".join(rows) or None
