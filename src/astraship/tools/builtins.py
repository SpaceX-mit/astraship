"""Workspace-contained built-in file tools."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .types import ToolContext, ToolDefinition


def builtin_file_tools(
    *, max_read_bytes: int = 1_048_576, max_list_results: int = 1_000
) -> tuple[ToolDefinition, ...]:
    """Create the standard workspace-scoped file tool definitions."""

    if max_read_bytes <= 0:
        raise ValueError("max_read_bytes must be greater than zero")
    if max_list_results <= 0:
        raise ValueError("max_list_results must be greater than zero")

    async def read_file(arguments: Mapping[str, Any], context: ToolContext) -> object:
        return await asyncio.to_thread(
            _read_file, context.workspace, str(arguments["path"]), max_read_bytes
        )

    async def write_file(arguments: Mapping[str, Any], context: ToolContext) -> object:
        return await asyncio.to_thread(
            _write_file,
            context.workspace,
            str(arguments["path"]),
            str(arguments["content"]),
            bool(arguments["overwrite"]),
        )

    async def list_files(arguments: Mapping[str, Any], context: ToolContext) -> object:
        return await asyncio.to_thread(
            _list_files,
            context.workspace,
            str(arguments["pattern"]),
            max_list_results,
        )

    path_schema = {"type": "string", "minLength": 1}
    return (
        ToolDefinition(
            name="read_file",
            description="Read a UTF-8 text file inside the workspace",
            parameters={
                "type": "object",
                "properties": {"path": path_schema},
                "required": ["path"],
                "additionalProperties": False,
            },
            execute=read_file,
            concurrency_safe=True,
        ),
        ToolDefinition(
            name="write_file",
            description="Write a UTF-8 text file inside the workspace",
            parameters={
                "type": "object",
                "properties": {
                    "path": path_schema,
                    "content": {"type": "string"},
                    "overwrite": {"type": "boolean"},
                },
                "required": ["path", "content", "overwrite"],
                "additionalProperties": False,
            },
            execute=write_file,
            concurrency_safe=False,
        ),
        ToolDefinition(
            name="list_files",
            description="List sorted files matching a workspace glob",
            parameters={
                "type": "object",
                "properties": {"pattern": {"type": "string", "minLength": 1}},
                "required": ["pattern"],
                "additionalProperties": False,
            },
            execute=list_files,
            concurrency_safe=True,
        ),
    )


def _read_file(root: Path, raw_path: str, max_bytes: int) -> dict[str, object]:
    path = _resolve_path(root, raw_path)
    if not path.is_file():
        raise FileNotFoundError(f"file does not exist: {raw_path}")
    size = path.stat().st_size
    if size > max_bytes:
        raise ValueError(f"file exceeds {max_bytes} byte limit")
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8: {raw_path}") from exc
    return {"path": _relative(root, path), "content": content}


def _write_file(root: Path, raw_path: str, content: str, overwrite: bool) -> dict[str, object]:
    path = _resolve_path(root, raw_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "x"
    try:
        with path.open(mode, encoding="utf-8", newline="") as stream:
            stream.write(content)
    except FileExistsError as exc:
        raise FileExistsError(f"file already exists: {raw_path}") from exc
    return {"path": _relative(root, path), "bytes": len(content.encode("utf-8"))}


def _list_files(root: Path, pattern: str, limit: int) -> dict[str, object]:
    _validate_relative(pattern)
    matches: list[str] = []
    for candidate in root.glob(pattern):
        resolved = candidate.resolve()
        _require_contained(root, resolved)
        if resolved.is_file():
            matches.append(_relative(root, resolved))
    ordered = sorted(set(matches))
    return {"paths": ordered[:limit], "truncated": len(ordered) > limit}


def _resolve_path(root: Path, raw_path: str) -> Path:
    _validate_relative(raw_path)
    resolved = (root / raw_path).resolve()
    _require_contained(root, resolved)
    return resolved


def _validate_relative(raw_path: str) -> None:
    path = Path(raw_path)
    if path.is_absolute():
        raise ValueError("file path must be relative to the workspace")
    if ".." in path.parts:
        raise ValueError("file path must remain inside the workspace")


def _require_contained(root: Path, path: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("file path resolves outside the workspace") from exc


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()
