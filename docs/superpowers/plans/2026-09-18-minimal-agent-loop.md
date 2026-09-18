# Minimal Agent Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose a typed Astraship session facade and a runnable prompt-to-assistant CLI path over Felix's session RPC.

**Architecture:** `KernelSession` wraps the existing `FelixClient`, validates session RPC payloads, and runs a bounded notification demultiplexer. A deterministic fixture provides the Felix-side mock LLM behavior for integration tests; the production platform only depends on the protocol and event types.

**Tech Stack:** Python 3.12+, asyncio, dataclasses, pytest, pytest-asyncio, Ruff, mypy, uv

**Spec:** `docs/superpowers/specs/2026-09-18-minimal-agent-loop-design.md`

## Global Constraints

- Felix remains an external process and owns agent execution.
- `session/prompt` returns enqueue acknowledgment; assistant output arrives as `session.event`.
- Runtime code uses Python standard library only.
- Unknown event types are preserved, not discarded.
- Queue overflow fails loudly; events are never silently dropped.

---

### Task 1: Session event and typed facade

**Files:**
- Create: `src/astraship/session.py`
- Modify: `src/astraship/errors.py`
- Create: `tests/test_session.py`

**Interfaces:**
- Produces: `SessionEvent(session_id, type, data)`, `PromptReceipt(message_id)`, and `KernelSession.create(client, event_queue_size=128)`.
- Produces: `prompt(content)`, `events()`, and idempotent `close()`.

- [ ] Write failing tests for creation, malformed results, prompt validation, event filtering, assistant delivery, and close state.
- [ ] Run the focused tests and verify they fail because `astraship.session` is absent.
- [ ] Implement typed parsing, bounded demultiplexing, and cleanup semantics.
- [ ] Run focused tests and verify they pass.

### Task 2: Deterministic Felix fixture and integration coverage

**Files:**
- Modify: `tests/fixtures/fake_felix.py`
- Modify: `tests/test_session.py`

**Interfaces:**
- Consumes: `KernelSession` and `FelixClient`.
- Produces: real-child-process coverage for `session/new`, `session/prompt`, `session/close`, `mock: <prompt>`, interleaving, and queue overflow.

- [ ] Add fixture modes and handlers for session RPC and durable notifications.
- [ ] Add tests that use the real subprocess, not an in-process mock.
- [ ] Run the session integration tests and verify all pass.

### Task 3: Run command

**Files:**
- Modify: `src/astraship/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- Produces: `astraship run --prompt TEXT`.

- [ ] Write a subprocess test for successful mock response and no-traceback failure output.
- [ ] Verify the new test fails before implementation.
- [ ] Implement prompt submission, event consumption through `turn/end`, output, and guaranteed cleanup.
- [ ] Update README's quick start to use Python commands.
- [ ] Run CLI tests.

### Task 4: Full verification and commit

- [ ] Run `uv run pytest`.
- [ ] Run `uv run ruff check .`.
- [ ] Run `uv run ruff format --check .`.
- [ ] Run `uv run mypy src tests`.
- [ ] Run `git diff --check` and commit Astraship changes.
