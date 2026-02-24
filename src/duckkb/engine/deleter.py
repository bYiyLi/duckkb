"""文档删除模块。

本模块处理知识库中文档的删除操作，确保数据库和文件系统的一致性。
"""

import asyncio

from duckkb.constants import SYS_SEARCH_TABLE, validate_table_name
from duckkb.db import get_db


def delete_records_from_db(table_name: str, ids: list[str]) -> None:
    """从数据库中删除指定 ID 的记录。

    Args:
        table_name: 表名。
        ids: 要删除的记录 ID 列表。
    """
    if not ids:
        return
    with get_db(read_only=False) as conn:
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"DELETE FROM {SYS_SEARCH_TABLE} WHERE source_table = ? AND ref_id IN ({placeholders})",
            [table_name, *ids],
        )


async def delete_documents(table_name: str, doc_ids: list[str]) -> dict:
    """从知识库中删除指定文档。

    Args:
        table_name: 表名。
        doc_ids: 要删除的文档 ID 列表。

    Returns:
        包含操作结果统计的字典。
    """
    from duckkb.engine.sync import sync_db_to_file

    validate_table_name(table_name)
    if not doc_ids:
        return {"status": "success", "count": 0}

    count = len(doc_ids)
    await asyncio.to_thread(delete_records_from_db, table_name, doc_ids)

    await sync_db_to_file(table_name)

    return {
        "status": "success",
        "table_name": table_name,
        "deleted_count": count,
        "message": f"Successfully deleted {count} records",
    }
