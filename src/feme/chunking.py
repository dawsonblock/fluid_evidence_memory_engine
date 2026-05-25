from __future__ import annotations

from dataclasses import dataclass

from .token_trace import Tokenizer


@dataclass(frozen=True)
class ChunkSpec:
    chunk_index: int
    char_start: int
    char_end: int
    token_start: int
    token_end: int
    text: str
    token_count: int


def chunk_text(
    text: str, tokenizer: Tokenizer, max_tokens: int = 900, overlap_tokens: int = 120
) -> list[ChunkSpec]:
    tokens = tokenizer.tokenize(text)
    if not tokens:
        return []
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")

    chunks: list[ChunkSpec] = []
    start = 0
    idx = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        char_start, char_end = tokenizer.slice_by_token_range(tokens, start, end)
        chunk = text[char_start:char_end]
        chunks.append(
            ChunkSpec(idx, char_start, char_end, start, end, chunk, end - start)
        )
        if end >= len(tokens):
            break
        start = max(0, end - overlap_tokens)
        idx += 1
    return chunks
