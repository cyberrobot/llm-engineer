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
        base_chunks = self._rebalance_small_tail(base_chunks)
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

    def _rebalance_small_tail(self, chunks: list[_Unit]) -> list[_Unit]:
        if len(chunks) < 2 or len(chunks[-1].text) >= self._min_chunk_size:
            return chunks
        previous, tail = chunks[-2:]
        separator = "\n\n"
        if len(previous.text) + len(separator) + len(tail.text) <= self._chunk_size:
            return [
                *chunks[:-2],
                _Unit(previous.text + separator + tail.text, previous.heading_path),
            ]
        needed = self._min_chunk_size - len(tail.text)
        if len(previous.text) - needed < self._min_chunk_size:
            return chunks
        boundary = len(previous.text) - needed
        moved = previous.text[boundary:]
        shortened = previous.text[:boundary].rstrip()
        extended = f"{moved.lstrip()} {tail.text}".strip()
        if shortened and len(extended) <= self._chunk_size:
            return [
                *chunks[:-2],
                _Unit(shortened, previous.heading_path),
                _Unit(extended, tail.heading_path),
            ]
        return chunks

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
