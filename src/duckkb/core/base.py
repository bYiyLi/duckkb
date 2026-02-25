"""核心引擎抽象基类。"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from duckkb.config import KBConfig
    from duckkb.core.config import CoreConfig
    from duckkb.database.engine.ontology import Ontology


class BaseEngine(ABC):
    """核心引擎抽象基类。

    只存储基础路径，定义抽象接口。
    具体实现由各 Mixin 提供。

    Attributes:
        kb_path: 知识库根目录。
    """

    def __init__(self, kb_path: Path | str) -> None:
        """初始化引擎基类。

        Args:
            kb_path: 知识库根目录路径。
        """
        self._kb_path = Path(kb_path).resolve()

    @property
    def kb_path(self) -> Path:
        """知识库根目录。"""
        return self._kb_path

    @property
    @abstractmethod
    def config(self) -> "CoreConfig":
        """核心配置对象。"""
        ...

    @property
    @abstractmethod
    def kb_config(self) -> "KBConfig":
        """知识库配置对象。"""
        ...

    @property
    @abstractmethod
    def conn(self) -> duckdb.DuckDBPyConnection:
        """数据库连接。"""
        ...

    @property
    @abstractmethod
    def ontology(self) -> "Ontology":
        """本体定义。"""
        ...
