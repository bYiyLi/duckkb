"""存储能力 Mixin。"""

import asyncio
from pathlib import Path

from duckkb.constants import validate_table_name
from duckkb.core.base import BaseEngine
from duckkb.logger import logger


class StorageMixin(BaseEngine):
    """存储能力 Mixin。

    提供 SQL 驱动的数据加载和导出。
    依赖 conn (DBMixin) 和 ontology (OntologyMixin)。
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
        2. ID Generation: 为缺失 __id 的记录生成 ID
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

                identity_expr = " || '.-.' || ".join(identity_fields)
                self.conn.execute(
                    f"UPDATE {staging_table} SET __id = hash({identity_expr}) WHERE __id IS NULL"
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
        partition_by_date: bool = True,
    ) -> int:
        """导出表数据到 JSONL 文件。

        使用 DuckDB 的 Partitioned Write 特性，按日期自动分区导出。
        生成的目录结构为：
            {output_dir}/part_date={YYYYMMDD}/data_0.json

        Args:
            table_name: 源表名。
            output_dir: 输出目录。
            partition_by_date: 是否按日期分区，默认为 True。

        Returns:
            导出的记录数。
        """
        output_dir = output_dir.resolve()
        await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)

        if partition_by_date:
            sql = f"""
                COPY (
                    SELECT *, strftime(__updated_at, '%Y%m%d') as part_date
                    FROM {table_name}
                    ORDER BY __id
                ) TO '{output_dir}' (FORMAT JSON, PARTITION_BY (part_date), OVERWRITE_OR_IGNORE)
            """
        else:
            sql = f"""
                COPY (
                    SELECT *
                    FROM {table_name}
                    ORDER BY __id
                ) TO '{output_dir}/{table_name}.jsonl' (FORMAT JSON, OVERWRITE_OR_IGNORE)
            """

        def _execute_dump() -> int:
            self.conn.execute(sql)
            count_row = self.conn.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()
            return count_row[0] if count_row else 0

        record_count = await asyncio.to_thread(_execute_dump)

        logger.info(f"Dumped table {table_name} to {output_dir}: {record_count} records")

        return record_count

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

        将表数据导出到 data/nodes/{node_type}/ 目录，按日期分区。

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
        )

    async def load_edge(self, edge_name: str) -> int:
        """加载边数据。

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
            self.config.storage.data_dir / "edges" / table_name / "**" / "*.jsonl"
        )

        identity_fields = ["__from_id", "__to_id"]
        return await self.load_table(
            table_name=table_name,
            path_pattern=path_pattern,
            identity_fields=identity_fields,
        )

    async def dump_edge(self, edge_name: str) -> int:
        """导出边数据。

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
        output_dir = self.config.storage.data_dir / "edges" / table_name
        return await self.dump_table(
            table_name=table_name,
            output_dir=output_dir,
            partition_by_date=self.config.storage.partition_by_date,
        )
