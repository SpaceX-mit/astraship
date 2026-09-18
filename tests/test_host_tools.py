from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from astraship.kernel.host_tools import HostToolAdapter, InvalidRequestParams
from astraship.kernel.protocol import ServerRequest
from astraship.tools import ToolContext, ToolDefinition, ToolRegistry


async def _return_none(arguments: Mapping[str, Any], context: ToolContext) -> None:
    return None


def make_registry(seen: list[tuple[dict[str, Any], ToolContext]] | None = None) -> ToolRegistry:
    async def inspect(arguments: Mapping[str, Any], context: ToolContext) -> object:
        if seen is not None:
            seen.append((dict(arguments), context))
        return {"value": arguments["value"], "session": context.metadata["sessionId"]}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="inspect",
            description="Inspect trusted execution context",
            parameters={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            execute=inspect,
        )
    )
    return registry


def execute_request(params: object) -> ServerRequest:
    return ServerRequest(request_id="rpc-1", method="tool/execute", params=params)


def test_capability_is_a_defensive_snapshot(tmp_path: Path) -> None:
    registry = make_registry()
    adapter = HostToolAdapter(registry, ToolContext(tmp_path))
    capability = adapter.capability()

    capability["hostTools"]["tools"][0]["name"] = "mutated"
    registry.register(
        ToolDefinition(
            name="later",
            description="Registered after negotiation",
            parameters={"type": "object", "additionalProperties": False},
            execute=_return_none,
        )
    )

    assert adapter.capability() == {
        "hostTools": {
            "version": 1,
            "tools": [
                {
                    "name": "inspect",
                    "description": "Inspect trusted execution context",
                    "parameters": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                        "required": ["value"],
                        "additionalProperties": False,
                    },
                }
            ],
        }
    }
    assert set(adapter.handlers()) == {"tool/execute"}


@pytest.mark.asyncio
async def test_handle_executes_with_trusted_workspace_and_session_metadata(tmp_path: Path) -> None:
    seen: list[tuple[dict[str, Any], ToolContext]] = []
    adapter = HostToolAdapter(make_registry(seen), ToolContext(tmp_path, {"tenant": "a"}))

    result = await adapter.handle(
        execute_request(
            {
                "sessionId": "s-1",
                "callId": "call-1",
                "name": "inspect",
                "arguments": {"value": "hello"},
            }
        )
    )

    assert result["callId"] == "call-1"
    assert result["name"] == "inspect"
    assert result["isError"] is False
    assert result["output"] == {"value": "hello", "session": "s-1"}
    assert result["elapsedMs"] >= 0
    assert seen[0][1].workspace == tmp_path.resolve()
    assert seen[0][1].metadata == {"tenant": "a", "sessionId": "s-1"}


@pytest.mark.asyncio
async def test_handle_serializes_tool_level_failure_as_success_result(tmp_path: Path) -> None:
    adapter = HostToolAdapter(make_registry(), ToolContext(tmp_path))

    result = await adapter.handle(
        execute_request(
            {
                "sessionId": "s-1",
                "callId": "call-1",
                "name": "inspect",
                "arguments": {},
            }
        )
    )

    assert result["isError"] is True
    assert result["output"] is None
    assert result["error"]["code"] == "invalid_arguments"
    assert isinstance(result["error"]["message"], str)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        None,
        [],
        {},
        {"sessionId": "", "callId": "c", "name": "inspect", "arguments": {}},
        {"sessionId": "s", "callId": 1, "name": "inspect", "arguments": {}},
        {"sessionId": "s", "callId": "c", "name": "", "arguments": {}},
        {"sessionId": "s", "callId": "c", "name": "inspect", "arguments": []},
        {
            "sessionId": "s",
            "callId": "c",
            "name": "inspect",
            "arguments": {},
            "workspace": "/tmp/untrusted",
        },
    ],
)
async def test_handle_rejects_malformed_envelopes_before_execution(
    tmp_path: Path, params: object
) -> None:
    seen: list[tuple[dict[str, Any], ToolContext]] = []
    adapter = HostToolAdapter(make_registry(seen), ToolContext(tmp_path))

    with pytest.raises(InvalidRequestParams):
        await adapter.handle(execute_request(params))

    assert seen == []
