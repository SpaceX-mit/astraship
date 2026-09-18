# Session Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist Astraship session events as recoverable, append-only JSONL transcripts.

**Architecture:** A small filesystem store owns path validation, JSON encoding, durable append, and strict replay. `KernelSession` optionally receives the store and persists matching events before consumer delivery; Felix's runtime state remains external and live-only.

**Tech Stack:** Python 3.12+, pathlib, json, os, dataclasses, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-09-18-session-persistence-design.md`

## Global Constraints

- Store writes are append-only and fsync before success.
- JSONL records are UTF-8 JSON objects with `sessionId`, `type`, and object `data`.
- Invalid records and unsafe IDs fail loudly.
- Persistence happens before event delivery.

---

### Task 1: JSONL store

**Files:**
- Create: `src/astraship/persistence.py`
- Modify: `src/astraship/errors.py`
- Create: `tests/test_persistence.py`

- [ ] Write failing tests for append/reopen, ordering, listing, malformed records, mismatched IDs, and unsafe paths.
- [ ] Run focused tests and verify the persistence module is absent.
- [ ] Implement strict path validation, durable append, and full-file replay.
- [ ] Run focused tests and verify they pass.

### Task 2: Session integration

**Files:**
- Modify: `src/astraship/session.py`
- Modify: `tests/test_session.py`

- [ ] Add a test proving the store contains an event before `events()` yields it.
- [ ] Add optional store injection and persist matching events before queue delivery.
- [ ] Add a persistence failure test and propagate the exception through the event stream.
- [ ] Run session tests.

### Task 3: Verification and commit

- [ ] Run pytest, ruff, format, mypy, and git diff checks.
- [ ] Commit Astraship changes.
