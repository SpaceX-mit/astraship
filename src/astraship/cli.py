"""Astraship command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .config import KernelConfig
from .errors import AstrashipError
from .kernel.client import FelixClient
from .persistence import JsonlSessionStore
from .session import KernelSession


def build_parser() -> argparse.ArgumentParser:
    """Build the public CLI parser."""

    parser = argparse.ArgumentParser(prog="astraship", description="Astraship Agent OS")
    subparsers = parser.add_subparsers(dest="command")
    kernel = subparsers.add_parser("kernel", help="inspect the Felix kernel")
    kernel_subparsers = kernel.add_subparsers(dest="kernel_command")
    kernel_subparsers.add_parser("check", help="negotiate with Felix and report its version")
    run = subparsers.add_parser("run", help="run one prompt through Felix")
    run.add_argument("--prompt", required=True, help="user prompt")
    run.add_argument("--store", type=Path, help="directory for durable session transcripts")
    session = subparsers.add_parser("session", help="inspect persisted sessions")
    session_subparsers = session.add_subparsers(dest="session_command")
    session_list = session_subparsers.add_parser("list", help="list persisted sessions")
    session_list.add_argument("--store", type=Path, required=True, help="transcript directory")
    replay = session_subparsers.add_parser("replay", help="replay a persisted session")
    replay.add_argument("session_id", help="persisted session ID")
    replay.add_argument("--store", type=Path, required=True, help="transcript directory")
    replay.add_argument("--type", dest="event_type", help="filter by event type")
    replay.add_argument("--offset", type=int, default=0, help="events to skip")
    replay.add_argument("--limit", type=int, help="maximum events to return")
    return parser


async def _kernel_check() -> int:
    async with FelixClient(KernelConfig()) as client:
        result = client.initialize_result
        print(
            f"Felix {result.server_info.name} {result.server_info.version} "
            f"(protocol {result.protocol_version})"
        )
    return 0


async def _run_prompt(content: str, store_path: Path | None = None) -> int:
    store = JsonlSessionStore(store_path) if store_path is not None else None
    async with FelixClient(KernelConfig()) as client:
        session = await KernelSession.create(client, store=store)
        try:
            await session.prompt(content)
            async for event in session.events():
                if event.type == "assistant/message":
                    assistant_content = event.data.get("content")
                    if isinstance(assistant_content, str):
                        print(assistant_content)
                if event.type == "turn/end":
                    break
        finally:
            await session.close()
    return 0


def _session_list(store_path: Path) -> int:
    for session_id in JsonlSessionStore(store_path).list_sessions():
        print(session_id)
    return 0


def _session_replay(
    store_path: Path,
    session_id: str,
    *,
    event_type: str | None,
    offset: int,
    limit: int | None,
) -> int:
    events = JsonlSessionStore(store_path).query(
        session_id, event_type=event_type, offset=offset, limit=limit
    )
    print(
        json.dumps(
            [
                {"sessionId": event.session_id, "type": event.type, "data": event.data}
                for event in events
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the Astraship CLI and return an exit status."""

    args = build_parser().parse_args(argv)
    if args.command == "kernel" and args.kernel_command == "check":
        try:
            return asyncio.run(_kernel_check())
        except AstrashipError as exc:
            print(f"astraship: {exc}", file=sys.stderr)
            return 1
    if args.command == "run":
        try:
            return asyncio.run(_run_prompt(args.prompt, args.store))
        except AstrashipError as exc:
            print(f"astraship: {exc}", file=sys.stderr)
            return 1
    if args.command == "session" and args.session_command == "list":
        try:
            return _session_list(args.store)
        except AstrashipError as exc:
            print(f"astraship: {exc}", file=sys.stderr)
            return 1
    if args.command == "session" and args.session_command == "replay":
        try:
            return _session_replay(
                args.store,
                args.session_id,
                event_type=args.event_type,
                offset=args.offset,
                limit=args.limit,
            )
        except AstrashipError as exc:
            print(f"astraship: {exc}", file=sys.stderr)
            return 1
    build_parser().print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
