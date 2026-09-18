"""Astraship command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import sys

from .config import KernelConfig
from .errors import AstrashipError
from .kernel.client import FelixClient


def build_parser() -> argparse.ArgumentParser:
    """Build the public CLI parser."""

    parser = argparse.ArgumentParser(prog="astraship", description="Astraship Agent OS")
    subparsers = parser.add_subparsers(dest="command")
    kernel = subparsers.add_parser("kernel", help="inspect the Felix kernel")
    kernel_subparsers = kernel.add_subparsers(dest="kernel_command")
    kernel_subparsers.add_parser("check", help="negotiate with Felix and report its version")
    return parser


async def _kernel_check() -> int:
    async with FelixClient(KernelConfig()) as client:
        result = client.initialize_result
        print(
            f"Felix {result.server_info.name} {result.server_info.version} "
            f"(protocol {result.protocol_version})"
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
    build_parser().print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
