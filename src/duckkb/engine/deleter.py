"""知识库删除模块。"""

import asyncio
from pathlib import Path

import orjson

from duckkb.config import AppContext
from duckkb.constants import BUILD_DIR_NAME, DATA_DIR_NAME, SYS_SEARCH_TABLE
from duckkb.db import get_db
from duckkb.logger import logger


async def delete_records(table_name: str, record_ids: list[str]) -> dict:
    """
    删除指定表中的记录。

    该函数执行完整的删除流程：
    1. 验证表是否存在
    2. 从 JSONL 文件中删除指定记录
    3. 从数据库中删除对应的索引记录
    4. 返回删除统计

    Args:
        table_name: 目标表名（不含 .jsonl 扩展名）。
        record_ids: 要删除的记录 ID 列表。

    Returns:
        包含删除统计的字典。

    Raises:
        FileNotFoundError: 表不存在。
        ValueError: 参数验证失败。
    """
    if not table_name:
        raise ValueError("table_name is required")
    if not record_ids:
        raise ValueError("record_ids is required and cannot be empty")

    kb_path = AppContext.get().kb_path
    target_path = kb_path / DATA_DIR_NAME / f"{table_name}.jsonl"

    if not target_path.exists():
        raise FileNotFoundError(f"Table '{table_name}' does not exist")

    record_ids_set = {str(rid) for rid in record_ids}

    existing_records = await _read_records(target_path)
    existing_id_map = {str(r.get("id", "")): r for r in existing_records}

    deleted_count = 0
    not_found_ids = []

    for rid in record_ids_set:
        if rid in existing_id_map:
            del existing_id_map[rid]
            deleted_count += 1
        else:
            not_found_ids.append(rid)

    remaining_records = list(existing_id_map.values())
    await _write_records_atomic(target_path, remaining_records)

    await _delete_from_search_table(table_name, record_ids_set)

    logger.info(f"Deleted {deleted_count} records from {table_name}")

    result = {
        "status": "success",
        "table_name": table_name,
        "deleted_count": deleted_count,
        "not_found_ids": not_found_ids,
        "remaining_count": len(remaining_records),
        "message": f"Deleted {deleted_count} records from {table_name}",
    }
    return result


async def drop_table(table_name: str, confirm: bool = False) -> dict:
    """
    删除整个表（数据文件 + 数据库记录）。

    Args:
        table_name: 要删除的表名。
        confirm: 确认删除，必须为 True。

    Returns:
        操作结果字典。

    Raises:
        ValueError: 未确认删除或参数无效。
        FileNotFoundError: 表不存在。
    """
    if not confirm:
        raise ValueError("Must set confirm=True to drop table")
    if not table_name:
        raise ValueError("table_name is required")

    kb_path = AppContext.get().kb_path
    target_path = kb_path / DATA_DIR_NAME / f"{table_name}.jsonl"

    if not target_path.exists():
        raise FileNotFoundError(f"Table '{table_name}' does not exist")

    try:
        await asyncio.to_thread(target_path.unlink)
    except Exception as e:
        raise OSError(f"Failed to delete file {target_path}: {e}") from e

    await _delete_table_from_search_table(table_name)

    state_file = kb_path / BUILD_DIR_NAME / "sync_state.json"
    if state_file.exists():
        try:
            state_content = await asyncio.to_thread(state_file.read_bytes)
            state = orjson.loads(state_content)
            if table_name in state:
                del state[table_name]
                await asyncio.to_thread(state_file.write_bytes, orjson.dumps(state))
        except Exception as e:
            logger.warning(f"Failed to update sync state: {e}")

    logger.info(f"Dropped table {table_name}")

    return {
        "status": "success",
        "table_name": table_name,
        "message": f"Table '{table_name}' dropped successfully",
    }


async def _read_records(file_path: Path) -> list[dict]:
    """
    读取 JSONL 文件中的所有记录。

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
        logger.warning(f"Failed to read records: {e}")
        return []


async def _write_records_atomic(file_path: Path, records: list[dict]) -> None:
    """
    原子写入记录到 JSONL 文件。

    Args:
        file_path: 目标文件路径。
        records: 要写入的记录列表。
    """
    if not records:
        staging_path = file_path.with_suffix(".jsonl.staging")
        await asyncio.to_thread(staging_path.write_bytes, b"")
        staging_path.replace(file_path)
        return

    lines = [orjson.dumps(record) for record in records]
    content = b"\n".join(lines) + b"\n"

    staging_path = file_path.with_suffix(".jsonl.staging")
    await asyncio.to_thread(staging_path.write_bytes, content)
    staging_path.replace(file_path)


async def _delete_from_search_table(table_name: str, record_ids: set[str]) -> None:
    """
    从搜索表中删除指定记录。

    Args:
        table_name: 表名。
        record_ids: 要删除的记录 ID 集合。
    """
    if not record_ids:
        return

    try:
        placeholders = ",".join("?" * len(record_ids))
        sql = (
            f"DELETE FROM {SYS_SEARCH_TABLE} WHERE source_table = ? AND ref_id IN ({placeholders})"
        )
        params = [table_name] + list(record_ids)

        await asyncio.to_thread(_execute_delete, sql, params)
    except Exception as e:
        logger.warning(f"Failed to delete from search table: {e}")


async def _delete_table_from_search_table(table_name: str) -> None:
    """
    从搜索表中删除指定表的所有记录。

    Args:
        table_name: 表名。
    """
    try:
        sql = f"DELETE FROM {SYS_SEARCH_TABLE} WHERE source_table = ?"
        await asyncio.to_thread(_execute_delete, sql, [table_name])
    except Exception as e:
        logger.warning(f"Failed to delete table from search table: {e}")


def _execute_delete(sql: str, params: list) -> None:
    """
    执行删除 SQL。

    Args:
        sql: SQL 语句。
        params: 参数列表。
    """
    with get_db(read_only=False) as conn:
        conn.execute(sql, params)
