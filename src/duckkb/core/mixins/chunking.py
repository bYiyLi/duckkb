"""文本切片 Mixin。"""

from duckkb.core.base import BaseEngine


class ChunkingMixin(BaseEngine):
    """文本切片 Mixin。

    提供长文本切分功能，用于向量化前的预处理。
    chunk_size 和 chunk_overlap 从 config.yaml 的 global 节读取。

    Attributes:
        chunk_size: 切片大小（字符数）。
        chunk_overlap: 切片重叠大小（字符数）。
    """

    def __init__(self, *args, chunk_overlap: int = 100, **kwargs) -> None:
        """初始化切片 Mixin。

        Args:
            chunk_overlap: 切片重叠大小，默认 100 字符。
        """
        super().__init__(*args, **kwargs)
        self._chunk_overlap = chunk_overlap

    @property
    def chunk_size(self) -> int:
        """切片大小，从全局配置读取。"""
        return self.config.global_config.chunk_size

    @property
    def chunk_overlap(self) -> int:
        """切片重叠大小。"""
        return self._chunk_overlap

    def chunk_text(self, text: str) -> list[str]:
        """将文本切分为多个片段。

        使用滑动窗口策略，支持重叠切片以提高检索召回率。

        Args:
            text: 待切分的文本。

        Returns:
            文本片段列表。
        """
        if not text:
            return []

        if len(text) <= self.chunk_size:
            return [text]

        chunks: list[str] = []
        start = 0
        step = self.chunk_size - self._chunk_overlap

        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]

            if len(chunk) < self.chunk_size // 2 and chunks:
                chunks[-1] += chunk
            else:
                chunks.append(chunk)

            start += step

        return [c.strip() for c in chunks if c.strip()]

    def chunk_by_sentence(self, text: str, max_size: int | None = None) -> list[str]:
        """按句子边界切分文本。

        尝试在句子边界处切分，避免截断句子。

        Args:
            text: 待切分的文本。
            max_size: 最大片段大小，默认使用全局 chunk_size。

        Returns:
            文本片段列表。
        """
        if max_size is None:
            max_size = self.chunk_size

        if not text:
            return []

        if len(text) <= max_size:
            return [text]

        import re

        sentence_endings = re.compile(r'[。！？.!?]\s*')
        chunks: list[str] = []
        current_chunk = ""

        sentences = sentence_endings.split(text)
        separators = sentence_endings.findall(text)

        for i, sentence in enumerate(sentences):
            sep = separators[i] if i < len(separators) else ""
            full_sentence = sentence + sep

            if len(current_chunk) + len(full_sentence) > max_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = full_sentence
            else:
                current_chunk += full_sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks
