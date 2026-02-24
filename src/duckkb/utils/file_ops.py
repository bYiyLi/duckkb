"""Async file operations utility module.

This module provides asynchronous wrappers for common file operations using
aiofiles and asyncio.to_thread to ensure non-blocking I/O in async contexts.
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
    """Asynchronously reads the content of a file.

    Args:
        file_path: The path to the file to read.
        encoding: The encoding to use (default: "utf-8").

    Returns:
        The content of the file as a string.

    Raises:
        FileNotFoundError: If the file does not exist.
        IOError: If an I/O error occurs during reading.
    """
    async with aiofiles.open(file_path, encoding=encoding) as f:
        return await f.read()


async def read_file_lines(file_path: str | Path, encoding: str = "utf-8") -> AsyncGenerator[str, None]:
    """Asynchronously reads a file line by line.

    Args:
        file_path: The path to the file to read.
        encoding: The encoding to use (default: "utf-8").

    Yields:
        Each line of the file.

    Raises:
        FileNotFoundError: If the file does not exist.
        IOError: If an I/O error occurs during reading.
    """
    async with aiofiles.open(file_path, encoding=encoding) as f:
        async for line in f:
            yield line


async def read_json(file_path: str | Path, encoding: str = "utf-8") -> Any:
    """Asynchronously reads a JSON file.

    Args:
        file_path: The path to the JSON file.
        encoding: The encoding to use (default: "utf-8").

    Returns:
        The parsed JSON content (dict or list).

    Raises:
        FileNotFoundError: If the file does not exist.
        JSONDecodeError: If the file content is not valid JSON.
    """
    content = await read_file(file_path, encoding=encoding)
    return orjson.loads(content)


async def read_jsonl(file_path: str | Path, encoding: str = "utf-8") -> list[Any]:
    """Asynchronously reads a JSONL file.

    Args:
        file_path: The path to the JSONL file.
        encoding: The encoding to use (default: "utf-8").

    Returns:
        A list of parsed JSON objects.

    Raises:
        FileNotFoundError: If the file does not exist.
        JSONDecodeError: If any line is not valid JSON.
    """
    content = await read_file(file_path, encoding=encoding)
    records = []
    for line in content.splitlines():
        if not line.strip():
            continue
        records.append(orjson.loads(line))
    return records


async def write_file(file_path: str | Path, content: str, encoding: str = "utf-8") -> None:
    """Asynchronously writes content to a file.

    Args:
        file_path: The path to the file to write.
        content: The string content to write.
        encoding: The encoding to use (default: "utf-8").

    Raises:
        IOError: If an I/O error occurs during writing.
    """
    async with aiofiles.open(file_path, mode="w", encoding=encoding) as f:
        await f.write(content)


async def write_json(
    file_path: str | Path,
    data: Any,
    encoding: str = "utf-8",
    atomic: bool = False,
) -> None:
    """Asynchronously writes data to a JSON file.

    Args:
        file_path: The path to the file to write.
        data: The data to serialize to JSON.
        encoding: The encoding to use (default: "utf-8").
        atomic: If True, uses atomic write (default: False).

    Raises:
        IOError: If an I/O error occurs during writing.
    """
    content = orjson.dumps(data).decode(encoding)
    if atomic:
        await atomic_write_file(file_path, content, encoding=encoding)
    else:
        await write_file(file_path, content, encoding=encoding)


async def atomic_write_file(file_path: str | Path, content: str, encoding: str = "utf-8") -> None:
    """Asynchronously writes content to a file atomically.

    This function writes the content to a temporary file in the same directory
    as the target file, then renames the temporary file to the target file.
    This ensures that the file is either fully written or not written at all,
    preventing partial writes in case of failure.

    Args:
        file_path: The path to the destination file.
        content: The string content to write.
        encoding: The encoding to use (default: "utf-8").

    Raises:
        IOError: If an I/O error occurs during writing or renaming.
    """
    file_path = Path(file_path)
    directory = file_path.parent

    # Ensure the directory exists
    if not await dir_exists(directory):
        await mkdir(directory)

    # Create a temporary file in the same directory
    # We use a context manager for the temporary file logic manually
    # because aiofiles doesn't directly support tempfile.NamedTemporaryFile cleanly in async
    # for this specific atomic pattern involving rename across filesystems (if we used /tmp)
    # But here we use same dir to ensure atomic rename.

    fd, temp_path = await asyncio.to_thread(tempfile.mkstemp, dir=directory, text=True)

    try:
        # We need to close the file descriptor opened by mkstemp
        # because aiofiles will open it again by path
        await asyncio.to_thread(os.close, fd)

        async with aiofiles.open(temp_path, mode="w", encoding=encoding) as f:
            await f.write(content)
            await f.flush()
            # Ensure data is written to disk
            await asyncio.to_thread(os.fsync, f.fileno())

        # Atomic rename
        await asyncio.to_thread(os.replace, temp_path, file_path)
    except Exception:
        # Clean up temp file if something goes wrong
        if await file_exists(temp_path):
            await unlink(temp_path)
        raise


async def file_exists(file_path: str | Path) -> bool:
    """Asynchronously checks if a file exists.

    Args:
        file_path: The path to check.

    Returns:
        True if the file exists and is a file, False otherwise.
    """
    return await asyncio.to_thread(os.path.isfile, file_path)


async def dir_exists(dir_path: str | Path) -> bool:
    """Asynchronously checks if a directory exists.

    Args:
        dir_path: The path to check.

    Returns:
        True if the directory exists, False otherwise.
    """
    return await asyncio.to_thread(os.path.isdir, dir_path)


async def glob_files(pattern: str) -> list[str]:
    """Asynchronously finds files matching a glob pattern.

    Args:
        pattern: The glob pattern to match.

    Returns:
        A list of matching file paths.
    """
    return await asyncio.to_thread(glob.glob, pattern)


async def mkdir(path: str | Path, parents: bool = True, exist_ok: bool = True) -> None:
    """Asynchronously creates a directory.

    Args:
        path: The directory path to create.
        parents: If True, creates parent directories as needed (default: True).
        exist_ok: If True, does not raise an error if the directory already exists (default: True).

    Raises:
        OSError: If directory creation fails.
    """
    await asyncio.to_thread(os.makedirs, path, exist_ok=exist_ok)


async def unlink(path: str | Path) -> None:
    """Asynchronously removes a file.

    Args:
        path: The path to the file to remove.

    Raises:
        FileNotFoundError: If the file does not exist.
        OSError: If removal fails.
    """
    await asyncio.to_thread(os.unlink, path)


async def get_file_stat(path: str | Path) -> os.stat_result:
    """Asynchronously gets file status.

    Args:
        path: The path to the file.

    Returns:
        The status structure of the file.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    return await asyncio.to_thread(os.stat, path)
