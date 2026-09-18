# Tool Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Astraship's platform-owned tool registry, validated async execution runtime, and workspace-contained file tools.

**Architecture:** A focused `tools` package separates immutable public types, strict schema validation, execution scheduling, and built-in capabilities. The registry normalizes every completed invocation into a stable result while preserving caller cancellation and enforcing safe/unsafe concurrency semantics.

**Tech Stack:** Python 3.12+, asyncio, dataclasses, pathlib, json, pytest, pytest-asyncio, Ruff, mypy

**Spec:** `docs/superpowers/specs/2026-09-18-tool-runtime-design.md`

## Global Constraints

- Runtime code remains standard-library-only.
- Unsupported JSON Schema keywords fail registration.
- Tool failures become stable results; caller cancellation propagates.
- Unsafe tools run exclusively; safe tools obey `max_concurrency`.
- Built-in filesystem tools never escape `ToolContext.workspace`.

---

### Task 1: Public types and schema validator

**Files:**
- Create: `src/astraship/tools/__init__.py`
- Create: `src/astraship/tools/types.py`
- Create: `src/astraship/tools/schema.py`
- Modify: `src/astraship/errors.py`
- Create: `tests/tools/test_schema.py`

**Interfaces:**
- Produces: `ToolDefinition`, `ToolContext`, `ToolCall`, `ToolResult`, `ToolError`, and `validate_arguments(schema, value)`.
- Produces: `ToolRegistrationError` and `ToolCallError`.

- [ ] Write failing tests for names, unsupported keywords, all supported primitive/container constraints, boolean-vs-integer, additional properties, and JSON-path diagnostics.
- [ ] Run `pytest tests/tools/test_schema.py -v` and verify failure because `astraship.tools` is absent.
- [ ] Implement immutable types and recursive schema compilation/validation.
- [ ] Run the focused tests and static checks.
- [ ] Commit the independently passing schema/type layer.

### Task 2: Registry and single-call execution

**Files:**
- Create: `src/astraship/tools/registry.py`
- Modify: `src/astraship/tools/__init__.py`
- Create: `tests/tools/test_registry.py`

**Interfaces:**
- Consumes: Task 1 public values and validator.
- Produces: `ToolRegistry(default_timeout=30.0, max_concurrency=8, observer=None)`, `register()`, `schemas()`, `execute()`.

- [ ] Write failing tests for registration, deterministic discovery, unknown tools, invalid arguments without dispatch, success, timeout, exception normalization, caller cancellation, invalid JSON output, elapsed time, and observer isolation.
- [ ] Run focused tests and confirm expected RED failures.
- [ ] Implement lookup, validation, timeout, JSON-result validation, immutable final results, and observer notification.
- [ ] Run focused tests and static checks.
- [ ] Commit the single-call runtime.

### Task 3: Batch scheduling and exclusivity

**Files:**
- Modify: `src/astraship/tools/registry.py`
- Modify: `tests/tools/test_registry.py`

**Interfaces:**
- Produces: `execute_many(calls, context) -> list[ToolResult]`.

- [ ] Write failing timing/barrier tests for submission-order results, maximum safe concurrency, duplicate call rejection before dispatch, and unsafe calls that overlap nothing.
- [ ] Run focused tests and confirm RED.
- [ ] Implement a fair read/write-style async gate: safe calls share up to the limit; unsafe calls acquire exclusive access in batch order.
- [ ] Run focused tests repeatedly to detect scheduling flakes.
- [ ] Commit batch execution.

### Task 4: Workspace file tools

**Files:**
- Create: `src/astraship/tools/builtins.py`
- Modify: `src/astraship/tools/__init__.py`
- Create: `tests/tools/test_builtins.py`

**Interfaces:**
- Produces: `builtin_file_tools(max_read_bytes=1048576, max_list_results=1000) -> tuple[ToolDefinition, ...]`.
- Tool names: `read_file`, `write_file`, `list_files`.

- [ ] Write failing tests for normal reads/writes/listing, sorted relative output, overwrite control, byte/result limits, absolute/traversal paths, and escaping symlinks.
- [ ] Run focused tests and confirm RED.
- [ ] Implement resolved workspace containment and the three async definitions (using `asyncio.to_thread` for filesystem work).
- [ ] Run focused and full tool tests.
- [ ] Commit built-in tools.

### Task 5: Documentation and release verification

**Files:**
- Modify: `README.md`
- Modify: only files implicated by verification failures

**Interfaces:**
- Documents direct Python registration, discovery, execution, and built-in tool usage.

- [ ] Add a concise Python example and state that Felix tool-call integration is a later protocol adapter.
- [ ] Run `pytest`, `ruff check .`, `ruff format --check .`, `mypy src tests`, and `git diff --check`.
- [ ] Run `uv build`, inspect both artifacts, install the wheel into a temporary virtual environment, and import/execute a registry smoke test.
- [ ] Inspect Astraship and Felix status to ensure no unrelated files are included.
- [ ] Commit documentation and any verified corrections.
