from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


Metadata = dict[str, Any]


@dataclass(frozen=True)
class Document:
    ref_id: str
    source_table: str
    data: Metadata
    priority_weight: float


@dataclass(frozen=True)
class Chunk:
    ref_id: str
    source_table: str
    source_field: str
    chunk_id: int
    segmented_text: str
    content_hash: str
    metadata: Metadata
    priority_weight: float


@dataclass(frozen=True)
class SearchHit:
    ref_id: str
    source_table: str
    source_field: str
    segmented_text: str
    metadata: Metadata
    priority_weight: float
    score: float


@dataclass(frozen=True)
class KBPath:
    root: str
    data_dir: str
    build_dir: str
    schema_file: str


def to_metadata(value: Mapping[str, Any]) -> Metadata:
    return dict(value)
