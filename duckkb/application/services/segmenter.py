from __future__ import annotations

from typing import Iterable


def tokenize(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    if any(ch.isspace() for ch in stripped):
        return [tok for tok in stripped.split() if tok]
    return [ch for ch in stripped if ch.strip()]


def chunk_text(text: str, max_len: int) -> Iterable[str]:
    if max_len <= 0:
        raise ValueError("max_len must be positive")
    stripped = text.strip()
    if not stripped:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(stripped):
        end = min(len(stripped), start + max_len)
        chunks.append(stripped[start:end])
        start = end
    return chunks
