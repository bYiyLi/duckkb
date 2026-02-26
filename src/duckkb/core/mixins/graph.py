"""知识图谱检索 Mixin。"""

import asyncio
from typing import Any

from duckkb.constants import validate_table_name
from duckkb.core.base import BaseEngine
from duckkb.core.models.ontology import EdgeType
from duckkb.exceptions import InvalidDirectionError, NodeNotFoundError
from duckkb.logger import logger

VALID_DIRECTIONS = {"out", "in", "both"}


class GraphMixin(BaseEngine):
    """知识图谱检索 Mixin。

    提供基于边表的图遍历和查询能力。
    依赖 execute_read/write (DBMixin) 和 ontology (OntologyMixin)。

    Attributes:
        _node_id_cache: 节点 ID 缓存，用于 identity 到 __id 的映射。
    """

    def __init__(self, *args, **kwargs) -> None:
        """初始化图谱 Mixin。"""
        super().__init__(*args, **kwargs)
        self._node_id_cache: dict[tuple[str, str], int] = {}

    async def get_neighbors(
        self,
        node_type: str,
        node_id: int | str,
        *,
        edge_types: list[str] | None = None,
        direction: str = "both",
        limit: int = 100,
    ) -> dict[str, Any]:
        """获取节点的邻居节点。

        Args:
            node_type: 起始节点类型名称。
            node_id: 起始节点 ID（__id）或 identity 字段值。
            edge_types: 边类型过滤列表，None 表示所有边类型。
            direction: 遍历方向，可选值：
                - "out": 仅出边（从起始节点指向目标节点）
                - "in": 仅入边（从目标节点指向起始节点）
                - "both": 双向（默认）
            limit: 每种边类型返回的最大邻居数。

        Returns:
            包含节点信息和邻居列表的字典。

        Raises:
            ValueError: 节点类型不存在。
            NodeNotFoundError: 节点不存在。
            InvalidDirectionError: 方向参数无效。
        """
        if direction not in VALID_DIRECTIONS:
            raise InvalidDirectionError(direction)

        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        resolved_id = await self._resolve_node_id(node_type, node_id)
        node_data = await self._get_node_data(node_def.table, resolved_id)
        if node_data is None:
            raise NodeNotFoundError(node_type, node_id)

        edges_to_query = self._get_edges_for_node(node_type, direction)
        if edge_types:
            edges_to_query = [
                (name, from_type, to_type)
                for name, from_type, to_type in edges_to_query
                if name in edge_types
            ]

        all_neighbors: list[dict[str, Any]] = []
        stats_by_edge_type: dict[str, int] = {}

        for edge_name, from_node_type, to_node_type in edges_to_query:
            edge_def = self.ontology.edges.get(edge_name)
            if edge_def is None:
                continue

            neighbors = await self._query_neighbors(
                edge_name=edge_name,
                edge_def=edge_def,
                node_id=resolved_id,
                direction=direction,
                limit=limit,
                from_node_type=from_node_type,
                to_node_type=to_node_type,
            )
            all_neighbors.extend(neighbors)
            stats_by_edge_type[edge_name] = len(neighbors)

        return {
            "node": node_data,
            "neighbors": all_neighbors,
            "stats": {
                "total_count": len(all_neighbors),
                "by_edge_type": stats_by_edge_type,
            },
        }

    async def graph_search(
        self,
        query: str,
        *,
        node_type: str | None = None,
        edge_types: list[str] | None = None,
        direction: str = "both",
        traverse_depth: int = 1,
        search_limit: int = 5,
        neighbor_limit: int = 10,
        alpha: float = 0.5,
    ) -> list[dict[str, Any]]:
        """向量检索 + 图遍历融合检索。

        流程：
        1. 使用混合检索（向量+全文）找到语义相关的种子节点
        2. 对每个种子节点进行图遍历扩展
        3. 返回种子节点及其关联上下文

        Args:
            query: 查询文本。
            node_type: 种子节点类型过滤，None 表示所有类型。
            edge_types: 遍历边类型过滤，None 表示所有边类型。
            direction: 图遍历方向，"out" | "in" | "both"。
            traverse_depth: 图遍历深度，默认 1。
            search_limit: 向量检索返回的种子节点数，默认 5。
            neighbor_limit: 每个种子节点的邻居数限制，默认 10。
            alpha: 向量搜索权重（传递给混合检索）。

        Returns:
            包含种子节点和上下文的结果列表。

        Raises:
            InvalidDirectionError: 方向参数无效。
        """
        if direction not in VALID_DIRECTIONS:
            raise InvalidDirectionError(direction)

        if not query:
            return []

        search_results = await self.search(
            query,
            node_type=node_type,
            limit=search_limit,
            alpha=alpha,
        )

        results: list[dict[str, Any]] = []

        for search_result in search_results:
            source_table = search_result.get("source_table")
            source_id = search_result.get("source_id")

            if source_table is None or source_id is None:
                continue

            node_type_name = self._get_node_type_by_table(source_table)
            if node_type_name is None:
                continue

            try:
                node_data = await self._get_node_data(source_table, source_id)
                if node_data is None:
                    continue

                context = await self._get_context_recursive(
                    node_type=node_type_name,
                    node_id=source_id,
                    edge_types=edge_types,
                    direction=direction,
                    depth=traverse_depth,
                    neighbor_limit=neighbor_limit,
                    visited=None,
                )

                results.append(
                    {
                        "seed": {
                            "node_type": node_type_name,
                            "node": node_data,
                            "score": search_result.get("score"),
                            "source_field": search_result.get("source_field"),
                            "content": search_result.get("content"),
                        },
                        "context": context,
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to get context for node {source_id}: {e}")
                continue

        return results

    async def _resolve_node_id(
        self,
        node_type: str,
        node_id: int | str,
    ) -> int:
        """解析节点 ID，支持 __id 或 identity 字段值。

        Args:
            node_type: 节点类型名称。
            node_id: 节点 ID（整数）或 identity 字段值（字符串）。

        Returns:
            解析后的 __id 值。

        Raises:
            NodeNotFoundError: 节点不存在。
        """
        if isinstance(node_id, int):
            return node_id

        cache_key = (node_type, str(node_id))
        if cache_key in self._node_id_cache:
            return self._node_id_cache[cache_key]

        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        identity_fields = node_def.identity
        if not identity_fields:
            raise ValueError(f"Node type {node_type} has no identity fields")

        identity_field = identity_fields[0]
        table_name = node_def.table
        validate_table_name(table_name)

        def _fetch_id() -> int | None:
            rows = self.execute_read(
                f"SELECT __id FROM {table_name} WHERE {identity_field} = ?",
                [str(node_id)],
            )
            return rows[0][0] if rows else None

        resolved_id = await asyncio.to_thread(_fetch_id)
        if resolved_id is None:
            raise NodeNotFoundError(node_type, node_id)

        self._node_id_cache[cache_key] = resolved_id
        return resolved_id

    def _get_edges_for_node(
        self,
        node_type: str,
        direction: str,
    ) -> list[tuple[str, str, str]]:
        """获取与节点类型相关的边信息。

        Args:
            node_type: 节点类型名称。
            direction: 遍历方向。

        Returns:
            [(edge_name, from_node_type, to_node_type), ...]
        """
        edges: list[tuple[str, str, str]] = []

        for edge_name, edge_def in self.ontology.edges.items():
            if direction in ("out", "both"):
                if edge_def.from_ == node_type:
                    edges.append((edge_name, edge_def.from_, edge_def.to))
            if direction in ("in", "both"):
                if edge_def.to == node_type:
                    edges.append((edge_name, edge_def.from_, edge_def.to))

        return edges

    async def _query_neighbors(
        self,
        edge_name: str,
        edge_def: EdgeType,
        node_id: int,
        direction: str,
        limit: int,
        from_node_type: str,
        to_node_type: str,
    ) -> list[dict[str, Any]]:
        """查询邻居节点。

        Args:
            edge_name: 边类型名称。
            edge_def: 边类型定义。
            node_id: 起始节点 ID。
            direction: 遍历方向。
            limit: 返回数量限制。
            from_node_type: 起始节点类型。
            to_node_type: 目标节点类型。

        Returns:
            邻居节点列表。
        """
        table_name = f"edge_{edge_name}"
        validate_table_name(table_name)

        from_node_def = self.ontology.nodes.get(from_node_type)
        to_node_def = self.ontology.nodes.get(to_node_type)

        if from_node_def is None or to_node_def is None:
            return []

        from_table = from_node_def.table
        to_table = to_node_def.table
        validate_table_name(from_table)
        validate_table_name(to_table)

        results: list[dict[str, Any]] = []

        if direction in ("out", "both"):
            out_neighbors = await self._query_direction(
                edge_table=table_name,
                node_table=to_table,
                node_id=node_id,
                direction="out",
                limit=limit,
                edge_name=edge_name,
            )
            results.extend(out_neighbors)

        if direction in ("in", "both"):
            in_neighbors = await self._query_direction(
                edge_table=table_name,
                node_table=from_table,
                node_id=node_id,
                direction="in",
                limit=limit,
                edge_name=edge_name,
            )
            results.extend(in_neighbors)

        return results[:limit]

    async def _query_direction(
        self,
        edge_table: str,
        node_table: str,
        node_id: int,
        direction: str,
        limit: int,
        edge_name: str,
    ) -> list[dict[str, Any]]:
        """查询单向邻居。

        Args:
            edge_table: 边表名。
            node_table: 邻居节点表名。
            node_id: 起始节点 ID。
            direction: 方向（"out" 或 "in"）。
            limit: 返回数量限制。
            edge_name: 边类型名称。

        Returns:
            邻居节点列表。
        """
        if direction == "out":
            join_condition = "e.__to_id = n.__id"
            where_condition = "e.__from_id = ?"
        else:
            join_condition = "e.__from_id = n.__id"
            where_condition = "e.__to_id = ?"

        sql = f"""
        SELECT 
            e.__id as edge_id,
            n.__id as neighbor_id,
            n.* as neighbor_data
        FROM {edge_table} e
        JOIN {node_table} n ON {join_condition}
        WHERE {where_condition}
        LIMIT ?
        """

        neighbor_node_type = self._get_node_type_by_table(node_table)

        def _execute() -> list[dict[str, Any]]:
            rows = self.execute_read(sql, [node_id, limit])
            if not rows:
                return []

            neighbors = []
            for row in rows:
                edge_id = row[0]
                neighbor_id = row[1]

                neighbor_data: dict[str, Any] = {}
                if len(row) > 2:
                    neighbor_data["__id"] = neighbor_id
                    for i in range(2, len(row)):
                        neighbor_data[f"col_{i}"] = row[i]

                neighbors.append(
                    {
                        "edge_type": edge_name,
                        "direction": direction,
                        "edge": {"__id": edge_id},
                        "node": neighbor_data,
                        "node_type": neighbor_node_type,
                    }
                )

            return neighbors

        return await asyncio.to_thread(_execute)

    async def _get_node_data(
        self,
        table_name: str,
        node_id: int,
    ) -> dict[str, Any] | None:
        """获取节点完整数据。

        Args:
            table_name: 节点表名。
            node_id: 节点 ID。

        Returns:
            节点数据字典，不存在时返回 None。
        """
        validate_table_name(table_name)

        def _fetch() -> dict[str, Any] | None:
            rows = self.execute_read(
                f"SELECT * FROM {table_name} WHERE __id = ?",
                [node_id],
            )
            if not rows:
                return None

            columns = self._get_table_columns(table_name)
            return dict(zip(columns, rows[0], strict=True))

        return await asyncio.to_thread(_fetch)

    def _get_node_type_by_table(self, table_name: str) -> str | None:
        """根据表名获取节点类型名称。

        Args:
            table_name: 表名。

        Returns:
            节点类型名称，不存在时返回 None。
        """
        for node_type, node_def in self.ontology.nodes.items():
            if node_def.table == table_name:
                return node_type
        return None

    async def _get_context_recursive(
        self,
        node_type: str,
        node_id: int,
        edge_types: list[str] | None,
        direction: str,
        depth: int,
        neighbor_limit: int,
        visited: set[int] | None,
    ) -> list[dict[str, Any]]:
        """递归获取上下文。

        Args:
            node_type: 节点类型。
            node_id: 节点 ID。
            edge_types: 边类型过滤。
            direction: 遍历方向。
            depth: 剩余深度。
            neighbor_limit: 邻居数限制。
            visited: 已访问节点集合。

        Returns:
            上下文列表。
        """
        if depth <= 0:
            return []

        if visited is None:
            visited = set()

        if node_id in visited:
            return []

        visited = visited | {node_id}

        try:
            result = await self.get_neighbors(
                node_type=node_type,
                node_id=node_id,
                edge_types=edge_types,
                direction=direction,
                limit=neighbor_limit,
            )
        except Exception:
            return []

        context: list[dict[str, Any]] = []

        for neighbor in result.get("neighbors", []):
            neighbor_node = neighbor.get("node", {})
            neighbor_id = neighbor_node.get("__id")

            if neighbor_id is None or neighbor_id in visited:
                continue

            neighbor_type_name = neighbor.get("node_type", "Unknown")

            context.append(
                {
                    "edge_type": neighbor.get("edge_type"),
                    "direction": neighbor.get("direction"),
                    "edge": neighbor.get("edge", {}),
                    "node_type": neighbor_type_name,
                    "node": neighbor_node,
                }
            )

        return context

    async def traverse(
        self,
        node_type: str,
        node_id: int | str,
        *,
        edge_types: list[str] | None = None,
        direction: str = "out",
        max_depth: int = 3,
        limit: int = 1000,
        return_paths: bool = True,
    ) -> list[dict[str, Any]]:
        """多跳图遍历。

        Args:
            node_type: 起始节点类型名称。
            node_id: 起始节点 ID 或 identity 字段值。
            edge_types: 允许的边类型列表，None 表示所有边类型。
            direction: 遍历方向，"out" | "in" | "both"。
            max_depth: 最大遍历深度，默认 3。
            limit: 返回结果数量限制，默认 1000。
            return_paths: 是否返回完整路径信息，默认 True。
                - True: 返回每条遍历路径的详细信息
                - False: 仅返回可达节点列表（去重）

        Returns:
            遍历结果列表。

        Raises:
            ValueError: 参数无效时抛出。
            NodeNotFoundError: 起始节点不存在。
            InvalidDirectionError: 方向参数无效。
        """
        if direction not in VALID_DIRECTIONS:
            raise InvalidDirectionError(direction)

        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        resolved_id = await self._resolve_node_id(node_type, node_id)
        start_node_data = await self._get_node_data(node_def.table, resolved_id)
        if start_node_data is None:
            raise NodeNotFoundError(node_type, node_id)

        if return_paths:
            return await self._traverse_with_paths(
                start_node_type=node_type,
                start_node_id=resolved_id,
                edge_types=edge_types,
                direction=direction,
                max_depth=max_depth,
                limit=limit,
            )
        else:
            return await self._traverse_nodes_only(
                start_node_type=node_type,
                start_node_id=resolved_id,
                edge_types=edge_types,
                direction=direction,
                max_depth=max_depth,
                limit=limit,
            )

    async def _traverse_with_paths(
        self,
        start_node_type: str,
        start_node_id: int,
        edge_types: list[str] | None,
        direction: str,
        max_depth: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        """带路径信息的遍历。"""
        results: list[dict[str, Any]] = []
        visited_paths: set[tuple[int, ...]] = set()

        async def _bfs(
            current_type: str,
            current_id: int,
            path: list[dict[str, Any]],
            depth: int,
        ) -> None:
            if len(results) >= limit or depth > max_depth:
                return

            neighbors_result = await self.get_neighbors(
                node_type=current_type,
                node_id=current_id,
                edge_types=edge_types,
                direction=direction,
                limit=limit,
            )

            for neighbor in neighbors_result.get("neighbors", []):
                if len(results) >= limit:
                    return

                neighbor_node = neighbor.get("node", {})
                neighbor_id = neighbor_node.get("__id")

                if neighbor_id is None:
                    continue

                path_ids = tuple(
                    n.get("__id") for n in [p.get("node", {}) for p in path] if n.get("__id")
                )
                if neighbor_id in path_ids:
                    continue

                new_path = path + [
                    {"edge_type": neighbor.get("edge_type"), "edge": neighbor.get("edge", {})},
                    {"node": neighbor_node, "node_type": neighbor.get("node_type", "Unknown")},
                ]

                path_key = tuple(
                    n.get("__id")
                    for n in [
                        p.get("node", {}) for p in new_path if isinstance(p, dict) and "node" in p
                    ]
                )
                if path_key in visited_paths:
                    continue
                visited_paths.add(path_key)

                results.append(
                    {
                        "path": new_path,
                        "depth": depth,
                        "end_node": neighbor_node,
                    }
                )

                await _bfs(
                    current_type=neighbor.get("node_type", current_type),
                    current_id=neighbor_id,
                    path=new_path,
                    depth=depth + 1,
                )

        start_node = {
            "node": await self._get_node_data(
                self.ontology.nodes[start_node_type].table,
                start_node_id,
            )
            or {},
            "node_type": start_node_type,
        }

        await _bfs(start_node_type, start_node_id, [start_node], 1)
        return results

    async def _traverse_nodes_only(
        self,
        start_node_type: str,
        start_node_id: int,
        edge_types: list[str] | None,
        direction: str,
        max_depth: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        """仅返回节点的遍历。"""
        visited: set[int] = {start_node_id}
        results: list[dict[str, Any]] = []
        node_depths: dict[int, int] = {start_node_id: 0}
        node_paths_count: dict[int, int] = {start_node_id: 1}

        current_level: list[tuple[str, int]] = [(start_node_type, start_node_id)]
        depth = 0

        while current_level and depth < max_depth and len(results) < limit:
            next_level: list[tuple[str, int]] = []
            depth += 1

            for node_type, node_id in current_level:
                if len(results) >= limit:
                    break

                try:
                    neighbors_result = await self.get_neighbors(
                        node_type=node_type,
                        node_id=node_id,
                        edge_types=edge_types,
                        direction=direction,
                        limit=limit,
                    )
                except Exception:
                    continue

                for neighbor in neighbors_result.get("neighbors", []):
                    neighbor_node = neighbor.get("node", {})
                    neighbor_id = neighbor_node.get("__id")

                    if neighbor_id is None or neighbor_id in visited:
                        continue

                    visited.add(neighbor_id)
                    node_depths[neighbor_id] = depth
                    node_paths_count[neighbor_id] = node_paths_count.get(node_id, 1)

                    results.append(
                        {
                            "node": neighbor_node,
                            "min_depth": depth,
                            "paths_count": node_paths_count[neighbor_id],
                        }
                    )

                    neighbor_type = neighbor.get("node_type", node_type)
                    next_level.append((neighbor_type, neighbor_id))

            current_level = next_level

        return results[:limit]

    async def extract_subgraph(
        self,
        node_type: str,
        node_id: int | str,
        *,
        edge_types: list[str] | None = None,
        max_depth: int = 2,
        node_limit: int = 100,
        edge_limit: int = 200,
    ) -> dict[str, Any]:
        """提取子图。

        Args:
            node_type: 中心节点类型名称。
            node_id: 中心节点 ID 或 identity 值。
            edge_types: 包含的边类型列表。
            max_depth: 扩展深度，默认 2。
            node_limit: 节点数量上限，默认 100。
            edge_limit: 边数量上限，默认 200。

        Returns:
            包含中心节点、节点列表、边列表和统计信息的字典。

        Raises:
            ValueError: 参数无效时抛出。
            NodeNotFoundError: 中心节点不存在。
        """
        node_def = self.ontology.nodes.get(node_type)
        if node_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        resolved_id = await self._resolve_node_id(node_type, node_id)
        center_node_data = await self._get_node_data(node_def.table, resolved_id)
        if center_node_data is None:
            raise NodeNotFoundError(node_type, node_id)

        visited_nodes: dict[int, dict[str, Any]] = {resolved_id: center_node_data}
        visited_edges: dict[int, dict[str, Any]] = {}
        node_types_map: dict[int, str] = {resolved_id: node_type}

        current_level: list[tuple[str, int]] = [(node_type, resolved_id)]
        depth = 0

        while current_level and depth < max_depth:
            next_level: list[tuple[str, int]] = []
            depth += 1

            for current_type, current_id in current_level:
                if len(visited_nodes) >= node_limit:
                    break

                try:
                    neighbors_result = await self.get_neighbors(
                        node_type=current_type,
                        node_id=current_id,
                        edge_types=edge_types,
                        direction="both",
                        limit=node_limit,
                    )
                except Exception:
                    continue

                for neighbor in neighbors_result.get("neighbors", []):
                    if len(visited_nodes) >= node_limit or len(visited_edges) >= edge_limit:
                        break

                    neighbor_node = neighbor.get("node", {})
                    neighbor_id = neighbor_node.get("__id")
                    edge_data = neighbor.get("edge", {})
                    edge_id = edge_data.get("__id")

                    if neighbor_id is not None and neighbor_id not in visited_nodes:
                        visited_nodes[neighbor_id] = neighbor_node
                        neighbor_type = neighbor.get("node_type", current_type)
                        node_types_map[neighbor_id] = neighbor_type
                        next_level.append((neighbor_type, neighbor_id))

                    if edge_id is not None and edge_id not in visited_edges:
                        visited_edges[edge_id] = {
                            "type": neighbor.get("edge_type"),
                            "__id": edge_id,
                            "__from_id": current_id,
                            "__to_id": neighbor_id,
                        }

            current_level = next_level

        nodes_list = [
            {"type": node_types_map.get(nid, "Unknown"), **ndata}
            for nid, ndata in visited_nodes.items()
            if nid != resolved_id
        ]

        edges_list = list(visited_edges.values())

        return {
            "center_node": {
                "type": node_type,
                **center_node_data,
            },
            "nodes": nodes_list,
            "edges": edges_list,
            "stats": {
                "node_count": len(visited_nodes),
                "edge_count": len(visited_edges),
                "depth_reached": depth,
                "truncated": len(visited_nodes) >= node_limit or len(visited_edges) >= edge_limit,
            },
        }

    async def find_paths(
        self,
        from_node: tuple[str, int | str],
        to_node: tuple[str, int | str],
        *,
        edge_types: list[str] | None = None,
        max_depth: int = 5,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """查找两节点间的路径。

        Args:
            from_node: 起始节点 (类型名称, ID 或 identity 值)。
            to_node: 目标节点 (类型名称, ID 或 identity 值)。
            edge_types: 允许的边类型列表。
            max_depth: 最大路径长度（边数），默认 5。
            limit: 返回路径数量限制，默认 10。

        Returns:
            路径列表。

        Raises:
            ValueError: 节点不存在或参数无效。
        """
        from_type, from_id = from_node
        to_type, to_id = to_node

        from_def = self.ontology.nodes.get(from_type)
        to_def = self.ontology.nodes.get(to_type)

        if from_def is None:
            raise ValueError(f"Unknown node type: {from_type}")
        if to_def is None:
            raise ValueError(f"Unknown node type: {to_type}")

        resolved_from_id = await self._resolve_node_id(from_type, from_id)
        resolved_to_id = await self._resolve_node_id(to_type, to_id)

        from_data = await self._get_node_data(from_def.table, resolved_from_id)
        to_data = await self._get_node_data(to_def.table, resolved_to_id)

        if from_data is None:
            raise NodeNotFoundError(from_type, from_id)
        if to_data is None:
            raise NodeNotFoundError(to_type, to_id)

        if resolved_from_id == resolved_to_id:
            return [
                {
                    "path": [{"type": from_type, **from_data}],
                    "length": 0,
                    "node_types": [from_type],
                }
            ]

        results: list[dict[str, Any]] = []
        visited_paths: set[tuple[int, ...]] = set()

        async def _dfs(
            current_type: str,
            current_id: int,
            path: list[dict[str, Any]],
            path_ids: tuple[int, ...],
            depth: int,
        ) -> None:
            if len(results) >= limit or depth > max_depth:
                return

            if current_id == resolved_to_id:
                path_key = path_ids
                if path_key not in visited_paths:
                    visited_paths.add(path_key)
                    results.append(
                        {
                            "path": path,
                            "length": len(path) // 2,
                            "node_types": [
                                p.get("type") or p.get("node_type")
                                for p in path
                                if "node" in p or "type" in p
                            ],
                        }
                    )
                return

            try:
                neighbors_result = await self.get_neighbors(
                    node_type=current_type,
                    node_id=current_id,
                    edge_types=edge_types,
                    direction="both",
                    limit=limit * 2,
                )
            except Exception:
                return

            for neighbor in neighbors_result.get("neighbors", []):
                neighbor_node = neighbor.get("node", {})
                neighbor_id = neighbor_node.get("__id")

                if neighbor_id is None or neighbor_id in path_ids:
                    continue

                neighbor_type = neighbor.get("node_type", current_type)

                new_path = path + [
                    {"edge_type": neighbor.get("edge_type"), "edge": neighbor.get("edge", {})},
                    {"type": neighbor_type, **neighbor_node},
                ]

                new_path_ids = path_ids + (neighbor_id,)

                await _dfs(
                    current_type=neighbor_type,
                    current_id=neighbor_id,
                    path=new_path,
                    path_ids=new_path_ids,
                    depth=depth + 1,
                )

        start_path = [{"type": from_type, **from_data}]
        await _dfs(from_type, resolved_from_id, start_path, (resolved_from_id,), 0)

        results.sort(key=lambda x: x["length"])
        return results[:limit]
