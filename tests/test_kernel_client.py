import asyncio
import sys
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

import pytest

from astraship.config import KernelConfig
from astraship.errors import (
    KernelProcessError,
    KernelProtocolError,
    KernelRemoteError,
    KernelStateError,
    KernelTimeoutError,
    KernelVersionMismatchError,
)
from astraship.kernel.client import FelixClient
from astraship.kernel.host_tools import HostToolAdapter, InvalidRequestParams
from astraship.kernel.protocol import Notification, ServerRequest
from astraship.tools import ToolContext, ToolDefinition, ToolRegistry

FIXTURE = Path(__file__).parent / "fixtures" / "fake_felix.py"


def fixture_config(mode: str = "normal", *, timeout: float = 1.0) -> KernelConfig:
    return KernelConfig(
        command=(sys.executable, str(FIXTURE), "--mode", mode),
        request_timeout=timeout,
        shutdown_timeout=0.2,
    )


@pytest.mark.asyncio
async def test_start_negotiates_protocol_and_server_capabilities() -> None:
    async with FelixClient(fixture_config()) as client:
        result = client.initialize_result

        assert result.protocol_version == 1
        assert result.server_info.name == "fake-felix"
        assert result.server_info.version == "9.8.7"
        assert result.capabilities == {"fixture": True}


@pytest.mark.asyncio
async def test_request_returns_result_and_receives_notification() -> None:
    async with FelixClient(fixture_config()) as client:
        assert await client.request("echo", {"value": 7}) == {"value": 7}
        await client.request("notify")
        notification = await client.next_notification()

        assert notification.method == "kernel.tick"
        assert notification.params == {"count": 1}


@pytest.mark.asyncio
async def test_concurrent_requests_are_correlated_when_responses_are_reordered() -> None:
    async with FelixClient(fixture_config()) as client:
        first, second = await asyncio.gather(
            client.request("out-of-order", {"value": "first"}),
            client.request("echo", {"value": "second"}),
        )

    assert first == "first"
    assert second == "second"


@pytest.mark.asyncio
async def test_remote_error_preserves_wire_details() -> None:
    async with FelixClient(fixture_config()) as client:
        with pytest.raises(KernelRemoteError) as caught:
            await client.request("fail")

    assert caught.value.code == 42
    assert caught.value.data == {"detail": "x"}


@pytest.mark.asyncio
async def test_server_request_receives_method_not_found_response() -> None:
    async with FelixClient(fixture_config()) as client:
        assert await client.request("server-request") == -32601


@pytest.mark.asyncio
async def test_initialization_negotiates_defensive_capability_snapshot() -> None:
    capabilities = {"hostTools": {"version": 1, "tools": []}}
    client = FelixClient(fixture_config(), capabilities=capabilities)
    capabilities["hostTools"]["version"] = 99

    async with client:
        assert client.initialize_result.capabilities["hostTools"] == {"version": 1}


@pytest.mark.parametrize(
    "capabilities",
    [
        {"hostTools": {"version": float("nan")}},
        {"hostTools": {"tools": [object()]}},
    ],
)
def test_client_rejects_non_json_capabilities_before_start(capabilities: object) -> None:
    with pytest.raises(KernelProtocolError, match="capabilities.*JSON-compatible"):
        FelixClient(fixture_config(), capabilities=capabilities)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_server_request_handler_returns_json_rpc_result() -> None:
    async def handle(request: ServerRequest) -> object:
        return {"accepted": request.params}

    params = {"sessionId": "s", "callId": "c", "name": "inspect", "arguments": {}}
    async with FelixClient(fixture_config(), request_handlers={"tool/execute": handle}) as client:
        response = await client.request("server-execute", params)

    assert response == {
        "jsonrpc": "2.0",
        "id": "tool-1",
        "result": {"accepted": params},
    }


@pytest.mark.asyncio
async def test_host_tool_adapter_executes_over_reverse_stdio(
    tmp_path: Path,
) -> None:
    async def execute(arguments: Mapping[str, object], context: ToolContext) -> object:
        assert context.workspace == tmp_path.resolve()
        return {"sessionId": context.metadata["sessionId"]}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="inspect",
            description="Inspect the host context",
            parameters={"type": "object", "additionalProperties": False},
            execute=execute,
        )
    )
    adapter = HostToolAdapter(registry, ToolContext(tmp_path))
    params = {
        "sessionId": "s-1",
        "callId": "call-1",
        "name": "inspect",
        "arguments": {},
    }

    async with FelixClient(
        fixture_config(),
        capabilities=adapter.capability(),
        request_handlers=adapter.handlers(),
    ) as client:
        response = await client.request("server-execute", params)

    assert client.initialize_result.capabilities["hostTools"] == {"version": 1}
    assert response["result"]["callId"] == "call-1"
    assert response["result"]["isError"] is False
    assert response["result"]["output"] == {"sessionId": "s-1"}


@pytest.mark.asyncio
async def test_host_tool_adapter_rejects_malformed_reverse_request(
    tmp_path: Path,
) -> None:
    adapter = HostToolAdapter(ToolRegistry(), ToolContext(tmp_path))

    async with FelixClient(
        fixture_config(),
        capabilities=adapter.capability(),
        request_handlers=adapter.handlers(),
    ) as client:
        response = await client.request("server-execute", {"sessionId": "missing-fields"})
        follow_up = await client.request("echo", {"still": "alive"})

    assert response["error"]["code"] == -32602
    assert follow_up == {"still": "alive"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "code"),
    [(InvalidRequestParams("bad envelope"), -32602), (RuntimeError("boom"), -32603)],
)
async def test_server_request_handler_maps_stable_errors(exception: Exception, code: int) -> None:
    async def fail(request: ServerRequest) -> object:
        raise exception

    async with FelixClient(fixture_config(), request_handlers={"tool/execute": fail}) as client:
        response = await client.request("server-execute", {})

    assert response["error"]["code"] == code


