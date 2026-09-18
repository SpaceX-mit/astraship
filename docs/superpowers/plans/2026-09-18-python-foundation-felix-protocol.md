# Python Foundation and Felix Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Astraship's Python project foundation and a production-shaped async client for the Felix version-1 stdio JSON-RPC bootstrap protocol.

**Architecture:** A standard-library async transport launches an externally configured Felix executable, validates newline-delimited JSON-RPC frames, correlates requests, and owns deterministic process shutdown. Small immutable protocol and configuration types isolate wire validation and executable discovery from process I/O; a fake child process proves the real transport without requiring the pending Felix server implementation.

**Tech Stack:** Python 3.12+, asyncio, dataclasses, argparse, Hatchling, pytest, pytest-asyncio, Ruff, mypy, uv

**Spec:** `docs/superpowers/specs/2026-09-18-python-foundation-felix-protocol-design.md`

## Global Constraints

- Python 3.12 or newer.
- Runtime code in this sub-project uses only the Python standard library.
- Felix is an external process; Astraship never downloads, builds, bundles, or imports it.
- stdin/stdout carry one UTF-8 JSON-RPC 2.0 object per line; stderr carries diagnostics only.
- Protocol version `1` is the only accepted version.
- New behavior is developed test-first and every completion command must pass.

---

### Task 1: Python distribution and command resolution

**Files:**
- Create: `pyproject.toml`
- Create: `src/astraship/__init__.py`
- Create: `src/astraship/errors.py`
- Create: `src/astraship/config.py`
- Create: `tests/test_config.py`
- Modify: `.gitignore`
- Remove: `package.json`, `tsconfig.json`, `jest.config.js`, `.eslintrc.js`, `.prettierrc`, `src/types/index.ts`, `src/utils/helpers.ts`

**Interfaces:**
- Produces: `KernelConfig(command: tuple[str, ...] | None, request_timeout: float, shutdown_timeout: float, stderr_tail_lines: int)`.
- Produces: `resolve_kernel_command(config, environ=None, which=shutil.which) -> tuple[str, ...]`.
- Produces: stable errors rooted at `AstrashipError`.

- [ ] Write tests proving explicit command precedence, environment parsing, PATH fallback, invalid empty commands, and missing executable diagnostics.
- [ ] Run `uv run pytest tests/test_config.py -v` and verify collection fails because `astraship.config` is absent.
- [ ] Add the Python build configuration, error classes, immutable configuration, and command resolver.
- [ ] Remove the obsolete TypeScript scaffold and extend ignores for Python artifacts.
- [ ] Run `uv run pytest tests/test_config.py -v` and verify all configuration tests pass.
- [ ] Run `uv run ruff check src tests` and `uv run mypy src tests`.

### Task 2: Typed protocol validation

**Files:**
- Create: `src/astraship/kernel/__init__.py`
- Create: `src/astraship/kernel/protocol.py`
- Create: `tests/test_protocol.py`

**Interfaces:**
- Produces: `PROTOCOL_VERSION: Final[int] = 1`.
- Produces: immutable `ServerInfo`, `InitializeResult`, `Notification`, `Response`, and `RemoteError` values.
- Produces: `encode_request()`, `encode_error_response()`, and `decode_message()`.

- [ ] Write parameterized tests for valid results, remote errors, notifications, server requests, malformed JSON, non-object JSON, wrong JSON-RPC versions, and structurally ambiguous messages.
- [ ] Run `uv run pytest tests/test_protocol.py -v` and verify it fails because `astraship.kernel.protocol` is absent.
- [ ] Implement strict JSON parsing and structural classification without accepting booleans as integer request IDs.
- [ ] Run `uv run pytest tests/test_protocol.py -v` and verify all protocol tests pass.
- [ ] Run the configuration and protocol tests together to detect interface regressions.

### Task 3: Async Felix process client

**Files:**
- Create: `src/astraship/kernel/client.py`
- Create: `tests/fixtures/fake_felix.py`
- Create: `tests/test_kernel_client.py`

**Interfaces:**
- Consumes: `KernelConfig`, `resolve_kernel_command()`, protocol message types and codecs.
- Produces: `FelixClient(config=KernelConfig())` async context manager.
- Produces: `start() -> InitializeResult`, `request(method, params) -> object`, `next_notification() -> Notification`, `close() -> None`, and read-only `initialize_result`.

- [ ] Build a configurable fake Felix fixture and tests for initialization, out-of-order responses, remote errors, notifications, request timeout, malformed output, version mismatch, unexpected exit with stderr, state errors, and idempotent close.
- [ ] Run `uv run pytest tests/test_kernel_client.py -v` and verify it fails because `FelixClient` is absent.
- [ ] Implement process launch, read loops, pending-request correlation, initialization, bounded stderr capture, stable failure conversion, and deterministic shutdown.
- [ ] Run `uv run pytest tests/test_kernel_client.py -v` and verify all process-client tests pass without leaked-task warnings.
- [ ] Run all tests and refactor duplicated lifecycle cleanup while keeping them green.

### Task 4: Kernel check CLI

**Files:**
- Create: `src/astraship/cli.py`
- Create: `tests/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `FelixClient` and `KernelConfig`.
- Produces: console entry point `astraship` and command `astraship kernel check`.

- [ ] Write subprocess tests proving the command prints negotiated server information on success and a concise stderr diagnostic with non-zero status on failure.
- [ ] Run `uv run pytest tests/test_cli.py -v` and verify it fails because the CLI module is absent.
- [ ] Implement an argparse entry point whose async command always closes the kernel client.
- [ ] Replace TypeScript installation and usage snippets in the README with the Python/uv workflow and kernel-check command.
- [ ] Run the CLI tests and then the complete test suite.

### Task 5: Quality and packaging verification

**Files:**
- Modify only files implicated by verification failures.

**Interfaces:**
- Consumes all prior task outputs.
- Produces a buildable wheel and source distribution with the `astraship` console script.

- [ ] Run `uv run pytest` and fix only demonstrated failures with a regression test first.
- [ ] Run `uv run ruff check .`.
- [ ] Run `uv run ruff format --check .`.
- [ ] Run `uv run mypy src tests`.
- [ ] Run `uv build`, inspect the artifact listing, install the wheel into a temporary uv environment, and run `astraship --help`.
- [ ] Run `git diff --check` and inspect both Astraship and Felix repository status before committing each repository's scoped changes.
