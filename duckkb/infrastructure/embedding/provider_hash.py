from __future__ import annotations

import hashlib

from duckkb.domain.ports.embedding import EmbeddingProvider


class HashEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dim: int = 16) -> None:
        self._dim = dim

    def embed(self, text: str) -> list[float] | None:
        data = hashlib.sha256(text.encode("utf-8")).digest()
        values = [byte / 255.0 for byte in data]
        if self._dim <= 0:
            return []
        if self._dim <= len(values):
            return values[: self._dim]
        padded = values[:]
        while len(padded) < self._dim:
            padded.extend(values)
        return padded[: self._dim]
