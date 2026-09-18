#!/usr/bin/env python3
import argparse
import json
import sys
import time


def send(message: object) -> None:
    print(json.dumps(message, separators=(",", ":")), flush=True)


parser = argparse.ArgumentParser()
parser.add_argument(
    "--mode",
    choices=(
        "normal",
        "wrong-version",
        "malformed",
        "exit",
        "timeout",
        "session",
        "bad-session",
    ),
    default="normal",
)
args = parser.parse_args()
sessions = {}
next_session = 1

for raw_line in sys.stdin:
    if not raw_line.strip():
        continue
    request = json.loads(raw_line)
    method = request.get("method")
    if method == "initialize":
        if args.mode == "malformed":
            print("not-json", flush=True)
            continue
        if args.mode == "exit":
            print("fatal fixture failure", file=sys.stderr, flush=True)
            raise SystemExit(23)
        send(
            {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "protocolVersion": 2 if args.mode == "wrong-version" else 1,
                    "serverInfo": {"name": "fake-felix", "version": "9.8.7"},
                    "capabilities": {
                        "fixture": True,
                        **(
                            {"hostTools": {"version": 1}}
                            if "hostTools" in request.get("params", {}).get("capabilities", {})
                            else {}
                        ),
                    },
                },
            }
        )
    elif method == "session/new":
        if args.mode == "bad-session":
            send({"jsonrpc": "2.0", "id": request["id"], "result": {"wrong": True}})
        else:
            session_id = f"s-{next_session}"
            next_session += 1
            sessions[session_id] = 0
            send({"jsonrpc": "2.0", "id": request["id"], "result": {"sessionId": session_id}})
    elif method == "session/prompt":
        params = request.get("params", {})
        session_id = params.get("sessionId")
        content = params.get("content")
        if session_id not in sessions:
            send(
                {
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "error": {"code": -32010, "message": "unknown session"},
                }
            )
            continue
        sessions[session_id] += 1
        message_id = f"m-{sessions[session_id]}"
        send(
            {
                "jsonrpc": "2.0",
                "method": "session.event",
                "params": {
                    "sessionId": session_id,
                    "event": {
                        "type": "user/message",
                        "data": {"messageId": message_id, "content": content},
                    },
                },
            }
        )
        if sessions[session_id] == 1:
            send(
                {
                    "jsonrpc": "2.0",
                    "method": "session.event",
                    "params": {
                        "sessionId": session_id,
                        "event": {"type": "future/event", "data": {"value": True}},
                    },
                }
            )
        send(
            {
                "jsonrpc": "2.0",
                "method": "session.event",
                "params": {
                    "sessionId": session_id,
                    "event": {
                        "type": "assistant/message",
                        "data": {"messageId": f"a-{message_id}", "content": f"mock: {content}"},
                    },
                },
            }
        )
        send(
            {
                "jsonrpc": "2.0",
                "method": "session.event",
                "params": {
                    "sessionId": session_id,
                    "event": {"type": "turn/end", "data": {"messageId": message_id}},
                },
            }
        )
        send({"jsonrpc": "2.0", "id": request["id"], "result": {"messageId": message_id}})
    elif method == "session/close":
        session_id = request.get("params", {}).get("sessionId")
        sessions.pop(session_id, None)
        send({"jsonrpc": "2.0", "id": request["id"], "result": {}})
    elif method == "delayed":
        time.sleep(0.2)
        send({"jsonrpc": "2.0", "id": request["id"], "result": "late"})
    elif method == "out-of-order":
        second = json.loads(sys.stdin.readline())
        send({"jsonrpc": "2.0", "id": second["id"], "result": second["params"]["value"]})
        send({"jsonrpc": "2.0", "id": request["id"], "result": request["params"]["value"]})
    elif method == "fail":
        send(
            {
                "jsonrpc": "2.0",
                "id": request["id"],
                "error": {"code": 42, "message": "fixture error", "data": {"detail": "x"}},
            }
        )
    elif method == "notify":
        send({"jsonrpc": "2.0", "method": "kernel.tick", "params": {"count": 1}})
        send({"jsonrpc": "2.0", "id": request["id"], "result": None})
    elif method == "server-request":
        send({"jsonrpc": "2.0", "id": "server-1", "method": "client.unknown"})
        response = json.loads(sys.stdin.readline())
        send({"jsonrpc": "2.0", "id": request["id"], "result": response["error"]["code"]})
    elif method == "server-execute":
        send(
            {
                "jsonrpc": "2.0",
                "id": "tool-1",
                "method": "tool/execute",
                "params": request.get("params"),
            }
        )
        response = json.loads(sys.stdin.readline())
        send({"jsonrpc": "2.0", "id": request["id"], "result": response})
    elif method == "server-concurrent":
        send({"jsonrpc": "2.0", "id": "slow", "method": "fixture/slow"})
        send({"jsonrpc": "2.0", "id": "fast", "method": "fixture/fast"})
        first = json.loads(sys.stdin.readline())
        second = json.loads(sys.stdin.readline())
        send(
            {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": [first, second],
            }
        )
    elif method == "server-cancel":
        send({"jsonrpc": "2.0", "id": "cancel-me", "method": "fixture/hang"})
        send(
            {
                "jsonrpc": "2.0",
                "method": "$/cancelRequest",
                "params": {"id": "cancel-me"},
            }
        )
        response = json.loads(sys.stdin.readline())
        send({"jsonrpc": "2.0", "id": request["id"], "result": response})
    elif method == "server-cancel-running":
        send({"jsonrpc": "2.0", "id": "cancel-running", "method": "fixture/hang"})
        time.sleep(0.05)
        send(
            {
                "jsonrpc": "2.0",
                "method": "$/cancelRequest",
                "params": {"id": "cancel-running"},
            }
        )
        response = json.loads(sys.stdin.readline())
        send({"jsonrpc": "2.0", "id": request["id"], "result": response})
    elif method == "server-duplicate":
        send({"jsonrpc": "2.0", "id": "duplicate", "method": "fixture/hang"})
        time.sleep(0.05)
        send({"jsonrpc": "2.0", "id": "duplicate", "method": "client.unknown"})
        response = json.loads(sys.stdin.readline())
        send({"jsonrpc": "2.0", "id": request["id"], "result": response})
    elif method == "server-hang":
        send({"jsonrpc": "2.0", "id": "close-me", "method": "fixture/hang"})
        response_line = sys.stdin.readline()
        if response_line:
            send({"jsonrpc": "2.0", "id": request["id"], "result": json.loads(response_line)})
    elif method == "exit":
        print("requested fixture exit", file=sys.stderr, flush=True)
        raise SystemExit(17)
    elif args.mode == "timeout" or method == "hang":
        time.sleep(60)
    else:
        send({"jsonrpc": "2.0", "id": request["id"], "result": request.get("params")})
