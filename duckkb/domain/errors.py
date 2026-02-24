from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DuckKBError(Exception):
    code: str
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class DomainError(DuckKBError):
    pass


class InfraError(DuckKBError):
    pass


class BugError(DuckKBError):
    pass
