"""
DuckKB MCP 服务模块

本模块提供基于 FastMCP 的 Model Context Protocol (MCP) 服务实现，
为 AI 助手提供知识库操作工具集。

提供的工具：
- check_health: 健康检查，返回服务状态和知识库信息
- sync_knowledge_base: 同步知识库，从 JSONL 文件导入到 DuckDB
- get_schema_info: 获取数据库模式定义和 ER 图信息
- smart_search: 智能混合搜索（向量 + 元数据）
- query_raw_sql: 执行只读 SQL 查询
- validate_and_import: 验证并导入数据文件（upsert 语义）
- delete_records: 删除指定表中的记录
"""

import json
from pathlib import Path

from fastmcp import FastMCP

from duckkb.config import AppContext
from duckkb.constants import BUILD_DIR_NAME, DATA_DIR_NAME, DB_FILE_NAME
from duckkb.engine.deleter import delete_records as _delete_records
from duckkb.engine.importer import validate_and_import as _validate
from duckkb.engine.searcher import query_raw_sql as _query
from duckkb.engine.searcher import smart_search as _search
from duckkb.engine.sync import sync_knowledge_base as _sync
from duckkb.schema import get_schema_info as _get_schema_info

mcp = FastMCP("DuckKB")


@mcp.tool()
async def check_health() -> str:
    """
    检查服务健康状态。

    返回知识库的详细状态信息，包括路径、数据库是否存在、数据文件数量等。

    Returns:
        str: JSON 格式的状态信息，包含以下字段：
            - status: 状态标识，正常为 "healthy"
            - kb_path: 知识库路径
            - db_exists: 数据库文件是否存在
            - data_files_count: 数据文件数量
            - data_files: 数据文件名列表（不含扩展名）
    """
    ctx = AppContext.get()
    db_path = ctx.kb_path / BUILD_DIR_NAME / DB_FILE_NAME
    data_dir = ctx.kb_path / DATA_DIR_NAME

    data_files = list(data_dir.glob("*.jsonl")) if data_dir.exists() else []

    status = {
        "status": "healthy",
        "kb_path": str(ctx.kb_path),
        "db_exists": db_path.exists(),
        "data_files_count": len(data_files),
        "data_files": [f.stem for f in data_files],
    }
    return json.dumps(status, ensure_ascii=False)


@mcp.tool()
async def sync_knowledge_base() -> str:
    """
    同步知识库。

    从 JSONL 数据文件导入内容到 DuckDB 数据库，包括向量化处理。
    此操作会更新数据库索引和向量存储。

    Returns:
        str: 操作结果消息，成功时返回 "Synchronization completed."
    """
    await _sync(AppContext.get().kb_path)
    return "Synchronization completed."


@mcp.tool()
async def get_schema_info() -> str:
    """
    获取数据库模式信息。

    返回知识库的表结构定义和实体关系图（ER 图）信息，
    帮助用户了解数据模型和表间关系。

    Returns:
        str: 数据库模式的详细描述，包含表结构和 ER 图信息。
    """
    return await _get_schema_info()


@mcp.tool()
async def smart_search(
    query: str, limit: int = 10, table_filter: str | None = None, alpha: float = 0.5
) -> str:
    """
    执行智能混合搜索（向量 + 元数据）。

    结合向量相似度搜索和元数据匹配，提供更精准的搜索结果。
    向量搜索基于语义相似性，元数据搜索基于精确匹配。

    Args:
        query: 搜索查询字符串，支持自然语言描述。
        limit: 返回结果的最大数量，默认为 10。
        table_filter: 可选的源表过滤器，限定搜索范围到指定表。
        alpha: 向量搜索的权重系数，取值范围 0.0 到 1.0。
               0.0 表示仅使用元数据搜索，1.0 表示仅使用向量搜索。
               默认为 0.5，表示两种搜索方式权重相等。

    Returns:
        str: JSON 格式的搜索结果列表，每个结果包含匹配的记录详情。
    """
    results = await _search(query, limit, table_filter, alpha)
    return json.dumps(results, ensure_ascii=False, default=str)


@mcp.tool()
async def query_raw_sql(sql: str) -> str:
    """
    执行只读 SQL 查询。

    安全地执行原始 SQL 查询语句，仅支持 SELECT 操作。
    系统会自动应用 LIMIT 限制，防止返回过多数据。

    Args:
        sql: 要执行的 SQL 查询语句，必须是 SELECT 语句。

    Returns:
        str: JSON 格式的查询结果列表。

    Raises:
        ValueError: 当 SQL 语句不是只读查询时抛出。
    """
    results = await _query(sql)
    return json.dumps(results, ensure_ascii=False, default=str)


@mcp.tool()
async def validate_and_import(table_name: str, temp_file_path: str) -> str:
    """
    验证并导入数据文件（upsert 语义）。

    验证临时 JSONL 文件的格式和内容，验证通过后将其导入到数据目录。
    如果目标表已存在，基于 id 字段进行 upsert（更新已存在的记录，插入新记录）。
    如果目标表不存在，创建新表。

    Args:
        table_name: 目标表名（不含 .jsonl 扩展名）。
                   文件将被命名为 {table_name}.jsonl。
        temp_file_path: 临时 JSONL 文件的绝对路径。
                       文件必须符合知识库的数据格式规范，每条记录必须包含 id 字段。

    Returns:
        str: JSON 格式的操作结果，包含更新/插入统计。

    Raises:
        ValueError: 当文件格式不正确或验证失败时抛出。
        FileNotFoundError: 当临时文件不存在时抛出。
    """
    return await _validate(table_name, Path(temp_file_path))


@mcp.tool()
async def delete_records(table_name: str, record_ids: list[str]) -> str:
    """
    删除指定表中的记录。

    从知识库中删除指定的记录，包括 JSONL 数据文件和数据库索引。

    Args:
        table_name: 目标表名（不含 .jsonl 扩展名）。
        record_ids: 要删除的记录 ID 列表。

    Returns:
        str: JSON 格式的删除结果，包含删除统计和未找到的 ID 列表。

    Raises:
        ValueError: 当参数无效时抛出。
        FileNotFoundError: 当表不存在时抛出。
    """
    result = await _delete_records(table_name, record_ids)
    return json.dumps(result, ensure_ascii=False)
