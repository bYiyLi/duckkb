from __future__ import annotations

from typing import Callable

from duckkb.types import SqlQueryResult


def query_raw_sql(
    sql: str,
    guard: Callable[[str], str],
    executor: Callable[[str], tuple[list[str], list[list[object]]]],
    max_bytes: int,
) -> SqlQueryResult:
    safe_sql = guard(sql)
    columns, rows = executor(safe_sql)
    truncated = False
    if max_bytes > 0:
        size = _payload_size(columns, rows)
        while size > max_bytes and rows:
            truncated = True
            rows = rows[: max(0, int(len(rows) * 0.5))]
            size = _payload_size(columns, rows)
    return SqlQueryResult(columns=columns, rows=rows, truncated=truncated)


def _payload_size(columns: list[str], rows: list[list[object]]) -> int:
    payload = {"columns": columns, "rows": rows}
    return len(str(payload).encode("utf-8"))
