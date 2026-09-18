# Felix Host-Tool Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect Astraship's Python tool runtime to Felix reverse JSON-RPC host-tool requests.

**Architecture:** A focused adapter translates the host-tool wire contract into registry calls, while `FelixClient` provides generic asynchronous server-request dispatch, serialized writes, cancellation, and cleanup. Initialization advertises an immutable capability snapshot.

**Tech Stack:** Python 3.12+, asyncio, dataclasses, JSON-RPC 2.0, pytest, pytest-asyncio, Ruff, mypy

**Spec:** `docs/superpowers/specs/2026-09-18-host-tool-adapter-design.md`

## Global Constraints

- Runtime code remains standard-library-only.
- Felix Rust implementation is out of scope; required protocol changes live under `felix/docs/design/api/`.
- Tool failures are JSON-RPC success results; envelope and transport failures are JSON-RPC errors.
- The model cannot supply or override a tool workspace.
- The existing no-adapter client API remains backward compatible.

---

### Task 1: Reverse-response protocol encoders

**Files:**
- Modify: `src/astraship/kernel/protocol.py`
- Modify: `tests/test_protocol.py`

**Interfaces:**
- Produces: `encode_result_response(request_id, result)` and `encode_error_response(request_id, code, message, data=None)`.

- [ ] Add focused tests for compact newline-terminated result encoding, optional error data, invalid IDs, and non-JSON values.
- [ ] Run the focused tests and observe failure because the result encoder and data argument do not exist.
- [ ] Implement strict shared response encoding with finite JSON enforcement.
- [ ] Run the focused protocol tests and static checks.

### Task 2: Host tool contract adapter

**Files:**
- Create: `src/astraship/kernel/host_tools.py`
- Modify: `src/astraship/kernel/__init__.py`
- Create: `tests/test_host_tools.py`

**Interfaces:**
- Consumes: `ToolRegistry`, `ToolContext`, `ToolCall`, `ToolResult`, and `ServerRequest`.
- Produces: `HostToolAdapter.capability()`, `.handlers()`, and async `.handle()`.
- Produces: `InvalidRequestParams` for JSON-RPC `-32602` translation.

- [ ] Add tests for sorted schema negotiation, immutable snapshots, trusted session metadata, success/error serialization, and every malformed required field.
- [ ] Run tests and observe import failure for the missing adapter.
- [ ] Implement strict parsing, per-session context derivation, registry execution, and wire serialization.
- [ ] Run adapter and tool-runtime tests.

### Task 3: Concurrent server-request transport

**Files:**
- Modify: `src/astraship/kernel/client.py`
- Modify: `tests/fixtures/fake_felix.py`
- Modify: `tests/test_kernel_client.py`

**Interfaces:**
- Extends: `FelixClient(config, *, capabilities=None, request_handlers=None)`.
- Consumes: async `RequestHandler(ServerRequest) -> JsonValue`.

- [ ] Add fixture-backed tests proving capabilities are negotiated, a handler result returns, malformed input maps to `-32602`, unknown methods remain `-32601`, and unexpected failures map to `-32603`.
- [ ] Add tests proving overlapping server requests may finish out of order, cancellation returns `-32800`, and close cancels in-flight handlers.
- [ ] Run focused tests and observe failures against synchronous rejection behavior.
- [ ] Implement defensive input snapshots, one task per reverse request, a shared stdin write lock, cancellation routing, stable error translation, and close cleanup.
- [ ] Run kernel, adapter, session, and full tests.

### Task 4: Integration and release verification

**Files:**
- Modify: `README.md` only if a public usage example is missing after implementation
- Modify: only files implicated by verification failures

**Interfaces:**
- Wires: `HostToolAdapter.capability()` and `.handlers()` into a usable `FelixClient` construction example.

- [ ] Add a concise documented construction example without claiming real Felix support before requirement 0003 lands.
- [ ] Run `PYTHONPATH=src .venv/bin/pytest`, Ruff check/format, mypy, and `git diff --check`.
- [ ] Run `uv build`, inspect artifacts, install the wheel into a temporary environment, and execute an adapter smoke test.
- [ ] Inspect status and stage only milestone files, excluding the existing `uv.lock` modification.
- [ ] Commit the verified milestone.
