"""异步文件操作工具模块。

本模块提供常用文件操作的异步封装，使用 aiofiles 和 asyncio.to_thread
确保在异步上下文中的非阻塞 I/O 操作。
"""

import asyncio
import glob
import os
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import aiofiles
import orjson


async def read_file(file_path: str | Path, encoding: str = "utf-8") -> str:
    """异步读取文件内容。

    Args:
        file_path: 文件路径。
        encoding: 文件编码，默认为 utf-8。

    Returns:
        文件内容字符串。

    Raises:
        FileNotFoundError: 文件不存在。
        IOError: 读取时发生 I/O 错误。
    """
    async with aiofiles.open(file_path, encoding=encoding) as f:
        return await f.read()


async def read_file_lines(
    file_path: str | Path, encoding: str = "utf-8"
) -> AsyncGenerator[str, None]:
    """异步逐行读取文件。

    Args:
        file_path: 文件路径。
        encoding: 文件编码，默认为 utf-8。

    Yields:
        文件的每一行。

    Raises:
        FileNotFoundError: 文件不存在。
        IOError: 读取时发生 I/O 错误。
    """
    async with aiofiles.open(file_path, encoding=encoding) as f:
        async for line in f:
            yield line


async def read_json(file_path: str | Path, encoding: str = "utf-8") -> Any:
    """异步读取 JSON 文件。

    Args:
        file_path: JSON 文件路径。
        encoding: 文件编码，默认为 utf-8。

    Returns:
        解析后的 JSON 内容（字典或列表）。

    Raises:
        FileNotFoundError: 文件不存在。
        JSONDecodeError: 文件内容不是有效的 JSON。
    """
    content = await read_file(file_path, encoding=encoding)
    return orjson.loads(content)


async def read_jsonl(file_path: str | Path, encoding: str = "utf-8") -> list[Any]:
    """异步读取 JSONL 文件。

    Args:
        file_path: JSONL 文件路径。
        encoding: 文件编码，默认为 utf-8。

    Returns:
        解析后的 JSON 对象列表。

    Raises:
        FileNotFoundError: 文件不存在。
        JSONDecodeError: 某行不是有效的 JSON。
    """
    content = await read_file(file_path, encoding=encoding)
    records = []
    for line in content.splitlines():
        if not line.strip():
            continue
        records.append(orjson.loads(line))
    return records


async def write_file(file_path: str | Path, content: str, encoding: str = "utf-8") -> None:
    """异步写入文件。

    Args:
        file_path: 文件路径。
        content: 要写入的字符串内容。
        encoding: 文件编码，默认为 utf-8。

    Raises:
        IOError: 写入时发生 I/O 错误。
    """
    async with aiofiles.open(file_path, mode="w", encoding=encoding) as f:
        await f.write(content)


async def write_json(
    file_path: str | Path,
    data: Any,
    encoding: str = "utf-8",
    atomic: bool = False,
) -> None:
    """异步写入 JSON 文件。

    Args:
        file_path: 文件路径。
        data: 要序列化为 JSON 的数据。
        encoding: 文件编码，默认为 utf-8。
        atomic: 是否使用原子写入，默认为 False。

    Raises:
        IOError: 写入时发生 I/O 错误。
    """
    content = orjson.dumps(data).decode(encoding)
    if atomic:
        await atomic_write_file(file_path, content, encoding=encoding)
    else:
        await write_file(file_path, content, encoding=encoding)


async def atomic_write_file(file_path: str | Path, content: str, encoding: str = "utf-8") -> None:
    """异步原子写入文件。

    将内容写入目标文件所在目录的临时文件，然后重命名为目标文件。
    确保文件要么完全写入，要么完全不写入，防止写入失败导致的部分写入。

    Args:
        file_path: 目标文件路径。
        content: 要写入的字符串内容。
        encoding: 文件编码，默认为 utf-8。

    Raises:
        IOError: 写入或重命名时发生 I/O 错误。
    """
    file_path = Path(file_path)
    directory = file_path.parent

    if not await dir_exists(directory):
        await mkdir(directory)

    fd, temp_path = await asyncio.to_thread(tempfile.mkstemp, dir=directory, text=True)

    try:
        await asyncio.to_thread(os.close, fd)

        async with aiofiles.open(temp_path, mode="w", encoding=encoding) as f:
            await f.write(content)
            await f.flush()
            await asyncio.to_thread(os.fsync, f.fileno())

        await asyncio.to_thread(os.replace, temp_path, file_path)
    except Exception:
        if await file_exists(temp_path):
            await unlink(temp_path)
        raise


async def file_exists(file_path: str | Path) -> bool:
    """异步检查文件是否存在。

    Args:
        file_path: 要检查的路径。

    Returns:
        如果文件存在且是文件则返回 True，否则返回 False。
    """
    return await asyncio.to_thread(os.path.isfile, file_path)


async def dir_exists(dir_path: str | Path) -> bool:
    """异步检查目录是否存在。

    Args:
        dir_path: 要检查的路径。

    Returns:
        如果目录存在则返回 True，否则返回 False。
    """
    return await asyncio.to_thread(os.path.isdir, dir_path)


async def glob_files(pattern: str) -> list[str]:
    """异步查找匹配 glob 模式的文件。

    Args:
        pattern: glob 匹配模式。

    Returns:
        匹配的文件路径列表。
    """
    return await asyncio.to_thread(glob.glob, pattern)


async def mkdir(path: str | Path, parents: bool = True, exist_ok: bool = True) -> None:
    """异步创建目录。

    Args:
        path: 要创建的目录路径。
        parents: 是否创建父目录，默认为 True。
        exist_ok: 目录已存在时是否不报错，默认为 True。

    Raises:
        OSError: 目录创建失败。
    """
    await asyncio.to_thread(os.makedirs, path, exist_ok=exist_ok)


async def unlink(path: str | Path) -> None:
    """异步删除文件。

    Args:
        path: 要删除的文件路径。

    Raises:
        FileNotFoundError: 文件不存在。
        OSError: 删除失败。
    """
    await asyncio.to_thread(os.unlink, path)


async def get_file_stat(path: str | Path) -> os.stat_result:
    """异步获取文件状态。

    Args:
        path: 文件路径。

    Returns:
        文件状态结构。

    Raises:
        FileNotFoundError: 文件不存在。
    """
    return await asyncio.to_thread(os.stat, path)
