"""知识导入能力 Mixin。"""

import asyncio
import hashlib
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import ValidationError, validate

from duckkb.constants import validate_table_name
from duckkb.core.base import BaseEngine
from duckkb.core.mixins.index import SEARCH_CACHE_TABLE, SEARCH_INDEX_TABLE
from duckkb.logger import logger


class ImportMixin(BaseEngine):
    """知识导入能力 Mixin。

    提供知识包导入功能，遵循原子同步协议 (Shadow Copy)：
    - 单一事务包装所有数据库操作（业务表 + 索引）
    - 边引用完整性检查在事务内执行
    - 影子导出 + 原子替换确保数据一致性
    """

    def __init__(self, *args, **kwargs) -> None:
        """初始化导入 Mixin。"""
        super().__init__(*args, **kwargs)
        self._import_lock = asyncio.Lock()

    async def import_knowledge_bundle(self, temp_file_path: str) -> dict[str, Any]:
        """导入知识包。

        从 YAML 文件导入数据到知识库，执行完整的校验和原子同步协议处理。

        流程：
        1. 读取 YAML 文件
        2. Schema 校验
        3. 开启事务
           - 导入节点（业务表）
           - 导入边（业务表）
           - 验证边引用完整性
           - 构建索引（search_index）
           - 提交事务（失败则回滚）
        4. 异步计算向量嵌入
        5. 影子导出
           - 创建影子目录
           - 导出业务数据（JSONL）
           - 导出缓存数据（PARQUET）
        6. 原子替换 data/ 目录
        7. 删除临时文件
        8. 返回结果

        Args:
            temp_file_path: 临时 YAML 文件的绝对路径。

        Returns:
            导入结果统计，包含：
            - status: 操作状态
            - nodes: 节点导入统计
            - edges: 边导入统计
            - indexed: 索引构建统计
            - vectors: 向量计算统计
            - dumped: 持久化导出统计

        Raises:
            ValidationError: Schema 校验失败时抛出。
            FileNotFoundError: 临时文件不存在时抛出。
            ValueError: 语义校验失败时抛出。
        """
        async with self._import_lock:
            path = Path(temp_file_path)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {temp_file_path}")

            data_dir = self.config.storage.data_dir
            shadow_dir = data_dir.parent / f"{data_dir.name}_shadow"

            try:
                content = await self._read_file(path)
                data = yaml.safe_load(content)

                if not isinstance(data, list):
                    raise ValueError("YAML file must contain an array at root level")

                get_bundle_schema = getattr(self, "get_bundle_schema", None)
                if get_bundle_schema is None:
                    raise RuntimeError("get_bundle_schema method not available")
                bundle_schema = get_bundle_schema()
                full_schema = bundle_schema["full_bundle_schema"]

                try:
                    validate(instance=data, schema=full_schema)
                except ValidationError as e:
                    path_str = ".".join(str(p) for p in e.absolute_path)
                    raise ValueError(f"Validation error at [{path_str}]: {e.message}") from e

                nodes_data: list[dict[str, Any]] = []
                edges_data: list[dict[str, Any]] = []

                for item in data:
                    item_type = item.get("type")
                    if item_type in self.ontology.nodes:
                        nodes_data.append(item)
                    elif item_type in self.ontology.edges:
                        edges_data.append(item)

                result = await self._execute_import_in_transaction(nodes_data, edges_data)
                nodes_result = result["nodes"]
                edges_result = result["edges"]
                indexed_result = result["indexed"]
                upserted_ids = result["upserted_ids"]
                deleted_ids = result["deleted_ids"]

                vector_result = await self._compute_vectors_async(upserted_ids)

                if hasattr(self, "rebuild_fts_index"):
                    await asyncio.to_thread(self.rebuild_fts_index)

                dumped = await self._dump_to_shadow_dir(
                    upserted_ids,
                    deleted_ids,
                )

                if dumped:
                    await self._atomic_replace_data_dir()

                return {
                    "status": "success",
                    "nodes": nodes_result,
                    "edges": edges_result,
                    "indexed": indexed_result,
                    "vectors": vector_result,
                    "dumped": dumped,
                }

            except Exception:
                if shadow_dir.exists():
                    try:
                        await asyncio.to_thread(shutil.rmtree, shadow_dir)
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to cleanup shadow directory: {cleanup_error}")
                raise
            finally:
                if path.exists():
                    try:
                        await self._unlink_file(path)
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to cleanup temp file {path}: {cleanup_error}")

    async def _read_file(self, path: Path) -> str:
        """异步读取文件内容。

        Args:
            path: 文件路径。

        Returns:
            文件内容字符串。
        """
        import aiofiles

        async with aiofiles.open(path, encoding="utf-8") as f:
            return await f.read()

    async def _unlink_file(self, path: Path) -> None:
        """异步删除文件。

        Args:
            path: 文件路径。
        """
        await asyncio.to_thread(os.unlink, path)

    def _node_exists_in_transaction(self, conn: Any, table_name: str, node_id: int) -> bool:
        """在事务内检查节点是否存在。

        包括已提交和未提交的数据。

        Args:
            conn: 数据库连接。
            table_name: 节点表名。
            node_id: 节点 ID。

        Returns:
            节点存在返回 True，否则返回 False。
        """
        validate_table_name(table_name)
        result = conn.execute(
            f"SELECT 1 FROM {table_name} WHERE __id = ? LIMIT 1",
            [node_id],
        ).fetchone()
        return result is not None

    def _validate_edge_references(
        self,
        conn: Any,
        edge_type: str,
        items: list[dict[str, Any]],
    ) -> None:
        """验证边引用的节点是否存在。

        在事务内执行，检查 source/target 节点是否存在于数据库中
        （包括同一事务中刚插入的数据）。

        Args:
            conn: 数据库连接。
            edge_type: 边类型名称。
            items: 边数据列表。

        Raises:
            ValueError: 当引用的节点不存在时抛出。
        """
        edge_def = self.ontology.edges.get(edge_type)
        if edge_def is None:
            return

        source_node_def = self.ontology.nodes.get(edge_def.from_)
        target_node_def = self.ontology.nodes.get(edge_def.to)

        if source_node_def is None or target_node_def is None:
            return

        for idx, item in enumerate(items):
            source = item.get("source", {})
            target = item.get("target", {})

            source_identity_values = [source.get(f) for f in source_node_def.identity]
            source_placeholders = " AND ".join(
                f"{f} = ?" for f in source_node_def.identity
            )
            source_row = conn.execute(
                f"SELECT __id FROM {source_node_def.table} WHERE {source_placeholders}",
                source_identity_values,
            ).fetchone()

            if not source_row:
                raise ValueError(
                    f"[{idx}] Cannot create '{edge_type}' relation: "
                    f"Source '{edge_def.from_}' with identity {source} not found."
                )

            target_identity_values = [target.get(f) for f in target_node_def.identity]
            target_placeholders = " AND ".join(
                f"{f} = ?" for f in target_node_def.identity
            )
            target_row = conn.execute(
                f"SELECT __id FROM {target_node_def.table} WHERE {target_placeholders}",
                target_identity_values,
            ).fetchone()

            if not target_row:
                raise ValueError(
                    f"[{idx}] Cannot create '{edge_type}' relation: "
                    f"Target '{edge_def.to}' with identity {target} not found."
                )

    async def _execute_import_in_transaction(
        self,
        nodes_data: list[dict[str, Any]],
        edges_data: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """在单一事务中执行所有导入操作。

        流程：
        1. 开启事务
        2. 导入所有节点
        3. 导入所有边
        4. 验证边引用完整性
        5. 构建索引
        6. 提交事务（失败则回滚）

        Args:
            nodes_data: 节点数据列表。
            edges_data: 边数据列表。

        Returns:
            包含节点导入结果、边导入结果、索引结果和 ID 列表的字典。

        Raises:
            ValueError: 边引用验证失败时抛出（事务已回滚）。
        """

        def _execute() -> dict[str, Any]:
            with self.write_transaction() as conn:
                nodes_result, node_upserted_ids, node_deleted_ids = self._import_nodes_sync(
                    conn, nodes_data
                )
                edges_result = self._import_edges_sync(conn, edges_data)

                for edge_type, items in self._group_edges_by_type(edges_data).items():
                    upsert_items = [
                        item for item in items if item.get("action", "upsert") == "upsert"
                    ]
                    if upsert_items:
                        self._validate_edge_references(conn, edge_type, upsert_items)

                indexed_result = self._build_index_for_ids_sync(conn, node_upserted_ids)

                return {
                    "nodes": nodes_result,
                    "edges": edges_result,
                    "indexed": indexed_result,
                    "upserted_ids": node_upserted_ids,
                    "deleted_ids": node_deleted_ids,
                }

        return await asyncio.to_thread(_execute)

    def _import_nodes_sync(
        self, conn: Any, data: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], dict[str, list[int]], dict[str, list[int]]]:
        """同步导入节点（在事务内执行）。

        Args:
            conn: 数据库连接。
            data: 节点数据列表。

        Returns:
            (导入统计, upserted_ids, deleted_ids)
        """
        upserted: dict[str, int] = {}
        deleted: dict[str, int] = {}
        upserted_ids: dict[str, list[int]] = {}
        deleted_ids: dict[str, list[int]] = {}

        grouped = self._group_items_by_type_and_action(data)

        for node_type, actions in grouped.items():
            if actions["upsert"]:
                ids, count = self._upsert_nodes_sync(conn, node_type, actions["upsert"])
                upserted[node_type] = count
                upserted_ids[node_type] = ids
            if actions["delete"]:
                ids, count = self._delete_nodes_sync(conn, node_type, actions["delete"])
                deleted[node_type] = count
                deleted_ids[node_type] = ids

        return {"upserted": upserted, "deleted": deleted}, upserted_ids, deleted_ids

    def _import_edges_sync(self, conn: Any, data: list[dict[str, Any]]) -> dict[str, Any]:
        """同步导入边（在事务内执行）。

        Args:
            conn: 数据库连接。
            data: 边数据列表。

        Returns:
            导入统计。
        """
        upserted: dict[str, int] = {}
        deleted: dict[str, int] = {}

        grouped = self._group_items_by_type_and_action(data)

        for edge_type, actions in grouped.items():
            if actions["upsert"]:
                count = self._upsert_edges_sync(conn, edge_type, actions["upsert"])
                upserted[edge_type] = count
            if actions["delete"]:
                count = self._delete_edges_sync(conn, edge_type, actions["delete"])
                deleted[edge_type] = count

        return {"upserted": upserted, "deleted": deleted}

    def _group_items_by_type_and_action(
        self, data: list[dict[str, Any]]
    ) -> dict[str, dict[str, list]]:
        """按类型和操作分组数据。

        Args:
            data: 数据列表。

        Returns:
            分组后的数据字典。
        """
        grouped: dict[str, dict[str, list]] = {}
        for item in data:
            item_type = item.get("type")
            if item_type is None:
                continue
            action = item.get("action", "upsert")
            if action not in ("upsert", "delete"):
                action = "upsert"

            if item_type not in grouped:
                grouped[item_type] = {"upsert": [], "delete": []}
            grouped[item_type][action].append(item)

        return grouped

    def _group_edges_by_type(self, data: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """按类型分组边数据。

        Args:
            data: 边数据列表。

        Returns:
            分组后的边数据字典。
        """
        result: dict[str, list[dict[str, Any]]] = {}
        for item in data:
            edge_type = item.get("type")
            if edge_type is None:
                continue
            if edge_type not in result:
                result[edge_type] = []
            result[edge_type].append(item)
        return result

    def _upsert_nodes_sync(
        self, conn: Any, node_type: str, items: list[dict[str, Any]]
    ) -> tuple[list[int], int]:
        """同步 upsert 节点（批量优化版）。

        使用 INSERT ... ON CONFLICT DO UPDATE 语法，保留原始 __created_at。
        通过 UNIQUE 约束（identity 字段）处理冲突。

        Args:
            conn: 数据库连接。
            node_type: 节点类型名称。
            items: 节点数据列表。

        Returns:
            (插入的 ID 列表, 导入的记录数)
        """
        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        if not items:
            return [], 0

        table_name = node_def.table
        validate_table_name(table_name)
        now = datetime.now(UTC)

        records: list[dict[str, Any]] = []
        for item in items:
            record = {k: v for k, v in item.items() if k not in ("type", "action")}
            record["__created_at"] = now
            record["__updated_at"] = now
            records.append(record)

        if not records:
            return [], 0

        columns = list(records[0].keys())
        placeholders = ", ".join(["?" for _ in columns])
        batch_params = [[record[c] for c in columns] for record in records]

        identity_cols = ", ".join(node_def.identity)
        update_columns = [c for c in columns if c not in ("__id",) + tuple(node_def.identity)]
        update_set = ", ".join(
            f"{c} = {table_name}.{c}" if c == "__created_at" else f"{c} = excluded.{c}"
            for c in update_columns
        )

        conn.executemany(
            f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({identity_cols}) DO UPDATE SET {update_set}",
            batch_params,
        )

        identity_placeholders = " AND ".join(f"{f} = ?" for f in node_def.identity)
        record_ids: list[int] = []
        for record in records:
            identity_values = [record.get(f) for f in node_def.identity]
            row = conn.execute(
                f"SELECT __id FROM {table_name} WHERE {identity_placeholders}",
                identity_values,
            ).fetchone()
            if row:
                record_ids.append(row[0])

        return record_ids, len(records)

    def _delete_nodes_sync(
        self, conn: Any, node_type: str, items: list[dict[str, Any]]
    ) -> tuple[list[int], int]:
        """同步删除节点（批量优化版）。

        先删除相关的边，再删除节点。
        通过业务键查询节点 ID。

        Args:
            conn: 数据库连接。
            node_type: 节点类型名称。
            items: 节点数据列表。

        Returns:
            (删除的 ID 列表, 删除的记录数)
        """
        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        if not items:
            return [], 0

        table_name = node_def.table
        validate_table_name(table_name)

        identity_placeholders = " AND ".join(f"{f} = ?" for f in node_def.identity)
        record_ids: list[int] = []
        for item in items:
            record = {k: v for k, v in item.items() if k not in ("type", "action")}
            identity_values = [record.get(f) for f in node_def.identity]
            row = conn.execute(
                f"SELECT __id FROM {table_name} WHERE {identity_placeholders}",
                identity_values,
            ).fetchone()
            if row:
                record_ids.append(row[0])

        if not record_ids:
            return [], 0

        self._delete_edges_for_nodes(conn, record_ids)

        self._delete_index_for_ids(conn, table_name, record_ids)

        placeholders = ", ".join(["?" for _ in record_ids])
        conn.execute(
            f"DELETE FROM {table_name} WHERE __id IN ({placeholders})",
            record_ids,
        )

        return record_ids, len(record_ids)

    def _delete_edges_for_nodes(self, conn: Any, node_ids: list[int]) -> int:
        """删除与指定节点相关的所有边。

        Args:
            conn: 数据库连接。
            node_ids: 节点 ID 列表。

        Returns:
            删除的边数量。
        """
        if not node_ids:
            return 0

        total_deleted = 0
        placeholders = ", ".join(["?" for _ in node_ids])

        for edge_name in self.ontology.edges.keys():
            table_name = f"edge_{edge_name}"
            validate_table_name(table_name)

            if not self._table_exists_in_conn(conn, table_name):
                continue

            count_before = self._get_table_count_in_conn(conn, table_name)

            conn.execute(
                f"DELETE FROM {table_name} "
                f"WHERE __from_id IN ({placeholders}) OR __to_id IN ({placeholders})",
                node_ids + node_ids,
            )

            count_after = self._get_table_count_in_conn(conn, table_name)
            total_deleted += count_before - count_after

        return total_deleted

    def _table_exists_in_conn(self, conn: Any, table_name: str) -> bool:
        """检查表是否存在。

        Args:
            conn: 数据库连接。
            table_name: 表名。

        Returns:
            表存在返回 True，否则返回 False。
        """
        validate_table_name(table_name)
        result = conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = ? LIMIT 1",
            [table_name],
        ).fetchone()
        return result is not None

    def _get_table_count_in_conn(self, conn: Any, table_name: str) -> int:
        """获取表的记录数。

        Args:
            conn: 数据库连接。
            table_name: 表名。

        Returns:
            记录数。
        """
        validate_table_name(table_name)
        result = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return result[0] if result else 0

    def _delete_index_for_ids(self, conn: Any, table_name: str, record_ids: list[int]) -> int:
        """删除指定记录的索引条目。

        Args:
            conn: 数据库连接。
            table_name: 表名。
            record_ids: 记录 ID 列表。

        Returns:
            删除的索引条目数。
        """
        if not record_ids:
            return 0

        validate_table_name(table_name)

        if not self._table_exists_in_conn(conn, SEARCH_INDEX_TABLE):
            return 0

        placeholders = ", ".join(["?" for _ in record_ids])

        row = conn.execute(
            f"SELECT COUNT(*) FROM {SEARCH_INDEX_TABLE} WHERE source_table = ?",
            [table_name],
        ).fetchone()
        count_before = row[0] if row else 0

        conn.execute(
            f"DELETE FROM {SEARCH_INDEX_TABLE} "
            f"WHERE source_table = ? AND source_id IN ({placeholders})",
            [table_name] + record_ids,
        )

        row = conn.execute(
            f"SELECT COUNT(*) FROM {SEARCH_INDEX_TABLE} WHERE source_table = ?",
            [table_name],
        ).fetchone()
        count_after = row[0] if row else 0

        return count_before - count_after

    def _upsert_edges_sync(self, conn: Any, edge_type: str, items: list[dict[str, Any]]) -> int:
        """同步 upsert 边（批量优化版）。

        使用 INSERT ... ON CONFLICT DO UPDATE 语法，保留原始 __created_at。
        通过 UNIQUE(__from_id, __to_id) 约束处理冲突。

        Args:
            conn: 数据库连接。
            edge_type: 边类型名称。
            items: 边数据列表。

        Returns:
            导入的记录数。
        """
        edge_def = self.ontology.edges.get(edge_type)
        if edge_def is None:
            raise ValueError(f"Unknown edge type: {edge_type}")

        if not items:
            return 0

        table_name = f"edge_{edge_type}"
        validate_table_name(table_name)

        if not self._table_exists_in_conn(conn, table_name):
            raise ValueError(f"Edge table {table_name} does not exist")

        source_node = self.ontology.nodes.get(edge_def.from_)
        target_node = self.ontology.nodes.get(edge_def.to)

        if source_node is None or target_node is None:
            raise ValueError(f"Invalid edge definition: {edge_type}")

        now = datetime.now(UTC)

        records: list[dict[str, Any]] = []
        for item in items:
            source = item.get("source", {})
            target = item.get("target", {})

            source_identity_values = [source.get(f) for f in source_node.identity]
            source_placeholders = " AND ".join(f"{f} = ?" for f in source_node.identity)
            source_row = conn.execute(
                f"SELECT __id FROM {source_node.table} WHERE {source_placeholders}",
                source_identity_values,
            ).fetchone()
            source_id = source_row[0] if source_row else None

            target_identity_values = [target.get(f) for f in target_node.identity]
            target_placeholders = " AND ".join(f"{f} = ?" for f in target_node.identity)
            target_row = conn.execute(
                f"SELECT __id FROM {target_node.table} WHERE {target_placeholders}",
                target_identity_values,
            ).fetchone()
            target_id = target_row[0] if target_row else None

            if source_id is None or target_id is None:
                continue

            record: dict[str, Any] = {
                "__from_id": source_id,
                "__to_id": target_id,
                "__created_at": now,
                "__updated_at": now,
            }

            for k, v in item.items():
                if k not in ("type", "action", "source", "target"):
                    record[k] = v

            records.append(record)

        if not records:
            return 0

        columns = list(records[0].keys())
        placeholders = ", ".join(["?" for _ in columns])
        batch_params = [[record[c] for c in columns] for record in records]

        update_columns = [c for c in columns if c not in ("__id", "__from_id", "__to_id")]
        update_set = ", ".join(
            f"{c} = {table_name}.{c}" if c == "__created_at" else f"{c} = excluded.{c}"
            for c in update_columns
        )

        conn.executemany(
            f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT (__from_id, __to_id) DO UPDATE SET {update_set}",
            batch_params,
        )

        return len(records)

    def _delete_edges_sync(self, conn: Any, edge_type: str, items: list[dict[str, Any]]) -> int:
        """同步删除边（批量优化版）。

        通过 source/target 的业务键查询边 ID。

        Args:
            conn: 数据库连接。
            edge_type: 边类型名称。
            items: 边数据列表。

        Returns:
            删除的记录数。
        """
        edge_def = self.ontology.edges.get(edge_type)
        if edge_def is None:
            raise ValueError(f"Unknown edge type: {edge_type}")

        if not items:
            return 0

        table_name = f"edge_{edge_type}"
        validate_table_name(table_name)

        if not self._table_exists_in_conn(conn, table_name):
            return 0

        source_node = self.ontology.nodes.get(edge_def.from_)
        target_node = self.ontology.nodes.get(edge_def.to)

        if source_node is None or target_node is None:
            raise ValueError(f"Invalid edge definition: {edge_type}")

        record_ids: list[int] = []
        for item in items:
            source = item.get("source", {})
            target = item.get("target", {})

            source_identity_values = [source.get(f) for f in source_node.identity]
            source_placeholders = " AND ".join(f"{f} = ?" for f in source_node.identity)
            source_row = conn.execute(
                f"SELECT __id FROM {source_node.table} WHERE {source_placeholders}",
                source_identity_values,
            ).fetchone()
            source_id = source_row[0] if source_row else None

            target_identity_values = [target.get(f) for f in target_node.identity]
            target_placeholders = " AND ".join(f"{f} = ?" for f in target_node.identity)
            target_row = conn.execute(
                f"SELECT __id FROM {target_node.table} WHERE {target_placeholders}",
                target_identity_values,
            ).fetchone()
            target_id = target_row[0] if target_row else None

            if source_id is None or target_id is None:
                continue

            edge_row = conn.execute(
                f"SELECT __id FROM {table_name} WHERE __from_id = ? AND __to_id = ?",
                [source_id, target_id],
            ).fetchone()
            if edge_row:
                record_ids.append(edge_row[0])

        if not record_ids:
            return 0

        self._delete_index_for_ids(conn, table_name, record_ids)

        placeholders = ", ".join(["?" for _ in record_ids])
        conn.execute(
            f"DELETE FROM {table_name} WHERE __id IN ({placeholders})",
            record_ids,
        )

        return len(record_ids)

    def _build_index_for_ids_sync(
        self,
        conn: Any,
        upserted_ids: dict[str, list[int]],
    ) -> dict[str, int]:
        """在事务内为变更的记录构建索引（增量更新）。

        先删除旧索引，再重建，确保 chunk 数量变化时旧索引被清理。

        Args:
            conn: 数据库连接。
            upserted_ids: 新增/更新的记录 ID。

        Returns:
            索引统计。
        """
        if not self._table_exists_in_conn(conn, SEARCH_INDEX_TABLE):
            create_index_tables = getattr(self, "create_index_tables", None)
            if create_index_tables:
                create_index_tables()
            else:
                return {}

        for node_type, ids in upserted_ids.items():
            if not ids:
                continue
            node_def = self.ontology.nodes.get(node_type)
            if node_def is None:
                continue
            table_name = node_def.table
            validate_table_name(table_name)
            placeholders = ", ".join(["?" for _ in ids])
            conn.execute(
                f"DELETE FROM {SEARCH_INDEX_TABLE} WHERE source_table = ? AND source_id IN ({placeholders})",
                [table_name] + ids,
            )

        indexed: dict[str, int] = {}

        for node_type, ids in upserted_ids.items():
            if not ids:
                continue

            node_def = self.ontology.nodes.get(node_type)
            if node_def is None:
                continue

            search_config = getattr(node_def, "search", None)
            if not search_config:
                continue

            fts_fields: list[str] = getattr(search_config, "full_text", []) or []
            vector_fields: list[str] = getattr(search_config, "vectors", []) or []
            all_fields: set[str] = set(fts_fields) | set(vector_fields)

            if not all_fields:
                continue

            table_name = node_def.table
            validate_table_name(table_name)
            fields_str = ", ".join(all_fields)
            placeholders = ", ".join(["?" for _ in ids])

            rows = conn.execute(
                f"SELECT __id, {fields_str} FROM {table_name} WHERE __id IN ({placeholders})",
                ids,
            ).fetchall()

            count = 0

            for row in rows:
                source_id = row[0]
                field_values = row[1:]
                field_list = list(all_fields)

                for field_idx, field_name in enumerate(field_list):
                    content = field_values[field_idx]
                    if not content or not isinstance(content, str):
                        continue

                    chunks = self._chunk_text_sync(content)

                    for chunk_seq, chunk in enumerate(chunks):
                        content_hash = self._compute_hash_sync(chunk)

                        fts_content = None
                        if field_name in fts_fields:
                            fts_content = self._get_or_compute_fts_sync(conn, chunk, content_hash)

                        vector = None
                        if field_name in vector_fields:
                            vector = self._get_or_compute_vector_sync(conn, chunk, content_hash)

                        conn.execute(
                            f"INSERT INTO {SEARCH_INDEX_TABLE} "
                            "(source_table, source_id, source_field, chunk_seq, content, "
                            "fts_content, vector, content_hash, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                            "ON CONFLICT (source_table, source_id, source_field, chunk_seq) "
                            "DO UPDATE SET content = excluded.content, "
                            "fts_content = excluded.fts_content, "
                            "vector = excluded.vector, "
                            "content_hash = excluded.content_hash, "
                            "created_at = excluded.created_at",
                            (
                                table_name,
                                source_id,
                                field_name,
                                chunk_seq,
                                chunk,
                                fts_content,
                                vector,
                                content_hash,
                                datetime.now(UTC),
                            ),
                        )
                        count += 1

            indexed[node_type] = count

        return indexed

    def _chunk_text_sync(self, text: str) -> list[str]:
        """将文本切分为多个片段（同步版本）。

        委托给 ChunkingMixin.chunk_text 方法。

        Args:
            text: 待切分的文本。

        Returns:
            文本片段列表，空文本返回空列表。

        Raises:
            RuntimeError: ChunkingMixin 未被正确继承时抛出。
        """
        if not hasattr(self, "chunk_text"):
            raise RuntimeError("ChunkingMixin not available, check Engine MRO")
        return self.chunk_text(text)

    def _compute_hash_sync(self, text: str) -> str:
        """计算文本哈希（同步版本）。

        Args:
            text: 待哈希的文本。

        Returns:
            文本哈希值。
        """
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def _get_or_compute_fts_sync(self, conn: Any, text: str, content_hash: str) -> str:
        """获取或计算分词结果（同步版本）。

        优先从缓存获取，缓存未命中则计算并存入缓存。

        Args:
            conn: 数据库连接。
            text: 待分词文本。
            content_hash: 文本哈希。

        Returns:
            分词结果（空格分隔）。
        """
        if not self._table_exists_in_conn(conn, SEARCH_CACHE_TABLE):
            return self._segment_text_sync(text)

        row = conn.execute(
            f"SELECT fts_content FROM {SEARCH_CACHE_TABLE} WHERE content_hash = ?",
            [content_hash],
        ).fetchone()

        if row and row[0]:
            return row[0]

        fts_content = self._segment_text_sync(text)

        now = datetime.now(UTC)
        conn.execute(
            f"INSERT OR REPLACE INTO {SEARCH_CACHE_TABLE} "
            "(content_hash, fts_content, last_used, created_at) VALUES (?, ?, ?, ?)",
            [content_hash, fts_content, now, now],
        )

        return fts_content

    def _get_or_compute_vector_sync(
        self, conn: Any, text: str, content_hash: str
    ) -> list[float] | None:
        """获取或计算向量嵌入（同步版本）。

        优先从缓存获取，缓存未命中则返回 None（向量化需要异步 API）。

        Args:
            conn: 数据库连接。
            text: 待向量化文本。
            content_hash: 文本哈希。

        Returns:
            向量嵌入，如果无法同步计算则返回 None。
        """
        if not self._table_exists_in_conn(conn, SEARCH_CACHE_TABLE):
            return None

        row = conn.execute(
            f"SELECT vector FROM {SEARCH_CACHE_TABLE} WHERE content_hash = ?",
            [content_hash],
        ).fetchone()

        if row and row[0]:
            return row[0]

        return None

    def _segment_text_sync(self, text: str) -> str:
        """分词处理（同步版本）。

        Args:
            text: 待分词文本。

        Returns:
            分词结果。
        """
        if hasattr(self, "_segment_sync"):
            return self._segment_sync(text)
        return text

    async def _compute_vectors_async(
        self,
        upserted_ids: dict[str, list[int]],
    ) -> dict[str, dict[str, int]]:
        """异步计算向量嵌入。

        在事务提交后执行，为缓存未命中的内容计算向量。
        使用批量 API 提高效率。

        Args:
            upserted_ids: 需要计算向量的记录 ID。

        Returns:
            计算结果统计，包含 success 和 failed 计数。
        """
        if not hasattr(self, "embed"):
            return {}

        vector_result: dict[str, dict[str, int]] = {}

        for node_type, ids in upserted_ids.items():
            if not ids:
                continue

            node_def = self.ontology.nodes.get(node_type)
            if node_def is None:
                continue

            search_config = getattr(node_def, "search", None)
            if not search_config:
                continue

            vector_fields: list[str] = getattr(search_config, "vectors", []) or []
            if not vector_fields:
                continue

            table_name = node_def.table
            validate_table_name(table_name)
            fields_str = ", ".join(vector_fields)
            placeholders = ", ".join(["?" for _ in ids])

            records = await asyncio.to_thread(
                self._fetch_records_for_vector,
                table_name,
                fields_str,
                placeholders,
                ids,
            )

            chunks_to_embed: list[tuple[str, str, int, str, int]] = []
            for record in records:
                source_id = record[0]
                field_values = record[1:]

                for field_idx, field_name in enumerate(vector_fields):
                    content = field_values[field_idx]
                    if not content or not isinstance(content, str):
                        continue

                    text_chunks = self._chunk_text_sync(content)

                    for chunk_seq, chunk in enumerate(text_chunks):
                        content_hash = self._compute_hash_sync(chunk)

                        existing_vector = await asyncio.to_thread(
                            self._check_vector_cache,
                            content_hash,
                        )
                        if existing_vector:
                            continue

                        chunks_to_embed.append(
                            (content_hash, chunk, source_id, field_name, chunk_seq)
                        )

            if not chunks_to_embed:
                vector_result[node_type] = {"success": 0, "failed": 0}
                continue

            batch_size = 100
            success_count = 0
            failed_count = 0

            for i in range(0, len(chunks_to_embed), batch_size):
                batch = chunks_to_embed[i : i + batch_size]
                hashes = [item[0] for item in batch]
                texts = [item[1] for item in batch]
                metas = [(item[2], item[3], item[4]) for item in batch]

                try:
                    vectors = await self.embed(texts)

                    save_tasks = []
                    for j, (content_hash, vector, (source_id, field_name, chunk_seq)) in enumerate(
                        zip(hashes, vectors, metas)
                    ):
                        save_tasks.append(
                            asyncio.to_thread(
                                self._save_vector_to_cache,
                                content_hash,
                                vector,
                                table_name,
                                source_id,
                                field_name,
                                chunk_seq,
                            )
                        )

                    await asyncio.gather(*save_tasks)
                    success_count += len(batch)

                except Exception as e:
                    logger.error(f"Failed to compute vectors batch for {table_name}: {e}")
                    failed_count += len(batch)

            vector_result[node_type] = {"success": success_count, "failed": failed_count}

        return vector_result

    def _fetch_records_for_vector(
        self,
        table_name: str,
        fields_str: str,
        placeholders: str,
        ids: list[int],
    ) -> list[tuple]:
        """获取需要计算向量的记录。

        Args:
            table_name: 表名。
            fields_str: 字段列表字符串。
            placeholders: 占位符字符串。
            ids: 记录 ID 列表。

        Returns:
            记录列表。
        """
        validate_table_name(table_name)
        return self.execute_read(
            f"SELECT __id, {fields_str} FROM {table_name} WHERE __id IN ({placeholders})",
            ids,
        )

    def _check_vector_cache(self, content_hash: str) -> list[float] | None:
        """检查向量缓存。

        Args:
            content_hash: 内容哈希。

        Returns:
            缓存的向量，如果不存在则返回 None。
        """
        rows = self.execute_read(
            f"SELECT vector FROM {SEARCH_CACHE_TABLE} WHERE content_hash = ?",
            [content_hash],
        )
        return rows[0][0] if rows else None

    def _save_vector_to_cache(
        self,
        content_hash: str,
        vector: list[float],
        table_name: str,
        source_id: int,
        field_name: str,
        chunk_seq: int,
    ) -> None:
        """保存向量到缓存并更新索引。

        使用事务确保缓存和索引的一致性。

        Args:
            content_hash: 内容哈希。
            vector: 向量嵌入。
            table_name: 表名。
            source_id: 源记录 ID。
            field_name: 字段名。
            chunk_seq: 分片序号。
        """
        validate_table_name(table_name)
        now = datetime.now(UTC)

        with self.write_transaction() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO {SEARCH_CACHE_TABLE} "
                "(content_hash, vector, last_used, created_at) VALUES (?, ?, ?, ?)",
                [content_hash, vector, now, now],
            )
            conn.execute(
                f"UPDATE {SEARCH_INDEX_TABLE} SET vector = ? "
                f"WHERE source_table = ? AND source_id = ? AND "
                f"source_field = ? AND chunk_seq = ?",
                [vector, table_name, source_id, field_name, chunk_seq],
            )

    async def _dump_to_shadow_dir(
        self,
        upserted_ids: dict[str, list[int]],
        deleted_ids: dict[str, list[int]],
    ) -> dict[str, int]:
        """导出数据到影子目录。

        导出所有节点类型和边类型的数据，确保原子替换后数据完整。

        Args:
            upserted_ids: 新增/更新的 ID 列表。
            deleted_ids: 删除的 ID 列表。

        Returns:
            导出统计。
        """
        data_dir = self.config.storage.data_dir
        shadow_dir = data_dir.parent / f"{data_dir.name}_shadow"

        def _prepare_shadow_dir() -> None:
            if shadow_dir.exists():
                shutil.rmtree(shadow_dir)
            shadow_dir.mkdir(parents=True)

        await asyncio.to_thread(_prepare_shadow_dir)

        dumped: dict[str, int] = {}

        for node_type, node_def in self.ontology.nodes.items():
            output_dir = shadow_dir / "nodes" / node_def.table
            count = await self.dump_table(
                table_name=node_def.table,
                output_dir=output_dir,
                partition_by_date=self.config.storage.partition_by_date,
                max_rows_per_file=self.config.storage.max_rows_per_file,
            )
            if count > 0:
                dumped[node_type] = count

        for edge_name in self.ontology.edges.keys():
            table_name = f"edge_{edge_name}"
            output_dir = shadow_dir / "edges" / edge_name.lower()
            count = await self.dump_table(
                table_name=table_name,
                output_dir=output_dir,
                partition_by_date=self.config.storage.partition_by_date,
                max_rows_per_file=self.config.storage.max_rows_per_file,
            )
            if count > 0:
                dumped[edge_name] = count

        cache_count = await self._dump_cache_to_parquet(shadow_dir)
        if cache_count > 0:
            dumped["_sys_search_cache"] = cache_count

        return dumped

    async def _dump_cache_to_parquet(self, shadow_dir: Path) -> int:
        """导出搜索缓存到 Parquet 文件。

        Args:
            shadow_dir: 影子目录路径。

        Returns:
            导出的缓存条目数。
        """
        cache_dir = shadow_dir / "cache"
        await asyncio.to_thread(cache_dir.mkdir, parents=True, exist_ok=True)
        cache_path = cache_dir / "search_cache.parquet"

        def _execute_dump() -> int:
            rows = self.execute_read(f"SELECT COUNT(*) FROM {SEARCH_CACHE_TABLE}")
            count = rows[0][0] if rows else 0

            if count == 0:
                return 0

            self.execute_write(f"COPY {SEARCH_CACHE_TABLE} TO '{cache_path}' (FORMAT PARQUET)")
            return count

        return await asyncio.to_thread(_execute_dump)

    async def _atomic_replace_data_dir(self) -> None:
        """原子替换 data/ 目录。

        使用操作系统级别的 rename 操作，确保原子性。
        使用时间戳 + UUID 命名 backup 目录，避免删除操作带来的竞态条件。
        """
        data_dir = self.config.storage.data_dir
        shadow_dir = data_dir.parent / f"{data_dir.name}_shadow"
        timestamp = int(datetime.now(UTC).timestamp() * 1000000)
        backup_dir = data_dir.parent / f"{data_dir.name}_backup_{timestamp}_{uuid.uuid4().hex[:8]}"

        def _replace() -> None:
            if data_dir.exists():
                os.rename(str(data_dir), str(backup_dir))

            os.rename(str(shadow_dir), str(data_dir))

            try:
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
            except Exception as e:
                logger.warning(f"Failed to cleanup backup directory: {e}")

        await asyncio.to_thread(_replace)
