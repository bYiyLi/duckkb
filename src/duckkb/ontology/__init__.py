"""本体管理模块。

本模块负责知识库本体定义的加载、验证和 DDL 生成，包括：
- 节点类型定义（对应数据库表）
- 边类型定义（实体间关系）
- JSON Schema 验证
- DDL 自动生成
"""

from duckkb.ontology._models import EdgeType, NodeType, Ontology, VectorConfig
from duckkb.ontology.engine import OntologyEngine

__all__ = [
    "VectorConfig",
    "NodeType",
    "EdgeType",
    "Ontology",
    "OntologyEngine",
]
