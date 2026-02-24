"""负责将文件系统中的数据同步到数据库 (File -> DB)。"""

import asyncio
from pathlib import Path
from typing import Any

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
from duckkb.database.connection import get_db
from duckkb.database.engine.cache import clean_cache
from duckkb.exceptions import InvalidTableNameError
from duckkb.logger import logger
from duckkb.database.engine.ontology import OntologyEngine
from duckkb.utils.embedding import get_embeddings
from duckkb.utils.file_ops import (
    dir_exists,
    file_exists,
    get_file_stat,
    glob_files,
    mkdir,
    read_file,
    write_file,
)
from duckkb.utils.text import compute_text_hash, segment_text


class DataLoader:
    def __init__(self, kb_path: Path):
        self.kb_path = kb_path

    async def sync_files_to_db(self) -> None:
        """将知识库从 JSONL 文件同步到 DuckDB 数据库。

        采用增量同步策略：
        1. 读取文件中的所有记录。
        2. 对比数据库中的现有记录。
        3. 仅对新增、修改或删除的记录执行数据库操作。
        """
        segment_text("")  # 预热分词器

        data_dir = self.kb_path / DATA_DIR_NAME
        if not await dir_exists(data_dir):
            logger.warning(f"Data directory {data_dir} does not exist.")
            return

        # 加载同步状态（仅用于跳过完全未修改的文件，优化性能）
        state_file = self.kb_path / BUILD_DIR_NAME / SYNC_STATE_FILE
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
                await self._process_file(file_path, table_name, ontology_engine)
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

    async def _process_file(
        self, file_path: Path, table_name: str, ontology_engine: OntologyEngine
    ) -> None:
        """处理单个文件的同步逻辑。"""
        # 1. 读取并解析文件
        try:
            file_records = await self._read_and_parse(file_path)
        except Exception as e:
            raise ValueError(f"Failed to read {file_path}: {e}") from e

        # 2. 获取 DB 状态
        db_state = await asyncio.to_thread(self._get_db_state, table_name)

        # 3. 获取向量字段配置
        node_type = ontology_engine.get_node_by_table(table_name)
        fields_to_embed: set[str] | None = None
        if node_type and node_type.vectors:
            fields_to_embed = set(node_type.vectors.keys())

        # 4. 计算 Diff
        to_upsert_records, to_delete_ids = self._compute_diff(
            file_records, db_state, fields_to_embed
        )

        # 5. 执行更新
        if not to_delete_ids and not to_upsert_records:
            logger.info(f"Table {table_name} is up to date.")
            return

        logger.info(
            f"Diff for {table_name}: {len(to_upsert_records)} to upsert, {len(to_delete_ids)} to delete."
        )

        # 5. 执行更新（事务包装）
        if to_delete_ids or to_upsert_records:
            await self._execute_update_with_transaction(
                table_name, to_delete_ids, to_upsert_records, fields_to_embed
            )

    async def _read_and_parse(self, file_path: Path) -> list[dict]:
        """异步读取并解析 JSONL 文件。"""
        content = await read_file(file_path)
        records = []
        for line in content.splitlines():
            if not line.strip():
                continue
            records.append(orjson.loads(line))
        return records

    def _get_db_state(self, table_name: str) -> dict[str, dict[str, str]]:
        """获取数据库中某表的现有状态。"""
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

    def _compute_diff(
        self,
        file_records: list[dict],
        db_state: dict[str, dict[str, str]],
        fields_to_embed: set[str] | None,
    ) -> tuple[list[dict], set[str]]:
        """计算需要 Upsert 的记录和需要删除的 ID。"""
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

    async def _execute_update_with_transaction(
        self,
        table_name: str,
        to_delete_ids: set[str],
        to_upsert_records: list[dict],
        fields_to_embed: set[str] | None,
    ) -> None:
        """在事务中执行删除和插入操作。"""
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

        rows_to_insert = await self._prepare_rows_for_insert(
            table_name, to_upsert_records, fields_to_embed
        )

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

                    if rows_to_insert:
                        conn.executemany(
                            f"INSERT INTO {SYS_SEARCH_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            rows_to_insert,
                        )

                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

        await asyncio.to_thread(_do_update)

    async def _prepare_rows_for_insert(
        self,
        table_name: str,
        records: list[dict],
        fields_to_embed: set[str] | None,
    ) -> list[SearchRow]:
        """生成要插入的行数据（包括 embedding）。"""
        embedding_requests = []

        for i, record in enumerate(records):
            for key, value in record.items():
                if isinstance(value, str) and value.strip():
                    if fields_to_embed is not None and key not in fields_to_embed:
                        continue
                    embedding_requests.append((i, key, value))

        if not embedding_requests:
            return []

        texts_to_embed = [req[2] for req in embedding_requests]

        embeddings = await self._generate_embeddings(texts_to_embed)
        if not embeddings:
            return []

        loop = asyncio.get_running_loop()
        try:
            segmented_texts = await asyncio.gather(
                *[loop.run_in_executor(None, segment_text, text) for text in texts_to_embed]
            )
        except Exception as e:
            logger.error(f"Failed to segment text: {e}")
            return []

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

        return rows_to_insert

    async def _generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """生成文本的 Embeddings。"""
        try:
            return await get_embeddings(texts)
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            return []
