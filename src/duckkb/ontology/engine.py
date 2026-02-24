"""本体引擎模块。

本模块负责本体的加载、验证和 DDL 生成，包括：
- 从配置加载本体定义
- JSON Schema 到 DuckDB 类型映射
- 节点表 DDL 生成
"""

from typing import Any

from duckkb.logger import logger
from duckkb.ontology._models import NodeType, Ontology

JSON_TO_DUCKDB_TYPE_MAP = {
    "string": "VARCHAR",
    "integer": "INTEGER",
    "number": "DOUBLE",
    "boolean": "BOOLEAN",
    "array": "JSON",
    "object": "JSON",
    "null": "VARCHAR",
}


class OntologyEngine:
    """本体引擎类。

    负责本体的加载、验证和 DDL 生成。

    Attributes:
        ontology: 本体定义实例。
    """

    def __init__(self, ontology: Ontology):
        """初始化本体引擎。

        Args:
            ontology: 本体定义实例。
        """
        self.ontology = ontology

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

    @staticmethod
    def _generate_node_ddl(node_name: str, node_type: NodeType) -> str:
        """根据节点定义生成 DDL 语句。

        Args:
            node_name: 节点类型名称。
            node_type: 节点类型定义。

        Returns:
            CREATE TABLE DDL 语句。
        """
        columns = []

        schema = node_type.json_schema
        if schema and "properties" in schema:
            for prop_name, prop_def in schema["properties"].items():
                col_type = OntologyEngine._json_type_to_duckdb(prop_def)
                columns.append(f"    {prop_name} {col_type}")

        if node_type.identity:
            pk_str = ", ".join(node_type.identity)
            columns.append(f"    PRIMARY KEY ({pk_str})")

        if not columns:
            logger.warning(f"Node {node_name} has no columns defined")
            return ""

        columns_str = ",\n".join(columns)
        return f"CREATE TABLE IF NOT EXISTS {node_type.table} (\n{columns_str}\n);"

    def get_node_tables(self) -> dict[str, str]:
        """获取所有节点表名映射。

        Returns:
            节点类型名称到表名的映射字典。
        """
        return {name: node.table for name, node in self.ontology.nodes.items()}

    def get_node_by_table(self, table_name: str) -> NodeType | None:
        """根据表名获取节点类型定义。

        Args:
            table_name: 数据库表名。

        Returns:
            节点类型定义，若未找到则返回 None。
        """
        for node_type in self.ontology.nodes.values():
            if node_type.table == table_name:
                return node_type
        return None

    def generate_ddl(self) -> str:
        """生成所有节点表的 DDL 语句。

        Returns:
            所有节点表的 DDL 语句。
        """
        if not self.ontology.nodes:
            return ""

        ddl_statements = []
        for node_name, node_type in self.ontology.nodes.items():
            ddl = self._generate_node_ddl(node_name, node_type)
            if ddl:
                ddl_statements.append(ddl)

        return "\n\n".join(ddl_statements)

    def get_vector_fields(self, node_name: str) -> dict[str, Any] | None:
        """获取节点的向量字段定义。

        Args:
            node_name: 节点类型名称。

        Returns:
            向量字段定义字典，若无则返回 None。
        """
        node_type = self.ontology.nodes.get(node_name)
        if node_type and node_type.vectors:
            return node_type.vectors
        return None

    def has_vectors(self) -> bool:
        """检查本体是否定义了向量字段。

        Returns:
            若存在向量字段定义则返回 True。
        """
        for node_type in self.ontology.nodes.values():
            if node_type.vectors:
                return True
        return False
