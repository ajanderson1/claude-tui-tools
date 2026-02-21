"""Tests for schema module."""

from claude_tui_settings.models.schema import parse_schema_properties


def test_parse_basic_properties():
    schema = {
        "properties": {
            "effortLevel": {
                "type": "string",
                "description": "Effort level",
                "default": "medium",
                "enum": ["low", "medium", "high"],
            },
            "respectGitignore": {
                "type": "boolean",
                "description": "Respect .gitignore",
                "default": True,
            },
            "maxTokens": {
                "type": "number",
                "description": "Max tokens",
            },
        }
    }
    result = parse_schema_properties(schema)
    assert len(result) == 3

    effort = next(r for r in result if r["key"] == "effortLevel")
    assert effort["type"] == "string"
    assert effort["enum"] == ["low", "medium", "high"]
    assert effort["default"] == "medium"

    respect = next(r for r in result if r["key"] == "respectGitignore")
    assert respect["type"] == "boolean"
    assert respect["default"] is True


def test_parse_oneof_enum():
    """Test oneOf pattern for enum-like settings."""
    schema = {
        "properties": {
            "outputStyle": {
                "description": "Output style",
                "oneOf": [
                    {"const": "concise"},
                    {"const": "verbose"},
                    {"const": "normal"},
                ],
            },
        }
    }
    result = parse_schema_properties(schema)
    assert len(result) == 1
    assert result[0]["enum"] == ["concise", "verbose", "normal"]


def test_parse_union_type():
    """Test union type like ['string', 'null']."""
    schema = {
        "properties": {
            "model": {
                "type": ["string", "null"],
                "description": "Model name",
            },
        }
    }
    result = parse_schema_properties(schema)
    assert result[0]["type"] == "string"


def test_parse_empty_schema():
    result = parse_schema_properties({})
    assert result == []
