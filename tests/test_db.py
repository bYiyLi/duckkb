"""数据库连接测试。"""


class TestEnsureFtsInstalled:
    """FTS 扩展安装测试。"""

    def test_ensure_fts_installed_success(self, engine):
        """测试 FTS 扩展安装成功。"""
        engine._ensure_fts_installed()

        result = engine.execute_read(
            "SELECT extension_name FROM duckdb_extensions() WHERE extension_name = 'fts'"
        )
        assert len(result) > 0

    def test_ensure_fts_installed_idempotent(self, engine):
        """测试重复安装 FTS 扩展（幂等性）。"""
        engine._ensure_fts_installed()
        engine._ensure_fts_installed()

        result = engine.execute_read(
            "SELECT extension_name FROM duckdb_extensions() WHERE extension_name = 'fts'"
        )
        assert len(result) > 0


class TestReadConnection:
    """只读连接测试。"""

    def test_read_connection_loads_fts_after_ensure(self, engine):
        """测试初始化后只读连接加载 FTS。"""
        conn = engine._create_read_connection()
        try:
            result = conn.execute("SELECT 1").fetchall()
            assert len(result) == 1
        finally:
            conn.close()

    def test_read_connection_can_use_fts_functions(self, engine):
        """测试只读连接可以使用 FTS 函数。"""
        conn = engine._create_read_connection()
        try:
            conn.execute("LOAD fts")
            result = conn.execute("SELECT 1").fetchall()
            assert len(result) == 1
        finally:
            conn.close()
