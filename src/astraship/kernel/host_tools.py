"""Translate Felix host-tool requests into Astraship registry calls."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from typing import Any

from ..errors import KernelProtocolError
from ..tools import ToolCall, ToolContext, ToolRegistry
from .protocol import ServerRequest

type RequestHandler = Callable[[ServerRequest], Awaitable[Any]]

_EXECUTE_FIELDS = frozenset({"sessionId", "callId", "name", "arguments"})


class InvalidRequestParams(KernelProtocolError):
    """A server request has an invalid application-level envelope."""


class HostToolAdapter:
    """Expose one immutable registry snapshot through the Felix wire contract."""

    def __init__(self, registry: ToolRegistry, context: ToolContext) -> None:
        self._registry = registry
        self._context = context
        self._capability: dict[str, Any] = {
            "hostTools": {"version": 1, "tools": registry.schemas()}
        }

    def capability(self) -> dict[str, Any]:
        """Return a defensive copy of the initialization capability."""

        return deepcopy(self._capability)

    def handlers(self) -> dict[str, RequestHandler]:
        """Return handlers suitable for direct FelixClient registration."""

        return {"tool/execute": self.handle}

    async def handle(self, request: ServerRequest) -> dict[str, Any]:
        """Validate and execute one Felix host-tool request."""

        params = request.params
        if not isinstance(params, Mapping):
            raise InvalidRequestParams("tool/execute params must be an object")
        if set(params) != _EXECUTE_FIELDS:
            raise InvalidRequestParams(
                "tool/execute params require only sessionId, callId, name, and arguments"
            )
        session_id = _non_empty_string(params.get("sessionId"), "sessionId")
        call_id = _non_empty_string(params.get("callId"), "callId")
        name = _non_empty_string(params.get("name"), "name")
        arguments = params.get("arguments")
        if not isinstance(arguments, Mapping):
            raise InvalidRequestParams("tool/execute arguments must be an object")

        metadata = dict(self._context.metadata)
        metadata["sessionId"] = session_id
        context = ToolContext(workspace=self._context.workspace, metadata=metadata)
        result = await self._registry.execute(
            ToolCall(call_id=call_id, name=name, arguments=arguments), context
        )
        wire: dict[str, Any] = {
            "callId": result.call_id,
            "name": result.name,
            "isError": result.is_error,
            "output": result.output,
            "elapsedMs": result.elapsed_ms,
        }
        if result.error is not None:
            wire["error"] = {"code": result.error.code, "message": result.error.message}
        return wire


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidRequestParams(f"tool/execute {field} must be a non-empty string")
    return value
