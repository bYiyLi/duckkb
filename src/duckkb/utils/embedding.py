import asyncio
import hashlib
from datetime import datetime

from openai import AsyncOpenAI

from duckkb.config import settings
from duckkb.constants import SYS_CACHE_TABLE
from duckkb.db import get_db
from duckkb.logger import logger

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
    return _client


def _get_cached_embeddings_batch(hashes: list[str]) -> dict[str, list[float]]:
    """Batch check if embeddings exist in cache."""
    if not hashes:
        return {}
    try:
        with get_db(read_only=True) as conn:
            # DuckDB supports list parameter for IN clause
            query = f"SELECT content_hash, embedding FROM {SYS_CACHE_TABLE} WHERE content_hash IN ({','.join(['?'] * len(hashes))})"
            results = conn.execute(query, hashes).fetchall()
            return {r[0]: r[1] for r in results}
    except Exception as e:
        logger.warning(f"Batch cache lookup failed: {e}")
        return {}


def _cache_embeddings_batch(hashes: list[str], embeddings: list[list[float]]):
    """Batch store embeddings in cache."""
    if not hashes:
        return
    try:
        data = []
        now = datetime.now()
        for h, emb in zip(hashes, embeddings):
            data.append((h, emb, now))

        with get_db(read_only=False) as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {SYS_CACHE_TABLE} (content_hash, embedding, last_used) VALUES (?, ?, ?)",
                data,
            )
    except Exception as e:
        logger.error(f"Failed to batch cache embeddings: {e}")


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Get embeddings for a list of texts using OpenAI with caching."""
    if not texts:
        return []

    # Filter out empty strings to match index logic (though indexer usually filters before calling)
    # But to keep indices aligned, we assume input texts are all valid.

    # 1. Calculate hashes
    hashes = [hashlib.md5(t.encode("utf-8")).hexdigest() for t in texts]

    # 2. Check cache
    cached_map = await asyncio.to_thread(_get_cached_embeddings_batch, hashes)

    results: list[list[float] | None] = [None] * len(texts)
    missing_indices = []
    missing_texts = []

    for i, h in enumerate(hashes):
        if h in cached_map:
            results[i] = cached_map[h]
        else:
            missing_indices.append(i)
            missing_texts.append(texts[i])

    if missing_texts:
        logger.debug(f"Embedding cache miss: {len(missing_texts)}/{len(texts)}")
        client = get_openai_client()
        try:
            # OpenAI API call
            response = await client.embeddings.create(
                input=missing_texts, model=settings.EMBEDDING_MODEL
            )
            new_embeddings = [d.embedding for d in response.data]

            # 3. Store in cache
            # Use hashes of missing texts
            missing_hashes = [hashes[i] for i in missing_indices]
            await asyncio.to_thread(_cache_embeddings_batch, missing_hashes, new_embeddings)

            # Fill results
            for idx, embedding in zip(missing_indices, new_embeddings):
                results[idx] = embedding

        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise e

    # Ensure all results are filled (should be unless exception raised)
    return [r for r in results if r is not None]


async def get_embedding(text: str) -> list[float]:
    """Wrapper for single text (backward compatibility)."""
    res = await get_embeddings([text])
    return res[0] if res else []
