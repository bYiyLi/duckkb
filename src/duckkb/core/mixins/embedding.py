"""嵌入向量管理 Mixin。"""

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from duckkb.core.base import BaseEngine
from duckkb.logger import logger

if TYPE_CHECKING:
    from openai import AsyncOpenAI

SEARCH_CACHE_TABLE = "_sys_search_cache"


class EmbeddingMixin(BaseEngine):
    """嵌入向量管理 Mixin。

    提供文本向量嵌入的获取与缓存功能，支持批量查询和自动缓存。
    embedding_model 从 config.yaml 的 embedding.model 读取。

    Attributes:
        embedding_model: 嵌入模型名称。
        embedding_dim: 嵌入向量维度。
    """

    def __init__(self, *args, **kwargs) -> None:
        """初始化嵌入向量 Mixin。"""
        super().__init__(*args, **kwargs)
        self._openai_client: AsyncOpenAI | None = None

    @property
    def embedding_model(self) -> str:
        """嵌入模型名称，从 embedding 配置读取。"""
        return self.kb_config.embedding.model

    @property
    def embedding_dim(self) -> int:
        """嵌入向量维度。"""
        return self.config.embedding_dim

    @property
    def openai_client(self) -> "AsyncOpenAI":
        """OpenAI 客户端（懒加载）。"""
        if self._openai_client is None:
            from openai import AsyncOpenAI

            from duckkb.config import get_global_config

            config = get_global_config()
            self._openai_client = AsyncOpenAI(
                api_key=config.OPENAI_API_KEY,
                base_url=config.OPENAI_BASE_URL,
            )
        return self._openai_client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """获取文本列表的向量嵌入，支持缓存和批量处理。

        流程：
        1. 计算文本哈希
        2. 批量查询缓存
        3. 对缓存未命中的文本调用 OpenAI API
        4. 将新嵌入存入缓存

        Args:
            texts: 待获取嵌入的文本列表。

        Returns:
            向量嵌入列表，每个元素是与输入文本对应的嵌入向量。
        """
        if not texts:
            return []

        hashes = [self.compute_hash(t) for t in texts]

        cached_map = await asyncio.to_thread(self._get_cached_embeddings_batch, hashes)

        results: list[list[float] | None] = [None] * len(texts)
        missing_indices: list[int] = []
        missing_texts: list[str] = []

        for i, h in enumerate(hashes):
            if h in cached_map:
                results[i] = cached_map[h]
            else:
                missing_indices.append(i)
                missing_texts.append(texts[i])

        if missing_texts:
            logger.debug(f"Embedding cache miss: {len(missing_texts)}/{len(texts)}")
            new_embeddings = await self._call_embedding_api(missing_texts)

            missing_hashes = [hashes[i] for i in missing_indices]
            await asyncio.to_thread(self._cache_embeddings_batch, missing_hashes, new_embeddings)

            for idx, embedding in zip(missing_indices, new_embeddings, strict=True):
                results[idx] = embedding

        return [r if r is not None else [] for r in results]

    async def embed_single(self, text: str) -> list[float]:
        """获取单个文本的向量嵌入。

        Args:
            text: 待获取嵌入的文本。

        Returns:
            文本的向量嵌入列表。
        """
        res = await self.embed([text])
        return res[0] if res else []

    def compute_hash(self, text: str) -> str:
        """计算文本哈希。

        Args:
            text: 待计算哈希的文本。

        Returns:
            MD5 哈希字符串。
        """
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def _get_cached_embeddings_batch(self, hashes: list[str]) -> dict[str, list[float]]:
        """批量查询缓存中的向量嵌入。

        Args:
            hashes: 文本哈希列表。

        Returns:
            哈希到嵌入向量的映射。
        """
        if not hashes:
            return {}
        try:
            placeholders = ",".join("?" * len(hashes))
            rows = self.execute_read(
                f"SELECT content_hash, vector FROM {SEARCH_CACHE_TABLE} "
                f"WHERE content_hash IN ({placeholders})",
                hashes,
            )

            now = datetime.now(UTC)
            for h, _ in rows:
                self.execute_write(
                    f"UPDATE {SEARCH_CACHE_TABLE} SET last_used = ? WHERE content_hash = ?",
                    [now, h],
                )

            return {r[0]: r[1] for r in rows if r[1] is not None}
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")
            return {}

    def _cache_embeddings_batch(self, hashes: list[str], embeddings: list[list[float]]) -> None:
        """批量存储向量嵌入到缓存。

        Args:
            hashes: 文本哈希列表。
            embeddings: 嵌入向量列表。
        """
        if not hashes:
            return
        try:
            now = datetime.now(UTC)
            data = [(h, emb, now, now) for h, emb in zip(hashes, embeddings, strict=True)]
            with self.write_transaction() as conn:
                conn.executemany(
                    f"INSERT OR REPLACE INTO {SEARCH_CACHE_TABLE} "
                    "(content_hash, vector, last_used, created_at) VALUES (?, ?, ?, ?)",
                    data,
                )
        except Exception as e:
            logger.error(f"Failed to cache embeddings: {e}")

    async def _call_embedding_api(self, texts: list[str]) -> list[list[float]]:
        """调用 OpenAI Embedding API。

        Args:
            texts: 待嵌入的文本列表。

        Returns:
            嵌入向量列表。

        Raises:
            Exception: API 调用失败时抛出。
        """
        try:
            response = await self.openai_client.embeddings.create(
                input=texts, model=self.embedding_model
            )
            return [d.embedding for d in response.data]
        except Exception as e:
            logger.error(f"Failed to call embedding API: {e}")
            raise
