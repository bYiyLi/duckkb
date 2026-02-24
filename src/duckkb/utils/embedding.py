"""
向量嵌入工具模块。

提供文本向量嵌入的获取与缓存功能，支持批量查询和自动缓存。
通过缓存机制避免重复调用 OpenAI API，降低成本并提升性能。
"""

import asyncio
from datetime import UTC, datetime

from duckkb.config import get_kb_config, get_openai_client
from duckkb.constants import SYS_CACHE_TABLE
from duckkb.database.connection import get_db
from duckkb.logger import logger
from duckkb.utils.text import compute_text_hash


def _get_cached_embeddings_batch(hashes: list[str]) -> dict[str, list[float]]:
    """
    批量查询缓存中的向量嵌入。

    Args:
        hashes: 内容哈希值列表，用于作为缓存键。

    Returns:
        字典，键为哈希值，值为对应的向量嵌入列表。
        如果查询失败或无缓存，返回空字典。
    """
    if not hashes:
        return {}
    try:
        with get_db(read_only=True) as conn:
            query = f"SELECT content_hash, embedding FROM {SYS_CACHE_TABLE} WHERE content_hash IN ({','.join(['?'] * len(hashes))})"
            results = conn.execute(query, hashes).fetchall()
            return {r[0]: r[1] for r in results}
    except Exception as e:
        logger.warning(f"Batch cache lookup failed: {e}")
        return {}


def _cache_embeddings_batch(hashes: list[str], embeddings: list[list[float]]) -> None:
    """
    批量存储向量嵌入到缓存。

    Args:
        hashes: 内容哈希值列表，作为缓存键。
        embeddings: 对应的向量嵌入列表，与 hashes 一一对应。

    Note:
        使用 INSERT OR REPLACE 策略，已存在的缓存会被更新。
        同时更新 last_used 时间戳，用于后续的缓存清理策略。
    """
    if not hashes:
        return
    try:
        data = []
        now = datetime.now(UTC)
        for h, emb in zip(hashes, embeddings, strict=True):
            data.append((h, emb, now))

        with get_db(read_only=False) as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {SYS_CACHE_TABLE} (content_hash, embedding, last_used) VALUES (?, ?, ?)",
                data,
            )
    except Exception as e:
        logger.error(f"Failed to batch cache embeddings: {e}")


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """
    获取文本列表的向量嵌入，支持缓存和批量处理。

    首先查询本地缓存，对未命中的文本调用 OpenAI API 获取嵌入，
    然后将新获取的嵌入存入缓存以供后续复用。

    Args:
        texts: 待获取嵌入的文本列表。

    Returns:
        向量嵌入列表，每个元素是与输入文本对应的嵌入向量。
        返回列表长度与输入一致，失败的项为空列表。

    Raises:
        Exception: 调用 OpenAI API 失败时抛出异常。

    Note:
        - 使用文本哈希作为缓存键，相同文本不会重复调用 API
        - 批量处理优化：一次性查询所有缓存，一次性请求所有缺失的嵌入
        - 使用 asyncio.to_thread 将同步的数据库操作转为异步
    """
    if not texts:
        return []

    hashes = [compute_text_hash(t) for t in texts]

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
        kb_config = get_kb_config()
        try:
            response = await client.embeddings.create(
                input=missing_texts, model=kb_config.EMBEDDING_MODEL
            )
            new_embeddings = [d.embedding for d in response.data]

            missing_hashes = [hashes[i] for i in missing_indices]
            await asyncio.to_thread(_cache_embeddings_batch, missing_hashes, new_embeddings)

            for idx, embedding in zip(missing_indices, new_embeddings, strict=True):
                results[idx] = embedding

        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise

    return [r if r is not None else [] for r in results]


async def get_embedding(text: str) -> list[float]:
    """
    获取单个文本的向量嵌入。

    这是 get_embeddings 的便捷封装，用于向后兼容单文本调用场景。

    Args:
        text: 待获取嵌入的文本。

    Returns:
        文本的向量嵌入列表。如果输入为空或处理失败，返回空列表。
    """
    res = await get_embeddings([text])
    return res[0] if res else []
