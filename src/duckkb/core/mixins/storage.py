"""存储能力 Mixin。"""

import asyncio
import shutil
from pathlib import Path

from duckkb.constants import validate_table_name
from duckkb.core.base import BaseEngine
from duckkb.logger import logger


class StorageMixin(BaseEngine):
    """存储能力 Mixin。

    提供 SQL 驱动的数据加载和导出。
    依赖 execute_read/write (DBMixin) 和 ontology (OntologyMixin)。

    导出时按 __id 排序，支持分片。
    目录结构符合设计文档：
    - 节点：{table_name}/{YYYYMMDD}/part_{NNN}.jsonl
    - 边：{label_name}/{YYYYMMDD}/part_{NNN}.jsonl
    """

    async def load_table(
        self,
        table_name: str,
        path_pattern: str,
        unique_fields: list[str],
    ) -> int:
        """从 JSONL 文件加载表数据。

        流程：
        1. Staging: 使用 read_json_auto 加载到临时表
        2. ID Generation: 为缺失 __id 的记录使用 SEQUENCE 生成 ID
        3. Merge: 使用 INSERT OR REPLACE 同步到主表（按 unique_fields 去重）
        4. Sync Sequence: 更新 SEQUENCE 起始值为 MAX(__id) + 1

        Args:
            table_name: 目标表名。
            path_pattern: 文件路径模式，支持 glob 模式。
            unique_fields: 业务键字段列表，用于去重。

        Returns:
            加载的记录数。

        Raises:
            ValueError: 表名无效时抛出。
        """
        validate_table_name(table_name)

        staging_table = f"_staging_{table_name}"
        seq_name = f"{table_name}_id_seq"

        def _execute_load() -> int:
            with self.write_transaction() as conn:
                conn.execute(f"DROP TABLE IF EXISTS {staging_table}")

                conn.execute(
                    f"CREATE TEMP TABLE {staging_table} AS "
                    f"SELECT * FROM read_json_auto('{path_pattern}', union_by_name=true)"
                )

                count_result = conn.execute(f"SELECT COUNT(*) FROM {staging_table}").fetchone()
                record_count = count_result[0] if count_result else 0

                if record_count == 0:
                    logger.warning(f"No records loaded from {path_pattern}")
                    return 0

                rows_needing_id = conn.execute(
                    f"SELECT rowid FROM {staging_table} WHERE __id IS NULL"
                ).fetchall()

                for (rowid,) in rows_needing_id:
                    conn.execute(
                        f"UPDATE {staging_table} SET __id = nextval('{seq_name}') WHERE rowid = ?",
                        [rowid],
                    )

                conn.execute(f"INSERT OR REPLACE INTO {table_name} SELECT * FROM {staging_table}")

                conn.execute(f"DROP TABLE {staging_table}")

                max_id_result = conn.execute(f"SELECT COALESCE(MAX(__id), 0) FROM {table_name}").fetchone()
                max_id = max_id_result[0] if max_id_result else 0
                conn.execute(f"DROP SEQUENCE IF EXISTS {seq_name}")
                conn.execute(f"CREATE SEQUENCE {seq_name} START {max_id + 1}")

                logger.info(f"Loaded {record_count} records into {table_name}")
                return record_count

        return await asyncio.to_thread(_execute_load)

    async def dump_table(
        self,
        table_name: str,
        output_dir: Path,
        partition_by_date: bool = True,
        max_rows_per_file: int = 1000,
    ) -> int:
        """导出表数据到 JSONL 文件。

        导出时按 __id 排序，支持分片。
        目录结构：{output_dir}/{YYYYMMDD}/part_{NNN}.jsonl

        Args:
            table_name: 源表名。
            output_dir: 输出目录。
            partition_by_date: 是否按日期分区，默认为 True。
            max_rows_per_file: 每个文件最大行数，默认 1000。

        Returns:
            导出的记录数。
        """
        output_dir = output_dir.resolve()
        await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)

        def _execute_dump() -> int:
            count_row = self.execute_read(f"SELECT COUNT(*) FROM {table_name}")
            record_count = count_row[0][0] if count_row else 0

            if record_count == 0:
                logger.warning(f"No records to dump from {table_name}")
                return 0

            if partition_by_date:
                self._dump_partitioned_by_date(table_name, output_dir, max_rows_per_file)
            else:
                self._dump_single_file(table_name, output_dir, max_rows_per_file)

            return record_count

        record_count = await asyncio.to_thread(_execute_dump)

        logger.info(f"Dumped table {table_name} to {output_dir}: {record_count} records")

        return record_count

    def _dump_partitioned_by_date(
        self,
        table_name: str,
        output_dir: Path,
        max_rows_per_file: int,
    ) -> None:
        """按日期分区导出，支持分片。

        目录结构：{output_dir}/{YYYYMMDD}/part_{NNN}.jsonl
        """
        rows = self.execute_read(
            f"SELECT DISTINCT strftime(__created_at, '%Y%m%d') as date_part "
            f"FROM {table_name} ORDER BY date_part"
        )

        for (date_part,) in rows:
            date_dir = output_dir / date_part
            date_dir.mkdir(parents=True, exist_ok=True)

            count_row = self.execute_read(
                f"SELECT COUNT(*) FROM {table_name} "
                f"WHERE strftime(__created_at, '%Y%m%d') = '{date_part}'"
            )
            total_rows = count_row[0][0] if count_row else 0

            if total_rows == 0:
                continue

            num_parts = (total_rows + max_rows_per_file - 1) // max_rows_per_file

            for part_idx in range(num_parts):
                offset = part_idx * max_rows_per_file
                temp_file = date_dir / "_temp.jsonl"
                final_file = date_dir / f"part_{part_idx}.jsonl"

                self.execute_write(
                    f"COPY ("
                    f"  SELECT * FROM {table_name} "
                    f"  WHERE strftime(__created_at, '%Y%m%d') = '{date_part}' "
                    f"  ORDER BY __id "
                    f"  LIMIT {max_rows_per_file} OFFSET {offset}"
                    f") TO '{temp_file}' (FORMAT JSON)"
                )

                shutil.move(str(temp_file), str(final_file))

    def _dump_single_file(
        self,
        table_name: str,
        output_dir: Path,
        max_rows_per_file: int,
    ) -> None:
        """导出为多个分片文件。"""
        count_row = self.execute_read(f"SELECT COUNT(*) FROM {table_name}")
        total_rows = count_row[0][0] if count_row else 0

        if total_rows == 0:
            return

        num_parts = (total_rows + max_rows_per_file - 1) // max_rows_per_file

        for part_idx in range(num_parts):
            offset = part_idx * max_rows_per_file
            temp_file = output_dir / "_temp.jsonl"
            final_file = output_dir / f"part_{part_idx}.jsonl"

            self.execute_write(
                f"COPY ("
                f"  SELECT * FROM {table_name} "
                f"  ORDER BY __id "
                f"  LIMIT {max_rows_per_file} OFFSET {offset}"
                f") TO '{temp_file}' (FORMAT JSON)"
            )

            shutil.move(str(temp_file), str(final_file))

    async def load_node(self, node_type: str) -> int:
        """加载节点数据。

        从 data/nodes/{node_type}/**/*.jsonl 加载数据到对应的表。

        Args:
            node_type: 节点类型名称。

        Returns:
            加载的记录数。

        Raises:
            ValueError: 节点类型不存在时抛出。
        """
        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        path_pattern = str(
            self.config.storage.data_dir / "nodes" / node_def.table / "**" / "*.jsonl"
        )
        return await self.load_table(
            table_name=node_def.table,
            path_pattern=path_pattern,
            unique_fields=node_def.identity,
        )

    async def dump_node(self, node_type: str) -> int:
        """导出节点数据。

        将表数据导出到 data/nodes/{table_name}/{YYYYMMDD}/part_{NNN}.jsonl 目录结构。

        Args:
            node_type: 节点类型名称。

        Returns:
            导出的记录数。

        Raises:
            ValueError: 节点类型不存在时抛出。
        """
        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        output_dir = self.config.storage.data_dir / "nodes" / node_def.table
        return await self.dump_table(
            table_name=node_def.table,
            output_dir=output_dir,
            partition_by_date=self.config.storage.partition_by_date,
            max_rows_per_file=self.config.storage.max_rows_per_file,
        )

    async def load_edge(self, edge_name: str) -> int:
        """加载边数据。

        从 data/edges/{edge_name}/**/*.jsonl 加载数据。

        Args:
            edge_name: 边类型名称。

        Returns:
            加载的记录数。

        Raises:
            ValueError: 边类型不存在时抛出。
        """
        edge_def = self.ontology.edges.get(edge_name)
        if edge_def is None:
            raise ValueError(f"Unknown edge type: {edge_name}")

        table_name = f"edge_{edge_name}"
        path_pattern = str(
            self.config.storage.data_dir / "edges" / edge_name.lower() / "**" / "*.jsonl"
        )

        unique_fields = ["__from_id", "__to_id"]
        return await self.load_table(
            table_name=table_name,
            path_pattern=path_pattern,
            unique_fields=unique_fields,
        )

    async def dump_edge(self, edge_name: str) -> int:
        """导出边数据。

        将表数据导出到 data/edges/{edge_name}/{YYYYMMDD}/part_{NNN}.jsonl 目录结构。

        Args:
            edge_name: 边类型名称。

        Returns:
            导出的记录数。

        Raises:
            ValueError: 边类型不存在时抛出。
        """
        edge_def = self.ontology.edges.get(edge_name)
        if edge_def is None:
            raise ValueError(f"Unknown edge type: {edge_name}")

        table_name = f"edge_{edge_name}"
        output_dir = self.config.storage.data_dir / "edges" / edge_name.lower()
        return await self.dump_table(
            table_name=table_name,
            output_dir=output_dir,
            partition_by_date=self.config.storage.partition_by_date,
            max_rows_per_file=self.config.storage.max_rows_per_file,
        )

    async def sync_node(self, node_type: str) -> dict:
        """原子同步节点数据。

        在同一事务中执行：加载 -> 索引构建 -> 导出。

        Args:
            node_type: 节点类型名称。

        Returns:
            同步结果统计。

        Raises:
            ValueError: 节点类型不存在时抛出。
        """
        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        loaded = await self.load_node(node_type)

        indexed = 0
        if hasattr(self, "rebuild_index"):
            indexed = await self.rebuild_index(node_type)

        dumped = await self.dump_node(node_type)

        return {"loaded": loaded, "indexed": indexed, "dumped": dumped}

    async def sync_edge(self, edge_name: str) -> dict:
        """原子同步边数据。

        在同一事务中执行：加载 -> 导出。

        Args:
            edge_name: 边类型名称。

        Returns:
            同步结果统计。

        Raises:
            ValueError: 边类型不存在时抛出。
        """
        edge_def = self.ontology.edges.get(edge_name)
        if edge_def is None:
            raise ValueError(f"Unknown edge type: {edge_name}")

        loaded = await self.load_edge(edge_name)
        dumped = await self.dump_edge(edge_name)

        return {"loaded": loaded, "dumped": dumped}
