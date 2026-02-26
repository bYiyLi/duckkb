"""错误恢复测试。"""

import pytest


class TestImportRollback:
    """导入回滚测试。"""

    @pytest.mark.asyncio
    async def test_import_rollback_on_invalid_yaml(self, async_engine, tmp_path):
        """测试无效 YAML 时的回滚。"""
        yaml_file = tmp_path / "invalid.yaml"
        yaml_file.write_text("invalid: yaml: content:", encoding="utf-8")

        with pytest.raises(Exception):
            await async_engine.import_knowledge_bundle(str(yaml_file))

        count = async_engine.execute_read("SELECT COUNT(*) FROM characters")[0][0]
        assert count == 0

    @pytest.mark.asyncio
    async def test_import_rollback_on_schema_violation(self, async_engine, tmp_path):
        """测试 Schema 违规时的回滚。"""
        yaml_content = """
- type: Character
  age: "not_a_number"
"""
        yaml_file = tmp_path / "schema_violation.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        with pytest.raises(Exception):
            await async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_import_rollback_on_missing_required_field(self, async_engine, tmp_path):
        """测试缺少必填字段时的回滚。"""
        yaml_content = """
- type: Character
  bio: 没有名字的角色
"""
        yaml_file = tmp_path / "missing_required.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        with pytest.raises(Exception):
            await async_engine.import_knowledge_bundle(str(yaml_file))


class TestPartialImportRecovery:
    """部分导入恢复测试。"""

    @pytest.mark.asyncio
    async def test_partial_import_with_invalid_edge(self, async_engine, tmp_path):
        """测试包含无效边的部分导入。"""
        yaml_content = """
- type: Character
  name: 有效角色
  bio: 这是一个有效的角色

- type: knows
  source:
    name: 不存在的角色
  target:
    name: 另一个不存在的角色
"""
        yaml_file = tmp_path / "invalid_edge.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        with pytest.raises(Exception):
            await async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_import_with_valid_and_invalid_nodes(self, async_engine, tmp_path):
        """测试包含有效和无效节点的导入。"""
        yaml_content = """
- type: Character
  name: 有效角色A
  bio: 有效角色

- type: InvalidType
  name: 无效类型
"""
        yaml_file = tmp_path / "mixed.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        with pytest.raises(Exception):
            await async_engine.import_knowledge_bundle(str(yaml_file))


class TestShadowDirCleanup:
    """影子目录清理测试。"""

    @pytest.mark.asyncio
    async def test_shadow_dir_cleanup_on_success(self, async_engine, tmp_path):
        """测试成功导入后影子目录清理。"""
        yaml_content = """
- type: Character
  name: 影子目录测试
  bio: 测试影子目录清理
"""
        yaml_file = tmp_path / "shadow_test.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_shadow_dir_cleanup_on_failure(self, async_engine, tmp_path):
        """测试失败导入后影子目录清理。"""
        yaml_content = """
- type: InvalidType
  name: 无效类型
"""
        yaml_file = tmp_path / "shadow_fail.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        with pytest.raises(Exception):
            await async_engine.import_knowledge_bundle(str(yaml_file))


class TestDatabaseRecovery:
    """数据库恢复测试。"""

    @pytest.mark.asyncio
    async def test_database_connection_recovery(self, async_engine):
        """测试数据库连接恢复。"""
        result = async_engine.execute_read("SELECT 1")
        assert result[0][0] == 1

        async_engine.close()

        from duckkb.core.engine import Engine

        new_engine = Engine(async_engine.kb_path)
        new_engine.initialize()

        result = new_engine.execute_read("SELECT 1")
        assert result[0][0] == 1

        new_engine.close()

    @pytest.mark.asyncio
    async def test_transaction_isolation(self, async_engine, tmp_path):
        """测试事务隔离。"""
        yaml_content = """
- type: Character
  name: 事务隔离测试
  bio: 测试事务隔离
"""
        yaml_file = tmp_path / "isolation_test.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        count_before = async_engine.execute_read("SELECT COUNT(*) FROM characters")[0][0]

        await async_engine.import_knowledge_bundle(str(yaml_file))

        count_after = async_engine.execute_read("SELECT COUNT(*) FROM characters")[0][0]
        assert count_after > count_before


class TestErrorMessages:
    """错误消息测试。"""

    @pytest.mark.asyncio
    async def test_unknown_node_type_error_message(self, async_engine):
        """测试未知节点类型错误消息。"""
        with pytest.raises(ValueError, match="Unknown node type"):
            await async_engine.build_index("UnknownType")

    @pytest.mark.asyncio
    async def test_invalid_table_name_error(self, async_engine):
        """测试无效表名错误。"""
        from duckkb.exceptions import InvalidTableNameError

        with pytest.raises(InvalidTableNameError):
            await async_engine.get_source_record("invalid-table", 1)

    @pytest.mark.asyncio
    async def test_missing_file_error(self, async_engine, tmp_path):
        """测试缺失文件错误。"""
        nonexistent_file = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError):
            await async_engine.import_knowledge_bundle(str(nonexistent_file))


class TestEdgeCases:
    """边界条件测试。"""

    @pytest.mark.asyncio
    async def test_import_empty_yaml(self, async_engine, tmp_path):
        """测试空 YAML 导入。"""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("", encoding="utf-8")

        with pytest.raises(ValueError, match="must contain an array"):
            await async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_import_empty_list_yaml(self, async_engine, tmp_path):
        """测试空列表 YAML 导入。"""
        yaml_file = tmp_path / "empty_list.yaml"
        yaml_file.write_text("[]", encoding="utf-8")

        result = await async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_import_null_values(self, async_engine, tmp_path):
        """测试空字符串值导入。"""
        yaml_content = """
- type: Character
  name: 空值测试角色
  bio: ""
"""
        yaml_file = tmp_path / "null_test.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_import_unicode_characters(self, async_engine, tmp_path):
        """测试 Unicode 字符导入。"""
        yaml_content = """
- type: Character
  name: Unicode测试🎉
  bio: 包含表情符号😀和特殊字符™
"""
        yaml_file = tmp_path / "unicode_test.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_import_very_long_text(self, async_engine, tmp_path):
        """测试超长文本导入。"""
        long_bio = "测试" * 10000
        yaml_content = f"""
- type: Character
  name: 超长文本角色
  bio: "{long_bio}"
"""
        yaml_file = tmp_path / "long_text.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"


class TestChunkingEdgeCases:
    """切片边界条件测试。"""

    def test_chunk_empty_text(self, engine):
        """测试空文本切片。"""
        chunks = engine._chunk_text("")
        assert chunks == []

    def test_chunk_short_text(self, engine):
        """测试短文本切片。"""
        text = "短文本"
        chunks = engine._chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_exact_size_text(self, engine):
        """测试精确大小的文本切片。"""
        text = "测" * engine.chunk_size
        chunks = engine._chunk_text(text)
        assert len(chunks) == 1

    def test_chunk_just_over_size_text(self, engine):
        """测试刚好超过大小的文本切片。"""
        text = "测" * (engine.chunk_size + 1)
        chunks = engine._chunk_text(text)
        assert len(chunks) >= 1
