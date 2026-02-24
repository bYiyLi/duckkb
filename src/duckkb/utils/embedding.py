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


def _get_cached_embedding(content_hash: str) -> list[float] | None:
    """Check if embedding exists in cache."""
    try:
        with get_db(read_only=True) as conn:
            # Check if table exists first to avoid error during init
            # Actually schema init should have run.
            result = conn.execute(
                f"SELECT embedding FROM {SYS_CACHE_TABLE} WHERE content_hash = ?", [content_hash]
            ).fetchone()
            if result:
                return result[0]
    except Exception as e:
        logger.warning(f"Cache lookup failed: {e}")
    return None


def _cache_embedding(content_hash: str, embedding: list[float]):
    """Store embedding in cache."""
    try:
        with get_db(read_only=False) as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO {SYS_CACHE_TABLE} (content_hash, embedding, last_used) VALUES (?, ?, ?)",
                [content_hash, embedding, datetime.now()],
            )
    except Exception as e:
        logger.error(f"Failed to cache embedding: {e}")


async def get_embedding(text: str) -> list[float]:
    """Get embedding for a text string using OpenAI with caching."""
    if not text or not text.strip():
        return []

    # Calculate hash
    content_hash = hashlib.md5(text.encode("utf-8")).hexdigest()

    # 1. Check cache
    cached = await asyncio.to_thread(_get_cached_embedding, content_hash)
    if cached:
        logger.debug(f"Embedding cache hit: {content_hash[:8]}")
        return cached

    # 2. Call API
    logger.debug(f"Embedding cache miss: {content_hash[:8]}")
    client = get_openai_client()
    try:
        response = await client.embeddings.create(input=text, model=settings.EMBEDDING_MODEL)
        embedding = response.data[0].embedding

        # 3. Store in cache
        await asyncio.to_thread(_cache_embedding, content_hash, embedding)
        return embedding
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        # In case of error, we might want to return empty list or raise
        # Raising is better so the caller knows it failed.
        raise
