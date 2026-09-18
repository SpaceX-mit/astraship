import asyncio
import sys
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
