import pytest

from duckkb.constants import SYS_SEARCH_TABLE
from duckkb.db import get_db
from duckkb.engine.importer import validate_and_import
from duckkb.engine.sync import _bulk_insert, _read_records
from duckkb.exceptions import ValidationError
from duckkb.schema import init_schema


class TestIndexer:
    def test_read_records_valid(self, tmp_path):
        jsonl_path = tmp_path / "test.jsonl"
        jsonl_path.write_text(
            '{"id": "1", "name": "Alice"}\n{"id": "2", "name": "Bob"}\n',
            encoding="utf-8",
        )

        records = _read_records(jsonl_path)

        assert len(records) == 2
        assert records[0]["id"] == "1"
        assert records[1]["name"] == "Bob"

    def test_read_records_empty_lines(self, tmp_path):
        jsonl_path = tmp_path / "test.jsonl"
        jsonl_path.write_text(
            '{"id": "1"}\n\n{"id": "2"}\n',
            encoding="utf-8",
        )

        records = _read_records(jsonl_path)

        assert len(records) == 2

    def test_read_records_invalid_json(self, tmp_path):
        jsonl_path = tmp_path / "test.jsonl"
        jsonl_path.write_text(
            '{"id": "1"}\ninvalid json\n',
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="Failed to parse"):
            _read_records(jsonl_path)

    def test_read_records_empty_file(self, tmp_path):
        jsonl_path = tmp_path / "test.jsonl"
        jsonl_path.write_text("", encoding="utf-8")

        records = _read_records(jsonl_path)

        assert records == []

    @pytest.mark.asyncio
    async def test_validate_and_import_missing_id(self, mock_kb_path):
        await init_schema()

        temp_file = mock_kb_path / "temp.jsonl"
        temp_file.write_text('{"name": "NoId"}', encoding="utf-8")

        with pytest.raises(ValidationError, match="Missing required field 'id'"):
            await validate_and_import("test", temp_file)

    @pytest.mark.asyncio
    async def test_validate_and_import_invalid_json(self, mock_kb_path):
        await init_schema()

        temp_file = mock_kb_path / "temp.jsonl"
        temp_file.write_text('{"id": "1"}\nnot json', encoding="utf-8")

        with pytest.raises(ValidationError, match="Invalid JSON format"):
            await validate_and_import("test", temp_file)

    @pytest.mark.asyncio
    async def test_validate_and_import_non_object(self, mock_kb_path):
        await init_schema()

        temp_file = mock_kb_path / "temp.jsonl"
        temp_file.write_text('["not", "an", "object"]', encoding="utf-8")

        with pytest.raises(ValidationError, match="must be a JSON object"):
            await validate_and_import("test", temp_file)

    @pytest.mark.asyncio
    async def test_validate_and_import_file_not_found(self, mock_kb_path):
        await init_schema()

        non_existent = mock_kb_path / "non_existent.jsonl"

        with pytest.raises(FileNotFoundError):
            await validate_and_import("test", non_existent)

    @pytest.mark.asyncio
    async def test_bulk_insert_transaction(self, mock_kb_path):
        await init_schema()

        rows = [
            ("1", "users", "name", "Alice", "hash1", '{"id": "1", "name": "Alice"}', 1.0),
            ("2", "users", "name", "Bob", "hash2", '{"id": "2", "name": "Bob"}', 1.0),
        ]

        _bulk_insert("users", rows)

        with get_db() as conn:
            count = conn.execute(f"SELECT count(*) FROM {SYS_SEARCH_TABLE}").fetchone()[0]
            assert count == 2

    @pytest.mark.asyncio
    async def test_bulk_insert_replaces_existing(self, mock_kb_path):
        await init_schema()

        rows1 = [
            ("1", "users", "name", "Alice", "hash1", '{"id": "1"}', 1.0),
        ]
        rows2 = [
            ("2", "users", "name", "Bob", "hash2", '{"id": "2"}', 1.0),
        ]

        _bulk_insert("users", rows1)
        _bulk_insert("users", rows2)

        with get_db() as conn:
            count = conn.execute(
                f"SELECT count(*) FROM {SYS_SEARCH_TABLE} WHERE source_table = 'users'"
            ).fetchone()[0]
            assert count == 1
