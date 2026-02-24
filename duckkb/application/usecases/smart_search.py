from __future__ import annotations

import math

from duckkb.application.services.ranker import bm25_score, fuse_score
from duckkb.application.services.segmenter import tokenize
from duckkb.domain.models import SearchHit
from duckkb.domain.ports.embedding import EmbeddingProvider
from duckkb.domain.ports.repository import CacheRepo, SearchIndexRepo


def smart_search(
    index_repo: SearchIndexRepo,
    cache_repo: CacheRepo,
    embedding_provider: EmbeddingProvider,
    query: str,
    limit: int = 10,
) -> list[SearchHit]:
    tokens = tokenize(query)
    query_vector = embedding_provider.embed(query)
    candidates = index_repo.search_by_tokens(tokens, limit=max(limit * 5, limit))
    hits: list[SearchHit] = []
    for chunk in candidates:
        text_tokens = tokenize(chunk.segmented_text)
        bm25 = bm25_score(tokens, text_tokens)
        vector_score = _vector_similarity(
            query_vector, cache_repo.get_embedding(chunk.content_hash)
        )
        score = fuse_score(bm25=bm25, vector=vector_score, weight=chunk.priority_weight)
        hits.append(
            SearchHit(
                ref_id=chunk.ref_id,
                source_table=chunk.source_table,
                source_field=chunk.source_field,
                segmented_text=chunk.segmented_text,
                metadata=chunk.metadata,
                priority_weight=chunk.priority_weight,
                score=score,
            )
        )
    hits.sort(key=lambda item: item.score, reverse=True)
    return hits[:limit]


def _vector_similarity(query: list[float] | None, doc: list[float] | None) -> float:
    if query is None or doc is None:
        return 0.0
    if len(query) != len(doc):
        return 0.0
    dot = 0.0
    norm_q = 0.0
    norm_d = 0.0
    for qv, dv in zip(query, doc):
        dot += qv * dv
        norm_q += qv * qv
        norm_d += dv * dv
    if norm_q <= 0.0 or norm_d <= 0.0:
        return 0.0
    return dot / math.sqrt(norm_q * norm_d)
