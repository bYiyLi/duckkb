"""负责将数据库中的数据持久化到文件系统 (DB -> File)。"""

import asyncio
from pathlib import Path

import orjson

from duckkb.config import AppContext
from duckkb.constants import (
    BUILD_DIR_NAME,
    DATA_DIR_NAME,
    SYNC_STATE_FILE,
    SYS_SEARCH_TABLE,
)
from duckkb.db import get_db
from duckkb.logger import logger
from duckkb.utils.file_ops import (
    atomic_write_file,
    file_exists,
    get_file_stat,
    read_file,
    write_file,
)


class DataPersister:
    def __init__(self, kb_path: Path):
        self.kb_path = kb_path

    async def dump_table_to_file(self, table_name: str) -> None:
        """将数据库中的数据回写到 JSONL 文件。

        Args:
            table_name: 表名。
        """
        target_path = self.kb_path / DATA_DIR_NAME / f"{table_name}.jsonl"

        try:
            records = await asyncio.to_thread(self._fetch_table_records, table_name)

            # Write records atomically using helper
            lines = [orjson.dumps(r).decode("utf-8") for r in records]
            content = "\n".join(lines)
            if content:
                content += "\n"

            await atomic_write_file(target_path, content)

            logger.info(f"Synced DB to file: {target_path} ({len(records)} records)")

            # 更新同步状态，防止下次启动时误判为文件变更
            state_file = self.kb_path / BUILD_DIR_NAME / SYNC_STATE_FILE
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
            raise  # Re-raise to let caller handle error (e.g., retry)

    def _fetch_table_records(self, table_name: str) -> list[dict]:
        """从数据库获取指定表的所有记录（通过 metadata 重组）。

        Args:
            table_name: 表名。

        Returns:
            包含所有记录的列表，每个记录为一个字典。
        """
        with get_db(read_only=True) as conn:
            # DISTINCT ref_id to avoid duplicates from multiple fields
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
            elif isinstance(metadata_json, dict):
                records.append(metadata_json)
        return records

    def get_all_table_names(self) -> list[str]:
        """获取数据库中所有用户表名。"""
        with get_db(read_only=True) as conn:
            rows = conn.execute(f"SELECT DISTINCT source_table FROM {SYS_SEARCH_TABLE}").fetchall()
        return [row[0] for row in rows]

    async def persist_all_tables(self) -> dict[str, int]:
        """将所有数据库表持久化到 JSONL 文件。"""
        table_names = await asyncio.to_thread(self.get_all_table_names)
        results: dict[str, int] = {}

        for table_name in table_names:
            try:
                records = await asyncio.to_thread(self._fetch_table_records, table_name)
                results[table_name] = len(records)

                target_path = self.kb_path / DATA_DIR_NAME / f"{table_name}.jsonl"
                lines = [orjson.dumps(r).decode("utf-8") for r in records]
                content = "\n".join(lines)
                if content:
                    content += "\n"

                await atomic_write_file(target_path, content)
                logger.info(f"Persisted table {table_name}: {len(records)} records")
            except Exception as e:
                logger.error(f"Failed to persist table {table_name}: {e}")
                results[table_name] = -1

        # Reset sync state
        state_file = self.kb_path / BUILD_DIR_NAME / SYNC_STATE_FILE
        if await file_exists(state_file):
            try:
                await write_file(state_file, "{}")
            except Exception as e:
                logger.warning(f"Failed to reset sync state file: {e}")

        return results
