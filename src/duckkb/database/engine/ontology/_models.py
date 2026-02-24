"""本体模型定义模块。

本模块定义了知识库本体的 Pydantic 模型，包括：
- VectorConfig: 向量字段配置
- NodeType: 节点类型定义
- EdgeType: 边类型定义
- Ontology: 本体定义
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from duckkb.constants import DEFAULT_METRIC, VALID_METRICS
from duckkb.database.engine.ontology._validator import _validate_schema_structure


class VectorConfig(BaseModel):
    """向量字段配置。

    用于定义节点中向量字段的属性，包括维度、模型和度量方式。

    Attributes:
        dim: 向量维度，必须为正整数。
        model: 嵌入模型名称。
        metric: 相似度度量方式，默认为 cosine。
    """

    dim: int
    model: str
    metric: str = DEFAULT_METRIC

    @field_validator("dim")
    @classmethod
    def validate_dim(cls, v: int) -> int:
        """验证向量维度。

        Args:
            v: 待验证的维度值。

        Returns:
            验证通过的维度值。

        Raises:
            ValueError: 维度值非正时抛出。
        """
        if v <= 0:
            raise ValueError("dim must be positive")
        return v

    @field_validator("metric")
    @classmethod
    def validate_metric(cls, v: str) -> str:
        """验证相似度度量方式。

        Args:
            v: 待验证的度量方式。

        Returns:
            验证通过的度量方式。

        Raises:
            ValueError: 度量方式无效时抛出。
        """
        if v not in VALID_METRICS:
            raise ValueError(f"metric must be one of: {VALID_METRICS}")
        return v


class NodeType(BaseModel):
    """节点类型定义。

    节点类型对应数据库中的表，定义了表名、主键字段、属性结构和向量字段。

    Attributes:
        table: 对应的数据库表名。
        identity: 标识字段列表（主键）。
        json_schema: 属性定义（JSON Schema Draft 7）。
        vectors: 向量字段定义。
    """

    table: str
    identity: list[str] = Field(...)
    json_schema: dict[str, Any] | None = Field(default=None, alias="schema")
    vectors: dict[str, VectorConfig] | None = None
    model_config = ConfigDict(extra="forbid")

    @field_validator("identity")
    @classmethod
    def validate_identity(cls, v: list[str]) -> list[str]:
        """验证标识字段列表。

        Args:
            v: 待验证的标识字段列表。

        Returns:
            验证通过的标识字段列表。

        Raises:
            ValueError: 标识字段列表为空时抛出。
        """
        if not v:
            raise ValueError("identity must not be empty")
        return v

    @field_validator("table")
    @classmethod
    def validate_table(cls, v: str) -> str:
        """验证表名。

        Args:
            v: 待验证的表名。

        Returns:
            验证通过的表名。

        Raises:
            ValueError: 表名为空时抛出。
        """
        if not v or not v.strip():
            raise ValueError("table name required")
        return v.strip()

    @field_validator("json_schema")
    @classmethod
    def validate_json_schema(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        """验证 JSON Schema 结构。

        Args:
            v: 待验证的 JSON Schema。

        Returns:
            验证通过的 JSON Schema。

        Raises:
            ValueError: Schema 结构不合法时抛出。
        """
        if v is not None:
            _validate_schema_structure(v, "schema")
        return v


class EdgeType(BaseModel):
    """边类型定义。

    边类型定义了实体间的关系，包括起始节点、目标节点和关系属性。

    Attributes:
        from_: 起始节点类型。
        to: 目标节点类型。
        cardinality: 基数（1:1, 1:N, N:1, N:N）。
        json_schema: 边属性定义（JSON Schema Draft 7）。
    """

    from_: str = Field(alias="from")
    to: str
    cardinality: str | None = None
    json_schema: dict[str, Any] | None = Field(default=None, alias="schema")
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @field_validator("cardinality")
    @classmethod
    def validate_cardinality(cls, v: str | None) -> str | None:
        """验证基数。

        Args:
            v: 待验证的基数值。

        Returns:
            验证通过的基数值。

        Raises:
            ValueError: 基数值无效时抛出。
        """
        if v is None:
            return v
        valid_cardinalities = {"1:1", "1:N", "N:1", "N:N"}
        if v not in valid_cardinalities:
            raise ValueError(f"cardinality must be one of: {valid_cardinalities}")
        return v

    @field_validator("json_schema")
    @classmethod
    def validate_json_schema(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        """验证 JSON Schema 结构。

        Args:
            v: 待验证的 JSON Schema。

        Returns:
            验证通过的 JSON Schema。

        Raises:
            ValueError: Schema 结构不合法时抛出。
        """
        if v is not None:
            _validate_schema_structure(v, "schema")
        return v


class Ontology(BaseModel):
    """本体定义。

    本体定义了知识库的完整结构，包括节点类型和边类型。

    Attributes:
        nodes: 节点类型定义。
        edges: 边类型定义。
    """

    nodes: dict[str, NodeType] = Field(default_factory=dict)
    edges: dict[str, EdgeType] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_edge_references(self) -> "Ontology":
        """验证边引用的节点类型是否存在。

        Returns:
            验证通过的本体实例。

        Raises:
            ValueError: 边引用的节点类型不存在时抛出。
        """
        for edge_name, edge in self.edges.items():
            if edge.from_ not in self.nodes:
                raise ValueError(f"Edge '{edge_name}' references unknown node type '{edge.from_}'")
            if edge.to not in self.nodes:
                raise ValueError(f"Edge '{edge_name}' references unknown node type '{edge.to}'")
        return self
