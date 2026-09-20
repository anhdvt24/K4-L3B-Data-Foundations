from __future__ import annotations

import math
import re


class FixedSizeChunker:
    """
    Split text into fixed-size chunks with optional overlap.

    Rules:
        - Each chunk is at most chunk_size characters long.
        - Consecutive chunks share overlap characters.
        - The last chunk contains whatever remains.
        - If text is shorter than chunk_size, return [text].
    """

    def __init__(self, chunk_size: int = 500, overlap: int = 50) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[str]:
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [text]

        step = self.chunk_size - self.overlap
        chunks: list[str] = []
        for start in range(0, len(text), step):
            chunk = text[start : start + self.chunk_size]
            chunks.append(chunk)
            if start + self.chunk_size >= len(text):
                break
        return chunks


class SentenceChunker:
    """
    Split text into chunks of at most max_sentences_per_chunk sentences.

    Sentence detection: split on ". ", "! ", "? " or ".\n".
    Strip extra whitespace from each chunk.
    """

    _SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

    def __init__(self, max_sentences_per_chunk: int = 3) -> None:
        self.max_sentences_per_chunk = max(1, max_sentences_per_chunk)

    def chunk(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []
        sentences = [s.strip() for s in self._SENTENCE_SPLIT.split(text.strip()) if s.strip()]
        if not sentences:
            return []
        chunks: list[str] = []
        for i in range(0, len(sentences), self.max_sentences_per_chunk):
            piece = " ".join(sentences[i : i + self.max_sentences_per_chunk]).strip()
            if piece:
                chunks.append(piece)
        return chunks


class RecursiveChunker:
    """
    Recursively split text using separators in priority order.

    Default separator priority:
        ["\n\n", "\n", ". ", " ", ""]
    """

    DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

    def __init__(self, separators: list[str] | None = None, chunk_size: int = 500) -> None:
        self.separators = self.DEFAULT_SEPARATORS if separators is None else list(separators)
        self.chunk_size = chunk_size

    def chunk(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []
        return [chunk.strip() for chunk in self._split(text, list(self.separators)) if chunk.strip()]

    def _split(self, current_text: str, remaining_separators: list[str]) -> list[str]:
        # Base case: text already small enough.
        if len(current_text) <= self.chunk_size:
            return [current_text]

        # If no separators left, hard-split on chunk_size.
        if not remaining_separators:
            return [
                current_text[i : i + self.chunk_size]
                for i in range(0, len(current_text), self.chunk_size)
            ]

        sep = remaining_separators[0]
        rest = remaining_separators[1:]

        # Empty separator or not present in text → recurse without it.
        if sep == "" or sep not in current_text:
            return self._split(current_text, rest)

        # Split keeping the trailing separator on each piece (except last) so the
        # text can be reassembled losslessly.
        pieces = current_text.split(sep)
        rejoined: list[str] = []
        for idx, piece in enumerate(pieces):
            if idx < len(pieces) - 1:
                rejoined.append(piece + sep)
            elif piece:
                rejoined.append(piece)

        # Pack pieces into chunks ≤ chunk_size; recurse on oversized ones.
        chunks: list[str] = []
        buffer = ""
        for piece in rejoined:
            if len(piece) > self.chunk_size:
                if buffer:
                    chunks.append(buffer)
                    buffer = ""
                chunks.extend(self._split(piece, rest))
                continue
            tentative = (buffer + piece) if buffer else piece
            if len(tentative) <= self.chunk_size:
                buffer = tentative
            else:
                if buffer:
                    chunks.append(buffer)
                buffer = piece
        if buffer:
            chunks.append(buffer)
        return chunks


class HeadingChunker:
    """
    Split a Markdown document into chunks aligned with its headings.

    Each chunk = the heading line + all content until the next heading of
    equal or higher level (smaller or equal level number).

    Heading patterns supported (in priority order):
      - ATX Markdown headings: "### Heading"
      - Numbered sections: "1. Heading", "1.2. Heading", "1.2.3. Heading"
      - Letter-prefixed sections: "A. Heading", "B. Heading"

    Rules:
      - The heading line is always the first line of its chunk.
      - Chunks never split inside a Markdown table (a row starting with "|").
      - If a single chunk exceeds max_chunk_chars, it is sub-split on
        blank lines ("\n\n") — sub-split chunks keep the heading as prefix.
      - Empty text returns [].
      - Text with no heading returns [text] (single chunk).
    """

    HEADING_RE = re.compile(
        r"^(?P<hash>#{1,6})\s+(?P<title_hash>.+?)\s*#*\s*$"
        r"|^(?P<num>\d+(?:\.\d+)*\.)\s+(?P<title_num>\S.*?)\s*$"
        r"|^(?P<letter>[A-Z]\.)\s+(?P<title_letter>\S.*?)\s*$"
    )

    def __init__(self, max_level: int = 3, max_chunk_chars: int = 2000) -> None:
        self.max_level = max_level
        self.max_chunk_chars = max_chunk_chars

    def chunk(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []

        lines = text.split("\n")
        # Find all heading positions; each "block" runs from one heading
        # (inclusive) to the line before the next heading.
        blocks: list[tuple[str, list[str]]] = []
        current_heading: str | None = None
        current_lines: list[str] = []

        def flush() -> None:
            if current_heading is not None or current_lines:
                blocks.append((current_heading or "", list(current_lines)))

        for line in lines:
            stripped = line.strip()
            is_heading = bool(self.HEADING_RE.match(stripped)) if stripped else False
            if is_heading and self._is_within_max_level(stripped):
                flush()
                current_heading = stripped
                current_lines = [line]
            else:
                if current_heading is None and not stripped:
                    # Skip leading blank lines before any heading
                    continue
                current_lines.append(line)
        flush()

        if not blocks:
            return [text.strip()] if text.strip() else []

        # Build chunks from blocks; sub-split oversized blocks on blank lines.
        chunks: list[str] = []
        for heading, body in blocks:
            content = "\n".join(body).strip("\n")
            if not content:
                continue
            if heading:
                chunk_text = heading + "\n\n" + content
            else:
                chunk_text = content
            if len(chunk_text) <= self.max_chunk_chars:
                chunks.append(chunk_text)
                continue
            chunks.extend(self._sub_split(chunk_text, heading))
        return chunks

    def _is_within_max_level(self, line: str) -> bool:
        """Return True if a detected heading is within the configured max_level."""
        match = self.HEADING_RE.match(line.strip())
        if not match:
            return False
        if match.group("hash"):
            return len(match.group("hash")) <= self.max_level
        if match.group("num"):
            depth = match.group("num").count(".")
            return depth <= self.max_level
        if match.group("letter"):
            # Letter headings are treated as level 1 by default.
            return 1 <= self.max_level
        return False

    def _sub_split(self, chunk_text: str, heading: str | None) -> list[str]:
        """Split an oversized chunk on blank lines, preserving the heading."""
        paragraphs = chunk_text.split("\n\n")
        prefix = (heading + "\n\n") if heading else ""
        prefix_len = len(prefix)
        budget = max(self.max_chunk_chars - prefix_len, 200)

        result: list[str] = []
        buffer: list[str] = []

        def emit() -> None:
            if buffer:
                body = "\n\n".join(buffer).strip()
                if body:
                    result.append(prefix + body)

        for paragraph in paragraphs:
            tentative = ("\n\n".join(buffer + [paragraph])) if buffer else paragraph
            if len(tentative) <= budget:
                buffer.append(paragraph)
            else:
                emit()
                buffer = [paragraph]
        emit()
        return result


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def compute_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.

    cosine_similarity = dot(a, b) / (||a|| * ||b||)

    Returns 0.0 if either vector has zero magnitude.
    """
    dot = sum(x * y for x, y in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(x * x for x in vec_a))
    norm_b = math.sqrt(sum(y * y for y in vec_b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


class ChunkingStrategyComparator:
    """Run all built-in chunking strategies and compare their results."""

    def compare(self, text: str, chunk_size: int = 200) -> dict:
        if not text or not text.strip():
            return {
                "fixed_size": {"count": 0, "avg_length": 0, "chunks": []},
                "by_sentences": {"count": 0, "avg_length": 0, "chunks": []},
                "recursive": {"count": 0, "avg_length": 0, "chunks": []},
            }

        def _stats(chunks: list[str]) -> dict:
            cleaned = [chunk for chunk in chunks if chunk]
            count = len(cleaned)
            avg = sum(len(chunk) for chunk in cleaned) / count if count else 0
            return {"count": count, "avg_length": avg, "chunks": cleaned}

        fixed_chunker = FixedSizeChunker(chunk_size=chunk_size, overlap=50)
        sentence_chunker = SentenceChunker(max_sentences_per_chunk=3)
        recursive_chunker = RecursiveChunker(chunk_size=chunk_size)

        return {
            "fixed_size": _stats(fixed_chunker.chunk(text)),
            "by_sentences": _stats(sentence_chunker.chunk(text)),
            "recursive": _stats(recursive_chunker.chunk(text)),
        }
