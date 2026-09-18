"""Strict dependency-free validation for Astraship's JSON Schema subset."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from astraship.errors import ToolRegistrationError

_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}
_COMMON = {"type"}
_KEYWORDS = {
    "object": _COMMON | {"properties", "required", "additionalProperties"},
    "array": _COMMON | {"items", "minItems", "maxItems"},
    "string": _COMMON | {"minLength", "maxLength", "enum", "pattern"},
    "integer": _COMMON | {"minimum", "maximum"},
    "number": _COMMON | {"minimum", "maximum"},
    "boolean": _COMMON,
    "null": _COMMON,
}


def validate_schema(schema: Mapping[str, Any], *, root_object: bool = False) -> None:
    """Reject unsupported or internally inconsistent schema definitions."""

    _validate_schema_node(schema, "$")
    if root_object and schema.get("type") != "object":
        raise ToolRegistrationError("tool parameters schema root must have type object")


def _validate_schema_node(schema: object, path: str) -> None:
    if not isinstance(schema, Mapping):
        raise ToolRegistrationError(f"schema {path} must be an object")
    schema_type = schema.get("type")
    if schema_type not in _TYPES:
        raise ToolRegistrationError(f"schema {path} has unsupported type {schema_type!r}")
    unsupported = set(schema) - _KEYWORDS[schema_type]
    if unsupported:
        keyword = sorted(unsupported)[0]
        raise ToolRegistrationError(f"schema {path} has unsupported keyword {keyword!r}")

    if schema_type == "object":
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping) or not all(
            isinstance(key, str) for key in properties
        ):
            raise ToolRegistrationError(f"schema {path}.properties must be an object")
        for key, child in properties.items():
            _validate_schema_node(child, _property_path(path, key))
        required = schema.get("required", [])
        if (
            not isinstance(required, list)
            or not all(isinstance(item, str) for item in required)
            or len(set(required)) != len(required)
        ):
            raise ToolRegistrationError(f"schema {path}.required must contain unique strings")
        missing = set(required) - set(properties)
        if missing:
            raise ToolRegistrationError(
                f"schema {path}.required references unknown property {sorted(missing)[0]!r}"
            )
        additional = schema.get("additionalProperties", True)
        if not isinstance(additional, bool):
            raise ToolRegistrationError(f"schema {path}.additionalProperties must be boolean")
    elif schema_type == "array":
        if "items" not in schema:
            raise ToolRegistrationError(f"schema {path}.items is required")
        _validate_schema_node(schema["items"], f"{path}[]")
        _validate_nonnegative_integer(schema, "minItems", path)
        _validate_nonnegative_integer(schema, "maxItems", path)
        if schema.get("minItems", 0) > schema.get("maxItems", math.inf):
            raise ToolRegistrationError(f"schema {path} has minItems greater than maxItems")
    elif schema_type == "string":
        _validate_nonnegative_integer(schema, "minLength", path)
        _validate_nonnegative_integer(schema, "maxLength", path)
        if schema.get("minLength", 0) > schema.get("maxLength", math.inf):
            raise ToolRegistrationError(f"schema {path} has minLength greater than maxLength")
        enum = schema.get("enum")
        if enum is not None and (
            not isinstance(enum, list)
            or not enum
            or not all(isinstance(item, str) for item in enum)
            or len(set(enum)) != len(enum)
        ):
            raise ToolRegistrationError(f"schema {path}.enum must contain unique strings")
        pattern = schema.get("pattern")
        if pattern is not None:
            if not isinstance(pattern, str):
                raise ToolRegistrationError(f"schema {path}.pattern must be a string")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ToolRegistrationError(f"schema {path}.pattern is invalid: {exc}") from exc
    elif schema_type in {"integer", "number"}:
        for keyword in ("minimum", "maximum"):
            value = schema.get(keyword)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ToolRegistrationError(f"schema {path}.{keyword} must be finite numeric")
        if schema.get("minimum", -math.inf) > schema.get("maximum", math.inf):
            raise ToolRegistrationError(f"schema {path} has minimum greater than maximum")


def _validate_nonnegative_integer(schema: Mapping[str, Any], keyword: str, path: str) -> None:
    value = schema.get(keyword)
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
        raise ToolRegistrationError(f"schema {path}.{keyword} must be a non-negative integer")


def validate_arguments(schema: Mapping[str, Any], value: object) -> str | None:
    """Return the first deterministic validation error, or ``None``."""

    validate_schema(schema)
    return _validate_value(schema, value, "$")


def _validate_value(schema: Mapping[str, Any], value: object, path: str) -> str | None:
    schema_type = schema["type"]
    if not _matches_type(schema_type, value):
        return f"{path}: expected {schema_type}"

    if schema_type == "object":
        assert isinstance(value, Mapping)
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                return f"{_property_path(path, key)}: required property is missing"
        for key, item in value.items():
            item_path = _property_path(path, str(key))
            if not isinstance(key, str):
                return f"{item_path}: property name must be a string"
            child = properties.get(key)
            if child is None:
                if schema.get("additionalProperties", True) is False:
                    return f"{item_path}: additional property is not allowed"
                continue
            error = _validate_value(child, item, item_path)
            if error is not None:
                return error
    elif schema_type == "array":
        assert isinstance(value, list)
        if len(value) < schema.get("minItems", 0):
            return f"{path}: must contain at least {schema['minItems']} items"
        if len(value) > schema.get("maxItems", math.inf):
            return f"{path}: must contain at most {schema['maxItems']} items"
        for index, item in enumerate(value):
            error = _validate_value(schema["items"], item, f"{path}[{index}]")
            if error is not None:
                return error
    elif schema_type == "string":
        assert isinstance(value, str)
        if len(value) < schema.get("minLength", 0):
            return f"{path}: length must be at least {schema['minLength']}"
        if len(value) > schema.get("maxLength", math.inf):
            return f"{path}: length must be at most {schema['maxLength']}"
        if "enum" in schema and value not in schema["enum"]:
            return f"{path}: value is not in enum"
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            return f"{path}: value does not match pattern"
    elif schema_type in {"integer", "number"}:
        assert isinstance(value, (int, float)) and not isinstance(value, bool)
        if not math.isfinite(value):
            return f"{path}: number must be finite"
        if value < schema.get("minimum", -math.inf):
            return f"{path}: must be at least {schema['minimum']}"
        if value > schema.get("maximum", math.inf):
            return f"{path}: must be at most {schema['maximum']}"
    return None


def _matches_type(schema_type: str, value: object) -> bool:
    return {
        "object": lambda: isinstance(value, Mapping),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda: isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": lambda: isinstance(value, bool),
        "null": lambda: value is None,
    }[schema_type]()


def _property_path(path: str, key: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return f"{path}.{key}"
    return f"{path}[{key!r}]"
