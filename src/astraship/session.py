"""Typed session facade over Felix session RPC methods."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from .errors import KernelProtocolError, SessionOverflowError, SessionStateError
from .kernel.client import FelixClient
from .kernel.protocol import Notification


@dataclass(frozen=True, slots=True)
class PromptReceipt:
    """Durable enqueue receipt for one user prompt."""

    message_id: str


@dataclass(frozen=True, slots=True)
class SessionEvent:
    """A durable event emitted by Felix for one session."""

    session_id: str
    type: str
    data: dict[str, Any]


class KernelSession:
    """Manage one Felix session and its filtered event stream."""

    def __init__(
        self,
        client: FelixClient,
        session_id: str,
        event_queue: asyncio.Queue[Notification],
        event_queue_size: int,
    ) -> None:
        self._client = client
        self.session_id = session_id
        self._event_queue = event_queue
        self._event_queue_size = event_queue_size
        self._events: asyncio.Queue[SessionEvent | BaseException] = asyncio.Queue(
            maxsize=event_queue_size
        )
        self._demux_task = asyncio.create_task(self._demultiplex())
        self._closed = False
        self._remote_closed = False

    @classmethod
    async def create(cls, client: FelixClient, event_queue_size: int = 128) -> KernelSession:
        """Create a remote session and start its event demultiplexer."""

        if event_queue_size <= 0:
            raise ValueError("event_queue_size must be greater than zero")
        value = await client.request("session/new", {})
        if not isinstance(value, dict) or not isinstance(value.get("sessionId"), str):
            raise KernelProtocolError("session/new result requires sessionId")
        session_id = value["sessionId"]
        if not session_id:
            raise KernelProtocolError("session/new result requires non-empty sessionId")
        # Keep the transport subscription lossless; apply the bounded policy in the facade queue.
        queue = client.subscribe_notifications()
        return cls(client, session_id, queue, event_queue_size)

    async def prompt(self, content: str) -> PromptReceipt:
        """Enqueue a user prompt and return its durable message ID."""

        self._require_open()
        if not content.strip():
            raise SessionStateError("prompt content must be non-empty")
        value = await self._client.request(
            "session/prompt", {"sessionId": self.session_id, "content": content}
        )
        if not isinstance(value, dict) or not isinstance(value.get("messageId"), str):
            raise KernelProtocolError("session/prompt result requires messageId")
        message_id = value["messageId"]
        if not message_id:
            raise KernelProtocolError("session/prompt result requires non-empty messageId")
        return PromptReceipt(message_id)

    async def events(self) -> AsyncIterator[SessionEvent]:
        """Yield all durable events for this session until the caller stops."""

        self._require_open()
        while True:
            item = await self._events.get()
            if isinstance(item, BaseException):
                raise item
            yield item

    async def close(self) -> None:
        """Close the remote session and release its notification subscription."""

        if self._closed:
            return
        self._closed = True
        self._client.unsubscribe_notifications(self._event_queue)
        self._demux_task.cancel()
        try:
            await self._client.request("session/close", {"sessionId": self.session_id})
        finally:
            self._remote_closed = True
            with suppress(asyncio.CancelledError):
                await self._demux_task

    async def _demultiplex(self) -> None:
        try:
            while True:
                notification = await self._event_queue.get()
                if notification.method != "session.event":
                    continue
                event = _parse_event(notification.params)
                if event.session_id != self.session_id:
                    continue
                try:
                    self._events.put_nowait(event)
                except asyncio.QueueFull:
                    _clear_queue(self._events)
                    self._events.put_nowait(
                        SessionOverflowError(
                            f"session event queue overflow (size={self._event_queue_size})"
                        )
                    )
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _clear_queue(self._events)
            self._events.put_nowait(exc)

    def _require_open(self) -> None:
        if self._closed:
            raise SessionStateError("session is closed")


def _parse_event(params: Any) -> SessionEvent:
    if not isinstance(params, dict):
        raise KernelProtocolError("session.event params must be an object")
    session_id = params.get("sessionId")
    payload = params.get("event")
    if not isinstance(session_id, str) or not session_id:
        raise KernelProtocolError("session.event requires sessionId")
    if not isinstance(payload, dict):
        raise KernelProtocolError("session.event requires event object")
    event_type = payload.get("type")
    data = payload.get("data")
    if not isinstance(event_type, str) or not event_type:
        raise KernelProtocolError("session.event requires event type")
    if not isinstance(data, dict):
        raise KernelProtocolError("session.event requires data object")
    return SessionEvent(session_id=session_id, type=event_type, data=data)


def _clear_queue(queue: asyncio.Queue[SessionEvent | BaseException]) -> None:
    """Discard queued events while preserving the queue's unfinished count."""

    while True:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            return
