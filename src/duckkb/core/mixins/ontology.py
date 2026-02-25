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

JSON_SCHEMA_TYPE_MAP = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
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
        - __created_at TIMESTAMP (创建时间)
        - __updated_at TIMESTAMP (更新时间)
        - __date DATE (分区日期字段，从 __updated_at 派生)
        - 其他字段根据 json_schema 推断

        Args:
            node_type: 节点类型定义。

        Returns:
            CREATE TABLE IF NOT EXISTS 语句。
        """
        columns = [
            "    __id BIGINT PRIMARY KEY",
            "    __created_at TIMESTAMP",
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
        - __created_at TIMESTAMP (创建时间)
        - __updated_at TIMESTAMP (更新时间)
        - __date DATE (分区日期字段，从 __updated_at 派生)
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
            "    __created_at TIMESTAMP",
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

    def get_bundle_schema(self) -> dict[str, Any]:
        """生成知识包的完整校验 Schema。

        根据当前本体定义，动态生成 JSON Schema Draft 7 格式的校验规则。
        用于验证 import_knowledge_bundle 的输入数据。

        Returns:
            包含 full_bundle_schema 和 example_yaml 的字典。
        """
        one_of_schemas: list[dict[str, Any]] = []
        example_items: list[str] = []

        for node_name, node_def in self.ontology.nodes.items():
            one_of_schemas.append(self._generate_node_schema(node_name, node_def))
            example_items.append(self._generate_node_example(node_name, node_def))

        for edge_name, edge_def in self.ontology.edges.items():
            one_of_schemas.append(self._generate_edge_schema(edge_name, edge_def))
            example_items.append(self._generate_edge_example(edge_name, edge_def))

        full_bundle_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "DuckKB Knowledge Bundle Schema",
            "type": "array",
            "items": {
                "oneOf": one_of_schemas
            }
        }

        return {
            "full_bundle_schema": full_bundle_schema,
            "example_yaml": "\n".join(example_items)
        }

    def _generate_node_schema(
        self, node_name: str, node_def: NodeType
    ) -> dict[str, Any]:
        """生成节点类型的 JSON Schema。

        Args:
            node_name: 节点类型名称。
            node_def: 节点定义。

        Returns:
            JSON Schema 字典。
        """
        required = ["type"] + node_def.identity
        properties: dict[str, Any] = {
            "type": {"const": node_name},
            "action": {
                "type": "string",
                "enum": ["upsert", "delete"],
                "default": "upsert"
            }
        }

        if node_def.json_schema and "properties" in node_def.json_schema:
            for prop_name, prop_def in node_def.json_schema["properties"].items():
                properties[prop_name] = self._prop_to_json_schema(prop_def)

        return {
            "title": f"{node_name} Node",
            "type": "object",
            "required": required,
            "properties": properties,
            "additionalProperties": False
        }

    def _generate_edge_schema(
        self, edge_name: str, edge_def: EdgeType
    ) -> dict[str, Any]:
        """生成边类型的 JSON Schema。

        Args:
            edge_name: 边类型名称。
            edge_def: 边定义。

        Returns:
            JSON Schema 字典。
        """
        source_node = self.ontology.nodes.get(edge_def.from_)
        target_node = self.ontology.nodes.get(edge_def.to)

        if source_node is None or target_node is None:
            return {}

        source_props = {
            f: {"type": "string"}
            for f in source_node.identity
        }
        target_props = {
            f: {"type": "string"}
            for f in target_node.identity
        }

        properties: dict[str, Any] = {
            "type": {"const": edge_name},
            "action": {
                "type": "string",
                "enum": ["upsert", "delete"],
                "default": "upsert"
            },
            "source": {
                "type": "object",
                "required": list(source_props.keys()),
                "properties": source_props
            },
            "target": {
                "type": "object",
                "required": list(target_props.keys()),
                "properties": target_props
            }
        }

        if edge_def.json_schema and "properties" in edge_def.json_schema:
            for prop_name, prop_def in edge_def.json_schema["properties"].items():
                properties[prop_name] = self._prop_to_json_schema(prop_def)

        return {
            "title": f"{edge_name} Edge",
            "type": "object",
            "required": ["type", "source", "target"],
            "properties": properties,
            "additionalProperties": False
        }

    def _prop_to_json_schema(self, prop_def: dict[str, Any]) -> dict[str, Any]:
        """将属性定义转换为 JSON Schema 格式。

        Args:
            prop_def: 属性定义。

        Returns:
            JSON Schema 属性定义。
        """
        json_type = prop_def.get("type", "string")
        schema_type = JSON_SCHEMA_TYPE_MAP.get(json_type, "string")

        result: dict[str, Any] = {"type": schema_type}

        if "description" in prop_def:
            result["description"] = prop_def["description"]

        if prop_def.get("format"):
            result["format"] = prop_def["format"]

        return result

    def _generate_node_example(self, node_name: str, node_def: NodeType) -> str:
        """生成节点类型的 YAML 示例。

        Args:
            node_name: 节点类型名称。
            node_def: 节点定义。

        Returns:
            YAML 格式的示例字符串。
        """
        lines = [f"- type: {node_name}"]
        for identity_field in node_def.identity:
            lines.append(f'  {identity_field}: "your-{identity_field}"')

        if node_def.json_schema and "properties" in node_def.json_schema:
            for prop_name in node_def.json_schema["properties"]:
                if prop_name not in node_def.identity:
                    lines.append(f'  {prop_name}: "..."')

        return "\n".join(lines)

    def _generate_edge_example(self, edge_name: str, edge_def: EdgeType) -> str:
        """生成边类型的 YAML 示例。

        Args:
            edge_name: 边类型名称。
            edge_def: 边定义。

        Returns:
            YAML 格式的示例字符串。
        """
        source_node = self.ontology.nodes.get(edge_def.from_)
        target_node = self.ontology.nodes.get(edge_def.to)

        if source_node is None or target_node is None:
            return ""

        lines = [f"- type: {edge_name}"]

        source_fields = ", ".join(
            f'{f}: "source-{f}"' for f in source_node.identity
        )
        lines.append(f"  source: {{{source_fields}}}")

        target_fields = ", ".join(
            f'{f}: "target-{f}"' for f in target_node.identity
        )
        lines.append(f"  target: {{{target_fields}}}")

        if edge_def.json_schema and "properties" in edge_def.json_schema:
            for prop_name in edge_def.json_schema["properties"]:
                lines.append(f'  {prop_name}: "..."')

        return "\n".join(lines)
