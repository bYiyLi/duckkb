import pytest

from duckkb.database.schema import init_schema
from duckkb.mcp.server import validate_and_import
from duckkb.utils.file_ops import read_jsonl


class TestIndexer:
    @pytest.mark.asyncio
    async def test_read_records_valid(self, tmp_path):
        jsonl_path = tmp_path / "test.jsonl"
        jsonl_path.write_text(
            '{"id": "1", "name": "Alice"}\n{"id": "2", "name": "Bob"}\n',
            encoding="utf-8",
        )

        records = await read_jsonl(jsonl_path)

        assert len(records) == 2
        assert records[0]["id"] == "1"
        assert records[1]["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_read_records_empty_lines(self, tmp_path):
        jsonl_path = tmp_path / "test.jsonl"
        jsonl_path.write_text(
            '{"id": "1"}\n\n{"id": "2"}\n',
            encoding="utf-8",
        )

        records = await read_jsonl(jsonl_path)

        assert len(records) == 2

    @pytest.mark.asyncio
    async def test_read_records_empty_file(self, tmp_path):
        jsonl_path = tmp_path / "test.jsonl"
        jsonl_path.write_text("", encoding="utf-8")

        records = await read_jsonl(jsonl_path)

        assert records == []

    @pytest.mark.asyncio
    async def test_validate_and_import_missing_id(self, mock_kb_path):
        await init_schema()

        temp_file = mock_kb_path / "temp.jsonl"
        temp_file.write_text('{"name": "NoId"}', encoding="utf-8")

        with pytest.raises(ValueError, match="Missing required field 'id'"):
            await validate_and_import("test", str(temp_file))

    @pytest.mark.asyncio
    async def test_validate_and_import_invalid_json(self, mock_kb_path):
        await init_schema()

        temp_file = mock_kb_path / "temp.jsonl"
        temp_file.write_text('{"id": "1"}\nnot json', encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid JSON format"):
            await validate_and_import("test", str(temp_file))

    @pytest.mark.asyncio
    async def test_validate_and_import_non_object(self, mock_kb_path):
        await init_schema()

        temp_file = mock_kb_path / "temp.jsonl"
        temp_file.write_text('["not", "an", "object"]', encoding="utf-8")

        with pytest.raises(ValueError, match="must be a JSON object"):
            await validate_and_import("test", str(temp_file))

    @pytest.mark.asyncio
    async def test_validate_and_import_file_not_found(self, mock_kb_path):
        await init_schema()

        non_existent = mock_kb_path / "non_existent.jsonl"

        with pytest.raises(FileNotFoundError):
            await validate_and_import("test", str(non_existent))
