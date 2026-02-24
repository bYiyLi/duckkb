"""知识库同步模块。"""

import asyncio
from pathlib import Path

import orjson

from duckkb.config import AppContext
from duckkb.constants import (
    BUILD_DIR_NAME,
    DATA_DIR_NAME,
    SYNC_STATE_FILE,
    SYS_SEARCH_TABLE,
    SearchRow,
    validate_table_name,
)
from duckkb.db import get_db
from duckkb.engine.cache import clean_cache
from duckkb.engine.deleter import delete_records_from_db
from duckkb.exceptions import InvalidTableNameError
from duckkb.logger import logger
from duckkb.ontology import OntologyEngine
from duckkb.utils.embedding import get_embeddings
from duckkb.utils.file_ops import (
    atomic_write_file,
    dir_exists,
    file_exists,
    get_file_stat,
    glob_files,
    mkdir,
    read_file,
    write_file,
)
from duckkb.utils.text import compute_text_hash, segment_text


def get_all_table_names() -> list[str]:
    """获取数据库中所有用户表名。

    Returns:
        包含所有表名的列表（从 _sys_search 表中提取）。
    """
    with get_db(read_only=True) as conn:
        rows = conn.execute(f"SELECT DISTINCT source_table FROM {SYS_SEARCH_TABLE}").fetchall()
    return [row[0] for row in rows]


async def persist_all_tables(kb_path: Path | None = None) -> dict[str, int]:
    """将所有数据库表持久化到 JSONL 文件。

    Args:
        kb_path: 知识库路径，如果为 None 则从 AppContext 获取。

    Returns:
        包含每个表记录数的字典。
    """
    if kb_path is None:
        kb_path = AppContext.get().kb_path

    table_names = await asyncio.to_thread(get_all_table_names)
    results: dict[str, int] = {}

    for table_name in table_names:
        try:
            records = await asyncio.to_thread(_fetch_table_records, table_name)
            results[table_name] = len(records)

            target_path = kb_path / DATA_DIR_NAME / f"{table_name}.jsonl"
            lines = [orjson.dumps(r).decode("utf-8") for r in records]
            content = "\n".join(lines)
            if content:
                content += "\n"

            await atomic_write_file(target_path, content)
            logger.info(f"Persisted table {table_name}: {len(records)} records")
        except Exception as e:
            logger.error(f"Failed to persist table {table_name}: {e}")
            results[table_name] = -1

    state_file = kb_path / BUILD_DIR_NAME / SYNC_STATE_FILE
    if await file_exists(state_file):
        try:
            await write_file(state_file, "{}")
        except Exception as e:
            logger.warning(f"Failed to reset sync state file: {e}")

    return results


