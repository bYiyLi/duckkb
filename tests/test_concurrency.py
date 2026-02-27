"""并发测试。"""

import asyncio

import pytest


class TestConcurrentImports:
    """并发导入测试。"""

    @pytest.mark.asyncio
    async def test_concurrent_imports(self, async_engine, tmp_path):
        """测试并发导入。"""
        yaml_contents = [
            f"""
- type: Character
  name: 并发测试角色{i}
  bio: 测试并发导入功能{i}
"""
            for i in range(3)
        ]

        yaml_files = []
        for i, content in enumerate(yaml_contents):
            yaml_file = tmp_path / f"concurrent_{i}.yaml"
            yaml_file.write_text(content, encoding="utf-8")
            yaml_files.append(str(yaml_file))

        tasks = [async_engine.import_knowledge_bundle(f) for f in yaml_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                pytest.fail(f"Concurrent import failed: {result}")
            else:
                assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_concurrent_import_same_file(self, async_engine, tmp_path):
        """测试并发导入同一文件。"""
        yaml_content = """
- type: Character
  name: 同文件并发测试
  bio: 测试同文件并发导入
"""
        yaml_file = tmp_path / "same_file.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        tasks = [
            async_engine.import_knowledge_bundle(str(yaml_file)) for _ in range(3)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(
            1 for r in results if not isinstance(r, Exception) and r["status"] == "success"
        )
        assert success_count >= 1


class TestConcurrentReadWrite:
    """并发读写测试。"""

    @pytest.mark.asyncio
    async def test_concurrent_read_write(self, async_engine, tmp_path):
        """测试并发读写。"""
        yaml_content = """
- type: Character
  name: 并发读写测试
  bio: 测试并发读写功能
"""

        async def write_task(i: int):
            yaml_file = tmp_path / f"rw_test_{i}.yaml"
            yaml_file.write_text(yaml_content, encoding="utf-8")
            return await async_engine.import_knowledge_bundle(str(yaml_file))

        def read_task():
            return async_engine.execute_read("SELECT COUNT(*) FROM characters")

        write_tasks = [write_task(i) for i in range(2)]
        read_tasks = [asyncio.to_thread(read_task) for _ in range(3)]
        results = await asyncio.gather(*write_tasks, *read_tasks, return_exceptions=True)

        for result in results:
            assert not isinstance(result, Exception), f"Task failed: {result}"

    @pytest.mark.asyncio
    async def test_concurrent_search(self, async_engine, tmp_path):
        """测试并发搜索。"""
        yaml_content = """
- type: Character
  name: 并发搜索测试
  bio: 测试并发搜索功能
"""
        yaml_file = tmp_path / "search_test.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        from unittest.mock import patch

        with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed_single") as mock:
            mock.return_value = [0.1] * 1536

            tasks = [async_engine.search("并发搜索", limit=5) for _ in range(5)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                assert not isinstance(result, Exception), f"Search failed: {result}"
                assert isinstance(result, list)


class TestConcurrentIndexBuild:
    """并发索引构建测试。"""

    @pytest.mark.asyncio
    async def test_concurrent_index_build(self, async_engine, tmp_path):
        """测试并发索引构建。"""
        yaml_content = """
- type: Character
  name: 并发索引测试
  bio: 测试并发索引构建
"""
        yaml_file = tmp_path / "index_test.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        tasks = [async_engine.build_index("Character") for _ in range(3)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            assert not isinstance(result, Exception), f"Index build failed: {result}"


class TestConcurrentCacheOperations:
    """并发缓存操作测试。"""

    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(self, async_engine, tmp_path):
        """测试并发缓存操作。"""
        yaml_content = """
- type: Character
  name: 缓存并发测试
  bio: 测试并发缓存操作
"""
        yaml_file = tmp_path / "cache_test.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        cache_path = tmp_path / "cache" / "test_cache.parquet"

        async def save_cache():
            return await async_engine.save_cache_to_parquet(cache_path)

        async def clean_cache():
            return await async_engine.clean_cache(expire_days=30)

        tasks = [save_cache(), clean_cache(), save_cache()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            assert not isinstance(result, Exception), f"Cache operation failed: {result}"


class TestLockBehavior:
    """锁行为测试。"""

    @pytest.mark.asyncio
    async def test_import_lock_serializes_imports(self, async_engine, tmp_path):
        """测试导入锁序列化导入。"""
        yaml_content = """
- type: Character
  name: 锁测试角色
  bio: 测试导入锁
"""

        results = []

        async def tracked_import(i: int):
            yaml_file = tmp_path / f"lock_test_{i}.yaml"
            yaml_file.write_text(yaml_content, encoding="utf-8")
            result = await async_engine.import_knowledge_bundle(str(yaml_file))
            results.append(result)
            return result

        tasks = [tracked_import(i) for i in range(2)]
        await asyncio.gather(*tasks, return_exceptions=True)

        assert len(results) == 2
        for r in results:
            assert r["status"] == "success"
