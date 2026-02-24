"""Deleter module for DuckKB.

This module handles deletion of documents from the knowledge base,
ensuring consistency between the database and the file system.
"""

import asyncio

from duckkb.constants import SYS_SEARCH_TABLE, validate_table_name
from duckkb.db import get_db


def delete_records_from_db(table_name: str, ids: list[str]) -> None:
    """Deletes records from the database by ID.

    Args:
        table_name: The name of the table.
        ids: A list of record IDs to delete.
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
    """
    Deletes specified documents from the knowledge base.

    Args:
        table_name: The name of the table.
        doc_ids: A list of document IDs to delete.

    Returns:
        A dictionary containing the operation result statistics.
    """
    # Local import to avoid circular dependency with sync.py
    from duckkb.engine.sync import sync_db_to_file

    validate_table_name(table_name)
    if not doc_ids:
        return {"status": "success", "count": 0}

    count = len(doc_ids)
    await asyncio.to_thread(delete_records_from_db, table_name, doc_ids)

    # Write changes back to file
    await sync_db_to_file(table_name)

    return {
        "status": "success",
        "table_name": table_name,
        "deleted_count": count,
        "message": f"Successfully deleted {count} records",
    }