async def sync_knowledge_base(kb_path: Path) -> None:
    """将知识库从 JSONL 文件同步到 DuckDB 数据库。

    采用增量同步策略：
    1. 读取文件中的所有记录。
    2. 对比数据库中的现有记录。
    3. 仅对新增、修改或删除的记录执行数据库操作。

    Args:
        kb_path: 知识库根目录路径。
    """
    segment_text("")  # 预热分词器

    data_dir = kb_path / DATA_DIR_NAME
    if not await dir_exists(data_dir):
        logger.warning(f"Data directory {data_dir} does not exist.")
        return

    # 加载同步状态（仅用于跳过完全未修改的文件，优化性能）
    state_file = kb_path / BUILD_DIR_NAME / SYNC_STATE_FILE
    sync_state = {}
    if await file_exists(state_file):
        try:
            sync_state_content = await read_file(state_file)
            sync_state = orjson.loads(sync_state_content)
        except (orjson.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load sync state, resetting: {e}")

    file_pattern = str(data_dir / "*.jsonl")
    matched_files = await glob_files(file_pattern)

    # Initialize OntologyEngine
    ontology_engine = OntologyEngine(AppContext.get().kb_config.ontology)

    for file_path_str in matched_files:
        file_path = Path(file_path_str)
        table_name = file_path.stem
        try:
            validate_table_name(table_name)
        except InvalidTableNameError as e:
            logger.error(f"Invalid table name: {e}")
            continue

        file_stat = await get_file_stat(file_path)
        mtime = file_stat.st_mtime

        # 如果文件 mtime 没变，且我们信任 mtime，可以跳过
        if sync_state.get(table_name) == mtime:
            logger.debug(f"Skipping {table_name}, up to date (mtime check).")
            continue

        logger.info(f"Syncing table {table_name}...")

        try:
            await _process_file(file_path, table_name, ontology_engine)
            sync_state[table_name] = mtime
        except Exception as e:
            logger.error(f"Failed to sync {table_name}: {e}")

    # 保存同步状态
    if not await dir_exists(state_file.parent):
        await mkdir(state_file.parent, parents=True, exist_ok=True)

    await write_file(state_file, orjson.dumps(sync_state).decode("utf-8"))

    # 重建 FTS 索引
    try:
        with get_db(read_only=False) as conn:
            conn.execute(
                f"PRAGMA create_fts_index('{SYS_SEARCH_TABLE}', 'rowid', 'segmented_text')"
            )
    except Exception as e:
        logger.warning(f"FTS index creation/refresh failed: {e}")

    await clean_cache()


async def sync_db_to_file(table_name: str, kb_path: Path | None = None) -> None:
    """将数据库中的数据回写到 JSONL 文件。

    Args:
        table_name: 表名。
        kb_path: 知识库路径，如果为 None 则从 AppContext 获取。
    """
    # 避免循环导入，运行时导入 AppContext
    if kb_path is None:
        kb_path = AppContext.get().kb_path

    target_path = kb_path / DATA_DIR_NAME / f"{table_name}.jsonl"

    try:
        records = await asyncio.to_thread(_fetch_table_records, table_name)

        # Write records atomically using helper
        lines = [orjson.dumps(r).decode("utf-8") for r in records]
        content = "\n".join(lines)
        if content:
            content += "\n"

        await atomic_write_file(target_path, content)

        logger.info(f"Synced DB to file: {target_path} ({len(records)} records)")

        # 更新同步状态，防止下次启动时误判为文件变更
        state_file = kb_path / BUILD_DIR_NAME / SYNC_STATE_FILE
        if await file_exists(state_file):
            try:
                sync_state_content = await read_file(state_file)
                sync_state = orjson.loads(sync_state_content)

                file_stat = await get_file_stat(target_path)
                sync_state[table_name] = file_stat.st_mtime

                await write_file(state_file, orjson.dumps(sync_state).decode("utf-8"))
            except Exception as e:
                logger.warning(f"Failed to update sync state: {e}")

    except Exception as e:
        logger.error(f"Failed to sync DB to file for {table_name}: {e}")


def _fetch_table_records(table_name: str) -> list[dict]:
    """从数据库获取指定表的所有记录（通过 metadata 重组）。

    Args:
        table_name: 表名。

    Returns:
        包含所有记录的列表，每个记录为一个字典。
    """
    with get_db(read_only=True) as conn:
        # DISTINCT ref_id to avoid duplicates from multiple fields
        # But we need the metadata. Metadata is stored per row (per field).
        # Assuming metadata is identical for all fields of the same record.
        # We group by ref_id and take the first metadata.
        rows = conn.execute(
            f"SELECT metadata FROM {SYS_SEARCH_TABLE} WHERE source_table = ? GROUP BY ref_id, metadata",
            [table_name],
        ).fetchall()

    records = []
    for (metadata_json,) in rows:
        if isinstance(metadata_json, str):
            try:
                records.append(orjson.loads(metadata_json))
            except orjson.JSONDecodeError:
                pass
        elif isinstance(metadata_json, dict):  # DuckDB distinct might return dict?
            records.append(metadata_json)
    return records


async def _process_file(file_path: Path, table_name: str, ontology_engine: OntologyEngine) -> None:
    """处理单个文件的同步逻辑。

    包括读取、解析、生成 Embedding、计算差异并更新数据库。

    Args:
        file_path: JSONL 文件路径。
        table_name: 对应的表名。
        ontology_engine: 本体引擎实例。

    Raises:
        ValueError: 如果文件读取失败。
    """
    # 1. 读取并解析文件
    try:
        file_records = await _read_and_parse(file_path)
    except Exception as e:
        raise ValueError(f"Failed to read {file_path}: {e}") from e

    # 2. 获取 DB 状态
    db_state = await asyncio.to_thread(_get_db_state, table_name)

    # 3. 获取向量字段配置
    node_type = ontology_engine.get_node_by_table(table_name)
    fields_to_embed: set[str] | None = None
    if node_type and node_type.vectors:
        fields_to_embed = set(node_type.vectors.keys())

    # 4. 计算 Diff
    to_upsert_records, to_delete_ids = _compute_diff(file_records, db_state, fields_to_embed)

    # 5. 执行更新
    if not to_delete_ids and not to_upsert_records:
        logger.info(f"Table {table_name} is up to date.")
        return

    logger.info(
        f"Diff for {table_name}: {len(to_upsert_records)} to upsert, {len(to_delete_ids)} to delete."
    )

    # 5. 执行更新（事务包装）
    if to_delete_ids or to_upsert_records:
        await _execute_update_with_transaction(
            table_name, to_delete_ids, to_upsert_records, fields_to_embed
        )


def _compute_diff(
    file_records: list[dict],
    db_state: dict[str, dict[str, str]],
    fields_to_embed: set[str] | None,
) -> tuple[list[dict], set[str]]:
    """计算需要 Upsert 的记录和需要删除的 ID。

    Args:
        file_records: 文件中的记录列表。
        db_state: 数据库中的状态 {ref_id: {field: embedding_hash}}。
        fields_to_embed: 需要嵌入的字段集合。如果为 None，则嵌入所有非空字符串字段。

    Returns:
        (to_upsert_records, to_delete_ids)
    """
    file_map = {str(r.get("id", "")): r for r in file_records if r.get("id")}
    to_delete_ids = set(db_state.keys()) - set(file_map.keys())
    to_upsert_records = []

    for ref_id, record in file_map.items():
        if ref_id not in db_state:
            to_upsert_records.append(record)
            continue

        # 检查内容是否变更
        db_field_hashes = db_state[ref_id]
        current_field_hashes = {}

        for key, value in record.items():
            if not isinstance(value, str) or not value.strip():
                continue

            # 如果定义了向量字段，则只检查这些字段
            if fields_to_embed is not None and key not in fields_to_embed:
                continue

            current_field_hashes[key] = compute_text_hash(value)

        if current_field_hashes != db_field_hashes:
            to_upsert_records.append(record)
            # 标记删除旧记录（为了重新插入）
            to_delete_ids.add(ref_id)

    return to_upsert_records, to_delete_ids


async def _read_and_parse(file_path: Path) -> list[dict]:
    """异步读取并解析 JSONL 文件。

    Args:
        file_path: 文件路径。

    Returns:
        解析后的记录列表。
    """
    content = await read_file(file_path)
    records = []
    for line in content.splitlines():
        if not line.strip():
            continue
        records.append(orjson.loads(line))
    return records


def _get_db_state(table_name: str) -> dict[str, dict[str, str]]:
    """获取数据库中某表的现有状态。

    Args:
        table_name: 表名。

    Returns:
        状态字典，格式为 {ref_id: {source_field: embedding_id}}。
    """
    with get_db(read_only=True) as conn:
        rows = conn.execute(
            f"SELECT ref_id, source_field, embedding_id FROM {SYS_SEARCH_TABLE} WHERE source_table = ?",
            [table_name],
        ).fetchall()

    state: dict[str, dict[str, str]] = {}
    for ref_id, field, emb_id in rows:
        if ref_id not in state:
            state[ref_id] = {}
        state[ref_id][field] = emb_id
    return state


async def _generate_embeddings(texts: list[str]) -> list[list[float]]:
    """生成文本的 Embeddings。

    Args:
        texts: 文本列表。

    Returns:
        Embeddings 列表。
    """
    try:
        return await get_embeddings(texts)
    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        return []


async def _upsert_records(
    table_name: str,
    records: list[dict],
    fields_to_embed: set[str] | None,
) -> None:
    """批量处理新记录：生成 Embedding 并插入。

    Args:
        table_name: 表名。
        records: 要插入的记录列表。
        fields_to_embed: 需要嵌入的字段集合。如果为 None，则嵌入所有非空字符串字段。
    """
    embedding_requests = []

    for i, record in enumerate(records):
        for key, value in record.items():
            if isinstance(value, str) and value.strip():
                if fields_to_embed is not None and key not in fields_to_embed:
                    continue
                embedding_requests.append((i, key, value))

    if not embedding_requests:
        return

    texts_to_embed = [req[2] for req in embedding_requests]

    # 获取 Embeddings
    embeddings = await _generate_embeddings(texts_to_embed)
    if not embeddings:
        return

    # 分词
    loop = asyncio.get_running_loop()
    try:
        segmented_texts = await asyncio.gather(
            *[loop.run_in_executor(None, segment_text, text) for text in texts_to_embed]
        )
    except Exception as e:
        logger.error(f"Failed to segment text: {e}")
        return

    rows_to_insert: list[SearchRow] = []

    for idx, (original_idx, key, text) in enumerate(embedding_requests):
        if idx >= len(embeddings) or not embeddings[idx]:
            continue

        record = records[original_idx]
        ref_id = str(record.get("id", ""))
        embedding_id = compute_text_hash(text)
        metadata_json = orjson.dumps(record).decode("utf-8")

        rows_to_insert.append(
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

    if rows_to_insert:
        await asyncio.to_thread(_bulk_insert_rows, rows_to_insert)


async def _execute_update_with_transaction(
    table_name: str,
    to_delete_ids: set[str],
    to_upsert_records: list[dict],
    fields_to_embed: set[str] | None,
) -> None:
    """在事务中执行删除和插入操作。

    防止并发场景下数据不一致。
    先在事务外生成 embedding，再在事务内执行数据库操作。

    Args:
        table_name: 表名。
        to_delete_ids: 要删除的 ID 集合。
        to_upsert_records: 要插入/更新的记录列表。
        fields_to_embed: 需要嵌入的字段集合。
    """
    if not to_upsert_records:
        def _do_delete_only() -> None:
            with get_db(read_only=False) as conn:
                conn.begin()
                try:
                    if to_delete_ids:
                        placeholders = ",".join("?" * len(to_delete_ids))
                        conn.execute(
                            f"DELETE FROM {SYS_SEARCH_TABLE} WHERE source_table = ? AND ref_id IN ({placeholders})",
                            [table_name, *to_delete_ids],
                        )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        await asyncio.to_thread(_do_delete_only)
        return

    await _upsert_records(table_name, to_upsert_records, fields_to_embed)

    def _do_update() -> None:
        with get_db(read_only=False) as conn:
            conn.begin()
            try:
                if to_delete_ids:
                    placeholders = ",".join("?" * len(to_delete_ids))
                    conn.execute(
                        f"DELETE FROM {SYS_SEARCH_TABLE} WHERE source_table = ? AND ref_id IN ({placeholders})",
                        [table_name, *to_delete_ids],
                    )

                if to_upsert_records:
                    _upsert_records_sync(conn, table_name, to_upsert_records, fields_to_embed)

                conn.commit()
            except Exception:
                conn.rollback()
                raise

    await asyncio.to_thread(_do_update)


def _upsert_records_sync(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    records: list[dict],
    fields_to_embed: set[str] | None,
) -> None:
    """同步版本：批量插入记录。

    Args:
        conn: 数据库连接。
        table_name: 表名。
        records: 要插入的记录列表。
        fields_to_embed: 需要嵌入的字段集合。
    """
    rows_to_insert: list[SearchRow] = []

    for record in records:
        for key, value in record.items():
            if isinstance(value, str) and value.strip():
                if fields_to_embed is not None and key not in fields_to_embed:
                    continue

                ref_id = str(record.get("id", ""))
                embedding_id = compute_text_hash(value)

                rows_to_insert.append(
                    (
                        ref_id,
                        table_name,
                        key,
                        "",
                        embedding_id,
                        [],
                        orjson.dumps(record).decode("utf-8"),
                        1.0,
                    )
                )

    if rows_to_insert:
        conn.executemany(
            f"INSERT INTO {SYS_SEARCH_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows_to_insert
        )


def _bulk_insert_rows(rows: list[SearchRow]) -> None:
    """批量插入行到数据库。

    使用事务包装以提高性能。

    Args:
        rows: 要插入的行数据列表。
    """
    with get_db(read_only=False) as conn:
        conn.begin()
        try:
            conn.executemany(
                f"INSERT INTO {SYS_SEARCH_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
