"""Immutable public values for Astraship tool execution."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from astraship.errors import ToolCallError, ToolRegistrationError

from .schema import validate_schema

type JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
type ToolExecutor = Callable[[Mapping[str, Any], "ToolContext"], Awaitable[object]]

_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Platform context explicitly granted to a tool invocation."""

    workspace: Path
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace", self.workspace.resolve())
        if not all(
            isinstance(key, str) and isinstance(value, str) for key, value in self.metadata.items()
        ):
            raise ToolCallError("tool context metadata must contain string keys and values")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """One model-visible capability and its async implementation."""

    name: str
    description: str
    parameters: Mapping[str, Any]
    execute: ToolExecutor
    concurrency_safe: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or _TOOL_NAME.fullmatch(self.name) is None:
            raise ToolRegistrationError("tool name must match ^[a-z][a-z0-9_]{0,63}$")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ToolRegistrationError("tool description must be non-empty")
        if not isinstance(self.parameters, Mapping):
            raise ToolRegistrationError("tool parameters schema must be an object")
        validate_schema(self.parameters, root_object=True)
        if not callable(self.execute):
            raise ToolRegistrationError("tool execute must be callable")
        if not isinstance(self.concurrency_safe, bool):
            raise ToolRegistrationError("tool concurrency_safe must be boolean")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A single invocation requested by an agent or application."""

    call_id: str
    name: str
    arguments: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str) or not self.call_id.strip():
            raise ToolCallError("tool call ID must be non-empty")
        if not isinstance(self.name, str) or not self.name:
            raise ToolCallError("tool call name must be non-empty")
        if not isinstance(self.arguments, Mapping):
            raise ToolCallError("tool call arguments must be an object")
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True, slots=True)
class ToolError:
    """Stable machine-readable failure returned by the tool runtime."""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Final authoritative outcome of one tool invocation."""

    call_id: str
    name: str
    output: JsonValue = None
    error: ToolError | None = None
    is_error: bool = False
    elapsed_ms: float = 0.0