@pytest.mark.asyncio
async def test_invalid_handler_result_returns_internal_error_without_breaking_client() -> None:
    async def invalid_result(request: ServerRequest) -> object:
        return object()

    async with FelixClient(
        fixture_config(), request_handlers={"tool/execute": invalid_result}
    ) as client:
        response = await client.request("server-execute", {})
        follow_up = await client.request("echo", {"still": "alive"})

    assert response["error"]["code"] == -32603
    assert follow_up == {"still": "alive"}


@pytest.mark.asyncio
async def test_server_requests_complete_concurrently_and_out_of_order() -> None:
    slow_started = asyncio.Event()
    release_slow = asyncio.Event()

    async def slow(request: ServerRequest) -> object:
        slow_started.set()
        await release_slow.wait()
        return "slow"

    async def fast(request: ServerRequest) -> object:
        await slow_started.wait()
        release_slow.set()
        return "fast"

    handlers: dict[str, Callable[[ServerRequest], Awaitable[object]]] = {
        "fixture/slow": slow,
        "fixture/fast": fast,
    }
    async with FelixClient(fixture_config(), request_handlers=handlers) as client:
        responses = await client.request("server-concurrent")

    assert [response["id"] for response in responses] == ["fast", "slow"]


@pytest.mark.asyncio
async def test_cancel_notification_cancels_matching_handler() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def hang(request: ServerRequest) -> object:
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return None

    async with FelixClient(fixture_config(), request_handlers={"fixture/hang": hang}) as client:
        response = await client.request("server-cancel")

    assert response["error"]["code"] == -32800
    assert not started.is_set() or cancelled.is_set()


@pytest.mark.asyncio
async def test_cancelled_handler_cannot_suppress_cancel_response() -> None:
    cancellation_seen = asyncio.Event()

    async def suppress_cancel(request: ServerRequest) -> object:
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancellation_seen.set()
            return "ignored cancellation"
        return None

    async with FelixClient(
        fixture_config(), request_handlers={"fixture/hang": suppress_cancel}
    ) as client:
        response = await client.request("server-cancel-running")

    assert cancellation_seen.is_set()
    assert response["error"]["code"] == -32800


@pytest.mark.asyncio
async def test_cancellation_while_result_waits_for_write_returns_cancel_error() -> None:
    class ObservedFelixClient(FelixClient):
        def __init__(self) -> None:
            super().__init__(
                fixture_config(timeout=0.3),
                request_handlers={"fixture/hang": immediate_result},
            )
            self.cancel_received = asyncio.Event()

        def _cancel_server_request(self, message: Notification) -> None:
            super()._cancel_server_request(message)
            self.cancel_received.set()

    client: ObservedFelixClient

    async def immediate_result(request: ServerRequest) -> object:
        await client._write_lock.acquire()
        return "completed"

    client = ObservedFelixClient()
    await client.start()
    request_task = asyncio.create_task(client.request("server-cancel-running"))
    try:
        await asyncio.wait_for(client.cancel_received.wait(), 1)
        client._write_lock.release()
        response = await request_task
    finally:
        if client._write_lock.locked():
            client._write_lock.release()
        await client.close()

    assert response["error"]["code"] == -32800


@pytest.mark.asyncio
async def test_duplicate_server_request_id_keeps_original_tracked_until_close() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def hang(request: ServerRequest) -> object:
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return None

    async with FelixClient(fixture_config(), request_handlers={"fixture/hang": hang}) as client:
        response = await client.request("server-duplicate")
        assert started.is_set()
        assert response["error"]["code"] == -32600

    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_close_cancels_in_flight_server_handlers() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def hang(request: ServerRequest) -> object:
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return None

    client = FelixClient(fixture_config(), request_handlers={"fixture/hang": hang})
    await client.start()
    request_task = asyncio.create_task(client.request("server-hang"))
    await asyncio.wait_for(started.wait(), 1)

    await client.close()

    assert cancelled.is_set()
    with pytest.raises(KernelProcessError):
        await request_task


@pytest.mark.asyncio
async def test_request_timeout_does_not_reuse_late_response() -> None:
    async with FelixClient(fixture_config(timeout=0.05)) as client:
        with pytest.raises(KernelTimeoutError, match="delayed"):
            await client.request("delayed")
        await asyncio.sleep(0.25)
        assert await client.request("echo", {"fresh": True}) == {"fresh": True}


@pytest.mark.asyncio
async def test_wrong_protocol_version_closes_process() -> None:
    client = FelixClient(fixture_config("wrong-version"))

    with pytest.raises(KernelVersionMismatchError, match="expected 1.*received 2"):
        await client.start()

    assert client.closed


@pytest.mark.asyncio
async def test_malformed_kernel_output_fails_initialization() -> None:
    client = FelixClient(fixture_config("malformed"))

    with pytest.raises(KernelProtocolError, match="invalid JSON"):
        await client.start()


@pytest.mark.asyncio
async def test_unexpected_exit_rejects_request_with_stderr_and_exit_code() -> None:
    async with FelixClient(fixture_config()) as client:
        with pytest.raises(KernelProcessError, match="17.*requested fixture exit"):
            await client.request("exit")


@pytest.mark.asyncio
async def test_state_rules_and_close_are_deterministic() -> None:
    client = FelixClient(fixture_config())
    with pytest.raises(KernelStateError, match="not initialized"):
        await client.request("echo")

    await client.start()
    with pytest.raises(KernelStateError, match="already started"):
        await client.start()

    await client.close()
    await client.close()
    assert client.closed
    with pytest.raises(KernelStateError, match="closed"):
        await client.request("echo")
