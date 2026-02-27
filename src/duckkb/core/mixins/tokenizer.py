"""分词 Mixin。"""

import asyncio
import threading

from duckkb.core.base import BaseEngine
from duckkb.logger import logger

_jieba_lock = threading.Lock()


class TokenizerMixin(BaseEngine):
    """分词 Mixin。

    提供中文分词功能，支持用户自定义词典。
    tokenizer 从 config.yaml 的 global.tokenizer 读取。

    Attributes:
        tokenizer: 分词器类型。
    """

    def __init__(self, *args, **kwargs) -> None:
        """初始化分词 Mixin。"""
        super().__init__(*args, **kwargs)
        self._jieba_initialized = False

    @property
    def tokenizer(self) -> str:
        """分词器类型，从全局配置读取。"""
        return self.config.global_config.tokenizer

    def init_tokenizer(self) -> None:
        """初始化分词器。

        加载用户自定义词典（如果存在）。
        """
        if self.tokenizer != "jieba":
            logger.warning(f"Unsupported tokenizer: {self.tokenizer}, using jieba")
            return

        if self._jieba_initialized:
            return

        with _jieba_lock:
            if self._jieba_initialized:
                return

            import jieba

            user_dict = self.kb_path / "user_dict.txt"
            if user_dict.exists():
                try:
                    jieba.load_userdict(str(user_dict))
                    logger.debug(f"Loaded user dict from {user_dict}")
                except Exception as e:
                    logger.warning(f"Failed to load user dict: {e}")

            self._jieba_initialized = True
            logger.debug("Jieba tokenizer initialized")

    async def segment(self, text: str) -> str:
        """对文本进行中文分词。

        使用搜索引擎模式分词，对长词进行更细粒度的切分，
        适合知识库检索场景，能提高召回率。

        Args:
            text: 待分词的文本。

        Returns:
            空格分隔的分词结果字符串。
        """
        if not text:
            return ""

        await asyncio.to_thread(self.init_tokenizer)

        def _do_segment() -> str:
            import jieba

            return " ".join(jieba.cut_for_search(text))

        return await asyncio.to_thread(_do_segment)

    async def segment_batch(self, texts: list[str]) -> list[str]:
        """批量分词。

        Args:
            texts: 待分词的文本列表。

        Returns:
            分词结果列表。
        """
        if not texts:
            return []

        await asyncio.to_thread(self.init_tokenizer)

        import jieba

        def _do_segment_batch() -> list[str]:
            return [" ".join(jieba.cut_for_search(t)) for t in texts]

        return await asyncio.to_thread(_do_segment_batch)

    def _segment_sync(self, text: str) -> str:
        """同步分词处理。

        用于事务内的同步索引构建场景。

        Args:
            text: 待分词文本。

        Returns:
            空格分隔的分词结果字符串。
        """
        if not text:
            return ""

        self.init_tokenizer()

        import jieba

        return " ".join(jieba.cut_for_search(text))
