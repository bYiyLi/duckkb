"""引擎测试。"""

import pytest


class TestEngineInit:
    """引擎初始化测试。"""

    def test_engine_initialize_success(self, test_kb_path):
        """测试引擎初始化成功。"""
        from duckkb.core.engine import Engine

        engine = Engine(test_kb_path)
        result = engine.initialize()

        assert result is engine
        engine.close()

    def test_engine_context_manager(self, test_kb_path):
        """测试引擎上下文管理器。"""
        from duckkb.core.engine import Engine

        with Engine(test_kb_path) as engine:
            assert engine.db_path is not None

    def test_engine_close(self, engine):
        """测试引擎关闭。"""
        assert engine._db_path is not None
        engine.close()

    def test_engine_properties(self, engine):
        """测试引擎属性。"""
        assert engine.kb_path is not None
        assert engine.config is not None
        assert engine.ontology is not None

    @pytest.mark.asyncio
    async def test_async_initialize(self, test_kb_path):
        """测试异步初始化。"""
        from duckkb.core.engine import Engine

        engine = Engine(test_kb_path)
        result = await engine.async_initialize()

        assert result is engine
        engine.close()


class TestEngineSchema:
    """引擎 Schema 测试。"""

    def test_sync_schema(self, engine):
        """测试同步 Schema。"""
        tables = engine.execute_read(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        )
        table_names = [t[0] for t in tables]

        assert "characters" in table_names
        assert "documents" in table_names
        assert "products" in table_names
        assert "edge_knows" in table_names
        assert "edge_authored" in table_names
        assert "edge_mentions" in table_names

    def test_create_index_tables(self, engine):
        """测试创建索引表。"""
        tables = engine.execute_read(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        )
        table_names = [t[0] for t in tables]

        assert "_sys_search_index" in table_names
        assert "_sys_search_cache" in table_names


class TestEngineConfig:
    """引擎配置测试。"""

    def test_get_global_config(self, engine):
        """测试获取全局配置。"""
        global_config = engine._get_global_config()
        assert global_config.chunk_size == 800
        assert global_config.embedding_model == "text-embedding-3-small"
        assert global_config.tokenizer == "jieba"

    def test_embedding_dim(self, engine):
        """测试嵌入维度。"""
        assert engine.embedding_dim == 1536

    def test_chunk_size(self, engine):
        """测试切片大小。"""
        assert engine.chunk_size == 800
