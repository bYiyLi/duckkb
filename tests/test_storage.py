"""存储测试。"""

import pytest


class TestStorageMixin:
    """存储 Mixin 测试。"""

    @pytest.mark.asyncio
    async def test_load_table_empty(self, async_engine, tmp_path):
        """测试加载空表。"""
        data_dir = tmp_path / "test_data"
        data_dir.mkdir(parents=True)
        (data_dir / "empty.jsonl").write_text("", encoding="utf-8")

        count = await async_engine.load_table(
            table_name="characters",
            path_pattern=str(data_dir / "*.jsonl"),
            unique_fields=["name"],
        )
        assert count == 0

    def test_table_exists(self, engine):
        """测试表存在检查。"""
        assert engine._table_exists("characters") is True
        assert engine._table_exists("nonexistent_table") is False

    def test_get_table_count(self, engine):
        """测试获取表记录数。"""
        count = engine._get_table_count("characters")
        assert count == 0


class TestStorageOperations:
    """存储操作测试。"""

    @pytest.mark.asyncio
    async def test_load_node_nonexistent(self, async_engine):
        """测试加载不存在的节点类型。"""
        with pytest.raises(ValueError, match="Unknown node type"):
            await async_engine.load_node("NonexistentNode")

    @pytest.mark.asyncio
    async def test_load_edge_nonexistent(self, async_engine):
        """测试加载不存在的边类型。"""
        with pytest.raises(ValueError, match="Unknown edge type"):
            await async_engine.load_edge("NonexistentEdge")

    @pytest.mark.asyncio
    async def test_dump_node_nonexistent(self, async_engine):
        """测试导出不存在的节点类型。"""
        with pytest.raises(ValueError, match="Unknown node type"):
            await async_engine.dump_node("NonexistentNode")

    @pytest.mark.asyncio
    async def test_dump_edge_nonexistent(self, async_engine):
        """测试导出不存在的边类型。"""
        with pytest.raises(ValueError, match="Unknown edge type"):
            await async_engine.dump_edge("NonexistentEdge")
