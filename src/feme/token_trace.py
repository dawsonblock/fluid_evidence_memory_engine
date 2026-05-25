from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    text: str
    char_start: int
    char_end: int
    token_index: int


class Tokenizer:
    """Tokenizer wrapper.

    The fallback tokenizer is intentionally simple and stable. It stores character
    offsets and approximate token offsets. If tiktoken is installed and selected,
    use it only for counts; exact offset mapping remains character-based because
    char offsets are more stable across model tokenizer changes.
    """

    def __init__(self, name: str = "fallback"):
        self.name = name

    def tokenize(self, text: str) -> list[Token]:
        if self.name == "fallback":
            return self._fallback_tokenize(text)
        # The fallback remains the canonical offset tokenizer.
        return self._fallback_tokenize(text)

    def _fallback_tokenize(self, text: str) -> list[Token]:
        pattern = re.compile(r"\w+|[^\w\s]", re.UNICODE)
        out: list[Token] = []
        for idx, match in enumerate(pattern.finditer(text)):
            out.append(Token(match.group(0), match.start(), match.end(), idx))
        return out

    def count(self, text: str) -> int:
        return len(self.tokenize(text))

    def slice_by_token_range(
        self, tokens: list[Token], start: int, end: int
    ) -> tuple[int, int]:
        selected = tokens[start:end]
        if not selected:
            return 0, 0
        return selected[0].char_start, selected[-1].char_end
