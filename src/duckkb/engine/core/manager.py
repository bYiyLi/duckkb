"""知识库统一管理入口。"""

import asyncio
from pathlib import Path
from typing import Any

import orjson

from duckkb.config import AppContext
from duckkb.constants import SYS_SEARCH_TABLE, SearchRow, validate_table_name
from duckkb.db import get_db
from duckkb.engine.core.loader import DataLoader
from duckkb.engine.core.persister import DataPersister
from duckkb.logger import logger
from duckkb.ontology import OntologyEngine
from duckkb.utils.embedding import get_embeddings
from duckkb.utils.text import compute_text_hash, segment_text


class KnowledgeBaseManager:
    def __init__(self, kb_path: Path):
        self.kb_path = kb_path
        self.loader = DataLoader(kb_path)
        self.persister = DataPersister(kb_path)
        self._save_tasks: dict[str, asyncio.Task] = {}
        # Ontology engine might be needed for embedding fields config
        # We defer initialization to avoid circular import issues if Config is not ready
        self._ontology_engine: OntologyEngine | None = None

    @property
    def ontology_engine(self) -> OntologyEngine:
        if self._ontology_engine is None:
            self._ontology_engine = OntologyEngine(AppContext.get().kb_config.ontology)
        return self._ontology_engine

    async def load_all(self) -> None:
        """启动时调用：File -> DB"""
        await self.loader.sync_files_to_db()

    async def add_documents(self, table_name: str, documents: list[dict]) -> dict[str, Any]:
        """导入数据：Write DB -> Return -> Async Save (Upsert semantics)"""
        validate_table_name(table_name)
        
        # 1. Validate IDs
        valid_records = []
        ids_to_update = set()
        for i, r in enumerate(documents):
            rid = str(r.get("id", ""))
            if not rid:
                logger.warning(f"Skipping record at index {i}: missing id")
                continue
            valid_records.append(r)
            ids_to_update.add(rid)

        if not valid_records:
            return {"status": "error", "message": "No valid records with IDs"}

        # 2. Prepare rows (generate embeddings)
        # Note: This is done BEFORE deleting to ensure we don't delete if embedding fails
        node_type = self.ontology_engine.get_node_by_table(table_name)
        fields_to_embed: set[str] | None = None
        if node_type and node_type.vectors:
            fields_to_embed = set(node_type.vectors.keys())

        try:
            rows_to_insert = await self._prepare_rows_for_insert(
                table_name, valid_records, fields_to_embed
            )
        except Exception as e:
            logger.error(f"Failed to prepare rows for insert: {e}")
            raise

        # 3. Write to DB (Transaction: Delete old + Insert new)
        def _do_upsert():
            with get_db(read_only=False) as conn:
                conn.begin()
                try:
                    # Delete old versions first (Upsert)
                    if ids_to_update:
                        placeholders = ",".join("?" * len(ids_to_update))
                        conn.execute(
                            f"DELETE FROM {SYS_SEARCH_TABLE} WHERE source_table = ? AND ref_id IN ({placeholders})",
                            [table_name, *ids_to_update],
                        )

                    # Insert new versions
                    if rows_to_insert:
                        conn.executemany(
                            f"INSERT INTO {SYS_SEARCH_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            rows_to_insert,
                        )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

        await asyncio.to_thread(_do_upsert)

        # 4. Schedule Async Save
        self._schedule_save(table_name)
        
        return {
            "status": "success",
            "table_name": table_name,
            "upserted_count": len(valid_records),
            "message": f"Successfully upserted {len(valid_records)} records",
        }

    async def delete_documents(self, table_name: str, doc_ids: list[str]) -> dict[str, Any]:
        """删除数据：Write DB -> Return -> Async Save"""
        validate_table_name(table_name)
        
        if not doc_ids:
            return {"status": "success", "deleted_count": 0}

        def _do_delete():
            with get_db(read_only=False) as conn:
                conn.begin()
                try:
                    placeholders = ",".join("?" * len(doc_ids))
                    conn.execute(
                        f"DELETE FROM {SYS_SEARCH_TABLE} WHERE source_table = ? AND ref_id IN ({placeholders})",
                        [table_name, *doc_ids],
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

        await asyncio.to_thread(_do_delete)
        
        # Schedule Async Save
        self._schedule_save(table_name)
        
        return {
            "status": "success",
            "table_name": table_name,
            "deleted_count": len(doc_ids),
            "message": f"Successfully deleted {len(doc_ids)} records",
        }

    def _schedule_save(self, table_name: str) -> None:
        """调度保存任务，支持简单的防抖 (Debounce)"""
        if table_name in self._save_tasks:
            self._save_tasks[table_name].cancel()

        # 创建新任务，延迟执行以合并短时间内的多次变更
        # Delay 1.0 second
        self._save_tasks[table_name] = asyncio.create_task(
            self._delayed_save(table_name, delay=1.0)
        )

    async def _delayed_save(self, table_name: str, delay: float) -> None:
        await asyncio.sleep(delay)
        try:
            await self.persister.dump_table_to_file(table_name)
        except Exception as e:
            logger.error(f"Async save failed for {table_name}: {e}")
        finally:
            self._save_tasks.pop(table_name, None)

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

        # Use get_embeddings from utils (async)
        embeddings = await get_embeddings(texts_to_embed)
        
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
