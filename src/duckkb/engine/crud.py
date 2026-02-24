"""CRUD 引擎模块。

提供直接操作数据库的增删改查接口，并自动处理数据回写。
"""

import asyncio

import orjson

from duckkb.constants import SYS_SEARCH_TABLE, validate_table_name
from duckkb.db import get_db
from duckkb.engine.deleter import delete_records_from_db
from duckkb.engine.sync import sync_db_to_file
from duckkb.logger import logger
from duckkb.utils.embedding import get_embeddings
from duckkb.utils.text import compute_text_hash, segment_text

# (ref_id, source_table, source_field, segmented_text, embedding_id, embedding, metadata, priority_weight)
type SearchRow = tuple[str, str, str, str, str, list[float], str, float]


async def add_documents(table_name: str, records: list[dict], sync_file: bool = True) -> dict:
    """
    添加或更新文档到知识库。

    Args:
        table_name: 表名。
        records: 记录列表，每条记录必须包含 'id' 字段。
        sync_file: 是否同步到文件（默认 True）。批量导入时可设为 False，最后统一同步。

    Returns:
        操作结果统计。
    """
    validate_table_name(table_name)
    if not records:
        return {"status": "success", "upserted_count": 0}

    # 1. 验证 ID
    valid_records = []
    ids_to_update = set()
    for i, r in enumerate(records):
        rid = str(r.get("id", ""))
        if not rid:
            logger.warning(f"Skipping record at index {i}: missing id")
            continue
        valid_records.append(r)
        ids_to_update.add(rid)

    if not valid_records:
        return {"status": "error", "message": "No valid records with IDs"}

    # 2. 先删除旧版本（实现 Upsert）
    # 必须先删除，因为新记录可能有不同的字段，或者字段内容变了导致 embedding 变了
    await asyncio.to_thread(delete_records_from_db, table_name, list(ids_to_update))

    # 3. 准备插入数据
    embedding_requests = []
    for i, record in enumerate(valid_records):
        for key, value in record.items():
            if isinstance(value, str) and value.strip():
                embedding_requests.append((i, key, value))

    if not embedding_requests:
        # 只有 ID 没有文本字段？也算成功吧，只是没索引
        if sync_file:
            await sync_db_to_file(table_name)
        return {"status": "success", "upserted_count": len(valid_records)}

    texts = [req[2] for req in embedding_requests]

    # 4. 获取 Embedding
    try:
        embeddings = await get_embeddings(texts)
    except Exception as e:
        raise ValueError(f"Failed to generate embeddings: {e}") from e

    # 5. 分词
    loop = asyncio.get_running_loop()
    segmented_texts = await asyncio.gather(
        *[loop.run_in_executor(None, segment_text, t) for t in texts]
    )

    # 6. 构建行
    rows: list[SearchRow] = []
    for idx, (original_idx, key, text) in enumerate(embedding_requests):
        if idx >= len(embeddings) or not embeddings[idx]:
            continue

        record = valid_records[original_idx]
        ref_id = str(record.get("id", ""))
        embedding_id = compute_text_hash(text)
        metadata_json = orjson.dumps(record).decode("utf-8")

        rows.append(
            (
                ref_id,
                table_name,
                key,
                segmented_texts[idx],
                embedding_id,
                embeddings[idx],
                metadata_json,
                1.0,
            )
        )

    # 7. 写入数据库
    if rows:
        await asyncio.to_thread(_insert_rows, rows)

    # 8. 回写文件
    if sync_file:
        await sync_db_to_file(table_name)

    return {
        "status": "success",
        "table_name": table_name,
        "upserted_count": len(valid_records),
        "message": f"Successfully upserted {len(valid_records)} records",
    }


def _insert_rows(rows: list[SearchRow]):
    """批量插入 DB 记录。"""
    with get_db(read_only=False) as conn:
        conn.executemany(f"INSERT INTO {SYS_SEARCH_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
