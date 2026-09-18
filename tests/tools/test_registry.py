import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from astraship.errors import ToolCallError, ToolRegistrationError
from astraship.tools import (
    ToolCall,
    ToolContext,
    ToolDefinition,
    ToolRegistry,
    ToolResult,
)


def context(tmp_path: Path) -> ToolContext:
    return ToolContext(tmp_path)


def definition(
    name: str,
    execute: Any,
    *,
    parameters: Mapping[str, Any] | None = None,
    concurrency_safe: bool = False,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"Execute {name}",
        parameters=parameters
        or {
            "type": "object",
            "properties": {"value": {"type": "integer"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        execute=execute,
        concurrency_safe=concurrency_safe,
    )


@pytest.mark.asyncio
async def test_registration_and_schemas_are_deterministic(tmp_path: Path) -> None:
    async def echo(arguments: Mapping[str, Any], tool_context: ToolContext) -> object:
        return dict(arguments)

    registry = ToolRegistry()
    registry.register(definition("zeta", echo))
    registry.register(definition("alpha", echo))

    assert [schema["name"] for schema in registry.schemas()] == ["alpha", "zeta"]
    assert registry.schemas()[0] == {
        "name": "alpha",
        "description": "Execute alpha",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "integer"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    }
    with pytest.raises(ToolRegistrationError, match="already registered"):
        registry.register(definition("alpha", echo))


@pytest.mark.asyncio
async def test_unknown_and_invalid_calls_do_not_dispatch(tmp_path: Path) -> None:
    dispatched = False

    async def body(arguments: Mapping[str, Any], tool_context: ToolContext) -> object:
        nonlocal dispatched
        dispatched = True
        return {}

    registry = ToolRegistry()
    registry.register(definition("known", body))

    missing = await registry.execute(ToolCall("c1", "missing", {}), context(tmp_path))
    invalid = await registry.execute(ToolCall("c2", "known", {"value": True}), context(tmp_path))

    assert missing.error is not None and missing.error.code == "tool_not_found"
    assert invalid.error is not None and invalid.error.code == "invalid_arguments"
    assert "$.value" in invalid.error.message
    assert not dispatched


@pytest.mark.asyncio
async def test_success_returns_json_output_and_elapsed_time(tmp_path: Path) -> None:
    async def double(arguments: Mapping[str, Any], tool_context: ToolContext) -> object:
        return {"result": arguments["value"] * 2}

    registry = ToolRegistry()
    registry.register(definition("double", double))
    result = await registry.execute(ToolCall("c1", "double", {"value": 4}), context(tmp_path))

    assert result == ToolResult(
        call_id="c1",
        name="double",
        output={"result": 8},
        elapsed_ms=result.elapsed_ms,
    )
    assert result.elapsed_ms >= 0


@pytest.mark.asyncio
async def test_timeout_and_exception_are_normalized(tmp_path: Path) -> None:
    async def slow(arguments: Mapping[str, Any], tool_context: ToolContext) -> object:
        await asyncio.sleep(1)
        return {}

    async def broken(arguments: Mapping[str, Any], tool_context: ToolContext) -> object:
        raise RuntimeError("secret traceback is not returned")

    timeout_registry = ToolRegistry(default_timeout=0.01)
    timeout_registry.register(definition("slow", slow))
    broken_registry = ToolRegistry()
    broken_registry.register(definition("broken", broken))

    timed_out = await timeout_registry.execute(
        ToolCall("c1", "slow", {"value": 1}), context(tmp_path)
    )
    failed = await broken_registry.execute(
        ToolCall("c2", "broken", {"value": 1}), context(tmp_path)
    )

    assert timed_out.error is not None and timed_out.error.code == "timeout"
    assert failed.error is not None and failed.error.code == "execution_error"
    assert failed.error.message == "secret traceback is not returned"


@pytest.mark.asyncio
async def test_caller_cancellation_propagates(tmp_path: Path) -> None:
    started = asyncio.Event()

    async def wait_forever(arguments: Mapping[str, Any], tool_context: ToolContext) -> object:
        started.set()
        await asyncio.Event().wait()
        return {}

    registry = ToolRegistry()
    registry.register(definition("waiter", wait_forever))
    task = asyncio.create_task(
        registry.execute(ToolCall("c1", "waiter", {"value": 1}), context(tmp_path))
    )
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
@pytest.mark.parametrize("output", [{"bad": {1, 2}}, float("inf"), {1: "bad key"}])
async def test_invalid_tool_output_becomes_error(tmp_path: Path, output: object) -> None:
    async def invalid(arguments: Mapping[str, Any], tool_context: ToolContext) -> object:
        return output

    registry = ToolRegistry()
    registry.register(definition("invalid", invalid))
    result = await registry.execute(ToolCall("c1", "invalid", {"value": 1}), context(tmp_path))

    assert result.error is not None and result.error.code == "invalid_result"


@pytest.mark.asyncio
async def test_observer_sees_final_result_once_and_cannot_replace_it(tmp_path: Path) -> None:
    observed: list[ToolResult] = []

    async def echo(arguments: Mapping[str, Any], tool_context: ToolContext) -> object:
        return {"value": arguments["value"]}

    async def observer(result: ToolResult) -> None:
        observed.append(result)
        raise RuntimeError("observer is isolated")

    registry = ToolRegistry(observer=observer)
    registry.register(definition("echo", echo))
    result = await registry.execute(ToolCall("c1", "echo", {"value": 3}), context(tmp_path))

    assert result.output == {"value": 3}
    assert observed == [result]


@pytest.mark.parametrize(
    "kwargs",
    [{"default_timeout": 0}, {"max_concurrency": 0}],
)
def test_registry_rejects_non_positive_limits(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ToolRegistry(**kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_execute_many_returns_submission_order_despite_completion_order(
    tmp_path: Path,
) -> None:
    async def delayed(arguments: Mapping[str, Any], tool_context: ToolContext) -> object:
        await asyncio.sleep(float(arguments["delay"]))
        return {"value": arguments["value"]}

    parameters = {
        "type": "object",
        "properties": {
            "value": {"type": "integer"},
            "delay": {"type": "number", "minimum": 0},
        },
        "required": ["value", "delay"],
        "additionalProperties": False,
    }
    registry = ToolRegistry(max_concurrency=2)
    registry.register(definition("delayed", delayed, parameters=parameters, concurrency_safe=True))

    results = await registry.execute_many(
        [
            ToolCall("slow", "delayed", {"value": 1, "delay": 0.03}),
            ToolCall("fast", "delayed", {"value": 2, "delay": 0}),
        ],
        context(tmp_path),
    )

    assert [result.call_id for result in results] == ["slow", "fast"]
    assert [result.output for result in results] == [{"value": 1}, {"value": 2}]


@pytest.mark.asyncio
async def test_safe_batch_obeys_max_concurrency(tmp_path: Path) -> None:
    active = 0
    peak = 0

    async def measured(arguments: Mapping[str, Any], tool_context: ToolContext) -> object:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {}

    registry = ToolRegistry(max_concurrency=2)
    registry.register(definition("safe", measured, concurrency_safe=True))
    calls = [ToolCall(f"c{index}", "safe", {"value": index}) for index in range(5)]

    await registry.execute_many(calls, context(tmp_path))

    assert peak == 2


@pytest.mark.asyncio
async def test_duplicate_batch_ids_fail_before_dispatch(tmp_path: Path) -> None:
    dispatched = False

    async def body(arguments: Mapping[str, Any], tool_context: ToolContext) -> object:
        nonlocal dispatched
        dispatched = True
        return {}

    registry = ToolRegistry()
    registry.register(definition("body", body, concurrency_safe=True))

    with pytest.raises(ToolCallError, match="duplicate.*c1"):
        await registry.execute_many(
            [
                ToolCall("c1", "body", {"value": 1}),
                ToolCall("c1", "body", {"value": 2}),
            ],
            context(tmp_path),
        )
    assert not dispatched


@pytest.mark.asyncio
async def test_unsafe_calls_are_exclusive_in_batch_order(tmp_path: Path) -> None:
    active: set[str] = set()
    overlaps: list[tuple[str, tuple[str, ...]]] = []
    starts: list[str] = []

    async def tracked(arguments: Mapping[str, Any], tool_context: ToolContext) -> object:
        label = str(arguments["label"])
        starts.append(label)
        if active:
            overlaps.append((label, tuple(sorted(active))))
        active.add(label)
        await asyncio.sleep(0.01)
        active.remove(label)
        return {"label": label}

    parameters = {
        "type": "object",
        "properties": {"label": {"type": "string"}},
        "required": ["label"],
        "additionalProperties": False,
    }
    registry = ToolRegistry(max_concurrency=3)
    registry.register(definition("safe", tracked, parameters=parameters, concurrency_safe=True))
    registry.register(definition("unsafe", tracked, parameters=parameters, concurrency_safe=False))

    await registry.execute_many(
        [
            ToolCall("c1", "safe", {"label": "safe-before"}),
            ToolCall("c2", "unsafe", {"label": "unsafe"}),
            ToolCall("c3", "safe", {"label": "safe-after"}),
        ],
        context(tmp_path),
    )

    assert overlaps == []
    assert starts == ["safe-before", "unsafe", "safe-after"]
