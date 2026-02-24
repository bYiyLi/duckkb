"""JSON Schema 验证器模块。

本模块提供基于 JSON Schema Draft 7 的数据验证功能，包括：
- Schema 结构验证
- 数据验证和类型转换
- 详细错误信息
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

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
        props = schema.get("properties") or {}
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
        props = schema.get("properties") or {}
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
