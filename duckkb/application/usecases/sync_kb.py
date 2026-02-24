from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from duckkb.application.services.segmenter import chunk_text, tokenize
from duckkb.domain.errors import DomainError
from duckkb.domain.models import Chunk, Document, Metadata
from duckkb.domain.ports.embedding import EmbeddingProvider
from duckkb.domain.ports.repository import CacheRepo, ImportRepo, SearchIndexRepo


def sync_knowledge_base(
    import_repo: ImportRepo,
    index_repo: SearchIndexRepo,
    cache_repo: CacheRepo,
    embedding_provider: EmbeddingProvider,
    max_chunk_len: int = 500,
    manifest_path: str | None = None,
) -> int:
    files = import_repo.list_data_files()
    if manifest_path is not None:
        if not _needs_resync(files, manifest_path):
            return 0
    documents: list[Document] = []
    for file_path in files:
        lines = import_repo.read_jsonl_lines(file_path)
        table = Path(file_path).stem
        for idx, line in enumerate(lines, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DomainError(
                    code="invalid_json",
                    message="jsonl 行不是合法 JSON",
                    details={"line": idx, "error": str(exc), "file": file_path},
                ) from exc
            if not isinstance(record, dict):
                raise DomainError(
                    code="invalid_record",
                    message="jsonl 行必须是对象",
                    details={"line": idx, "file": file_path},
                )
            ref_id = record.get("id")
            if not isinstance(ref_id, str) or not ref_id:
                raise DomainError(
                    code="missing_id",
                    message="记录缺少 id",
                    details={"line": idx, "file": file_path},
                )
            priority = record.get("priority_weight", 1.0)
            if isinstance(priority, bool) or not isinstance(priority, (int, float)):
                raise DomainError(
                    code="invalid_priority_weight",
                    message="priority_weight 必须是数字",
                    details={"line": idx, "file": file_path},
                )
            documents.append(
                Document(
                    ref_id=ref_id,
                    source_table=table,
                    data=record,
                    priority_weight=float(priority),
                )
            )

    chunks = list(_documents_to_chunks(documents, max_chunk_len=max_chunk_len))
    index_repo.clear_index()
    inserted = index_repo.insert_chunks(chunks)

    for chunk in chunks:
        vector = cache_repo.get_embedding(chunk.content_hash)
        if vector is None:
            vector = embedding_provider.embed(chunk.segmented_text)
            if vector is not None:
                cache_repo.put_embedding(chunk.content_hash, vector)
        else:
            cache_repo.touch(chunk.content_hash)

    if manifest_path is not None:
        _write_manifest(files, manifest_path)
    return inserted


def _documents_to_chunks(
    documents: Iterable[Document],
    max_chunk_len: int,
) -> Iterable[Chunk]:
    for doc in documents:
        indexed_fields = _indexed_fields(doc.data)
        for source_field, text in indexed_fields:
            parts = list(chunk_text(text, max_chunk_len=max_chunk_len))
            for chunk_id, part in enumerate(parts):
                content_hash = hashlib.sha256(part.encode("utf-8")).hexdigest()
                metadata = _metadata_snapshot(doc.data, exclude_key=source_field)
                yield Chunk(
                    ref_id=doc.ref_id,
                    source_table=doc.source_table,
                    source_field=source_field,
                    chunk_id=chunk_id,
                    segmented_text=" ".join(tokenize(part)),
                    content_hash=content_hash,
                    metadata=metadata,
                    priority_weight=doc.priority_weight,
                )


def _indexed_fields(data: Metadata) -> list[tuple[str, str]]:
    if "content" in data and isinstance(data["content"], str):
        fields = [("content", data["content"])]
        if "title" in data and isinstance(data["title"], str):
            fields.append(("title", data["title"]))
        return fields
    result: list[tuple[str, str]] = []
    for key, value in data.items():
        if key in {"id", "metadata", "priority_weight"}:
            continue
        if isinstance(value, str) and value.strip():
            result.append((key, value))
    return result


def _metadata_snapshot(data: Metadata, exclude_key: str) -> Metadata:
    snapshot = dict(data)
    snapshot.pop(exclude_key, None)
    return snapshot


def _needs_resync(files: list[str], manifest_path: str) -> bool:
    path = Path(manifest_path)
    if not path.exists():
        return True
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return True
    if not isinstance(stored, dict):
        return True
    current = _build_manifest(files)
    return stored != current


def _write_manifest(files: list[str], manifest_path: str) -> None:
    path = Path(manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _build_manifest(files)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _build_manifest(files: list[str]) -> dict[str, float]:
    manifest: dict[str, float] = {}
    for file_path in files:
        stat = Path(file_path).stat()
        manifest[file_path] = stat.st_mtime
    return manifest
