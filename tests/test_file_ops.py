"""Tests for async file operations."""

from unittest import mock

import pytest

from duckkb.utils.file_ops import (
    atomic_write_file,
    dir_exists,
    file_exists,
    get_file_stat,
    glob_files,
    mkdir,
    read_file,
    unlink,
    write_file,
)


@pytest.mark.asyncio
async def test_read_write_file(tmp_path):
    """Test basic read and write operations."""
    test_file = tmp_path / "test.txt"
    content = "Hello, World!"

    await write_file(test_file, content)
    assert test_file.exists()

    read_content = await read_file(test_file)
    assert read_content == content


@pytest.mark.asyncio
async def test_atomic_write_file(tmp_path):
    """Test atomic write operation."""
    test_file = tmp_path / "atomic.txt"
    content = "Atomic Content"

    await atomic_write_file(test_file, content)
    assert test_file.exists()

    read_content = await read_file(test_file)
    assert read_content == content

    # Test overwriting
    new_content = "New Atomic Content"
    await atomic_write_file(test_file, new_content)
    read_content = await read_file(test_file)
    assert read_content == new_content


@pytest.mark.asyncio
async def test_atomic_write_file_creates_dir(tmp_path):
    """Test atomic write creates directory if it doesn't exist."""
    test_file = tmp_path / "subdir" / "atomic.txt"
    content = "Atomic Content"

    await atomic_write_file(test_file, content)
    assert test_file.exists()
    assert (tmp_path / "subdir").exists()


@pytest.mark.asyncio
async def test_atomic_write_file_failure(tmp_path):
    """Test atomic write failure cleans up temp file."""
    test_file = tmp_path / "atomic_fail.txt"
    content = "Atomic Content"

    # Mock os.replace to raise an exception
    with mock.patch("os.replace", side_effect=OSError("Mocked error")):
        with pytest.raises(OSError, match="Mocked error"):
            await atomic_write_file(test_file, content)

    # Check that temp file is cleaned up
    assert not test_file.exists()
    # Ensure no temp files are left behind
    assert len(list(tmp_path.iterdir())) == 0


@pytest.mark.asyncio
async def test_file_exists(tmp_path):
    """Test file existence check."""
    test_file = tmp_path / "exists.txt"
    assert not await file_exists(test_file)

    test_file.touch()
    assert await file_exists(test_file)
    
    # Directory should return False for file_exists
    assert not await file_exists(tmp_path)


@pytest.mark.asyncio
async def test_dir_exists(tmp_path):
    """Test directory existence check."""
    test_dir = tmp_path / "subdir"
    assert not await dir_exists(test_dir)

    test_dir.mkdir()
    assert await dir_exists(test_dir)
    
    # File should return False for dir_exists
    test_file = tmp_path / "file.txt"
    test_file.touch()
    assert not await dir_exists(test_file)


@pytest.mark.asyncio
async def test_glob_files(tmp_path):
    """Test glob file search."""
    # Create some files
    (tmp_path / "a.txt").touch()
    (tmp_path / "b.txt").touch()
    (tmp_path / "c.log").touch()

    pattern = str(tmp_path / "*.txt")
    files = await glob_files(pattern)
    
    assert len(files) == 2
    assert str(tmp_path / "a.txt") in files
    assert str(tmp_path / "b.txt") in files


@pytest.mark.asyncio
async def test_mkdir(tmp_path):
    """Test directory creation."""
    test_dir = tmp_path / "new_dir"
    await mkdir(test_dir)
    assert test_dir.exists()
    assert test_dir.is_dir()

    # Test nested creation
    nested_dir = tmp_path / "a" / "b" / "c"
    await mkdir(nested_dir)
    assert nested_dir.exists()


@pytest.mark.asyncio
async def test_unlink(tmp_path):
    """Test file removal."""
    test_file = tmp_path / "remove_me.txt"
    test_file.touch()
    assert test_file.exists()

    await unlink(test_file)
    assert not test_file.exists()

    # Test removing non-existent file raises error
    with pytest.raises(OSError):
        await unlink(test_file)


@pytest.mark.asyncio
async def test_get_file_stat(tmp_path):
    """Test getting file stats."""
    test_file = tmp_path / "stat.txt"
    content = "12345"
    test_file.write_text(content, encoding="utf-8")

    stats = await get_file_stat(test_file)
    assert stats.st_size == len(content)
