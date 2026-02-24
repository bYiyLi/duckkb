"""知识库导入模块。"""

import asyncio
from pathlib import Path

import orjson

from duckkb.config import AppContext
from duckkb.constants import DATA_DIR_NAME, MAX_ERROR_FEEDBACK, validate_table_name
from duckkb.engine.sync import sync_knowledge_base
from duckkb.exceptions import ValidationError
from duckkb.logger import logger


async def validate_and_import(table_name: str, temp_file_path: Path) -> str:
    """
    验证临时文件并将其导入到知识库数据目录（upsert 语义）。

    该函数执行完整的导入流程：
    1. 验证 JSONL 文件格式和必需字段
    2. 如果表存在，基于 id 进行 upsert（更新已存在，插入新记录）
    3. 如果表不存在，创建新表
    4. 使用原子写入确保数据完整性
    5. 触发知识库同步

    Args:
        table_name: 目标表名（不含 .jsonl 扩展名）。
        temp_file_path: 临时 JSONL 文件的路径。

    Returns:
        操作结果消息，包含更新/插入统计。

    Raises:
        FileNotFoundError: 临时文件不存在。
        ValidationError: 文件格式验证失败，包含详细错误信息。
        OSError: 文件写入失败。
    """
    validate_table_name(table_name)

    if not temp_file_path.exists():
        raise FileNotFoundError(f"File {temp_file_path} not found")

    errors = []
    new_records: list[dict] = []

    try:
        content = await asyncio.to_thread(temp_file_path.read_bytes)
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                record = orjson.loads(line)
                if not isinstance(record, dict):
                    errors.append(f"Line {i}: Record must be a JSON object")
                    continue

                if "id" not in record:
                    errors.append(f"Line {i}: Missing required field 'id'")
                    continue

                new_records.append(record)

            except orjson.JSONDecodeError:
                errors.append(f"Line {i}: Invalid JSON format")

    except Exception as e:
        raise ValidationError(f"Failed to read file: {e}") from e

    if errors:
        error_msg = f"Found {len(errors)} errors:\n" + "\n".join(errors[:MAX_ERROR_FEEDBACK])
        if len(errors) > MAX_ERROR_FEEDBACK:
            error_msg += "\n..."
        raise ValidationError(error_msg)

    if not new_records:
        try:
            temp_file_path.unlink()
        except OSError as e:
            logger.debug(f"Failed to remove temp file {temp_file_path}: {e}")
        return "No valid records to import"

    kb_path = AppContext.get().kb_path
    target_path = kb_path / DATA_DIR_NAME / f"{table_name}.jsonl"
    target_path.parent.mkdir(parents=True, exist_ok=True)

    updated_count = 0
    inserted_count = 0

    try:
        if not target_path.exists():
            staging_path = target_path.with_suffix(".jsonl.staging")
            await asyncio.to_thread(staging_path.write_bytes, content)
            staging_path.replace(target_path)
            inserted_count = len(new_records)
        else:
            existing_records = await _read_existing_records(target_path)
            existing_ids = {str(r.get("id", "")): r for r in existing_records}

            new_ids_set = set()
            for record in new_records:
                record_id = str(record.get("id", ""))
                if record_id in existing_ids:
                    updated_count += 1
                else:
                    inserted_count += 1
                new_ids_set.add(record_id)

            for record in new_records:
                record_id = str(record.get("id", ""))
                existing_ids[record_id] = record

            final_records = list(existing_ids.values())
            await _write_records_atomic(target_path, final_records)

        try:
            temp_file_path.unlink()
        except OSError as e:
            logger.debug(f"Failed to remove temp file {temp_file_path}: {e}")

    except Exception as e:
        raise OSError(f"Failed to write to {target_path}: {e}") from e

    total_records = updated_count + inserted_count
    logger.info(
        f"Upserted {table_name}: {updated_count} updated, {inserted_count} inserted, triggering sync..."
    )
    await sync_knowledge_base(kb_path)

    result = {
        "status": "success",
        "table_name": table_name,
        "total_records": total_records,
        "updated_count": updated_count,
        "inserted_count": inserted_count,
        "message": f"Upserted {total_records} records to {table_name} ({updated_count} updated, {inserted_count} inserted)",
    }
    return orjson.dumps(result).decode("utf-8")


async def _read_existing_records(file_path: Path) -> list[dict]:
    """
    读取现有 JSONL 文件中的所有记录。

    Args:
        file_path: JSONL 文件路径。

    Returns:
        记录列表。
    """
    try:
        content = await asyncio.to_thread(file_path.read_bytes)
        records = []
        for line in content.splitlines():
            if line.strip():
                records.append(orjson.loads(line))
        return records
    except Exception as e:
        logger.warning(f"Failed to read existing records: {e}")
        return []


async def _write_records_atomic(file_path: Path, records: list[dict]) -> None:
    """
    原子写入记录到 JSONL 文件。

    Args:
        file_path: 目标文件路径。
        records: 要写入的记录列表。
    """
    lines = [orjson.dumps(record) for record in records]
    content = b"\n".join(lines)
    if content:
        content += b"\n"

    staging_path = file_path.with_suffix(".jsonl.staging")
    await asyncio.to_thread(staging_path.write_bytes, content)
    staging_path.replace(file_path)
