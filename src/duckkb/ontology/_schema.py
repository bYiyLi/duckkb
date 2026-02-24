"""JSON Schema 元模式定义模块。

本模块定义了本体配置的 JSON Schema 元模式，用于验证配置文件的正确性。
参考 JSON Schema Draft 7 规范。
"""

from typing import Any

ONTOLOGY_META_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "nodes": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "identity": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "schema": {
                        "type": "object",
                        "description": "Standard JSON Schema Draft 7 definition for the node properties",
                    },
                    "vectors": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "dim": {"type": "integer", "minimum": 1},
                                "metric": {
                                    "type": "string",
                                    "enum": ["cosine", "l2", "inner"],
                                    "default": "cosine",
                                },
                                "model": {"type": "string"},
                            },
                            "required": ["dim", "model"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["table", "identity"],
                "additionalProperties": False,
            },
        },
        "edges": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "cardinality": {
                        "type": "string",
                        "enum": ["1:1", "1:N", "N:1", "N:N"],
                        "default": "N:N",
                    },
                    "schema": {
                        "type": "object",
                        "description": "Standard JSON Schema Draft 7 definition for the edge properties",
                    },
                },
                "required": ["from", "to"],
                "additionalProperties": False,
            },
        },
    },
    "required": [],
    "additionalProperties": False,
}

JSON_SCHEMA_DRAFT7_TYPES: set[str] = {
    "string",
    "integer",
    "number",
    "boolean",
    "array",
    "object",
    "null",
}

JSON_SCHEMA_DRAFT7_FORMATS: set[str] = {
    "date-time",
    "date",
    "time",
    "email",
    "uri",
    "hostname",
    "ipv4",
    "ipv6",
    "uuid",
    "regex",
}
