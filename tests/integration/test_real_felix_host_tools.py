from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from astraship.config import KernelConfig
from astraship.kernel.client import FelixClient
from astraship.kernel.host_tools import HostToolAdapter
from astraship.session import KernelSession
from astraship.tools import ToolContext, ToolRegistry, builtin_file_tools


class CompletionFixture:
    def __init__(self, expected_content: str) -> None:
        self.expected_content = expected_content
        self.requests: list[dict[str, Any]] = []
        self.server: asyncio.Server | None = None

    async def __aenter__(self) -> CompletionFixture:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *args: object) -> None:
        assert self.server is not None
        self.server.close()
        await self.server.wait_closed()

    @property
    def base_url(self) -> str:
        assert self.server is not None
        address = self.server.sockets[0].getsockname()
        return f"http://127.0.0.1:{address[1]}"

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            headers = head.decode("ascii").split("\r\n")
            content_length = next(
                int(line.split(":", 1)[1].strip())
                for line in headers[1:]
                if line.lower().startswith("content-length:")
            )
            body = await reader.readexactly(content_length)
            request = json.loads(body)
            assert isinstance(request, dict)
            self.requests.append(request)
            response = self._response(len(self.requests), request)
            encoded = json.dumps(response, separators=(",", ":")).encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                + f"Content-Length: {len(encoded)}\r\n".encode()
                + b"Content-Type: application/json\r\nConnection: close\r\n\r\n"
                + encoded
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    def _response(self, number: int, request: dict[str, Any]) -> dict[str, Any]:
        if number == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-read-1",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"path":"note.txt"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        assert number == 2, request
        return {
            "choices": [
                {
                    "message": {"content": "The file was read by Astraship.", "tool_calls": []},
                    "finish_reason": "stop",
                }
            ]
        }


def _felix_repository() -> Path:
    configured = os.environ.get("ASTRASHIP_TEST_FELIX_REPO")
    if configured:
        return Path(configured).resolve()
    return (Path(__file__).resolve().parents[2].parent / "felix").resolve()


async def _build_felix_server(repository: Path) -> Path:
    cargo = shutil.which("cargo")
    if cargo is None:
        pytest.fail("cargo is required for the real Felix integration test")
    await asyncio.to_thread(
        subprocess.run,
        [cargo, "build", "-p", "felix-server"],
        cwd=repository,
        check=True,
    )
    binary = repository / "target" / "debug" / "felix-server"
    assert binary.is_file()
    return binary


@pytest.mark.real_felix
@pytest.mark.asyncio
async def test_real_felix_executes_astraship_workspace_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = "real Felix read this exact Astraship workspace content\n"
    (tmp_path / "note.txt").write_text(content, encoding="utf-8")
    binary = await _build_felix_server(_felix_repository())

    registry = ToolRegistry()
    for definition in builtin_file_tools():
        registry.register(definition)
    adapter = HostToolAdapter(registry, ToolContext(tmp_path))

    async with CompletionFixture(content) as fixture:
        monkeypatch.setenv("FELIX_LLM_PROVIDER", "deepseek")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
        monkeypatch.setenv("DEEPSEEK_BASE_URL", fixture.base_url)
        monkeypatch.setenv("DEEPSEEK_MODEL", "fixture-model")
        monkeypatch.delenv("FELIX_RSI_DIR", raising=False)

        client = FelixClient(
            KernelConfig(command=(str(binary),), request_timeout=5, shutdown_timeout=2),
            capabilities=adapter.capability(),
            request_handlers=adapter.handlers(),
        )
        process: asyncio.subprocess.Process | None = None
        events = []
        async with client:
            assert client.initialize_result.capabilities["hostTools"] == {"version": 1}
            process = client._process
            session = await KernelSession.create(client)
            try:
                receipt = await session.prompt("Read note.txt")

                async with asyncio.timeout(2):
                    async for event in session.events():
                        events.append(event)
                        if event.type == "turn/end":
                            break
                assert receipt.message_id
            finally:
                await session.close()

        assert client.closed
        assert process is not None and process.returncode == 0

    assert len(fixture.requests) == 2
    first, second = fixture.requests
    read_schema = next(
        tool["function"] for tool in first["tools"] if tool["function"]["name"] == "read_file"
    )
    assert read_schema["parameters"]["required"] == ["path"]
    tool_message = next(message for message in second["messages"] if message["role"] == "tool")
    assert tool_message["tool_call_id"] == "call-read-1"
    assert tool_message["name"] == "read_file"
    tool_result = json.loads(tool_message["content"])
    assert tool_result["callId"] == "call-read-1"
    assert tool_result["output"]["content"] == content
    assistant = next(event for event in events if event.type == "assistant/message")
    assert assistant.data["content"] == "The file was read by Astraship."
    assert events[-1].type == "turn/end"
    assert events[-1].data["status"] == "finished"
