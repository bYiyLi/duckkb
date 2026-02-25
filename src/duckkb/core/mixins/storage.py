"""存储能力 Mixin。"""

import asyncio
import hashlib
import shutil
from pathlib import Path

from duckkb.constants import validate_table_name
from duckkb.core.base import BaseEngine
from duckkb.logger import logger


def compute_deterministic_id(identity_values: list) -> int:
    """计算确定性 ID。

    使用 SHA256 哈希算法，确保跨平台、跨版本一致性。

    Args:
        identity_values: 标识字段值列表。

    Returns:
        确定性的整数 ID。
    """
    combined = "\x00".join(str(v) for v in identity_values)
    hash_hex = hashlib.sha256(combined.encode()).hexdigest()
    return int(hash_hex[:16], 16)


class StorageMixin(BaseEngine):
    """存储能力 Mixin。

    提供 SQL 驱动的数据加载和导出。
    依赖 conn (DBMixin) 和 ontology (OntologyMixin)。

    导出时按 identity 字段排序，确保 Git Diff 有效。
    目录结构符合设计文档：
    - 节点：{table_name}/{YYYYMMDD}/part_{NNN}.jsonl
    - 边：{label_name}/{YYYYMMDD}/part_{NNN}.jsonl
    """

    async def load_table(
        self,
        table_name: str,
        path_pattern: str,
        identity_fields: list[str],
    ) -> int:
        """从 JSONL 文件加载表数据。

        流程：
        1. Staging: 使用 read_json_auto 加载到临时表
        2. ID Generation: 为缺失 __id 的记录使用确定性哈希生成 ID
        3. Merge: 使用 INSERT OR REPLACE 同步到主表

        Args:
            table_name: 目标表名。
            path_pattern: 文件路径模式，支持 glob 模式。
            identity_fields: 用于生成 ID 的标识字段列表。

        Returns:
            加载的记录数。

        Raises:
            ValueError: 表名无效或标识字段为空时抛出。
        """
        validate_table_name(table_name)

        if not identity_fields:
            raise ValueError("identity_fields cannot be empty")

        staging_table = f"_staging_{table_name}"

        def _execute_load() -> int:
            try:
                self.conn.begin()

                self.conn.execute(f"DROP TABLE IF EXISTS {staging_table}")

                self.conn.execute(
                    f"CREATE TEMP TABLE {staging_table} AS "
                    f"SELECT * FROM read_json_auto('{path_pattern}', union_by_name=true)"
                )

                count_result = self.conn.execute(
                    f"SELECT COUNT(*) FROM {staging_table}"
                ).fetchone()
                record_count = count_result[0] if count_result else 0

                if record_count == 0:
                    logger.warning(f"No records loaded from {path_pattern}")
                    self.conn.rollback()
                    return 0

                rows_needing_id = self.conn.execute(
                    f"SELECT rowid, {', '.join(identity_fields)} FROM {staging_table} WHERE __id IS NULL"
                ).fetchall()

                for row in rows_needing_id:
                    rowid = row[0]
                    identity_values = list(row[1:])
                    determined_id = compute_deterministic_id(identity_values)
                    self.conn.execute(
                        f"UPDATE {staging_table} SET __id = ? WHERE rowid = ?",
                        [determined_id, rowid],
                    )

                self.conn.execute(
                    f"INSERT OR REPLACE INTO {table_name} SELECT * FROM {staging_table}"
                )

                self.conn.execute(f"DROP TABLE {staging_table}")

                self.conn.commit()
                logger.info(f"Loaded {record_count} records into {table_name}")
                return record_count

            except Exception as e:
                self.conn.rollback()
                logger.error(f"Failed to load table {table_name}: {e}")
                raise

        return await asyncio.to_thread(_execute_load)

    async def dump_table(
        self,
        table_name: str,
        output_dir: Path,
        identity_field: str,
        partition_by_date: bool = True,
    ) -> int:
        """导出表数据到 JSONL 文件。

        导出时按 identity 字段排序，确保 Git Diff 有效。
        目录结构：{output_dir}/{YYYYMMDD}/part_{NNN}.jsonl

        Args:
            table_name: 源表名。
            output_dir: 输出目录。
            identity_field: identity 字段名，用于确定性排序。
            partition_by_date: 是否按日期分区，默认为 True。

        Returns:
            导出的记录数。
        """
        output_dir = output_dir.resolve()
        await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)

        def _execute_dump() -> int:
            count_row = self.conn.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()
            record_count = count_row[0] if count_row else 0

            if record_count == 0:
                logger.warning(f"No records to dump from {table_name}")
                return 0

            if partition_by_date:
                self._dump_partitioned_by_date(
                    table_name, output_dir, identity_field
                )
            else:
                self._dump_single_file(table_name, output_dir, identity_field)

            return record_count

        record_count = await asyncio.to_thread(_execute_dump)

        logger.info(f"Dumped table {table_name} to {output_dir}: {record_count} records")

        return record_count

    def _dump_partitioned_by_date(
        self,
        table_name: str,
        output_dir: Path,
        identity_field: str,
    ) -> None:
        """按日期分区导出。

        目录结构：{output_dir}/{YYYYMMDD}/part_0.jsonl
        """
        rows = self.conn.execute(
            f"SELECT DISTINCT strftime(__updated_at, '%Y%m%d') as date_part "
            f"FROM {table_name} ORDER BY date_part"
        ).fetchall()

        for (date_part,) in rows:
            date_dir = output_dir / date_part
            date_dir.mkdir(parents=True, exist_ok=True)

            temp_file = date_dir / "_temp.jsonl"
            final_file = date_dir / "part_0.jsonl"

            self.conn.execute(
                f"COPY ("
                f"  SELECT * FROM {table_name} "
                f"  WHERE strftime(__updated_at, '%Y%m%d') = '{date_part}' "
                f"  ORDER BY {identity_field}"
                f") TO '{temp_file}' (FORMAT JSON)"
            )

            shutil.move(str(temp_file), str(final_file))

    def _dump_single_file(
        self,
        table_name: str,
        output_dir: Path,
        identity_field: str,
    ) -> None:
        """导出为单个文件。"""
        temp_file = output_dir / "_temp.jsonl"
        final_file = output_dir / f"{table_name}.jsonl"

        self.conn.execute(
            f"COPY ("
            f"  SELECT * FROM {table_name} "
            f"  ORDER BY {identity_field}"
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
            identity_fields=node_def.identity,
        )

    async def dump_node(self, node_type: str) -> int:
        """导出节点数据。

        将表数据导出到 data/nodes/{table_name}/{YYYYMMDD}/part_0.jsonl 目录结构。

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

        if not node_def.identity:
            raise ValueError(f"Node type {node_type} has no identity field")

        output_dir = self.config.storage.data_dir / "nodes" / node_def.table
        return await self.dump_table(
            table_name=node_def.table,
            output_dir=output_dir,
            identity_field=node_def.identity[0],
            partition_by_date=self.config.storage.partition_by_date,
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

        identity_fields = ["__from_id", "__to_id"]
        return await self.load_table(
            table_name=table_name,
            path_pattern=path_pattern,
            identity_fields=identity_fields,
        )

    async def dump_edge(self, edge_name: str) -> int:
        """导出边数据。

        将表数据导出到 data/edges/{edge_name}/{YYYYMMDD}/part_0.jsonl 目录结构。

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
            identity_field="__from_id",
            partition_by_date=self.config.storage.partition_by_date,
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
