"""数据导入模块。"""

import json
from pathlib import Path

import orjson

from duckkb.config import AppContext
from duckkb.constants import MAX_ERROR_FEEDBACK
from duckkb.engine.crud import add_documents
from duckkb.engine.sync import sync_db_to_file
from duckkb.utils.file_ops import file_exists, read_file_lines, unlink


async def validate_and_import_file(table_name: str, temp_file_path: str) -> str:
    """
    验证并导入数据文件（upsert 语义）。

    验证临时 JSONL 文件的格式和内容，验证通过后将其导入到数据目录。
    如果目标表已存在，基于 id 字段进行 upsert（更新已存在的记录，插入新记录）。
    如果目标表不存在，创建新表。

    Args:
        table_name: 目标表名（不含 .jsonl 扩展名）。
        temp_file_path: 临时 JSONL 文件的绝对路径。

    Returns:
        JSON 格式的操作结果。

    Raises:
        ValueError: 当文件格式不正确或验证失败时抛出。
        FileNotFoundError: 当临时文件不存在时抛出。
    """
    path = Path(temp_file_path)
    if not await file_exists(path):
        raise FileNotFoundError(f"File {temp_file_path} not found")

    BATCH_SIZE = 100
    errors = []

    # Get schema for validation
    ctx = AppContext.get()
    schema = None
    if ctx.kb_config.ontology and ctx.kb_config.ontology.nodes:
        node = ctx.kb_config.ontology.nodes.get(table_name)
        if node and node.json_schema:
            schema = node.json_schema

    # Pass 1: Validation
    try:
        line_num = 0
        async for line in read_file_lines(path):
            line_num += 1
            if not line.strip():
                continue

            if len(errors) >= MAX_ERROR_FEEDBACK:
                break

            try:
                record = orjson.loads(line)
                if not isinstance(record, dict):
                    errors.append(f"Line {line_num}: Record must be a JSON object")
                    continue
                if "id" not in record:
                    errors.append(f"Line {line_num}: Missing required field 'id'")
                    continue

                # Schema validation
                if schema and "required" in schema:
                    missing = [f for f in schema["required"] if f not in record]
                    if missing:
                        errors.append(f"Line {line_num}: Missing required fields {missing}")
                        continue
            except orjson.JSONDecodeError:
                errors.append(f"Line {line_num}: Invalid JSON format")

    except Exception as e:
        raise ValueError(f"Failed to read file during validation: {e}") from e

    if errors:
        error_msg = f"Found {len(errors)} errors:\n" + "\n".join(errors[:MAX_ERROR_FEEDBACK])
        if len(errors) >= MAX_ERROR_FEEDBACK:
            error_msg += "\n..."
        raise ValueError(error_msg)

    # Pass 2: Import
    total_upserted = 0
    buffer = []

    try:
        async for line in read_file_lines(path):
            if not line.strip():
                continue

            record = orjson.loads(line)
            buffer.append(record)

            if len(buffer) >= BATCH_SIZE:
                res = await add_documents(table_name, buffer, sync_file=False)
                total_upserted += res.get("upserted_count", 0)
                buffer = []

        # Process remaining
        if buffer:
            res = await add_documents(table_name, buffer, sync_file=False)
            total_upserted += res.get("upserted_count", 0)

        # Final sync
        await sync_db_to_file(table_name)

    except Exception as e:
        raise ValueError(f"Failed to import data: {e}") from e
    finally:
        try:
            await unlink(path)
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file: {e}")

    return json.dumps(
        {
            "status": "success",
            "table_name": table_name,
            "upserted_count": total_upserted,
            "message": f"Successfully upserted {total_upserted} records",
        },
        ensure_ascii=False,
    )
