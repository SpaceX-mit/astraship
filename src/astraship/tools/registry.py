"""Registration and guarded execution for Astraship tools."""

from __future__ import annotations

import asyncio
import inspect
import json
import math
import time
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any, cast

from astraship.errors import ToolRegistrationError

from .schema import validate_arguments
from .types import JsonValue, ToolCall, ToolContext, ToolDefinition, ToolError, ToolResult

type ToolObserver = Callable[[ToolResult], Awaitable[None] | None]


class ToolRegistry:
    """Own model-visible tool definitions and normalize invocation outcomes."""

    def __init__(
        self,
        *,
        default_timeout: float = 30.0,
        max_concurrency: int = 8,
        observer: ToolObserver | None = None,
    ) -> None:
        if default_timeout <= 0:
            raise ValueError("default_timeout must be greater than zero")
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be greater than zero")
        self.default_timeout = default_timeout
        self.max_concurrency = max_concurrency
        self._observer = observer
        self._definitions: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        """Register one unique tool definition."""

        if definition.name in self._definitions:
            raise ToolRegistrationError(f"tool {definition.name!r} is already registered")
        self._definitions[definition.name] = definition

    def schemas(self) -> list[dict[str, Any]]:
        """Return deterministic model-facing tool schemas."""

        return [
            {
                "name": definition.name,
                "description": definition.description,
                "parameters": deepcopy(dict(definition.parameters)),
            }
            for definition in sorted(self._definitions.values(), key=lambda item: item.name)
        ]

    async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        """Execute one call and return its final normalized result."""

        started = time.monotonic()
        definition = self._definitions.get(call.name)
        if definition is None:
            result = self._error(
                call,
                "tool_not_found",
                f"tool {call.name!r} is not registered",
                started,
            )
            return await self._observe(result)

        validation_error = validate_arguments(definition.parameters, call.arguments)
        if validation_error is not None:
            result = self._error(call, "invalid_arguments", validation_error, started)
            return await self._observe(result)

        try:
            async with asyncio.timeout(self.default_timeout):
                output = await definition.execute(call.arguments, context)
        except TimeoutError:
            result = self._error(
                call,
                "timeout",
                f"tool exceeded {self.default_timeout:g} second timeout",
                started,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            result = self._error(call, "execution_error", str(exc) or type(exc).__name__, started)
        else:
            try:
                normalized = _normalize_json(output)
            except (TypeError, ValueError):
                result = self._error(
                    call, "invalid_result", "tool returned a non-JSON-compatible result", started
                )
            else:
                result = ToolResult(
                    call_id=call.call_id,
                    name=call.name,
                    output=normalized,
                    elapsed_ms=_elapsed_ms(started),
                )
        return await self._observe(result)

    async def _observe(self, result: ToolResult) -> ToolResult:
        if self._observer is None:
            return result
        try:
            observed = self._observer(result)
            if inspect.isawaitable(observed):
                await observed
        except Exception:
            pass
        return result

    @staticmethod
    def _error(call: ToolCall, code: str, message: str, started: float) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            error=ToolError(code=code, message=message),
            is_error=True,
            elapsed_ms=_elapsed_ms(started),
        )


def _elapsed_ms(started: float) -> float:
    return max(0.0, (time.monotonic() - started) * 1000)


def _normalize_json(value: object) -> JsonValue:
    _validate_json_value(value, set())
    encoded = json.dumps(value, allow_nan=False, ensure_ascii=False)
    return cast(JsonValue, json.loads(encoded))


def _validate_json_value(value: object, ancestors: set[int]) -> None:
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return
    if isinstance(value, (list, dict)):
        identity = id(value)
        if identity in ancestors:
            raise ValueError("cyclic values are not JSON-compatible")
        ancestors.add(identity)
        try:
            if isinstance(value, list):
                for item in value:
                    _validate_json_value(item, ancestors)
            else:
                for key, item in value.items():
                    if not isinstance(key, str):
                        raise TypeError("JSON object keys must be strings")
                    _validate_json_value(item, ancestors)
        finally:
            ancestors.remove(identity)
        return
    raise TypeError(f"{type(value).__name__} is not JSON-compatible")
