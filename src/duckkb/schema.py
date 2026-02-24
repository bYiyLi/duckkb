"""数据库模式管理模块。

本模块负责数据库模式的初始化和元信息查询，包括：
- 系统表（搜索表、缓存表）的 DDL 定义
- 本体定义的用户表 DDL 生成
- ER 图生成
"""

import asyncio
import re

from duckkb.config import AppContext
from duckkb.constants import SCHEMA_FILE_NAME, SYS_CACHE_TABLE, SYS_SEARCH_TABLE
from duckkb.db import get_async_db
from duckkb.logger import logger
from duckkb.ontology import OntologyEngine


def get_sys_schema_ddl(embedding_dim: int) -> str:
    """生成系统表的 DDL 语句。

    Args:
        embedding_dim: 嵌入向量维度。

    Returns:
        包含搜索表和缓存表 DDL 的 SQL 字符串。
    """
    return f"""
CREATE TABLE IF NOT EXISTS {SYS_SEARCH_TABLE} (
    ref_id VARCHAR,
    source_table VARCHAR,
    source_field VARCHAR,
    segmented_text TEXT,
    embedding_id VARCHAR,
    embedding FLOAT[{embedding_dim}],
    metadata JSON,
    priority_weight FLOAT DEFAULT 1.0,
    PRIMARY KEY (ref_id, source_table, source_field)
);

CREATE INDEX IF NOT EXISTS idx_vec ON {SYS_SEARCH_TABLE} USING HNSW (embedding) WITH (metric = 'cosine');

CREATE TABLE IF NOT EXISTS {SYS_CACHE_TABLE} (
    content_hash VARCHAR PRIMARY KEY,
    embedding FLOAT[{embedding_dim}],
    last_used TIMESTAMP
);
"""


def _parse_table_definitions(sql: str) -> list[dict]:
    """解析 CREATE TABLE 语句提取表信息用于生成 ER 图。

    Args:
        sql: SQL DDL 语句字符串。

    Returns:
        包含表定义信息的字典列表，每个字典包含表名、列、主键和外键。
    """
    tables = []
    table_pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(]+)\s*\(([^;]+)\)",
        re.IGNORECASE | re.DOTALL,
    )

    for match in table_pattern.finditer(sql):
        table_name = match.group(1).strip().strip('"').strip("'")
        columns_str = match.group(2)

        columns = []
        primary_keys = []
        foreign_keys = []

        for line in columns_str.split(","):
            line = line.strip()
            if not line:
                continue

            upper_line = line.upper()

            if upper_line.startswith("PRIMARY KEY"):
                pk_match = re.search(r"PRIMARY\s+KEY\s*\(([^)]+)\)", line, re.IGNORECASE)
                if pk_match:
                    pk_cols = [
                        c.strip().strip('"').strip("'") for c in pk_match.group(1).split(",")
                    ]
                    primary_keys.extend(pk_cols)
            elif upper_line.startswith("FOREIGN KEY"):
                fk_match = re.search(
                    r"FOREIGN\s+KEY\s*\(([^)]+)\)\s+REFERENCES\s+([^\s(]+)\s*\(([^)]+)\)",
                    line,
                    re.IGNORECASE,
                )
                if fk_match:
                    foreign_keys.append(
                        {
                            "columns": [c.strip() for c in fk_match.group(1).split(",")],
                            "ref_table": fk_match.group(2).strip().strip('"').strip("'"),
                            "ref_columns": [c.strip() for c in fk_match.group(3).split(",")],
                        }
                    )
            elif upper_line.startswith("CONSTRAINT"):
                continue
            else:
                col_match = re.match(r"([^\s]+)\s+([A-Za-z]+(?:\[[^\]]+\])?)", line)
                if col_match:
                    col_name = col_match.group(1).strip().strip('"').strip("'")
                    col_type = col_match.group(2).strip()
                    is_pk = "PRIMARY KEY" in upper_line
                    columns.append({"name": col_name, "type": col_type, "is_pk": is_pk})
                    if is_pk:
                        primary_keys.append(col_name)

        tables.append(
            {
                "name": table_name,
                "columns": columns,
                "primary_keys": list(set(primary_keys)),
                "foreign_keys": foreign_keys,
            }
        )

    return tables


def _generate_mermaid_er(tables: list[dict]) -> str:
    """从解析的表定义生成 Mermaid ER 图。

    Args:
        tables: 表定义信息列表。

    Returns:
        Mermaid ER 图的 Markdown 代码块字符串。
    """
    if not tables:
        return ""

    lines = ["```mermaid", "erDiagram"]

    for table in tables:
        table_name = table["name"]
        for col in table["columns"]:
            col_name = col["name"]
            col_type = col["type"]
            key_marker = " PK" if col["name"] in table["primary_keys"] else ""
            lines.append(f"    {table_name} {{")
            lines.append(f"        {col_type} {col_name}{key_marker}")
            lines.append("    }")

    for table in tables:
        for fk in table.get("foreign_keys", []):
            for col, ref_col in zip(fk["columns"], fk["ref_columns"], strict=True):
                lines.append(
                    f'    {table["name"]} ||--o{{ {fk["ref_table"]} : "{col} -> {ref_col}"'
                )

    lines.append("```")
    return "\n".join(lines)


