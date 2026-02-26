"""导入测试。"""

import hashlib
import json
from datetime import UTC, datetime

import pytest
import yaml


class TestImportNodes:
    """节点导入测试。"""

    @pytest.mark.asyncio
    async def test_import_single_node(self, async_engine, tmp_path):
        """测试导入单个节点。"""
        yaml_content = """
- type: Character
  name: 测试角色
  bio: 这是一个测试角色的简介。
"""
        yaml_file = tmp_path / "test_bundle.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await async_engine.import_knowledge_bundle(str(yaml_file))

        assert result["status"] == "success"
        assert "Character" in result["nodes"]["upserted"]

    @pytest.mark.asyncio
    async def test_import_node_update(self, async_engine, tmp_path):
        """测试更新已存在的节点。"""
        yaml_content1 = """
- type: Character
  name: 张明
  bio: 原始简介
"""
        yaml_file1 = tmp_path / "bundle1.yaml"
        yaml_file1.write_text(yaml_content1, encoding="utf-8")
        await async_engine.import_knowledge_bundle(str(yaml_file1))

        yaml_content2 = """
- type: Character
  name: 张明
  bio: 更新后的简介
"""
        yaml_file2 = tmp_path / "bundle2.yaml"
        yaml_file2.write_text(yaml_content2, encoding="utf-8")
        result = await async_engine.import_knowledge_bundle(str(yaml_file2))

        assert result["status"] == "success"

        row = async_engine.execute_read(
            "SELECT bio FROM characters WHERE name = ?", ["张明"]
        )[0]
        assert row is not None
        assert row[0] == "更新后的简介"


class TestImportValidation:
    """导入校验测试。"""

    @pytest.mark.asyncio
    async def test_import_invalid_yaml(self, async_engine, tmp_path):
        """测试无效 YAML 格式。"""
        yaml_file = tmp_path / "invalid.yaml"
        yaml_file.write_text("invalid: [unclosed", encoding="utf-8")

        with pytest.raises(Exception):
            await async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_import_not_array(self, async_engine, tmp_path):
        """测试非数组根节点。"""
        yaml_file = tmp_path / "not_array.yaml"
        yaml_file.write_text("key: value", encoding="utf-8")

        with pytest.raises(ValueError, match="must contain an array"):
            await async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_import_missing_type(self, async_engine, tmp_path):
        """测试缺失类型字段。"""
        yaml_content = """
- name: 张明
  bio: 没有类型字段
"""
        yaml_file = tmp_path / "missing_type.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        with pytest.raises(Exception):
            await async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_import_unknown_type(self, async_engine, tmp_path):
        """测试未知类型。"""
        yaml_content = """
- type: UnknownType
  id: test
"""
        yaml_file = tmp_path / "unknown_type.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        with pytest.raises(Exception):
            await async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_import_file_not_found(self, async_engine, tmp_path):
        """测试文件不存在。"""
        with pytest.raises(FileNotFoundError):
            await async_engine.import_knowledge_bundle(str(tmp_path / "nonexistent.yaml"))


class TestImportHelpers:
    """导入辅助方法测试。"""

    def test_compute_hash_sync(self, engine):
        """测试哈希计算。"""
        text = "测试文本"
        hash_result = engine._compute_hash_sync(text)
        expected = hashlib.md5(text.encode("utf-8")).hexdigest()
        assert hash_result == expected

    def test_chunk_text_sync_short(self, engine):
        """测试短文本切片。"""
        text = "短文本"
        chunks = engine._chunk_text_sync(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_text_sync_empty(self, engine):
        """测试空文本切片。"""
        chunks = engine._chunk_text_sync("")
        assert chunks == []

    def test_group_items_by_type_and_action(self, engine):
        """测试按类型和操作分组。"""
        items = [
            {"type": "Character", "name": "A"},
            {"type": "Character", "action": "delete", "name": "B"},
            {"type": "Document", "doc_id": "D1"},
        ]
        grouped = engine._group_items_by_type_and_action(items)

        assert "Character" in grouped
        assert len(grouped["Character"]["upsert"]) == 1
        assert len(grouped["Character"]["delete"]) == 1
        assert "Document" in grouped
        assert len(grouped["Document"]["upsert"]) == 1
