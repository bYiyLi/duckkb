"""本体模型定义模块。

本模块定义了知识库本体的 Pydantic 模型，包括：
- VectorConfig: 向量字段配置
- NodeType: 节点类型定义
- EdgeType: 边类型定义
- Ontology: 本体定义
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from collections.abc import Iterable

from duckkb.constants import DEFAULT_METRIC, VALID_METRICS

_ALLOWED_TYPES = {"string", "integer", "number", "boolean", "array", "object", "null"}


def _fail(path: str, message: str) -> None:
    """抛出带路径的校验错误。

    Args:
        path: 出错路径。
        message: 错误信息。

    Raises:
        ValueError: 始终抛出。
    """
    raise ValueError(f"{path}: {message}")


def _format_path(parts: Iterable[object]) -> str:
    """格式化 JSON 指向路径。

    Args:
        parts: 路径片段。

    Returns:
        格式化后的路径字符串。
    """
    path = ""
    for part in parts:
        if isinstance(part, int):
            path = f"{path}[{part}]"
        else:
            path = f"{path}.{part}" if path else str(part)
    return path


def _validate_schema_structure(schema: dict[str, object], path: str) -> None:
    """校验 Schema 结构的合法性。

    Args:
        schema: JSON Schema。
        path: 路径前缀。

    Raises:
        ValueError: Schema 结构不合法时抛出。
    """
    schema_type = schema.get("type")
    if schema_type is None:
        return
    if schema_type not in _ALLOWED_TYPES:
        _fail(path, f"unsupported schema type: {schema_type}")

    if schema_type == "object":
        required = schema.get("required") or []
        if not isinstance(required, list):
            _fail(path, "required must be a list")
        props = cast("dict[str, object]", schema.get("properties") or {})
        if not isinstance(props, dict):
            _fail(path, "properties must be an object")
        for key, prop in props.items():
            if isinstance(prop, dict):
                sub_path = f"{path}.{key}" if path else str(key)
                _validate_schema_structure(prop, sub_path)
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            sub_path = f"{path}.*" if path else "*"
            _validate_schema_structure(additional, sub_path)
        return

    if schema_type == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            sub_path = f"{path}[]" if path else "[]"
            _validate_schema_structure(items, sub_path)
        elif isinstance(items, list):
            for idx, item in enumerate(items):
                if isinstance(item, dict):
                    sub_path = f"{path}[{idx}]" if path else f"[{idx}]"
                    _validate_schema_structure(item, sub_path)


def _build_validator(schema: dict[str, object]) -> Any:
    """构建 Draft7Validator。

    Args:
        schema: JSON Schema。

    Returns:
        Draft7Validator 实例。
    """
    try:
        from jsonschema import Draft7Validator, FormatChecker, validators
    except ImportError as e:
        raise ImportError("jsonschema package required for validation") from e

    type_checker = Draft7Validator.TYPE_CHECKER.redefine(
        "integer",
        lambda checker, instance: isinstance(instance, int) and not isinstance(instance, bool),
    )
    type_checker = type_checker.redefine(
        "number",
        lambda checker, instance: (
            isinstance(instance, (int, float)) and not isinstance(instance, bool)
        ),
    )
    validator_cls = validators.extend(Draft7Validator, type_checker=type_checker)
    return validator_cls(schema, format_checker=FormatChecker())


def _raise_validation_error(error: Any) -> None:
    """将 jsonschema 错误转换为 ValueError。

    Args:
        error: jsonschema 校验错误。

    Raises:
        ValueError: 始终抛出。
    """
    path = _format_path(error.path)
    if error.validator == "required":
        if isinstance(error.instance, dict) and isinstance(error.validator_value, list):
            for key in error.validator_value:
                if key not in error.instance:
                    _fail(path, f"missing required property: {key}")
        _fail(path, "missing required property")
    if error.validator == "additionalProperties":
        unexpected: str | None = None
        params = getattr(error, "params", None)
        if isinstance(params, dict):
            extra = params.get("additionalProperties")
            if isinstance(extra, list) and extra:
                unexpected = str(extra[0])
            elif isinstance(extra, str):
                unexpected = extra
        if (
            unexpected is None
            and isinstance(error.instance, dict)
            and isinstance(error.schema, dict)
            and error.schema.get("additionalProperties") is False
        ):
            props = error.schema.get("properties")
            if isinstance(props, dict):
                extra_keys = sorted(set(error.instance.keys()) - set(props.keys()))
                if extra_keys:
                    unexpected = extra_keys[0]
        if unexpected is None and isinstance(error.message, str):
            match = re.search(r"\('(.+?)' was unexpected\)", error.message)
            if match:
                unexpected = match.group(1)
        if unexpected:
            _fail(path, f"unexpected property: {unexpected}")
        _fail(path, "unexpected property")
    if error.validator == "type":
        schema_type = error.validator_value
        if isinstance(schema_type, list) and schema_type:
            schema_type = schema_type[0]
        if isinstance(schema_type, str):
            _fail(path, f"expected {schema_type}")
        _fail(path, "type mismatch")
    if error.validator == "format":
        if error.validator_value == "date-time":
            _fail(path, "expected RFC3339 date-time")
        _fail(path, error.message)
    _fail(path, error.message)


def _coerce_by_schema(schema: dict[str, object], data: object) -> object:
    """按 Schema 对数据做必要的类型转换。

    Args:
        schema: JSON Schema。
        data: 已通过校验的数据。

    Returns:
        转换后的数据。
    """
    schema_type = schema.get("type")
    if schema_type is None:
        return data

    if schema_type == "null":
        return data

    if schema_type == "string":
        fmt = schema.get("format")
        if fmt == "date-time" and isinstance(data, str):
            try:
                return datetime.fromisoformat(data.replace("Z", "+00:00"))
            except Exception:
                _fail("", "expected RFC3339 date-time")
        return data

    if schema_type == "array":
        if not isinstance(data, list):
            return data
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            return [_coerce_by_schema(item_schema, item) for item in data]
        return data

    if schema_type == "object":
        if not isinstance(data, dict):
            return data
        props = cast("dict[str, object]", schema.get("properties") or {})
        out: dict[str, object] = {}
        for key, value in data.items():
            prop_schema = props.get(key)
            if isinstance(prop_schema, dict):
                out[key] = _coerce_by_schema(prop_schema, value)
            else:
                out[key] = value
        return out

    return data


def validate_json_by_schema(schema: dict[str, object], data: object) -> object:
    """使用 Draft7Validator 校验并转换数据。

    Args:
        schema: JSON Schema。
        data: 待校验数据。

    Returns:
        校验并转换后的数据。

    Raises:
        ValueError: 数据不符合 Schema 时抛出。
    """
    if schema.get("type") is None:
        return data

    _validate_schema_structure(schema, "")
    validator = _build_validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        _raise_validation_error(errors[0])
    return _coerce_by_schema(schema, data)


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


class SearchConfig(BaseModel):
    """搜索配置。

    定义节点的搜索索引配置。

    Attributes:
        full_text: 全文索引字段列表。
        vectors: 向量索引字段列表。
    """

    full_text: list[str] | None = None
    vectors: list[str] | None = None
    model_config = ConfigDict(extra="forbid")


class NodeType(BaseModel):
    """节点类型定义。

    节点类型对应数据库中的表，定义了表名、主键字段、属性结构和向量字段。

    Attributes:
        table: 对应的数据库表名。
        identity: 标识字段列表（主键）。
        json_schema: 属性定义（JSON Schema Draft 7）。
        vectors: 向量字段定义。
        search: 搜索配置。
    """

    table: str
    identity: list[str] = Field(...)
    json_schema: dict[str, Any] | None = Field(default=None, alias="schema")
    vectors: dict[str, VectorConfig] | None = None
    search: SearchConfig | None = None
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

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
    def validate_edge_references(self) -> Ontology:
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
