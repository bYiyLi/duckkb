"""嵌入向量管理 Mixin。"""

import hashlib
from typing import TYPE_CHECKING

from duckkb.core.base import BaseEngine
from duckkb.logger import logger

if TYPE_CHECKING:
    from openai import AsyncOpenAI


class EmbeddingMixin(BaseEngine):
    """嵌入向量管理 Mixin。

    提供文本向量嵌入的获取与缓存功能，支持批量查询和自动缓存。
    embedding_model 从 config.yaml 的 global.embedding_model 读取。

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
        """嵌入模型名称，从全局配置读取。"""
        return self.config.global_config.embedding_model

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
        """获取文本列表的向量嵌入。

        Args:
            texts: 待获取嵌入的文本列表。

        Returns:
            向量嵌入列表。
        """
        if not texts:
            return []

        try:
            response = await self.openai_client.embeddings.create(
                input=texts, model=self.embedding_model
            )
            return [d.embedding for d in response.data]
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise

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
