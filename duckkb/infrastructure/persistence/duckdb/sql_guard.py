from __future__ import annotations

import re

from duckkb.domain.errors import DomainError

SELECT_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
LIMIT_RE = re.compile(r"\blimit\b", re.IGNORECASE)
FORBIDDEN_RE = re.compile(
    r"\b(insert|update|delete|create|drop|alter|copy|pragma|attach|detach)\b",
    re.IGNORECASE,
)


def guard_select_only(sql: str, default_limit: int) -> str:
    cleaned = sql.strip().rstrip(";")
    if not SELECT_RE.match(cleaned):
        raise DomainError(
            code="sql_not_allowed",
            message="只允许 SELECT 查询",
            details={"sql": _preview_sql(cleaned)},
        )
    if FORBIDDEN_RE.search(cleaned):
        raise DomainError(
            code="sql_not_allowed",
            message="只允许 SELECT 查询",
            details={"sql": _preview_sql(cleaned)},
        )
    if not LIMIT_RE.search(cleaned):
        cleaned = f"{cleaned} LIMIT {default_limit}"
    return cleaned


def _preview_sql(sql: str) -> str:
    return sql[:200]
