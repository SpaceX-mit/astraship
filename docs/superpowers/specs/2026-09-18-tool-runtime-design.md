# Tool Runtime Design

## Scope

This sub-project adds Astraship's platform-owned tool registry and execution runtime. It follows the separation visible in deepseek-harness: model-facing schemas describe capabilities, while one guarded execution boundary owns lookup, argument validation, concurrency, timeout, error normalization, and observation. Felix remains responsible for agent reasoning and tool-call decisions; no Felix implementation changes are part of this sub-project.

The deliverable is independently usable from Python applications and ready for a later Felix protocol adapter. MCP discovery, human approval, sandbox enforcement, retries, background jobs, and kernel-driven tool calls remain separate sub-projects.

## Public model

`ToolDefinition` is an immutable value with a non-empty `name`, `description`, object-shaped `parameters` schema, async `execute(arguments, context)` callback, and `concurrency_safe` flag. Names match `^[a-z][a-z0-9_]{0,63}$`. The registry rejects duplicate names and invalid definitions at registration time.

`ToolContext` carries an immutable workspace root and optional string metadata. Paths and policy remain tool-specific; the registry does not silently grant filesystem access.

`ToolCall` contains a non-empty call ID, tool name, and object arguments. `ToolResult` contains the call ID, tool name, JSON-compatible output or a stable structured error, `is_error`, and elapsed milliseconds. Tool exceptions do not escape `execute`; programmer/configuration errors in registration do.

`ToolRegistry.schemas()` returns deterministic model-facing schemas sorted by tool name. `execute(call, context)` validates lookup and arguments, runs one tool, and always returns `ToolResult`. `execute_many(calls, context)` returns results in submission order. Calls for `concurrency_safe=True` tools may overlap up to `max_concurrency`; unsafe tools run exclusively and never overlap any other tool. Duplicate call IDs in one batch are rejected before execution.

## Schema validation

Astraship implements the JSON Schema subset needed by built-in tools without a runtime dependency:

- `type`: `object`, `array`, `string`, `integer`, `number`, `boolean`, or `null`
- object `properties`, `required`, and `additionalProperties` as a boolean
- array `items`, `minItems`, and `maxItems`
- string `minLength`, `maxLength`, `enum`, and `pattern`
- numeric `minimum` and `maximum`

Unsupported schema keywords fail registration instead of being ignored. Boolean values are not integers. Validation reports a stable JSON-path-like location such as `$.path` or `$.items[1]`; invalid arguments produce `invalid_arguments` results without calling the tool body.

## Execution semantics

The registry has positive `default_timeout` and `max_concurrency` settings. A call may specify no timeout override in this first API; each tool body is bounded by the registry default using `asyncio.timeout`. Timeout returns error code `timeout`; cancellation from the caller propagates rather than becoming a tool failure. Other tool exceptions return `execution_error` with a concise message and no traceback. Unknown names return `tool_not_found`.

Results must be JSON-compatible. Non-serializable, non-finite numeric, or cyclic output becomes `invalid_result`. The registry measures monotonic elapsed time for every outcome. An observer callback receives each final immutable result once; observer failures do not change the authoritative tool result.

## Built-in tools

The first built-in set operates only inside `ToolContext.workspace`:

- `read_file`: reads one UTF-8 text file with a configurable byte ceiling.
- `write_file`: writes UTF-8 text, creates parent directories, and optionally refuses overwrite.
- `list_files`: returns sorted relative file paths matching a glob, capped by a result limit.

Every requested path resolves beneath the workspace after symlink resolution. Absolute paths, `..` traversal, and symlinks escaping the workspace fail with a tool-visible error. These tools establish the capability seam; shell and HTTP tools are deferred because they require explicit policy and sandbox designs.

## Failure model

Stable result error codes are `tool_not_found`, `invalid_arguments`, `timeout`, `execution_error`, and `invalid_result`. Built-in capability failures use `execution_error` and a useful message. Registry misuse, such as duplicate registration, invalid schemas, invalid call IDs, or duplicate batch IDs, raises `ToolRegistrationError` or `ToolCallError` before work begins.

No tool invocation writes session events yet. A later Felix adapter will translate Felix tool requests into `ToolCall` and emit call/result events using a documented protocol. If Felix lacks that contract, Astraship will add a requirement document under `felix/docs/design/api/` before integration.

## Verification

Tests cover definition and schema rejection, schema discovery ordering, argument validation paths and edge cases, unknown tools, successful async execution, timeouts, exception normalization, invalid results, observer isolation, submission-order batching, concurrency limits, unsafe exclusivity, duplicate call IDs, and workspace containment for each built-in tool. Full pytest, Ruff, mypy, build, and wheel smoke tests must pass.
