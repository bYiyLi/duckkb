from __future__ import annotations

from pathlib import Path

from duckkb.domain.errors import DomainError
from duckkb.domain.models import KBPath


def resolve_kb_path(kb_path: str | Path) -> KBPath:
    root = Path(kb_path).expanduser().resolve()
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
    data_dir = safe_join(root, "data")
    build_dir = safe_join(root, ".build")
    data_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)
    schema_file = safe_join(root, "schema.sql")
    return KBPath(
        root=str(root),
        data_dir=str(data_dir),
        build_dir=str(build_dir),
        schema_file=str(schema_file),
    )


def safe_join(root: Path | str, *parts: str) -> Path:
    root_path = Path(root).expanduser().resolve()
    candidate = root_path.joinpath(*parts).resolve()
    if root_path not in candidate.parents and candidate != root_path:
        raise DomainError(
            code="path_traversal",
            message="路径越界",
            details={"root": str(root_path), "path": str(candidate)},
        )
    return candidate
