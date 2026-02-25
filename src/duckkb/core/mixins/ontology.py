"""本体管理 Mixin。"""

from typing import Any

from duckkb.core.base import BaseEngine
from duckkb.database.engine.ontology import EdgeType, NodeType, Ontology
from duckkb.logger import logger

JSON_TO_DUCKDB_TYPE_MAP = {
    "string": "VARCHAR",
    "integer": "BIGINT",
    "number": "DOUBLE",
    "boolean": "BOOLEAN",
    "array": "JSON",
    "object": "JSON",
    "null": "VARCHAR",
}


class OntologyMixin(BaseEngine):
    """本体管理 Mixin。

    负责本体定义的加载和 DDL 生成。

    Attributes:
        ontology: 本体定义。
    """

    def __init__(self, *args, **kwargs) -> None:
        """初始化本体 Mixin。"""
        super().__init__(*args, **kwargs)
        self._ontology: Ontology | None = None

    @property
    def ontology(self) -> Ontology:
        """本体定义（懒加载，从 config 读取）。"""
        if self._ontology is None:
            self._ontology = self.kb_config.ontology
        return self._ontology

    def sync_schema(self) -> None:
        """同步表结构到数据库。

        根据本体定义创建所有节点表和边表。如果表已存在则跳过。
        """
        for _node_name, node_type in self.ontology.nodes.items():
            ddl = self._generate_node_ddl(node_type)
            logger.debug(f"Creating node table: {node_type.table}")
            self.conn.execute(ddl)

        for edge_name, edge_type in self.ontology.edges.items():
            table_name = f"edge_{edge_name}"
            ddl = self._generate_edge_ddl(edge_name, edge_type)
            logger.debug(f"Creating edge table: {table_name}")
            self.conn.execute(ddl)

        logger.info(f"Schema synced: {len(self.ontology.nodes)} nodes, {len(self.ontology.edges)} edges")

    @staticmethod
    def _json_type_to_duckdb(prop_def: dict[str, Any]) -> str:
        """将 JSON Schema 类型映射到 DuckDB 类型。

        Args:
            prop_def: JSON Schema 属性定义。

        Returns:
            DuckDB 类型字符串。
        """
        json_type = prop_def.get("type", "string")
        duckdb_type = JSON_TO_DUCKDB_TYPE_MAP.get(json_type, "VARCHAR")

        if prop_def.get("format") == "date-time":
            duckdb_type = "TIMESTAMP"
        elif prop_def.get("format") == "date":
            duckdb_type = "DATE"
        elif prop_def.get("format") == "time":
            duckdb_type = "TIME"

        return duckdb_type

    def _generate_node_ddl(self, node_type: NodeType) -> str:
        """生成节点表 DDL。

        表结构：
        - __id BIGINT PRIMARY KEY (主键)
        - __date DATE (分区日期字段，从 __updated_at 派生)
        - __updated_at TIMESTAMP
        - 其他字段根据 json_schema 推断

        Args:
            node_type: 节点类型定义。

        Returns:
            CREATE TABLE IF NOT EXISTS 语句。
        """
        columns = [
            "    __id BIGINT PRIMARY KEY",
            "    __updated_at TIMESTAMP",
            "    __date DATE GENERATED ALWAYS AS (CAST(__updated_at AS DATE)) STORED",
        ]

        schema = node_type.json_schema
        if schema and "properties" in schema:
            for prop_name, prop_def in schema["properties"].items():
                col_type = self._json_type_to_duckdb(prop_def)
                columns.append(f"    {prop_name} {col_type}")

        columns_str = ",\n".join(columns)
        return f"CREATE TABLE IF NOT EXISTS {node_type.table} (\n{columns_str}\n);"

    def _generate_edge_ddl(self, edge_name: str, edge_type: EdgeType) -> str:
        """生成边表 DDL。

        表结构：
        - __id BIGINT PRIMARY KEY
        - __from_id BIGINT (起始节点ID)
        - __to_id BIGINT (目标节点ID)
        - __date DATE
        - __updated_at TIMESTAMP
        - 其他字段根据 json_schema 推断

        Args:
            edge_name: 边类型名称。
            edge_type: 边类型定义。

        Returns:
            CREATE TABLE IF NOT EXISTS 语句。
        """
        table_name = f"edge_{edge_name}"
        columns = [
            "    __id BIGINT PRIMARY KEY",
            "    __from_id BIGINT NOT NULL",
            "    __to_id BIGINT NOT NULL",
            "    __updated_at TIMESTAMP",
            "    __date DATE GENERATED ALWAYS AS (CAST(__updated_at AS DATE)) STORED",
        ]

        schema = edge_type.json_schema
        if schema and "properties" in schema:
            for prop_name, prop_def in schema["properties"].items():
                col_type = self._json_type_to_duckdb(prop_def)
                columns.append(f"    {prop_name} {col_type}")

        columns_str = ",\n".join(columns)
        return f"CREATE TABLE IF NOT EXISTS {table_name} (\n{columns_str}\n);"
