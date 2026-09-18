"""Async stdio client for the Felix bootstrap protocol."""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from .. import __version__
from ..config import KernelConfig, resolve_kernel_command
from ..errors import (
    KernelProcessError,
    KernelProtocolError,
    KernelRemoteError,
    KernelStateError,
    KernelTimeoutError,
    KernelVersionMismatchError,
)
from .protocol import (
    PROTOCOL_VERSION,
    InitializeResult,
    Notification,
    Response,
    ServerInfo,
    ServerRequest,
    decode_message,
    encode_error_response,
    encode_request,
)


@dataclass(slots=True)
class _Pending:
    future: asyncio.Future[Response]
    method: str


class FelixClient:
    """Own a Felix child process and its versioned JSON-RPC connection."""

    def __init__(self, config: KernelConfig) -> None:
        self._config = config
        self._process: asyncio.subprocess.Process | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._process_task: asyncio.Task[None] | None = None
        self._pending: dict[int | str, _Pending] = {}
        self._notifications: asyncio.Queue[Notification] = asyncio.Queue()
        self._notification_subscribers: set[asyncio.Queue[Notification]] = set()
        self._stderr_tail: deque[str] = deque(maxlen=config.stderr_tail_lines)
        self._next_id = 1
        self._started = False
        self._closed = False
        self._failure: KernelProcessError | KernelProtocolError | None = None
        self._initialize_result: InitializeResult | None = None

    @property
    def initialize_result(self) -> InitializeResult:
        """Return the immutable result of a successful initialization."""

        if self._initialize_result is None:
            raise KernelStateError("kernel is not initialized")
        return self._initialize_result

    @property
    def closed(self) -> bool:
        """Whether the child process has been closed."""

        return self._closed

    async def __aenter__(self) -> FelixClient:
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.close()

    async def start(self) -> InitializeResult:
        """Launch Felix and complete protocol initialization."""

        if self._closed:
            raise KernelStateError("kernel client is closed")
        if self._started:
            raise KernelStateError("kernel client is already started")
        command = resolve_kernel_command(self._config)
        try:
            self._process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            assert self._process.stdout is not None
            assert self._process.stderr is not None
            self._stdout_task = asyncio.create_task(self._read_stdout(self._process.stdout))
            self._stderr_task = asyncio.create_task(self._read_stderr(self._process.stderr))
            self._process_task = asyncio.create_task(self._watch_process(self._process))
            self._started = True
            response = await self._request(
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "clientInfo": {"name": "astraship", "version": __version__},
                    "capabilities": {},
                },
            )
            self._initialize_result = _parse_initialize_result(response)
            if self._initialize_result.protocol_version != PROTOCOL_VERSION:
                raise KernelVersionMismatchError(
                    f"unsupported Felix protocol version: expected {PROTOCOL_VERSION}, "
                    f"received {self._initialize_result.protocol_version}"
                )
            return self._initialize_result
        except OSError as exc:
            await self.close()
            raise KernelProcessError(f"failed to start Felix: {exc}") from exc
        except Exception:
            await self.close()
            raise

    async def request(self, method: str, params: Any = None) -> Any:
        """Send a request after initialization and return its JSON result."""

        self._require_initialized()
        return await self._request(method, params)

    async def next_notification(self) -> Notification:
        """Wait for the next server notification."""

        self._require_initialized()
        return await self._notifications.get()

    def subscribe_notifications(self, maxsize: int = 0) -> asyncio.Queue[Notification]:
        """Create a broadcast notification queue owned by the caller."""

        if self._closed:
            raise KernelStateError("kernel client is closed")
        if maxsize < 0:
            raise ValueError("maxsize cannot be negative")
        queue: asyncio.Queue[Notification] = asyncio.Queue(maxsize=maxsize)
        self._notification_subscribers.add(queue)
        return queue

    def unsubscribe_notifications(self, queue: asyncio.Queue[Notification]) -> None:
        """Remove a previously created notification subscription."""

        self._notification_subscribers.discard(queue)

    async def close(self) -> None:
        """Close, terminate, and reap Felix; safe to call repeatedly."""

        if self._closed:
            return
        self._closed = True
        process = self._process
        if process is not None and process.stdin is not None:
            process.stdin.close()
        if process is not None:
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), self._config.shutdown_timeout)
            if process.returncode is None:
                process.terminate()
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(process.wait(), self._config.shutdown_timeout)
            if process.returncode is None:
                process.kill()
                await process.wait()
        failure = self._failure or KernelProcessError("Felix kernel client closed")
        self._fail_pending(failure)
        for task in (self._stdout_task, self._stderr_task, self._process_task):
            if task is not None and not task.done():
                task.cancel()
        for task in (self._stdout_task, self._stderr_task, self._process_task):
            if task is not None:
                with suppress(asyncio.CancelledError, Exception):
                    await task

    async def _request(self, method: str, params: Any) -> Any:
        if self._process is None or self._process.stdin is None:
            raise KernelStateError("kernel process is not running")
        request_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Response] = loop.create_future()
        self._pending[request_id] = _Pending(future=future, method=method)
        try:
            self._process.stdin.write(encode_request(request_id, method, params).encode())
            await self._process.stdin.drain()
            if self._process_task is None:
                response = await asyncio.wait_for(future, self._config.request_timeout)
            else:
                done, _ = await asyncio.wait(
                    (future, self._process_task),
                    timeout=self._config.request_timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    raise TimeoutError
                if future in done:
                    response = future.result()
                else:
                    failure = self._failure or KernelProcessError(
                        "Felix process exited before completing the request"
                    )
                    raise failure
        except TimeoutError as exc:
            self._pending.pop(request_id, None)
            if self._process is not None and self._process.returncode is not None:
                raise self._process_failure() from exc
            raise KernelTimeoutError(f"Felix request timed out: {method}") from exc
        except Exception:
            self._pending.pop(request_id, None)
            raise
        if response.error is not None:
            raise KernelRemoteError(
                response.error.code, response.error.message, response.error.data
            )
        return response.result

    async def _read_stdout(self, stream: asyncio.StreamReader) -> None:
        try:
            while line := await stream.readline():
                try:
                    message = decode_message(line.decode("utf-8"))
                except UnicodeDecodeError as exc:
                    failure = KernelProtocolError("Felix emitted non-UTF-8 output")
                    self._set_failure(failure)
                    self._fail_pending(failure)
                    raise KernelProtocolError("Felix emitted non-UTF-8 output") from exc
                if isinstance(message, Response):
                    pending = self._pending.pop(message.request_id, None)
                    if pending is not None and not pending.future.done():
                        pending.future.set_result(message)
                elif isinstance(message, Notification):
                    await self._notifications.put(message)
                    for queue in tuple(self._notification_subscribers):
                        try:
                            queue.put_nowait(message)
                        except asyncio.QueueFull:
                            # The session consumer owns overflow reporting.
                            pass
                elif isinstance(message, ServerRequest):
                    await self._send_error(message)
            # Process watcher owns EOF failure reporting so exit code and stderr are retained.
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not isinstance(exc, (KernelProtocolError, KernelProcessError)):
                exc = KernelProcessError(str(exc))
            self._set_failure(exc)
            self._fail_pending(exc)

    async def _read_stderr(self, stream: asyncio.StreamReader) -> None:
        try:
            while line := await stream.readline():
                self._stderr_tail.append(line.decode("utf-8", errors="replace").rstrip())
        except asyncio.CancelledError:
            raise

    async def _send_error(self, message: ServerRequest) -> None:
        if self._process is None or self._process.stdin is None or self._closed:
            return
        self._process.stdin.write(
            encode_error_response(message.request_id, -32601, "Method not found").encode()
        )
        await self._process.stdin.drain()

    async def _watch_process(self, process: asyncio.subprocess.Process) -> None:
        returncode = await process.wait()
        if self._closed:
            return
        stderr = " | ".join(self._stderr_tail)
        detail = f"Felix process exited with code {returncode}"
        if stderr:
            detail += f": {stderr}"
        self._set_failure(KernelProcessError(detail))
        self._fail_pending(self._failure)

    def _process_failure(self) -> KernelProcessError:
        if isinstance(self._failure, KernelProcessError):
            return self._failure
        returncode = self._process.returncode if self._process is not None else None
        stderr = " | ".join(self._stderr_tail)
        detail = f"Felix process exited with code {returncode}"
        if stderr:
            detail += f": {stderr}"
        failure = KernelProcessError(detail)
        self._set_failure(failure)
        return failure

    def _require_initialized(self) -> None:
        if self._closed:
            raise KernelStateError("kernel client is closed")
        if not self._started or self._initialize_result is None:
            raise KernelStateError("kernel client is not initialized")

    def _set_failure(self, failure: KernelProcessError | KernelProtocolError) -> None:
        if self._failure is None:
            self._failure = failure

    def _fail_pending(self, failure: BaseException | None) -> None:
        if failure is None:
            failure = KernelProcessError("Felix kernel transport failed")
        for pending in self._pending.values():
            if not pending.future.done():
                pending.future.set_exception(failure)
        self._pending.clear()


def _parse_initialize_result(value: Any) -> InitializeResult:
    if not isinstance(value, dict):
        raise KernelProtocolError("initialize result must be an object")
    protocol_version = value.get("protocolVersion")
    server_info = value.get("serverInfo")
    capabilities = value.get("capabilities")
    if not isinstance(protocol_version, int) or isinstance(protocol_version, bool):
        raise KernelProtocolError("initialize.protocolVersion must be an integer")
    if not isinstance(server_info, dict):
        raise KernelProtocolError("initialize.serverInfo must be an object")
    name = server_info.get("name")
    version = server_info.get("version")
    if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
        raise KernelProtocolError("initialize.serverInfo requires name and version")
    if not isinstance(capabilities, dict) or not all(isinstance(key, str) for key in capabilities):
        raise KernelProtocolError("initialize.capabilities must be an object")
    return InitializeResult(
        protocol_version=protocol_version,
        server_info=ServerInfo(name=name, version=version),
        capabilities=capabilities,
    )