async def _get_kb_readme() -> str:
    """读取知识库 README.md 内容（如果存在）。

    Returns:
        README.md 的格式化内容，若文件不存在或读取失败则返回空字符串。
    """
    readme_path = AppContext.get().kb_path / "README.md"
    if readme_path.exists():
        try:
            content = await asyncio.to_thread(readme_path.read_text, encoding="utf-8")
            if content:
                return f"\n\n## Knowledge Base README\n\n{content.strip()}\n"
        except Exception as e:
            logger.warning(f"Failed to read README.md: {e}")
    return ""


async def init_schema():
    """初始化数据库模式。

    创建系统表并根据本体定义创建用户表。
    如果本体定义为空，则尝试加载 schema.sql 作为备选。
    """
    logger.info("Initializing schema...")
    kb_config = AppContext.get().kb_config
    sys_schema_ddl = get_sys_schema_ddl(kb_config.EMBEDDING_DIM)

    async with get_async_db(read_only=False) as conn:
        # Install and load vss extension for vector search
        try:
            await asyncio.to_thread(conn.execute, "INSTALL vss; LOAD vss;")
            await asyncio.to_thread(conn.execute, "SET hnsw_enable_experimental_persistence=true;")
        except Exception as e:
            logger.warning(
                f"Failed to load vss extension or set experimental persistence: {e}. Vector search might not work."
            )

        # Check if embedding column exists and add if missing (migration)
        try:
            # DuckDB specific: check columns
            cursor = conn.execute(f"PRAGMA table_info('{SYS_SEARCH_TABLE}')")
            columns = [row[1] for row in cursor.fetchall()]
            if "embedding" not in columns:
                logger.info(f"Migrating schema: Adding embedding column to {SYS_SEARCH_TABLE}")
                conn.execute(
                    f"ALTER TABLE {SYS_SEARCH_TABLE} ADD COLUMN embedding FLOAT[{kb_config.EMBEDDING_DIM}]"
                )
        except Exception:
            # Table might not exist yet, which is fine
            pass

        await asyncio.to_thread(conn.execute, sys_schema_ddl)
        logger.debug("System tables ensured.")

        ontology = kb_config.ontology
        if ontology.nodes:
            logger.info(f"Creating tables from ontology: {list(ontology.nodes.keys())}")
            nodes_ddl = OntologyEngine(ontology).generate_ddl()
            if nodes_ddl:
                try:
                    await asyncio.to_thread(conn.execute, nodes_ddl)
                    logger.debug("Ontology tables created.")
                except Exception as e:
                    logger.error(f"Failed to create ontology tables: {e}")
                    raise
        else:
            schema_path = AppContext.get().kb_path / SCHEMA_FILE_NAME
            if schema_path.exists():
                logger.info(f"Applying schema from {schema_path}")
                schema_sql = await asyncio.to_thread(schema_path.read_text, encoding="utf-8")
                try:
                    await asyncio.to_thread(conn.execute, schema_sql)
                except Exception as e:
                    logger.error(f"Failed to apply schema.sql: {e}")
                    raise
            else:
                logger.debug("No ontology or schema.sql defined, skipping user tables.")


async def get_schema_info() -> str:
    """获取模式定义信息，包含 Mermaid ER 图和知识库 README。

    Returns:
        包含用户模式、系统模式、ER 图和 README 的格式化字符串。
    """
    parts = []
    kb_config = AppContext.get().kb_config
    sys_schema_ddl = get_sys_schema_ddl(kb_config.EMBEDDING_DIM)

    ontology = kb_config.ontology
    if ontology.nodes:
        nodes_ddl = OntologyEngine(ontology).generate_ddl()
        if nodes_ddl:
            parts.append(f"-- Ontology Schema\n{nodes_ddl}\n")
    else:
        schema_path = AppContext.get().kb_path / SCHEMA_FILE_NAME
        if schema_path.exists():
            user_schema = await asyncio.to_thread(schema_path.read_text, encoding="utf-8")
            parts.append(f"-- User Schema ({SCHEMA_FILE_NAME})\n{user_schema}\n")

    parts.append(f"-- System Schema\n{sys_schema_ddl}\n")

    all_sql = "\n".join(parts)
    tables = _parse_table_definitions(all_sql)

    if tables:
        er_diagram = _generate_mermaid_er(tables)
        if er_diagram:
            parts.append("\n## ER Diagram\n\n" + er_diagram + "\n")

    readme_content = await _get_kb_readme()
    if readme_content:
        parts.append(readme_content)

    return "\n".join(parts)
