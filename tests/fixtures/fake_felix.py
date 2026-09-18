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
    choices=("normal", "wrong-version", "malformed", "exit", "timeout"),
    default="normal",
)
args = parser.parse_args()

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
                    "capabilities": {"fixture": True},
                },
            }
        )
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
    elif method == "exit":
        print("requested fixture exit", file=sys.stderr, flush=True)
        raise SystemExit(17)
    elif args.mode == "timeout" or method == "hang":
        time.sleep(60)
    else:
        send({"jsonrpc": "2.0", "id": request["id"], "result": request.get("params")})
