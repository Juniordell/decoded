from __future__ import annotations

import tiktoken

# Anthropic doesn't publish an official tokenizer; cl100k is close enough for budgeting.
_encoder = tiktoken.get_encoding("cl100k_base")

MAX_INPUT_TOKENS = 180_000  # leave 20k headroom on Sonnet's 200k context


def count_tokens(text: str) -> int:
    return len(_encoder.encode(text))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate a string to at most max_tokens tokens."""
    tokens = _encoder.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return _encoder.decode(tokens[:max_tokens]) + "\n\n[TRUNCATED — paper exceeded context window]"


def budget_for_full_text(title: str, abstract: str, system_prompt: str) -> int:
    """Compute how many tokens are available for the paper body."""
    overhead = count_tokens(title) + count_tokens(abstract) + count_tokens(system_prompt) + 500
    return max(1000, MAX_INPUT_TOKENS - overhead)