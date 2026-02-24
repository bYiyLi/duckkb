"""知识库同步模块。"""

import asyncio
from pathlib import Path

import orjson

from duckkb.constants import BUILD_DIR_NAME, DATA_DIR_NAME, SYS_SEARCH_TABLE
from duckkb.db import get_db
from duckkb.engine.cache import clean_cache
from duckkb.logger import logger
from duckkb.utils.embedding import get_embeddings
from duckkb.utils.text import compute_text_hash, segment_text

SYNC_STATE_FILE = "sync_state.json"


async def sync_knowledge_base(kb_path: Path):
    """
    将知识库从 JSONL 文件同步到 DuckDB 数据库。

    该函数是知识库索引的主入口，负责检测文件变更、处理新增/修改的数据、
    生成向量嵌入并构建全文搜索索引。采用增量同步策略，仅处理有变更的文件。

    Args:
        kb_path: 知识库根目录路径，应包含 data/ 和 build/ 子目录。
    """
    segment_text("")

    data_dir = kb_path / DATA_DIR_NAME
    if not data_dir.exists():
        logger.warning(f"Data directory {data_dir} does not exist.")
        return

    state_file = kb_path / BUILD_DIR_NAME / SYNC_STATE_FILE
    sync_state = {}
    if state_file.exists():
        try:
            sync_state = orjson.loads(state_file.read_bytes())
        except (orjson.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load sync state, resetting: {e}")

    for file_path in data_dir.glob("*.jsonl"):
        table_name = file_path.stem
        mtime = file_path.stat().st_mtime

        if sync_state.get(table_name) == mtime:
            logger.debug(f"Skipping {table_name}, up to date.")
            continue

        logger.info(f"Syncing table {table_name}...")

        try:
            await _process_file(file_path, table_name)
            sync_state[table_name] = mtime
        except Exception as e:
            logger.error(f"Failed to sync {table_name}: {e}")

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_bytes(orjson.dumps(sync_state))

    try:
        with get_db(read_only=False) as conn:
            conn.execute(
                f"PRAGMA create_fts_index('{SYS_SEARCH_TABLE}', 'rowid', 'segmented_text')"
            )
    except Exception as e:
        logger.warning(f"FTS index creation/refresh failed: {e}")

    await clean_cache()


def _read_records(file_path: Path) -> list[dict]:
    """读取并解析 JSONL 文件。"""
    records = []
    try:
        content = file_path.read_bytes()
        for line in content.splitlines():
            if not line.strip():
                continue
            records.append(orjson.loads(line))
    except Exception as e:
        raise ValueError(f"Failed to parse {file_path}: {e}") from e
    return records


async def _process_file(file_path: Path, table_name: str):
    """处理单个 JSONL 文件，生成向量嵌入并写入数据库。"""
    try:
        records = await asyncio.to_thread(_read_records, file_path)
    except Exception as e:
        raise ValueError(f"Failed to read {file_path}: {e}") from e

    embedding_requests = []

    for i, record in enumerate(records):
        ref_id = str(record.get("id", ""))
        if not ref_id:
            continue

        for key, value in record.items():
            if isinstance(value, str) and value.strip():
                embedding_requests.append((i, key, value))

    if not embedding_requests:
        return

    texts_to_embed = [req[2] for req in embedding_requests]

    try:
        embeddings = await get_embeddings(texts_to_embed)
    except Exception as e:
        logger.error(f"Failed to get embeddings for {table_name}: {e}")
        return

    loop = asyncio.get_running_loop()
    try:
        segmented_texts = await asyncio.gather(
            *[loop.run_in_executor(None, segment_text, text) for text in texts_to_embed]
        )
    except Exception as e:
        logger.error(f"Failed to segment text: {e}")
        return

    rows_to_insert: list[tuple] = []

    for idx, (original_idx, key, text) in enumerate(embedding_requests):
        record = records[original_idx]
        ref_id = str(record.get("id", ""))

        if idx >= len(embeddings) or not embeddings[idx]:
            continue

        embedding_id = compute_text_hash(text)
        metadata_json = orjson.dumps(record).decode("utf-8")

        rows_to_insert.append(
            (
                ref_id,
                table_name,
                key,
                segmented_texts[idx],
                embedding_id,
                metadata_json,
                1.0,
            )
        )

    if rows_to_insert:
        await asyncio.to_thread(_bulk_insert, table_name, rows_to_insert)


def _bulk_insert(table_name: str, rows: list[tuple[str, str, str, str, str, str, float]]):
    """批量插入数据到搜索表。"""
    with get_db(read_only=False) as conn:
        conn.execute("BEGIN TRANSACTION")
        try:
            conn.execute(f"DELETE FROM {SYS_SEARCH_TABLE} WHERE source_table = ?", [table_name])
            conn.executemany(f"INSERT INTO {SYS_SEARCH_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
            conn.execute("COMMIT")
            logger.info(f"Inserted {len(rows)} rows for {table_name}")
        except Exception as e:
            conn.execute("ROLLBACK")
            raise e
