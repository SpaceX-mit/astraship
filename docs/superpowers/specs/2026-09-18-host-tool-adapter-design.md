# Felix Host-Tool Adapter Design

## Scope

This milestone connects Astraship's existing `ToolRegistry` to Felix's reverse JSON-RPC request boundary defined in `felix/docs/design/api/0003-host-tool-execution.md`. Astraship advertises a snapshot of platform-owned tool schemas during initialization, accepts concurrent `tool/execute` server requests, and returns structured tool outcomes. Felix remains responsible for reasoning, call selection, and durable `tool/call` and `tool/result` events. No Felix implementation changes are part of this milestone.

## Components

`HostToolAdapter` owns the tool-specific wire contract. It receives a registry and base `ToolContext`, captures an immutable `hostTools` version 1 capability, strictly parses each `tool/execute` envelope, adds the trusted `sessionId` to a fresh context metadata mapping, executes one `ToolCall`, and serializes the resulting `ToolResult`. Model input can never select or replace the workspace. Invalid envelopes raise a dedicated invalid-params error before registry execution.

`FelixClient` remains the transport owner. Optional capabilities and server-request handlers are supplied at construction. Initialization sends a defensive snapshot. The stdout reader dispatches each server request in its own task so it can continue correlating responses and receiving overlapping calls. All client requests and reverse responses share one asynchronous write lock to preserve newline framing. Unknown methods return `-32601`, invalid handler input returns `-32602`, unexpected handler exceptions return `-32603`, and caller cancellation returns `-32800` when the connection remains writable.

`$/cancelRequest` is handled as a transport notification rather than delivered to application subscribers. A valid string or non-boolean integer request ID cancels its matching in-flight handler task; unknown or settled IDs are ignored. Invalid cancellation notifications are ignored because notifications have no response channel. Closing the client cancels and awaits all server-request tasks before transport tasks are discarded.

## Public API

`HostToolAdapter(registry, context)` exposes `capability() -> dict[str, JsonValue]` and `handle(request: ServerRequest) -> Awaitable[JsonValue]`. `HostToolAdapter.handlers()` maps `tool/execute` to `handle` for direct client wiring.

`FelixClient(config, *, capabilities=None, request_handlers=None)` accepts JSON-compatible initialization capabilities and a string-keyed mapping of asynchronous request handlers. Inputs are copied at construction so later caller mutation cannot change negotiation or routing. Existing construction remains backward compatible.

Tool responses contain `callId`, `name`, `isError`, `output`, and non-negative `elapsedMs`; failed results additionally contain `error.code` and `error.message`. `output` is always present and is `null` on failure.

## Validation and Failure Semantics

All five `tool/execute` fields are required: non-empty `sessionId`, `callId`, and `name`, plus object `arguments`. Boolean values are rejected where request IDs require integers. Envelope failures do not invoke the registry. Tool lookup, schema validation, timeouts, execution failures, and invalid outputs remain normal successful JSON-RPC results with `isError: true`.

The client validates supplied capability values as finite, acyclic JSON data before starting Felix. Handler results pass through the protocol encoder's strict JSON serialization. A transport write failure follows the existing connection-failure path rather than being converted into a tool result.

## Verification

Protocol tests cover result and data-bearing error encoders. Adapter tests cover immutable capability discovery, context injection, successful and failed tools, and malformed envelopes. Fixture integration tests cover negotiation, unknown methods, handler failures, overlapping out-of-order responses, cancellation, and closing with an in-flight handler. The full pytest, Ruff, mypy, build, and wheel smoke suites must pass. Real Felix integration remains pending implementation of requirement 0003 by the Felix session.
