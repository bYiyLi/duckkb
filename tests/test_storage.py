"""存储测试。"""

import pytest

from duckkb.core.mixins.storage import compute_deterministic_id


class TestDeterministicId:
    """确定性 ID 测试。"""

    def test_compute_deterministic_id_consistent(self):
        """测试 ID 计算一致性。"""
        id1 = compute_deterministic_id(["张明"])
        id2 = compute_deterministic_id(["张明"])
        assert id1 == id2

    def test_compute_deterministic_id_different(self):
        """测试不同值产生不同 ID。"""
        id1 = compute_deterministic_id(["张明"])
        id2 = compute_deterministic_id(["李婷"])
        assert id1 != id2

    def test_compute_deterministic_id_multiple_fields(self):
        """测试多字段 ID 计算。"""
        id1 = compute_deterministic_id(["张明", "研发部"])
        id2 = compute_deterministic_id(["张明", "产品部"])
        assert id1 != id2

    def test_compute_deterministic_id_integer(self):
        """测试整数值 ID 计算。"""
        id1 = compute_deterministic_id([123])
        id2 = compute_deterministic_id([123])
        assert id1 == id2

    def test_compute_deterministic_id_mixed_types(self):
        """测试混合类型 ID 计算。"""
        id1 = compute_deterministic_id(["张明", 28, True])
        id2 = compute_deterministic_id(["张明", 28, True])
        assert id1 == id2


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
            identity_fields=["name"],
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
