"""本体管理 Mixin。"""

import json
from typing import Any

from duckkb.core.base import BaseEngine
from duckkb.core.models.ontology import EdgeIndexConfig, EdgeType, NodeType, Ontology
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

SYSTEM_TABLES_DDL = {
    "_sys_search_index": """CREATE TABLE IF NOT EXISTS _sys_search_index (
    source_table VARCHAR NOT NULL,
    source_id BIGINT NOT NULL,
    source_field VARCHAR NOT NULL,
    chunk_seq INTEGER NOT NULL DEFAULT 0,
    content VARCHAR,
    fts_content VARCHAR,
    vector FLOAT[],
    content_hash VARCHAR,
    created_at TIMESTAMP,
    PRIMARY KEY (source_table, source_id, source_field, chunk_seq)
);""",
    "_sys_search_cache": """CREATE TABLE IF NOT EXISTS _sys_search_cache (
    content_hash VARCHAR PRIMARY KEY,
    fts_content VARCHAR,
    vector FLOAT[],
    last_used TIMESTAMP,
    created_at TIMESTAMP
);""",
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
            self.execute_write(ddl)

        for edge_name, edge_type in self.ontology.edges.items():
            table_name = f"edge_{edge_name}"
            ddl = self._generate_edge_ddl(edge_name, edge_type)
            logger.debug(f"Creating edge table: {table_name}")
            self.execute_write(ddl)

        logger.info(
            f"Schema synced: {len(self.ontology.nodes)} nodes, {len(self.ontology.edges)} edges"
        )

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
        - 其他字段根据 json_schema 推断

        Args:
            edge_name: 边类型名称。
            edge_type: 边类型定义。

        Returns:
            CREATE TABLE IF NOT EXISTS 语句及索引语句。
        """
        table_name = f"edge_{edge_name}"
        columns = [
            "    __id BIGINT PRIMARY KEY",
            "    __from_id BIGINT NOT NULL",
            "    __to_id BIGINT NOT NULL",
            "    __created_at TIMESTAMP",
            "    __updated_at TIMESTAMP",
        ]

        schema = edge_type.json_schema
        if schema and "properties" in schema:
            for prop_name, prop_def in schema["properties"].items():
                col_type = self._json_type_to_duckdb(prop_def)
                columns.append(f"    {prop_name} {col_type}")

        columns_str = ",\n".join(columns)
        ddl = f"CREATE TABLE IF NOT EXISTS {table_name} (\n{columns_str}\n);"

        index_config = edge_type.index or EdgeIndexConfig()
        index_statements = []
        if index_config.from_indexed:
            index_statements.append(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_from ON {table_name}(__from_id);"
            )
        if index_config.to_indexed:
            index_statements.append(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_to ON {table_name}(__to_id);"
            )

        if index_statements:
            ddl = ddl + "\n" + "\n".join(index_statements)

        return ddl

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
            "items": {"oneOf": one_of_schemas},
        }

        return {"full_bundle_schema": full_bundle_schema, "example_yaml": "\n".join(example_items)}

    def _generate_node_schema(self, node_name: str, node_def: NodeType) -> dict[str, Any]:
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
            "action": {"type": "string", "enum": ["upsert", "delete"], "default": "upsert"},
        }

        if node_def.json_schema and "properties" in node_def.json_schema:
            for prop_name, prop_def in node_def.json_schema["properties"].items():
                properties[prop_name] = self._prop_to_json_schema(prop_def)

        return {
            "title": f"{node_name} Node",
            "type": "object",
            "required": required,
            "properties": properties,
            "additionalProperties": False,
        }

    def _generate_edge_schema(self, edge_name: str, edge_def: EdgeType) -> dict[str, Any]:
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

        source_props = {f: {"type": "string"} for f in source_node.identity}
        target_props = {f: {"type": "string"} for f in target_node.identity}

        properties: dict[str, Any] = {
            "type": {"const": edge_name},
            "action": {"type": "string", "enum": ["upsert", "delete"], "default": "upsert"},
            "source": {
                "type": "object",
                "required": list(source_props.keys()),
                "properties": source_props,
            },
            "target": {
                "type": "object",
                "required": list(target_props.keys()),
                "properties": target_props,
            },
        }

        if edge_def.json_schema and "properties" in edge_def.json_schema:
            for prop_name, prop_def in edge_def.json_schema["properties"].items():
                properties[prop_name] = self._prop_to_json_schema(prop_def)

        return {
            "title": f"{edge_name} Edge",
            "type": "object",
            "required": ["type", "source", "target"],
            "properties": properties,
            "additionalProperties": False,
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

        source_fields = ", ".join(f'{f}: "source-{f}"' for f in source_node.identity)
        lines.append(f"  source: {{{source_fields}}}")

        target_fields = ", ".join(f'{f}: "target-{f}"' for f in target_node.identity)
        lines.append(f"  target: {{{target_fields}}}")

        if edge_def.json_schema and "properties" in edge_def.json_schema:
            for prop_name in edge_def.json_schema["properties"]:
                lines.append(f'  {prop_name}: "..."')

        return "\n".join(lines)

    def get_info(self) -> str:
        """生成知识库信息的 Markdown 文档。

        返回包含使用说明、导入格式、表结构和知识图谱关系的完整信息。

        Returns:
            Markdown 格式的知识库信息文档。
        """
        sections = [
            "# 知识库介绍\n",
            self._format_usage_instructions(),
            self._format_import_schema_as_markdown(),
            "## 表结构\n",
            self._format_node_tables_as_markdown(),
            self._format_edge_tables_as_markdown(),
            self._format_system_tables_as_markdown(),
            "## 知识图谱关系\n",
            self._format_relationship_table(),
            "### 关系图\n",
            f"```mermaid\n{self._generate_mermaid_knowledge_graph()}\n```",
        ]
        return "\n".join(sections)

    def _format_usage_instructions(self) -> str:
        """格式化使用说明。

        Returns:
            使用说明的 Markdown 片段。
        """
        instructions = self.kb_config.usage_instructions or "暂无使用说明。"
        return f"## 使用说明\n\n{instructions}\n"

    def _format_import_schema_as_markdown(self) -> str:
        """格式化导入数据格式为 Markdown。

        Returns:
            导入数据格式的 Markdown 片段。
        """
        bundle_schema = self.get_bundle_schema()
        schema_json = json.dumps(bundle_schema["full_bundle_schema"], ensure_ascii=False, indent=2)
        example_yaml = bundle_schema["example_yaml"]

        return f"""## 导入数据格式

### JSON Schema

```json
{schema_json}
```

### YAML 示例

```yaml
{example_yaml}
```
"""

    def _format_node_tables_as_markdown(self) -> str:
        """格式化节点表结构为 Markdown。

        Returns:
            节点表结构的 Markdown 片段。
        """
        sections = ["### 节点表\n"]
        for node_name, node_def in self.ontology.nodes.items():
            ddl = self._generate_node_ddl(node_def)
            sections.append(f"#### {node_name} ({node_def.table})\n\n```sql\n{ddl}\n```\n")
        return "\n".join(sections)

    def _format_edge_tables_as_markdown(self) -> str:
        """格式化边表结构为 Markdown。

        Returns:
            边表结构的 Markdown 片段。
        """
        if not self.ontology.edges:
            return ""

        sections = ["### 边表\n"]
        for edge_name, edge_def in self.ontology.edges.items():
            table_name = f"edge_{edge_name}"
            ddl = self._generate_edge_ddl(edge_name, edge_def)
            sections.append(f"#### {edge_name} ({table_name})\n\n```sql\n{ddl}\n```\n")
        return "\n".join(sections)

    def _format_system_tables_as_markdown(self) -> str:
        """格式化系统表结构为 Markdown。

        Returns:
            系统表结构的 Markdown 片段。
        """
        sections = ["### 系统表\n"]
        for table_name, ddl in SYSTEM_TABLES_DDL.items():
            sections.append(f"#### {table_name}\n\n```sql\n{ddl}\n```\n")
        return "\n".join(sections)

    def _format_relationship_table(self) -> str:
        """生成关系详情表格。

        Returns:
            关系详情的 Markdown 表格。
        """
        if not self.ontology.edges:
            return "暂无边定义。\n"

        lines = [
            "### 关系详情\n",
            "| 边名称 | 起始节点 | 目标节点 | 基数 | 起始节点标识 | 目标节点标识 |",
            "|--------|----------|----------|------|--------------|--------------|",
        ]

        for edge_name, edge_def in self.ontology.edges.items():
            from_node = edge_def.from_
            to_node = edge_def.to
            cardinality = edge_def.cardinality or "N:N"

            from_identity = ", ".join(self.ontology.nodes[from_node].identity)
            to_identity = ", ".join(self.ontology.nodes[to_node].identity)

            lines.append(
                f"| {edge_name} | {from_node} | {to_node} | {cardinality} | "
                f"{from_identity} | {to_identity} |"
            )

        return "\n".join(lines)

    def _generate_mermaid_knowledge_graph(self) -> str:
        """生成知识图谱关系的 Mermaid 图。

        Returns:
            Mermaid 图代码。
        """
        if not self.ontology.edges:
            return "graph LR\n    暂无边定义"

        lines = ["graph LR"]

        for edge_name, edge_def in self.ontology.edges.items():
            from_node = edge_def.from_
            to_node = edge_def.to
            cardinality = edge_def.cardinality or "N:N"

            from_identity = ", ".join(self.ontology.nodes[from_node].identity)
            to_identity = ", ".join(self.ontology.nodes[to_node].identity)

            label = f"{edge_name}<br/>{cardinality}<br/>{from_identity}→{to_identity}"

            lines.append(f'    {from_node} -- "{label}" --> {to_node}')

        return "\n".join(lines)
