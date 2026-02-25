"""核心引擎模块。

本模块提供 DuckKB 的核心引擎功能，包括：
- 配置管理
- 本体管理
- SQL 驱动的存储层
- 文本切片
- 中文分词
- 向量嵌入
- 搜索索引
- RRF 混合检索

架构设计：
- Layer 1: BaseEngine 抽象基类
- Layer 2: 能力 Mixin (ConfigMixin, DBMixin, OntologyMixin, StorageMixin,
              ChunkingMixin, TokenizerMixin, EmbeddingMixin, IndexMixin, SearchMixin)
- Layer 3: Engine 多继承聚合

核心设计理念：
- 计算与存储解耦：DuckDB 采用内存模式，不产生持久化 .db 文件
- 真理源于文件：所有数据以 JSONL 文本形式存储，Git 托管
- 确定性还原：通过 identity 字段排序，确保 Git Diff 有效
"""

from duckkb.core.base import BaseEngine
from duckkb.core.config import CoreConfig, GlobalConfig, StorageConfig
from duckkb.core.engine import Engine
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
from duckkb.core.models import EdgeType, NodeType, Ontology, VectorConfig

__all__ = [
    "BaseEngine",
    "ChunkingMixin",
    "ConfigMixin",
    "CoreConfig",
    "DBMixin",
    "EdgeType",
    "EmbeddingMixin",
    "Engine",
    "GlobalConfig",
    "IndexMixin",
    "NodeType",
    "Ontology",
    "OntologyMixin",
    "SearchMixin",
    "StorageConfig",
    "StorageMixin",
    "TokenizerMixin",
    "VectorConfig",
]
