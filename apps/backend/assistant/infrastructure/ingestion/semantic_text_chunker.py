import re
from dataclasses import dataclass

from assistant.application.ports.text_chunker import TextChunker
from assistant.domain.clean_document import CleanDocument
from assistant.domain.knowledge_chunk import KnowledgeChunk
from assistant.domain.split_sentences import split_sentences

_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")


@dataclass(frozen=True, slots=True)
class _Unit:
    text: str
    heading_path: tuple[str, ...]
    starts_section: bool = False


class SemanticTextChunker(TextChunker):
    """Character-based chunker that prefers sections, paragraphs, and sentences."""

    def __init__(self, *, chunk_size: int, overlap: int, min_chunk_size: int) -> None:
        if chunk_size <= 0:
            raise ValueError("Chunk size must be greater than zero.")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("Chunk overlap must be non-negative and smaller than chunk size.")
        if min_chunk_size <= 0 or min_chunk_size > chunk_size:
            raise ValueError("Minimum chunk size must be positive and no larger than chunk size.")
        self._chunk_size = chunk_size
        self._overlap = overlap
        self._min_chunk_size = min_chunk_size

    def chunk(self, document: CleanDocument) -> list[KnowledgeChunk]:
        units = self._units(document.text)
        base_chunks = self._pack(units)
        base_chunks = self._normalise_minimum_size(base_chunks)
        overlapped = self._apply_overlap(base_chunks)
        return [
            KnowledgeChunk.create(
                document=document,
                sequence=sequence,
                text=unit.text,
                heading_path=unit.heading_path,
            )
            for sequence, unit in enumerate(overlapped)
            if unit.text.strip()
        ]

    def _units(self, text: str) -> list[_Unit]:
        heading_stack: list[str] = []
        units: list[_Unit] = []
        for block in (value.strip() for value in re.split(r"\n{2,}", text)):
            if not block:
                continue
            heading = _HEADING.fullmatch(block)
            if heading:
                level = len(heading.group(1))
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(heading.group(2).strip())
                units.append(_Unit(block, tuple(heading_stack), starts_section=True))
                continue
            path = tuple(heading_stack)
            pieces = self._split_oversized(block)
            units.extend(_Unit(piece, path) for piece in pieces if piece)
        return units

    def _pack(self, units: list[_Unit]) -> list[_Unit]:
        chunks: list[_Unit] = []
        current_text = ""
        current_path: tuple[str, ...] = ()
        for unit in units:
            if unit.starts_section and current_text:
                chunks.append(_Unit(current_text, current_path))
                current_text = ""
            separator = "\n\n" if current_text else ""
            if (
                current_text
                and len(current_text) + len(separator) + len(unit.text) > self._chunk_size
            ):
                chunks.append(_Unit(current_text, current_path))
                current_text = ""
                separator = ""
            if not current_text:
                current_path = unit.heading_path
            current_text = f"{current_text}{separator}{unit.text}"
        if current_text:
            chunks.append(_Unit(current_text, current_path))
        return chunks

    def _split_oversized(self, text: str) -> list[str]:
        if len(text) <= self._chunk_size:
            return [text]
        sentences = [sentence.text for sentence in split_sentences(text)]
        if len(sentences) > 1:
            pieces = self._pack_fragments(sentences, separator=" ")
            if all(len(piece) <= self._chunk_size for piece in pieces):
                return pieces
        words = text.split()
        if len(words) > 1:
            return self._pack_fragments(words, separator=" ")
        return self._hard_split(text)

    def _pack_fragments(self, fragments: list[str], *, separator: str) -> list[str]:
        pieces: list[str] = []
        current = ""
        for fragment in fragments:
            if len(fragment) > self._chunk_size:
                if current:
                    pieces.append(current)
                    current = ""
                pieces.extend(self._hard_split(fragment))
                continue
            candidate = f"{current}{separator if current else ''}{fragment}"
            if len(candidate) <= self._chunk_size:
                current = candidate
            else:
                if current:
                    pieces.append(current)
                current = fragment
        if current:
            pieces.append(current)
        return pieces

    def _hard_split(self, text: str) -> list[str]:
        chunk_count = (len(text) + self._chunk_size - 1) // self._chunk_size
        remainder = len(text) % self._chunk_size
        if (
            chunk_count > 1
            and remainder
            and remainder < self._min_chunk_size
            and len(text) >= chunk_count * self._min_chunk_size
        ):
            base_size, larger_chunks = divmod(len(text), chunk_count)
            sizes = [base_size + (index < larger_chunks) for index in range(chunk_count)]
            pieces: list[str] = []
            start = 0
            for size in sizes:
                pieces.append(text[start : start + size])
                start += size
            return pieces
        return [
            text[index : index + self._chunk_size]
            for index in range(0, len(text), self._chunk_size)
        ]

    def _normalise_minimum_size(self, chunks: list[_Unit]) -> list[_Unit]:
        """Best-effort minimum-size normalisation across the full ordered sequence."""
        normalised = list(chunks)
        index = 0
        while index < len(normalised):
            current = normalised[index]
            if len(current.text) >= self._min_chunk_size or len(normalised) == 1:
                index += 1
                continue

            if (
                index > 0
                and self._combined_length(normalised[index - 1], current) <= self._chunk_size
            ):
                normalised[index - 1] = self._merge(normalised[index - 1], current)
                del normalised[index]
                index = max(0, index - 1)
                continue

            if (
                index + 1 < len(normalised)
                and self._combined_length(current, normalised[index + 1]) <= self._chunk_size
            ):
                normalised[index] = self._merge(current, normalised[index + 1])
                del normalised[index + 1]
                continue

            if index > 0:
                redistributed = self._redistribute_from_previous(normalised[index - 1], current)
                if redistributed is not None:
                    normalised[index - 1], normalised[index] = redistributed
                    index += 1
                    continue

            if index + 1 < len(normalised):
                redistributed = self._redistribute_from_following(current, normalised[index + 1])
                if redistributed is not None:
                    normalised[index], normalised[index + 1] = redistributed
                    index += 1
                    continue

            index += 1
        return normalised

    @staticmethod
    def _combined_length(left: _Unit, right: _Unit) -> int:
        return len(left.text) + 2 + len(right.text)

    @staticmethod
    def _merge(left: _Unit, right: _Unit) -> _Unit:
        # The earliest heading path deterministically describes merged ordered content.
        return _Unit(f"{left.text}\n\n{right.text}", left.heading_path)

    def _redistribute_from_previous(
        self, previous: _Unit, current: _Unit
    ) -> tuple[_Unit, _Unit] | None:
        needed = self._min_chunk_size - len(current.text)
        maximum = min(
            len(previous.text) - self._min_chunk_size,
            self._chunk_size - len(current.text) - 2,
        )
        split = self._split_suffix(previous.text, needed, maximum)
        if split is None:
            return None
        shortened, moved = split
        extended = f"{moved}\n\n{current.text}"
        if len(shortened) < self._min_chunk_size or len(extended) > self._chunk_size:
            return None
        return _Unit(shortened, previous.heading_path), _Unit(extended, current.heading_path)

    def _redistribute_from_following(
        self, current: _Unit, following: _Unit
    ) -> tuple[_Unit, _Unit] | None:
        needed = self._min_chunk_size - len(current.text)
        maximum = min(
            len(following.text) - self._min_chunk_size,
            self._chunk_size - len(current.text) - 2,
        )
        split = self._split_prefix(following.text, needed, maximum)
        if split is None:
            return None
        moved, shortened = split
        extended = f"{current.text}\n\n{moved}"
        if len(shortened) < self._min_chunk_size or len(extended) > self._chunk_size:
            return None
        return _Unit(extended, current.heading_path), _Unit(shortened, following.heading_path)

    @staticmethod
    def _split_suffix(text: str, minimum: int, maximum: int) -> tuple[str, str] | None:
        if minimum <= 0 or maximum < minimum:
            return None
        lower = len(text) - maximum
        upper = len(text) - minimum
        for boundary in range(upper, lower - 1, -1):
            if boundary > 0 and (text[boundary - 1].isspace() or text[boundary].isspace()):
                left, right = text[:boundary].rstrip(), text[boundary:].lstrip()
                if minimum <= len(right) <= maximum and left:
                    return left, right
        return None

    @staticmethod
    def _split_prefix(text: str, minimum: int, maximum: int) -> tuple[str, str] | None:
        if minimum <= 0 or maximum < minimum:
            return None
        for boundary in range(minimum, maximum + 1):
            if boundary < len(text) and (text[boundary - 1].isspace() or text[boundary].isspace()):
                left, right = text[:boundary].rstrip(), text[boundary:].lstrip()
                if minimum <= len(left) <= maximum and right:
                    return left, right
        return None

    def _apply_overlap(self, chunks: list[_Unit]) -> list[_Unit]:
        if self._overlap == 0 or len(chunks) < 2:
            return chunks
        result = [chunks[0]]
        for previous, current in zip(chunks, chunks[1:], strict=False):
            available = self._chunk_size - len(current.text) - 2
            budget = min(self._overlap, available, len(previous.text) - 1)
            if budget <= 0:
                result.append(current)
                continue
            context = self._context_suffix(previous.text, budget)
            text = f"{context}\n\n{current.text}" if context else current.text
            result.append(_Unit(text, current.heading_path))
        return result

    @staticmethod
    def _context_suffix(text: str, budget: int) -> str:
        candidate = text[-budget:].strip()
        if len(text) > budget and " " in candidate:
            candidate = candidate.split(" ", 1)[1].strip()
        return candidate
