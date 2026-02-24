from __future__ import annotations

from duckkb.domain.ports.embedding import EmbeddingProvider


class NoneEmbeddingProvider(EmbeddingProvider):
    def embed(self, text: str) -> list[float] | None:
        return None
