"""
DuckKB MCP 服务模块

本模块提供基于 FastMCP 的 Model Context Protocol (MCP) 服务实现，
为 AI 助手提供知识库操作工具集。

提供的工具：
- check_health: 健康检查，返回服务状态和知识库信息
- sync_knowledge_base: 同步知识库，支持 ontology 配置变更和数据迁移
- get_schema_info: 获取数据库模式定义和 ER 图信息
- smart_search: 智能混合搜索（向量 + 元数据）
- query_raw_sql: 执行只读 SQL 查询
- validate_and_import: 验证并导入数据文件（upsert 语义）
- delete_records: 删除指定表中的记录
- list_backups: 列出所有可用备份
- restore_backup: 从备份恢复知识库
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

from duckkb.config import AppContext
from duckkb.constants import BUILD_DIR_NAME, DATA_DIR_NAME, DB_FILE_NAME
from duckkb.engine.backup import BackupManager
from duckkb.engine.deleter import delete_documents
from duckkb.engine.importer import validate_and_import_file
from duckkb.engine.migration import MigrationManager
from duckkb.engine.searcher import query_raw_sql as _query
from duckkb.engine.searcher import smart_search as _search
from duckkb.engine.sync import persist_all_tables
from duckkb.engine.sync import sync_knowledge_base as _sync
from duckkb.logger import logger
from duckkb.schema import get_schema_info as _get_schema_info
from duckkb.schema import init_schema
from duckkb.utils.file_ops import file_exists, glob_files, read_file
from duckkb.utils.text import init_jieba_async


@lifespan
async def kb_lifespan(server: FastMCP) -> AsyncGenerator[dict[str, Path], None]:
    """知识库生命周期管理。

    在 MCP 服务启动时初始化知识库，关闭时持久化数据到磁盘。

    Args:
        server: FastMCP 服务器实例。

    Yields:
        包含知识库路径的上下文字典。
    """
    ctx = AppContext.get()

    logger.info("Initializing knowledge base...")
    try:
        await init_schema()
        await init_jieba_async()
        await _sync(ctx.kb_path)
        logger.info("Knowledge base initialized successfully.")
    except Exception as e:
        logger.error(f"Knowledge base initialization failed: {e}")
        raise

    yield {"kb_path": ctx.kb_path}

    logger.info("Persisting knowledge base to disk...")
    try:
        results = await persist_all_tables(ctx.kb_path)
        persisted = sum(1 for v in results.values() if v >= 0)
        logger.info(f"Knowledge base persisted: {persisted} tables saved.")
    except Exception as e:
        logger.error(f"Failed to persist knowledge base: {e}")


mcp = FastMCP("DuckKB", lifespan=kb_lifespan)


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

    data_files = await glob_files(str(data_dir / "*.jsonl"))
    db_exists_flag = await file_exists(db_path)

    status = {
        "status": "healthy",
        "kb_path": str(ctx.kb_path),
        "db_exists": db_exists_flag,
        "data_files_count": len(data_files),
        "data_files": [Path(f).stem for f in data_files],
    }
    return json.dumps(status, ensure_ascii=False)


@mcp.tool()
async def sync_knowledge_base(
    ontology_path: str | None = None,
    force: bool = False,
) -> str:
    """
    同步知识库，支持 ontology 配置变更和数据迁移。

    从 JSONL 数据文件导入内容到 DuckDB 数据库，包括向量化处理。
    如果提供 ontology_path 参数，将进行配置校验、数据库模式迁移和数据迁移。

    Args:
        ontology_path: 可选的新 ontology 配置文件路径（YAML 格式）。
                      如果提供，将读取文件内容并进行：
            - YAML 解析与配置校验
            - 数据库模式迁移
            - 数据迁移（如需要）
            - 失败时自动回滚

                      示例配置文件内容：
                      ```yaml
                      nodes:
                        documents:
                          table: documents
                          identity: [id]
                          schema:
                            type: object
                            properties:
                              id:
                                type: string
                              title:
                                type: string
                              content:
                                type: string
                            required: [id]
                          vectors:
                            content:
                              dim: 1536
                              model: text-embedding-3-small
                      ```
        force: 是否强制重新同步所有数据（忽略增量检测）。
               当 ontology 变更涉及删除表时，需要设置为 True 才能执行。

    Returns:
        str: JSON 格式的操作结果，包含迁移统计和状态。
    """
    ctx = AppContext.get()

    if ontology_path:
        path = Path(ontology_path)
        if not await file_exists(path):
            raise FileNotFoundError(f"Ontology file not found: {ontology_path}")

        content = await read_file(path)
        migration_manager = MigrationManager(ctx.kb_path)

        # Run migration in a separate thread to avoid blocking
        result = await asyncio.to_thread(migration_manager.migrate, content, force=force)
        return json.dumps(result.to_dict(), ensure_ascii=False)

    await _sync(ctx.kb_path)

    results = await persist_all_tables(ctx.kb_path)
    return json.dumps(
        {
            "status": "success",
            "message": "Synchronization completed.",
            "persisted_tables": results,
        },
        ensure_ascii=False,
    )


@mcp.tool()
async def get_schema_info() -> str:
    """
    获取数据库模式信息。

    返回知识库的表结构定义和实体关系图（ER 图）信息，
    帮助用户了解数据模型和表间关系。

    Returns:
        str: 数据库模式的详细描述，包含表结构和 ER 图信息。
    """
    schema_info = await _get_schema_info()
    kb_config = AppContext.get().kb_config

    if kb_config.usage_instructions:
        return f"{schema_info}\n\n{kb_config.usage_instructions}"
    return schema_info


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
                       文件必须符合知识库的数据格式规范。

    Returns:
        str: JSON 格式的操作结果，包含更新/插入统计。

    Raises:
        ValueError: 当文件格式不正确或验证失败时抛出。
        FileNotFoundError: 当临时文件不存在时抛出。
    """
    return await validate_and_import_file(table_name, temp_file_path)


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
    result = await delete_documents(table_name, record_ids)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def list_backups() -> str:
    """
    列出所有可用备份。

    返回知识库的所有备份列表，按创建时间倒序排列。

    Returns:
        str: JSON 格式的备份列表，每个备份包含名称、路径、创建时间和大小。
    """
    ctx = AppContext.get()
    backup_manager = BackupManager(ctx.kb_path)
    backups = backup_manager.list_backups()
    return json.dumps(backups, ensure_ascii=False)


