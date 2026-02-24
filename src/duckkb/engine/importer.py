"""知识库导入模块。"""

import asyncio
from pathlib import Path

import orjson

from duckkb.config import AppContext
from duckkb.constants import DATA_DIR_NAME, MAX_ERROR_FEEDBACK
from duckkb.engine.sync import sync_knowledge_base
from duckkb.logger import logger


async def validate_and_import(table_name: str, temp_file_path: Path) -> str:
    """
    验证临时文件并将其导入到知识库数据目录。

    该函数执行完整的导入流程：
    1. 验证 JSONL 文件格式和必需字段
    2. 将新数据追加到现有文件（如存在）
    3. 使用原子写入确保数据完整性
    4. 触发知识库同步

    Args:
        table_name: 目标表名（不含 .jsonl 扩展名）。
        temp_file_path: 临时 JSONL 文件的路径。

    Returns:
        成功导入的消息，包含记录数量。

    Raises:
        FileNotFoundError: 临时文件不存在。
        ValueError: 文件格式验证失败，包含详细错误信息。
        OSError: 文件写入失败。
    """
    if not temp_file_path.exists():
        raise FileNotFoundError(f"File {temp_file_path} not found")

    errors = []
    valid_count = 0

    try:
        content = await asyncio.to_thread(temp_file_path.read_bytes)
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                record = orjson.loads(line)
                if not isinstance(record, dict):
                    errors.append(f"Line {i}: Record must be a JSON object")
                    continue

                if "id" not in record:
                    errors.append(f"Line {i}: Missing required field 'id'")

                valid_count += 1

            except orjson.JSONDecodeError:
                errors.append(f"Line {i}: Invalid JSON format")

    except Exception as e:
        raise ValueError(f"Failed to read file: {e}") from e

    if errors:
        error_msg = f"Found {len(errors)} errors:\n" + "\n".join(errors[:MAX_ERROR_FEEDBACK])
        if len(errors) > MAX_ERROR_FEEDBACK:
            error_msg += "\n..."
        raise ValueError(error_msg)

    kb_path = AppContext.get().kb_path
    target_path = kb_path / DATA_DIR_NAME / f"{table_name}.jsonl"
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        final_content = b""
        if target_path.exists():
            final_content = await asyncio.to_thread(target_path.read_bytes)
            if final_content and not final_content.endswith(b"\n"):
                final_content += b"\n"

        new_content = await asyncio.to_thread(temp_file_path.read_bytes)
        final_content += new_content

        staging_path = target_path.with_suffix(".jsonl.staging")
        await asyncio.to_thread(staging_path.write_bytes, final_content)

        staging_path.replace(target_path)

        try:
            temp_file_path.unlink()
        except OSError:
            pass

    except Exception as e:
        raise OSError(f"Failed to merge file to {target_path}: {e}") from e

    logger.info(f"Imported {table_name}, triggering sync...")
    await sync_knowledge_base(kb_path)

    return f"Successfully imported {valid_count} records to {table_name}"
