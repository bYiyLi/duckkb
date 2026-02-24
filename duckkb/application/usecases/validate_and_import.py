from __future__ import annotations

import json
from typing import Any

from duckkb.domain.ports.repository import ImportRepo
from duckkb.types import ErrorEnvelope, ValidateImportResult


def validate_and_import(
    import_repo: ImportRepo,
    table_name: str,
    lines: list[str],
) -> ValidateImportResult:
    errors: list[ErrorEnvelope] = []
    accepted = 0
    for idx, line in enumerate(lines, start=1):
        has_error = False
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(
                ErrorEnvelope(
                    code="invalid_json",
                    message="jsonl 行不是合法 JSON",
                    details={"line": idx, "error": str(exc)},
                )
            )
            has_error = True
            continue
        if not isinstance(record, dict):
            errors.append(
                ErrorEnvelope(
                    code="invalid_record",
                    message="jsonl 行必须是对象",
                    details={"line": idx},
                )
            )
            has_error = True
            continue
        has_error = _validate_required(record, idx, errors) or has_error
        if not has_error:
            accepted += 1

    if errors:
        return ValidateImportResult(accepted=0, errors=errors)

    import_repo.write_table_jsonl(table_name, lines)
    return ValidateImportResult(accepted=accepted, errors=[])


def _validate_required(
    record: dict[str, Any],
    line: int,
    errors: list[ErrorEnvelope],
) -> bool:
    has_error = False
    if "id" not in record or not isinstance(record["id"], str) or not record["id"]:
        errors.append(
            ErrorEnvelope(
                code="missing_id",
                message="记录缺少 id",
                details={
                    "line": line,
                    "field": "id",
                    "expected": "non-empty string",
                    "actual": record.get("id"),
                },
            )
        )
        has_error = True
    if "priority_weight" in record:
        value = record["priority_weight"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(
                ErrorEnvelope(
                    code="invalid_priority_weight",
                    message="priority_weight 必须是数字",
                    details={
                        "line": line,
                        "field": "priority_weight",
                        "expected": "number",
                        "actual": value,
                    },
                )
            )
            has_error = True
    return has_error
