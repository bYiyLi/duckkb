import pytest

from duckkb.database.engine.search import query_raw_sql
from duckkb.exceptions import DatabaseError


class TestSQLSecurity:
    def test_forbidden_keyword_delete(self):
        with pytest.raises(DatabaseError, match="Only SELECT queries are allowed"):
            import asyncio

            asyncio.run(query_raw_sql("DELETE FROM users"))

    def test_forbidden_keyword_insert(self):
        with pytest.raises(DatabaseError, match="Only SELECT queries are allowed"):
            import asyncio

            asyncio.run(query_raw_sql("INSERT INTO users VALUES (1)"))

    def test_forbidden_keyword_drop(self):
        with pytest.raises(DatabaseError, match="Only SELECT queries are allowed"):
            import asyncio

            asyncio.run(query_raw_sql("DROP TABLE users"))

    def test_forbidden_keyword_update(self):
        with pytest.raises(DatabaseError, match="Only SELECT queries are allowed"):
            import asyncio

            asyncio.run(query_raw_sql("UPDATE users SET name = 'x'"))

    def test_forbidden_keyword_create(self):
        with pytest.raises(DatabaseError, match="Only SELECT queries are allowed"):
            import asyncio

            asyncio.run(query_raw_sql("CREATE TABLE test (id INT)"))

    def test_forbidden_keyword_alter(self):
        with pytest.raises(DatabaseError, match="Only SELECT queries are allowed"):
            import asyncio

            asyncio.run(query_raw_sql("ALTER TABLE users ADD COLUMN x INT"))

    def test_forbidden_keyword_pragma(self):
        with pytest.raises(DatabaseError, match="Only SELECT queries are allowed"):
            import asyncio

            asyncio.run(query_raw_sql("PRAGMA table_info(users)"))

    def test_forbidden_keyword_attach(self):
        with pytest.raises(DatabaseError, match="Only SELECT queries are allowed"):
            import asyncio

            asyncio.run(query_raw_sql("ATTACH DATABASE 'test.db' AS test"))

    def test_forbidden_keyword_begin(self):
        with pytest.raises(DatabaseError, match="Only SELECT queries are allowed"):
            import asyncio

            asyncio.run(query_raw_sql("BEGIN TRANSACTION"))

    def test_auto_limit_added(self):
        import asyncio
        from unittest.mock import MagicMock, patch

        from duckkb.constants import QUERY_DEFAULT_LIMIT

        with patch("duckkb.database.engine.search.get_db") as mock_get_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.description = [("id",), ("name",)]
            mock_conn.execute.return_value.fetchall.return_value = []
            mock_get_db.return_value.__enter__ = lambda s: mock_conn
            mock_get_db.return_value.__exit__ = lambda s, *args: None

            asyncio.run(query_raw_sql("SELECT * FROM users"))

            call_args = mock_conn.execute.call_args[0][0]
            assert f"LIMIT {QUERY_DEFAULT_LIMIT}" in call_args

    def test_existing_limit_preserved(self):
        import asyncio
        from unittest.mock import MagicMock, patch

        with patch("duckkb.database.engine.search.get_db") as mock_get_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.description = [("id",), ("name",)]
            mock_conn.execute.return_value.fetchall.return_value = []
            mock_get_db.return_value.__enter__ = lambda s: mock_conn
            mock_get_db.return_value.__exit__ = lambda s, *args: None

            asyncio.run(query_raw_sql("SELECT * FROM users LIMIT 5"))

            call_args = mock_conn.execute.call_args[0][0]
            assert call_args.count("LIMIT") == 1
            assert "LIMIT 5" in call_args

    def test_case_insensitive_forbidden(self):
        with pytest.raises(DatabaseError, match="Only SELECT queries are allowed"):
            import asyncio

            asyncio.run(query_raw_sql("delete from users"))

        with pytest.raises(DatabaseError, match="Only SELECT queries are allowed"):
            import asyncio

            asyncio.run(query_raw_sql("Delete From users"))

    def test_subquery_with_forbidden_keyword(self):
        """测试子查询中包含危险关键字的情况。"""
        import asyncio

        with pytest.raises(DatabaseError, match="Forbidden keyword"):
            asyncio.run(query_raw_sql("SELECT * FROM (DELETE FROM users)"))

    def test_select_with_insert_in_subquery(self):
        """测试 SELECT 语句中子查询包含 INSERT 的情况。"""
        import asyncio

        with pytest.raises(DatabaseError, match="Forbidden keyword"):
            asyncio.run(query_raw_sql("SELECT * FROM (INSERT INTO users VALUES (1))"))
