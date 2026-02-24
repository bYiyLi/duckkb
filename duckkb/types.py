from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class ErrorEnvelope:
    code: str
    message: str
    details: JsonDict


@dataclass(frozen=True)
class SearchItem:
    ref_id: str
    source_table: str
    source_field: str
    segmented_text: str
    metadata: JsonDict
    priority_weight: float
    score: float


@dataclass(frozen=True)
class SearchResponse:
    items: list[SearchItem]
    truncated: bool


@dataclass(frozen=True)
class SqlQueryResult:
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool


@dataclass(frozen=True)
class SyncResult:
    synced: int
    affected_tables: list[str]


@dataclass(frozen=True)
class SchemaInfo:
    schema_sql: str
    er_mermaid: str


@dataclass(frozen=True)
class ValidateImportResult:
    accepted: int
    errors: list[ErrorEnvelope]


def to_json_dict(value: Mapping[str, Any]) -> JsonDict:
    return dict(value)
