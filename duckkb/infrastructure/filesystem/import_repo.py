from __future__ import annotations

from pathlib import Path

from duckkb.domain.errors import DomainError
from duckkb.domain.ports.repository import ImportRepo
from duckkb.infrastructure.filesystem.fs_atomic import read_jsonl_lines, write_jsonl_atomic
from duckkb.infrastructure.filesystem.kb_env import safe_join


class FilesystemImportRepo(ImportRepo):
    def __init__(self, kb_root: str) -> None:
        self._kb_root = Path(kb_root)
        self._data_dir = safe_join(self._kb_root, "data")

    def list_data_files(self) -> list[str]:
        if not self._data_dir.exists():
            return []
        return [str(path) for path in sorted(self._data_dir.glob("*.jsonl"))]

    def read_jsonl_lines(self, file_path: str) -> list[str]:
        path = Path(file_path).resolve()
        allowed = safe_join(self._data_dir, path.name).resolve()
        if allowed != path:
            raise DomainError(
                code="path_traversal",
                message="路径越界",
                details={"path": str(path), "allowed": str(allowed)},
            )
        return read_jsonl_lines(str(allowed))

    def write_table_jsonl(self, table_name: str, lines: list[str]) -> None:
        file_path = safe_join(self._data_dir, f"{table_name}.jsonl")
        write_jsonl_atomic(str(file_path), lines)
