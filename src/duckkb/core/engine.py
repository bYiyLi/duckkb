"""知识库引擎。"""

from pathlib import Path
from typing import Self

from duckkb.core.mixins import (
    ConfigMixin,
    DBMixin,
    OntologyMixin,
    SearchMixin,
    StorageMixin,
)


class Engine(
    ConfigMixin,
    DBMixin,
    OntologyMixin,
    StorageMixin,
    SearchMixin,
):
    """知识库引擎。

    通过多继承聚合所有能力。
    初始化只需传入知识库路径，其他由各 Mixin 自动处理。

    Attributes:
        kb_path: 知识库根目录。
        config: 配置对象。
        conn: 数据库连接。
        ontology: 本体定义。

    Example:
        ```python
        # 简单使用
        with Engine("/path/to/kb") as engine:
            await engine.load_node("document")
            results = await engine.search("document", "embedding", vector, ["content"], "query")

        # 自定义配置
        engine = Engine(
            "/path/to/kb",
            config_path="/custom/config.yaml",
            db_path="/custom/data.db",
            rrf_k=100,
        )
        engine.initialize()
        ```
    """

    def __init__(
        self,
        kb_path: Path | str,
        *,
        config_path: Path | str | None = None,
        db_path: Path | str | None = None,
        rrf_k: int = 60,
    ) -> None:
        """初始化知识库引擎。

        Args:
            kb_path: 知识库根目录路径。
            config_path: 配置文件路径，默认为 kb_path/config.yaml。
            db_path: 数据库文件路径，默认从 config.storage.data_dir 派生。
            rrf_k: RRF 常数，默认 60。
        """
        super().__init__(
            kb_path=kb_path,
            config_path=config_path,
            db_path=db_path,
            rrf_k=rrf_k,
        )

    def initialize(self) -> Self:
        """初始化引擎。

        同步数据库表结构，确保所有节点表和边表已创建。

        Returns:
            初始化后的引擎实例，支持链式调用。
        """
        self.sync_schema()
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
