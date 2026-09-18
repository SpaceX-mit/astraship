import asyncio
import sys
from pathlib import Path

import pytest

from astraship.config import KernelConfig
from astraship.errors import KernelProtocolError, SessionOverflowError, SessionStateError
from astraship.kernel.client import FelixClient
from astraship.session import KernelSession, PromptReceipt, SessionEvent

FIXTURE = Path(__file__).parent / "fixtures" / "fake_felix.py"


def config(*, mode: str = "session", timeout: float = 1.0) -> KernelConfig:
    return KernelConfig(
        command=(sys.executable, str(FIXTURE), "--mode", mode),
        request_timeout=timeout,
        shutdown_timeout=0.2,
    )


async def collect_turn(session: KernelSession) -> list[SessionEvent]:
    events = []
    async for event in session.events():
        events.append(event)
        if event.type == "turn/end":
            return events
    raise AssertionError("session event stream ended unexpectedly")


@pytest.mark.asyncio
async def test_create_prompt_and_consume_assistant_events() -> None:
    async with FelixClient(config()) as client:
        session = await KernelSession.create(client)
        receipt = await session.prompt("hello")
        events = await collect_turn(session)

        assert isinstance(receipt, PromptReceipt)
        assert receipt.message_id == "m-1"
        assert [event.type for event in events] == [
            "user/message",
            "future/event",
            "assistant/message",
            "turn/end",
        ]
        assert events[2].data["content"] == "mock: hello"
        assert all(event.session_id == session.session_id for event in events)

        await session.close()


@pytest.mark.asyncio
async def test_events_filter_other_sessions_and_preserve_unknown_types() -> None:
    async with FelixClient(config()) as client:
        first = await KernelSession.create(client)
        second = await KernelSession.create(client)
        await first.prompt("one")
        await second.prompt("two")

        first_events = await collect_turn(first)
        second_events = await collect_turn(second)

        assert all(event.session_id == first.session_id for event in first_events)
        assert all(event.session_id == second.session_id for event in second_events)
        assert any(event.type == "future/event" for event in first_events)
        await first.close()
        await second.close()


@pytest.mark.asyncio
async def test_prompt_rejects_empty_content_without_rpc() -> None:
    async with FelixClient(config()) as client:
        session = await KernelSession.create(client)
        with pytest.raises(SessionStateError, match="non-empty"):
            await session.prompt("  \n")
        await session.close()


@pytest.mark.asyncio
async def test_malformed_session_result_is_protocol_error() -> None:
    async with FelixClient(config(mode="bad-session")) as client:
        with pytest.raises(KernelProtocolError, match="sessionId"):
            await KernelSession.create(client)


@pytest.mark.asyncio
async def test_close_is_idempotent_and_prompt_after_close_fails() -> None:
    async with FelixClient(config()) as client:
        session = await KernelSession.create(client)
        await session.close()
        await session.close()
        with pytest.raises(SessionStateError, match="closed"):
            await session.prompt("later")


@pytest.mark.asyncio
async def test_small_event_queue_fails_instead_of_dropping_events() -> None:
    async with FelixClient(config()) as client:
        session = await KernelSession.create(client, event_queue_size=1)
        await session.prompt("hello")
        await asyncio.sleep(0.05)
        with pytest.raises(SessionOverflowError, match="overflow"):
            await session.events().__anext__()
        await session.close()