@mcp.tool()
async def restore_backup(backup_name: str) -> str:
    """
    从备份恢复知识库。

    将知识库恢复到指定备份的状态。此操作会覆盖当前数据。

    Args:
        backup_name: 备份名称（可通过 list_backups 获取）。

    Returns:
        str: JSON 格式的恢复结果。

    Raises:
        ValueError: 当备份不存在或恢复失败时抛出。
    """
    ctx = AppContext.get()
    backup_manager = BackupManager(ctx.kb_path)

    backup_dir = backup_manager._get_backup_dir(backup_name)
    if not backup_dir.exists():
        raise ValueError(f"Backup not found: {backup_name}")

    success = backup_manager.restore_backup(backup_dir)
    if success:
        return json.dumps(
            {
                "status": "success",
                "message": f"Restored from backup: {backup_name}",
            },
            ensure_ascii=False,
        )
    else:
        raise ValueError(f"Failed to restore backup: {backup_name}")


@mcp.tool()
async def create_backup(prefix: str = "") -> str:
    """
    创建知识库备份。

    创建当前知识库状态的完整备份，包括数据库、数据文件和配置。

    Args:
        prefix: 备份名称前缀，用于标识备份类型。

    Returns:
        str: JSON 格式的备份结果，包含备份路径。
    """
    ctx = AppContext.get()
    backup_manager = BackupManager(ctx.kb_path)

    backup_path = backup_manager.create_backup(prefix=prefix)
    if backup_path:
        return json.dumps(
            {
                "status": "success",
                "backup_path": str(backup_path),
                "backup_name": backup_path.name,
            },
            ensure_ascii=False,
        )
    else:
        raise ValueError("Failed to create backup")
