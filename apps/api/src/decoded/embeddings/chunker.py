from __future__ import annotations

from dataclasses import dataclass

import tiktoken

# text-embedding-3-small max input: 8191 tokens. We stay well below.
TARGET_TOKENS = 500
OVERLAP_TOKENS = 50
MAX_TOKENS = 700  # hard cap per chunk

_encoder = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    text: str
    order: int
    section: str | None  # best-guess section title (e.g. "Introduction")


def _token_count(text: str) -> int:
    return len(_encoder.encode(text))


def _split_by_sections(markdown: str) -> list[tuple[str | None, str]]:
    """Split markdown by ## headers. Returns [(section_title, body), ...]."""
    lines = markdown.split("\n")
    sections: list[tuple[str | None, list[str]]] = [(None, [])]

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("###"):
            title = stripped.removeprefix("## ").strip()
            sections.append((title, []))
        else:
            sections[-1][1].append(line)

    return [(title, "\n".join(body).strip()) for title, body in sections if "\n".join(body).strip()]


def chunk_markdown(markdown: str) -> list[Chunk]:
    """
    Split markdown into token-sized chunks, respecting section boundaries when possible.
    """
    chunks: list[Chunk] = []
    order = 0

    for section_title, body in _split_by_sections(markdown):
        if not body:
            continue

        tokens = _encoder.encode(body)

        if len(tokens) <= MAX_TOKENS:
            chunks.append(Chunk(text=body, order=order, section=section_title))
            order += 1
            continue

        # Section too big — sliding window
        start = 0
        while start < len(tokens):
            end = min(start + TARGET_TOKENS, len(tokens))
            piece = _encoder.decode(tokens[start:end])
            chunks.append(Chunk(text=piece, order=order, section=section_title))
            order += 1

            if end == len(tokens):
                break
            start = end - OVERLAP_TOKENS

    return chunks