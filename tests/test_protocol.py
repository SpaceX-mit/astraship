import json

import pytest

from astraship.errors import KernelProtocolError
from astraship.kernel.protocol import (
    Notification,
    RemoteError,
    Response,
    ServerRequest,
    decode_message,
    encode_error_response,
    encode_request,
    encode_result_response,
)


def test_encode_request_emits_one_json_rpc_line() -> None:
    assert encode_request(7, "initialize", {"protocolVersion": 1}) == (
        '{"jsonrpc":"2.0","id":7,"method":"initialize","params":{"protocolVersion":1}}\n'
    )


def test_encode_result_response_emits_one_json_rpc_line() -> None:
    assert encode_result_response("tool-1", {"ok": True}) == (
        '{"jsonrpc":"2.0","id":"tool-1","result":{"ok":true}}\n'
    )


def test_encode_error_response_includes_optional_data() -> None:
    assert encode_error_response(3, -32602, "Invalid params", {"field": "name"}) == (
        '{"jsonrpc":"2.0","id":3,"error":{"code":-32602,'
        '"message":"Invalid params","data":{"field":"name"}}}\n'
    )


@pytest.mark.parametrize("request_id", [True, None, 1.5])
def test_response_encoders_reject_invalid_request_ids(request_id: object) -> None:
    with pytest.raises(KernelProtocolError, match="request ID"):
        encode_result_response(request_id, None)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [float("nan"), {"bad": object()}])
def test_response_encoders_reject_non_json_results(value: object) -> None:
    with pytest.raises(KernelProtocolError, match="JSON-compatible"):
        encode_result_response(1, value)


def test_decode_success_response() -> None:
    message = decode_message('{"jsonrpc":"2.0","id":7,"result":{"protocolVersion":1}}')

    assert message == Response(request_id=7, result={"protocolVersion": 1})


def test_decode_remote_error_preserves_code_message_and_data() -> None:
    message = decode_message(
        '{"jsonrpc":"2.0","id":"x","error":{"code":-32001,'
        '"message":"unsupported","data":{"supportedVersions":[1]}}}'
    )

    assert message == Response(
        request_id="x",
        error=RemoteError(-32001, "unsupported", {"supportedVersions": [1]}),
    )


def test_decode_notification_without_id() -> None:
    assert decode_message('{"jsonrpc":"2.0","method":"session.event"}') == Notification(
        method="session.event"
    )


def test_decode_server_request_with_id_for_explicit_rejection() -> None:
    assert decode_message('{"jsonrpc":"2.0","id":3,"method":"ping"}') == ServerRequest(
        request_id=3, method="ping"
    )


@pytest.mark.parametrize(
    "line",
    [
        "not json",
        "[]",
        '{"jsonrpc":"1.0","id":1,"result":{}}',
        '{"jsonrpc":"2.0","id":true,"result":{}}',
        '{"jsonrpc":"2.0","id":1}',
        '{"jsonrpc":"2.0","id":1,"result":{},"error":{"code":1,"message":"x"}}',
        '{"jsonrpc":"2.0","method":7}',
        '{"jsonrpc":"2.0","id":1,"error":{"code":1}}',
    ],
)
def test_decode_rejects_malformed_or_ambiguous_messages(line: str) -> None:
    with pytest.raises(KernelProtocolError):
        decode_message(line)


def test_decode_does_not_accept_json_values_with_trailing_content() -> None:
    with pytest.raises(KernelProtocolError):
        decode_message(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + " {}")
