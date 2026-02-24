from __future__ import annotations

from collections import Counter


def bm25_score(tokens: list[str], text_tokens: list[str]) -> float:
    if not tokens or not text_tokens:
        return 0.0
    tf = Counter(text_tokens)
    score = 0.0
    for token in tokens:
        score += tf.get(token, 0)
    return float(score)


def fuse_score(bm25: float, vector: float, weight: float) -> float:
    return (bm25 * 0.4 + vector * 0.6) * weight
