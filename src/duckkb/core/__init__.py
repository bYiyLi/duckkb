"""核心引擎模块。

本模块提供 DuckKB 的核心引擎功能，包括：
- 配置管理
- 本体管理
- SQL 驱动的存储层
- RRF 混合检索

架构设计：
- Layer 1: BaseEngine 抽象基类
- Layer 2: 能力 Mixin (ConfigMixin, DBMixin, OntologyMixin, StorageMixin, SearchMixin)
- Layer 3: Engine 多继承聚合
"""

from duckkb.core.base import BaseEngine
from duckkb.core.config import CoreConfig, StorageConfig
from duckkb.core.engine import Engine
from duckkb.core.mixins import (
    ConfigMixin,
    DBMixin,
    OntologyMixin,
    SearchMixin,
    StorageMixin,
)

__all__ = [
    "BaseEngine",
    "ConfigMixin",
    "CoreConfig",
    "DBMixin",
    "Engine",
    "OntologyMixin",
    "SearchMixin",
    "StorageConfig",
    "StorageMixin",
]
