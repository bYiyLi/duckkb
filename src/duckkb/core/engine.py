"""知识库引擎。"""

from pathlib import Path
from typing import Self

from duckkb.core.config import GlobalConfig
from duckkb.core.mixins import (
    ChunkingMixin,
    ConfigMixin,
    DBMixin,
    EmbeddingMixin,
    GraphMixin,
    ImportMixin,
    IndexMixin,
    OntologyMixin,
    SearchMixin,
    StorageMixin,
    TokenizerMixin,
)
from duckkb.logger import logger


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
    GraphMixin,
    ImportMixin,
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
    10. GraphMixin - 知识图谱检索
    11. ImportMixin - 知识导入

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
        注意：此方法不加载数据，需要异步加载请使用 async_initialize()。

        Returns:
            初始化后的引擎实例，支持链式调用。
        """
        self._ensure_fts_installed()
        self.sync_schema()
        self.create_index_tables()
        logger.warning(
            "initialize() does not load existing data. "
            "Use async_initialize() for full initialization."
        )
        return self

    async def async_initialize(self) -> Self:
        """异步初始化引擎。

        同步数据库表结构，创建搜索索引表，并从文件系统加载已有数据。

        Returns:
            初始化后的引擎实例，支持链式调用。
        """
        self._ensure_fts_installed()
        self.sync_schema()
        self.create_index_tables()
        await self._load_existing_data()
        return self

    async def _load_existing_data(self) -> None:
        """从文件系统加载已有数据。

        加载所有节点类型、边类型和搜索缓存。
        """
        data_dir = self.config.storage.data_dir

        if not data_dir.exists():
            logger.debug(f"Data directory does not exist: {data_dir}")
            return

        loaded_nodes = 0
        loaded_edges = 0

        for node_type in self.ontology.nodes.keys():
            try:
                count = await self.load_node(node_type)
                if count > 0:
                    loaded_nodes += count
            except Exception as e:
                error_msg = str(e)
                if "No files found" in error_msg:
                    logger.debug(f"No data files for node type {node_type}")
                else:
                    logger.warning(f"Failed to load node type {node_type}: {e}")

        for edge_name in self.ontology.edges.keys():
            try:
                count = await self.load_edge(edge_name)
                if count > 0:
                    loaded_edges += count
            except Exception as e:
                error_msg = str(e)
                if "No files found" in error_msg:
                    logger.debug(f"No data files for edge type {edge_name}")
                else:
                    logger.warning(f"Failed to load edge type {edge_name}: {e}")

        cache_path = data_dir / "cache" / "search_cache.parquet"
        if cache_path.exists():
            try:
                cache_count = await self.load_cache_from_parquet(cache_path)
                logger.info(f"Loaded {cache_count} cache entries from {cache_path}")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")

        if loaded_nodes > 0 or loaded_edges > 0:
            logger.info(f"Loaded existing data: {loaded_nodes} nodes, {loaded_edges} edges")

        await self._rebuild_index_from_cache()

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
