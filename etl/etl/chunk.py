"""Heading-aware Markdown chunking for the knowledge base. DATA_PIPELINE.md
§Chunking: split on headings first, cap ~1,200 tokens per chunk, ~100-token
overlap when a section has to split further, tables kept whole, no chunk
crosses a document boundary (chunk_markdown is always called on one document's
text).

No token count is available without a tokenizer dependency, so this uses the
common ~4-chars-per-English-token approximation — good enough for a soft
chunking budget, not for exact billing.
"""

import re
from dataclasses import dataclass

TOKEN_CAP = 1200
OVERLAP_TOKENS = 100
_CHARS_PER_TOKEN = 4

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class Chunk:
    heading_path: str | None
    content: str
    token_estimate: int


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _split_by_heading(markdown: str) -> list[tuple[str | None, str]]:
    """One (heading_path, section_text) pair per heading, plus a leading pair
    with heading_path=None for any text before the first heading. A heading's
    own line stays in its section's content; heading_path is the breadcrumb of
    enclosing headings, deepest last.
    """
    stack: list[tuple[int, str]] = []
    sections: list[tuple[str | None, list[str]]] = [(None, [])]

    for line in markdown.splitlines():
        m = _HEADING_RE.match(line)
        if m is None:
            sections[-1][1].append(line)
            continue
        level = len(m.group(1))
        title = m.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        sections.append((" > ".join(t for _, t in stack), [line]))

    result: list[tuple[str | None, str]] = []
    for heading_path, lines in sections:
        text = "\n".join(lines).strip()
        if text:
            result.append((heading_path, text))
    return result


def _paragraphs(text: str) -> list[str]:
    """Blank-line-separated blocks. A Markdown table has no blank line between
    its rows, so it already survives this split as one block — no separate
    table-detection pass needed to keep it whole.
    """
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def _pack_paragraphs(paragraphs: list[str], heading_path: str | None) -> list[Chunk]:
    chunks: list[Chunk] = []
    current: list[str] = []
    current_tokens = 0

    def flush(overlap_from: str | None) -> None:
        nonlocal current, current_tokens
        text = "\n\n".join(current).strip()
        if text:
            chunks.append(Chunk(heading_path, text, _estimate_tokens(text)))
        current = [overlap_from] if overlap_from else []
        current_tokens = _estimate_tokens(overlap_from) if overlap_from else 0

    for para in paragraphs:
        para_tokens = _estimate_tokens(para)
        if current and current_tokens + para_tokens > TOKEN_CAP:
            tail = current[-1]
            overlap_chars = OVERLAP_TOKENS * _CHARS_PER_TOKEN
            flush(tail if _estimate_tokens(tail) <= OVERLAP_TOKENS else tail[-overlap_chars:])
        current.append(para)
        current_tokens += para_tokens
    flush(None)
    return chunks


def chunk_markdown(markdown: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for heading_path, text in _split_by_heading(markdown):
        if _estimate_tokens(text) <= TOKEN_CAP:
            chunks.append(Chunk(heading_path, text, _estimate_tokens(text)))
        else:
            chunks.extend(_pack_paragraphs(_paragraphs(text), heading_path))
    return chunks
