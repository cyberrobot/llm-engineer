import re
import unicodedata
from hashlib import sha256

from assistant.application.ports.text_cleaner import TextCleaner
from assistant.domain.clean_document import CleanDocument
from assistant.domain.extracted_document import ExtractedDocument

_HORIZONTAL_WHITESPACE = re.compile(r"[^\S\n]+")
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")
_ZERO_WIDTH_CHARACTERS = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)


class NormalisingTextCleaner(TextCleaner):
    """Normalise extracted text without rewriting its meaning or structure."""

    def __init__(self, *, min_document_length: int) -> None:
        if min_document_length < 0:
            raise ValueError("Minimum document length must not be negative.")
        self._min_document_length = min_document_length

    def clean(self, document: ExtractedDocument) -> CleanDocument | None:
        text = unicodedata.normalize("NFC", document.text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.translate(_ZERO_WIDTH_CHARACTERS)
        text = "".join(
            character
            for character in text
            if character in "\n\t" or not unicodedata.category(character).startswith("C")
        )
        lines = [_HORIZONTAL_WHITESPACE.sub(" ", line).strip() for line in text.split("\n")]

        deduplicated: list[str] = []
        previous_content: str | None = None
        for line in lines:
            if line:
                if line == previous_content:
                    continue
                previous_content = line
            else:
                previous_content = None
            deduplicated.append(line)

        cleaned_text = _EXCESS_BLANK_LINES.sub("\n\n", "\n".join(deduplicated)).strip()
        meaningful_length = len(re.sub(r"(?m)^#{1,6}\s+", "", cleaned_text).strip())
        if not cleaned_text or meaningful_length < self._min_document_length:
            return None

        title = unicodedata.normalize("NFC", document.title).strip() if document.title else None
        return CleanDocument(
            source_url=document.source_url,
            title=title or None,
            text=cleaned_text,
            content_hash=sha256(cleaned_text.encode("utf-8")).hexdigest(),
            retrieved_at=document.retrieved_at,
        )
