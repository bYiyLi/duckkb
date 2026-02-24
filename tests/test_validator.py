from datetime import datetime

import pytest

from duckkb.database.engine.ontology._validator import validate_json_by_schema


class TestValidator:
    def test_basic_validation(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name"],
        }

        # Valid data
        data = {"name": "Alice", "age": 30}
        assert validate_json_by_schema(schema, data) == data

        # Missing required
        with pytest.raises(ValueError, match="missing required property"):
            validate_json_by_schema(schema, {"age": 30})

        # Type mismatch
        with pytest.raises(ValueError, match="expected integer"):
            validate_json_by_schema(schema, {"name": "Alice", "age": "30"})

    def test_coercion(self):
        schema = {
            "type": "object",
            "properties": {"created_at": {"type": "string", "format": "date-time"}},
        }

        data = {"created_at": "2023-01-01T12:00:00Z"}
        result = validate_json_by_schema(schema, data)
        # Assuming the validator converts to datetime object
        assert isinstance(result["created_at"], datetime)
        assert result["created_at"].year == 2023

    def test_additional_properties(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": False,
        }

        with pytest.raises(ValueError, match="unexpected property"):
            validate_json_by_schema(schema, {"name": "Alice", "extra": "value"})

    def test_nested_validation(self):
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                }
            },
        }

        # Valid
        validate_json_by_schema(schema, {"user": {"name": "Alice"}})

        # Invalid nested
        with pytest.raises(ValueError, match="missing required property"):
            validate_json_by_schema(schema, {"user": {}})
