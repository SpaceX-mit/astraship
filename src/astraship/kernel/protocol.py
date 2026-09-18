"""Strict newline-delimited JSON-RPC protocol values for Felix."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

from ..errors import KernelProtocolError

PROTOCOL_VERSION: Final[int] = 1
JsonValue = Any
RequestId = int | str


@dataclass(frozen=True, slots=True)
class ServerInfo:
    """Identity returned by Felix during initialization."""

    name: str
    version: str


@dataclass(frozen=True, slots=True)
class InitializeResult:
    """Negotiated bootstrap information."""

    protocol_version: int
    server_info: ServerInfo
    capabilities: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class RemoteError:
    """A JSON-RPC error returned by Felix."""

    code: int
    message: str
    data: JsonValue = None


@dataclass(frozen=True, slots=True)
class Response:
    """A JSON-RPC response received from Felix."""

    request_id: RequestId
    result: JsonValue = None
    error: RemoteError | None = None


@dataclass(frozen=True, slots=True)
class Notification:
    """A server notification with no response ID."""

    method: str
    params: JsonValue = None


@dataclass(frozen=True, slots=True)
class ServerRequest:
    """A server request that requires a future handler."""

    request_id: RequestId
    method: str
    params: JsonValue = None


def encode_request(request_id: RequestId, method: str, params: JsonValue = None) -> str:
    """Encode a client JSON-RPC request as one newline-terminated line."""

    if not _valid_request_id(request_id):
        raise KernelProtocolError("request ID must be a string or integer")
    if not method:
        raise KernelProtocolError("request method cannot be empty")
    payload: dict[str, JsonValue] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n"


def encode_error_response(request_id: RequestId, code: int, message: str) -> str:
    """Encode a JSON-RPC error response for a server-initiated request."""

    return (
        json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}},
            separators=(",", ":"),
        )
        + "\n"
    )


def decode_message(line: str) -> Response | Notification | ServerRequest:
    """Decode and validate one JSON-RPC line."""

    try:
        value = json.loads(line)
    except json.JSONDecodeError as exc:
        raise KernelProtocolError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise KernelProtocolError("JSON-RPC message must be an object")
    if value.get("jsonrpc") != "2.0":
        raise KernelProtocolError("JSON-RPC message must use version 2.0")

    if "method" in value:
        method = value["method"]
        if not isinstance(method, str) or not method:
            raise KernelProtocolError("JSON-RPC method must be a non-empty string")
        params = value.get("params")
        if "id" in value:
            request_id = _require_request_id(value["id"])
            return ServerRequest(request_id=request_id, method=method, params=params)
        return Notification(method=method, params=params)

    if "id" not in value:
        raise KernelProtocolError("JSON-RPC response is missing id")
    request_id = _require_request_id(value["id"])
    has_result = "result" in value
    has_error = "error" in value
    if has_result == has_error:
        raise KernelProtocolError("JSON-RPC response must contain exactly one of result or error")
    if has_result:
        return Response(request_id=request_id, result=value["result"])
    error = value["error"]
    if not isinstance(error, dict):
        raise KernelProtocolError("JSON-RPC error must be an object")
    code = error.get("code")
    message = error.get("message")
    if not isinstance(code, int) or isinstance(code, bool) or not isinstance(message, str):
        raise KernelProtocolError("JSON-RPC error requires integer code and string message")
    return Response(
        request_id=request_id,
        error=RemoteError(code=code, message=message, data=error.get("data")),
    )


def _valid_request_id(value: object) -> bool:
    return isinstance(value, (str, int)) and not isinstance(value, bool)


def _require_request_id(value: object) -> RequestId:
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise KernelProtocolError("JSON-RPC id must be a string or integer")
