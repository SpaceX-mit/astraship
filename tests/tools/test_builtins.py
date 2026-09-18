import os
from pathlib import Path

import pytest

from astraship.tools import (
    ToolCall,
    ToolContext,
    ToolRegistry,
    builtin_file_tools,
)


def registry(*, max_read_bytes: int = 1024, max_list_results: int = 100) -> ToolRegistry:
    tool_registry = ToolRegistry()
    for tool in builtin_file_tools(
        max_read_bytes=max_read_bytes, max_list_results=max_list_results
    ):
        tool_registry.register(tool)
    return tool_registry


@pytest.mark.asyncio
async def test_write_read_and_list_files_inside_workspace(tmp_path: Path) -> None:
    tool_registry = registry()
    context = ToolContext(tmp_path)

    written = await tool_registry.execute(
        ToolCall(
            "w1",
            "write_file",
            {"path": "notes/hello.txt", "content": "hello\n", "overwrite": False},
        ),
        context,
    )
    read = await tool_registry.execute(
        ToolCall("r1", "read_file", {"path": "notes/hello.txt"}), context
    )
    listed = await tool_registry.execute(
        ToolCall("l1", "list_files", {"pattern": "**/*.txt"}), context
    )

    assert written.output == {"path": "notes/hello.txt", "bytes": 6}
    assert (tmp_path / "notes" / "hello.txt").read_text(encoding="utf-8") == "hello\n"
    assert read.output == {"path": "notes/hello.txt", "content": "hello\n"}
    assert listed.output == {"paths": ["notes/hello.txt"], "truncated": False}


@pytest.mark.asyncio
async def test_list_files_is_sorted_and_reports_truncation(tmp_path: Path) -> None:
    (tmp_path / "z.txt").write_text("z", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "m.txt").write_text("m", encoding="utf-8")

    result = await registry(max_list_results=2).execute(
        ToolCall("l1", "list_files", {"pattern": "*.txt"}),
        ToolContext(tmp_path),
    )

    assert result.output == {"paths": ["a.txt", "m.txt"], "truncated": True}


@pytest.mark.asyncio
async def test_write_refuses_existing_file_unless_overwrite_is_true(tmp_path: Path) -> None:
    path = tmp_path / "existing.txt"
    path.write_text("old", encoding="utf-8")
    tool_registry = registry()
    context = ToolContext(tmp_path)

    refused = await tool_registry.execute(
        ToolCall(
            "w1",
            "write_file",
            {"path": "existing.txt", "content": "new", "overwrite": False},
        ),
        context,
    )
    replaced = await tool_registry.execute(
        ToolCall(
            "w2",
            "write_file",
            {"path": "existing.txt", "content": "new", "overwrite": True},
        ),
        context,
    )

    assert refused.error is not None and refused.error.code == "execution_error"
    assert "already exists" in refused.error.message
    assert replaced.output == {"path": "existing.txt", "bytes": 3}
    assert path.read_text(encoding="utf-8") == "new"


@pytest.mark.asyncio
async def test_read_rejects_files_over_byte_limit_and_invalid_utf8(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_bytes(b"12345")
    (tmp_path / "binary.txt").write_bytes(b"\xff")
    tool_registry = registry(max_read_bytes=4)
    context = ToolContext(tmp_path)

    large = await tool_registry.execute(ToolCall("r1", "read_file", {"path": "large.txt"}), context)
    binary = await tool_registry.execute(
        ToolCall("r2", "read_file", {"path": "binary.txt"}), context
    )

    assert large.error is not None and "byte limit" in large.error.message
    assert binary.error is not None and "UTF-8" in binary.error.message


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["../escape.txt", "nested/../../escape.txt"])
async def test_file_tools_reject_parent_traversal(tmp_path: Path, path: str) -> None:
    result = await registry().execute(
        ToolCall("r1", "read_file", {"path": path}), ToolContext(tmp_path)
    )

    assert result.error is not None and "workspace" in result.error.message


@pytest.mark.asyncio
async def test_file_tools_reject_absolute_paths(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    result = await registry().execute(
        ToolCall("r1", "read_file", {"path": str(outside)}), ToolContext(tmp_path)
    )

    assert result.error is not None and "relative" in result.error.message


@pytest.mark.asyncio
async def test_file_tools_reject_symlinks_escaping_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        os.symlink(outside, link)
    except OSError:
        pytest.skip("symlinks are not supported on this platform")

    tool_registry = registry()
    read = await tool_registry.execute(
        ToolCall("r1", "read_file", {"path": "link.txt"}), ToolContext(tmp_path)
    )
    write = await tool_registry.execute(
        ToolCall(
            "w1",
            "write_file",
            {"path": "link.txt", "content": "changed", "overwrite": True},
        ),
        ToolContext(tmp_path),
    )

    assert read.error is not None and "workspace" in read.error.message
    assert write.error is not None and "workspace" in write.error.message
    assert outside.read_text(encoding="utf-8") == "private"


@pytest.mark.parametrize("kwargs", [{"max_read_bytes": 0}, {"max_list_results": 0}])
def test_builtin_limits_must_be_positive(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        builtin_file_tools(**kwargs)
