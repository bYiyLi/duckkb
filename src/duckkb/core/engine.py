"""知识库引擎。"""

from pathlib import Path
from typing import Self

from duckkb.core.config import GlobalConfig
from duckkb.core.mixins import (
    ChunkingMixin,
    ConfigMixin,
    DBMixin,
    EmbeddingMixin,
    IndexMixin,
    OntologyMixin,
    SearchMixin,
    StorageMixin,
    TokenizerMixin,
)


class Engine(
    ConfigMixin,
    DBMixin,
    OntologyMixin,
    StorageMixin,
    ChunkingMixin,
    TokenizerMixin,
    EmbeddingMixin,
    IndexMixin,
    SearchMixin,
):
    """知识库引擎。

    通过多继承聚合所有能力。
    初始化只需传入知识库路径，其他由各 Mixin 自动处理。
    全局配置从 config.yaml 的 global 节读取。

    MRO 顺序确保依赖关系：
    1. ConfigMixin - 配置加载
    2. DBMixin - 数据库连接（内存模式）
    3. OntologyMixin - 本体管理
    4. StorageMixin - 数据存储
    5. ChunkingMixin - 文本切片
    6. TokenizerMixin - 分词处理
    7. EmbeddingMixin - 向量嵌入
    8. IndexMixin - 搜索索引
    9. SearchMixin - 混合检索

    Attributes:
        kb_path: 知识库根目录。
        config: 配置对象。
        conn: 数据库连接（内存模式）。
        ontology: 本体定义。

    Example:
        ```python
        # 简单使用
        with Engine("/path/to/kb") as engine:
            await engine.build_index()
            results = await engine.search("查询文本")

        # 自定义配置路径
        engine = Engine(
            "/path/to/kb",
            config_path="/custom/config.yaml",
        )
        engine.initialize()
        ```
    """

    def __init__(
        self,
        kb_path: Path | str,
        *,
        config_path: Path | str | None = None,
        rrf_k: int = 60,
    ) -> None:
        """初始化知识库引擎。

        全局配置（chunk_size, embedding_model, tokenizer）从 config.yaml 读取。

        Args:
            kb_path: 知识库根目录路径。
            config_path: 配置文件路径，默认为 kb_path/config.yaml。
            rrf_k: RRF 常数，默认 60。
        """
        super().__init__(
            kb_path=kb_path,
            config_path=config_path,
            rrf_k=rrf_k,
        )

    def _get_global_config(self) -> GlobalConfig:
        """获取全局配置。"""
        return self.config.global_config

    def initialize(self) -> Self:
        """初始化引擎。

        同步数据库表结构，创建搜索索引表。

        Returns:
            初始化后的引擎实例，支持链式调用。
        """
        self.sync_schema()
        self.create_index_tables()
        return self

    def close(self) -> None:
        """关闭引擎。

        关闭数据库连接。
        """
        super().close()

    def __enter__(self) -> Self:
        """同步上下文管理器入口。

        Returns:
            初始化后的引擎实例。
        """
        self.initialize()
        return self

    def __exit__(self, *args) -> None:
        """同步上下文管理器出口。"""
        self.close()
