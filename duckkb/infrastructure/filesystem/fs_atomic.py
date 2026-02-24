from __future__ import annotations

import os
from pathlib import Path


def read_jsonl_lines(file_path: str) -> list[str]:
    path = Path(file_path)
    if not path.exists():
        return []
    return [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines()]


def write_jsonl_atomic(file_path: str, lines: list[str]) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    data = "".join(line.rstrip("\n") + "\n" for line in lines)
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def replace_file_atomic(src: str, dst: str) -> None:
    dst_path = Path(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dst)
