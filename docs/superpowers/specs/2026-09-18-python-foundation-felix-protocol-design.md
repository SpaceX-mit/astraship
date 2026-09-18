# Python Foundation and Felix Protocol Design

## Scope

This sub-project converts Astraship from an inactive TypeScript scaffold to a Python 3.12 application foundation and establishes the process boundary to the Felix agent kernel. It delivers configuration, executable discovery, newline-delimited JSON-RPC 2.0 transport, initialization negotiation, deterministic shutdown, and protocol tests. Agent creation, turns, model providers, tools, and session persistence are later sub-projects.

Astraship owns platform policy and process management. Felix owns agent execution and kernel lifecycle. Neither repository imports implementation code from the other.

## Repository layout

Astraship uses one Python distribution with a `src/astraship/` package:

```text
src/astraship/
  __init__.py
  cli.py
  config.py
  errors.py
  kernel/
    __init__.py
    client.py
    protocol.py
tests/
  fixtures/fake_felix.py
  test_cli.py
  test_config.py
  test_kernel_client.py
  test_protocol.py
```

`pyproject.toml` is the single build, dependency, test, lint, and type-check authority. The project uses Python 3.12 or newer, Hatchling, pytest, pytest-asyncio, Ruff, and mypy. Runtime code uses only the Python standard library in this sub-project.

The obsolete TypeScript scaffold and Node-specific configuration are removed. Existing product documents remain until later documentation work replaces or corrects their TypeScript-era claims.

## Kernel command resolution

`KernelConfig` stores a command as an immutable tuple of argv elements. Resolution uses this strict order:

1. The explicit `kernel.command` value supplied by application configuration.
2. The `ASTRASHIP_FELIX_COMMAND` environment variable parsed with platform-appropriate shell tokenization.
3. `felix-server` resolved from `PATH`.

An empty explicit or environment command is invalid. If no executable resolves, Astraship raises `KernelNotFoundError` with the configuration key, environment variable, and expected executable name. Astraship does not download, build, or bundle Felix.

## Process and framing

Astraship starts Felix as a child process with stdin, stdout, and stderr pipes. Standard input and output carry UTF-8 JSON-RPC 2.0 messages, exactly one JSON object per line. Standard error carries Felix diagnostics and is never parsed as protocol data.

Only JSON objects are accepted. Blank lines may be ignored, while malformed JSON, arrays, invalid JSON-RPC versions, and structurally invalid messages terminate the connection with `KernelProtocolError`. Strict failure prevents a corrupted stream from being mistaken for valid kernel state.

Requests use monotonically increasing positive integer IDs within one process connection. Responses may arrive out of order. Notifications have a method and no ID. Server-initiated requests are rejected with JSON-RPC `-32601` until a later feature explicitly registers a handler.

## Initialization

Protocol version `1` is the only supported version in this sub-project. Immediately after process start, Astraship sends:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": 1,
    "clientInfo": {"name": "astraship", "version": "<package version>"},
    "capabilities": {}
  }
}
```

Felix returns its selected `protocolVersion`, `serverInfo` with `name` and `version`, and a string-keyed `capabilities` object. Astraship rejects any version other than `1` with `KernelVersionMismatchError`. The initialized result is immutable and exposed by the client.

Starting an already running client, making a request before initialization, or using a closed client raises `KernelStateError`. Initialization and ordinary requests have configurable timeouts. A timeout raises `KernelTimeoutError` and removes the pending request so a late response cannot satisfy another request.

## Lifecycle and failure semantics

`FelixClient` is an async context manager. `start()` resolves and launches the command, starts stdout and stderr reader tasks, performs initialization, and returns the negotiated result. If launch or initialization fails, it terminates and reaps the child before re-raising the stable Astraship error.

`close()` is idempotent. It closes stdin, gives the process a bounded graceful-exit interval, terminates it if still running, kills it only after a second bounded interval, awaits reader tasks, and rejects all pending requests. Unexpected EOF or child exit rejects every pending request with `KernelProcessError` including the exit code and captured stderr tail.

The client keeps a bounded stderr tail for diagnostics. It never writes kernel diagnostics to stdout, which remains available to future CLI protocols.

## CLI

The initial `astraship kernel check` command starts Felix, completes negotiation, prints one human-readable success line containing the Felix name, version, and protocol version, then closes it. Failures print a concise diagnostic to stderr and exit non-zero. This is the executable acceptance path for the first sub-project.

## Felix requirement

Felix needs a `felix-server` binary implementing the initialization and transport requirements above. Astraship does not implement that binary. The exact request is recorded in `felix/docs/design/api/0001-stdio-jsonrpc-bootstrap.md`, including conformance examples and acceptance commands for the Felix implementation session.

## Verification

Unit tests cover command precedence, parsing, message validation, version negotiation, out-of-order responses, remote errors, notifications, timeouts, malformed output, unexpected exit, stderr diagnostics, and idempotent close. Integration tests run `FelixClient` and the CLI against a deterministic Python fixture process using the same stdio framing expected from Felix.

The completion commands are:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv build
```
