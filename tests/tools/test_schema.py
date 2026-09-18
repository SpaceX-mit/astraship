from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from astraship.errors import ToolRegistrationError
from astraship.tools import ToolCall, ToolContext, ToolDefinition, validate_arguments


async def echo(arguments: Mapping[str, Any], context: ToolContext) -> object:
    return {"arguments": dict(arguments), "workspace": str(context.workspace)}


def test_public_values_validate_identity_and_normalize_workspace(tmp_path: Path) -> None:
    definition = ToolDefinition(
        name="echo_1",
        description="Echo arguments",
        parameters={"type": "object", "additionalProperties": False},
        execute=echo,
    )
    call = ToolCall(call_id="call-1", name="echo_1", arguments={})
    context = ToolContext(tmp_path / "nested" / "..", metadata={"source": "test"})

    assert definition.name == "echo_1"
    assert call.call_id == "call-1"
    assert context.workspace == tmp_path.resolve()
    assert context.metadata == {"source": "test"}


@pytest.mark.parametrize("name", ["", "Upper", "has-dash", "1tool", "a" * 65])
def test_definition_rejects_invalid_model_facing_names(name: str) -> None:
    with pytest.raises(ToolRegistrationError, match="name"):
        ToolDefinition(name, "description", {"type": "object"}, echo)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"description": ""},
        {"parameters": {"type": "string"}},
        {"execute": None},
    ],
)
def test_definition_rejects_invalid_contract_fields(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "name": "echo",
        "description": "Echo arguments",
        "parameters": {"type": "object"},
        "execute": echo,
    }
    values.update(kwargs)

    with pytest.raises(ToolRegistrationError):
        ToolDefinition(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "oneOf": []},
        {"type": "object", "properties": {"x": {"format": "uri"}}},
        {"type": "mystery"},
        {"type": "object", "required": ["missing"]},
    ],
)
def test_definition_rejects_unsupported_or_inconsistent_schema(schema: dict[str, object]) -> None:
    with pytest.raises(ToolRegistrationError, match="schema"):
        ToolDefinition("echo", "Echo arguments", schema, echo)


def test_validate_arguments_accepts_supported_nested_constraints() -> None:
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 2, "maxLength": 4},
            "count": {"type": "integer", "minimum": 1, "maximum": 3},
            "ratio": {"type": "number"},
            "enabled": {"type": "boolean"},
            "nothing": {"type": "null"},
            "tags": {
                "type": "array",
                "items": {"type": "string", "pattern": "^[a-z]+$"},
                "minItems": 1,
                "maxItems": 2,
            },
            "mode": {"type": "string", "enum": ["fast", "safe"]},
        },
        "required": ["name", "count", "tags"],
        "additionalProperties": False,
    }

    assert (
        validate_arguments(
            schema,
            {
                "name": "ship",
                "count": 2,
                "ratio": 1.5,
                "enabled": True,
                "nothing": None,
                "tags": ["alpha", "beta"],
                "mode": "safe",
            },
        )
        is None
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({}, "$.name: required property is missing"),
        ({"name": "ok", "items": [{"count": True}]}, "$.items[0].count: expected integer"),
        ({"name": "ok", "items": [{"count": 4}]}, "$.items[0].count: must be at most 3"),
        (
            {"name": "ok", "items": [{"count": 2}], "extra": 1},
            "$.extra: additional property is not allowed",
        ),
    ],
)
def test_validate_arguments_returns_first_precise_error(value: object, expected: str) -> None:
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"count": {"type": "integer", "maximum": 3}},
                    "required": ["count"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    }

    assert validate_arguments(schema, value) == expected
