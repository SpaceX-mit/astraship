# Minimal Agent Loop Design

## Scope

This sub-project adds the first usable Astraship runtime path on top of the existing Felix stdio client. It creates a kernel-backed session, submits user prompts, receives durable session events, and exposes a CLI command that drives a deterministic mock-LMM fixture end to end. Felix remains the owner of agent execution, model calls, lifecycle, and durable facts; Astraship owns typed request/notification decoding and the user-facing facade.

The implementation deliberately stops before real providers, session persistence, tools, streaming token chunks, or retries. Those capabilities are later sub-projects and must extend the same event protocol rather than bypassing it.

## RPC contract

The Felix bootstrap protocol remains unchanged. After initialization, the runtime supports:

```text
session/new     {}                              -> {sessionId}
session/prompt  {sessionId, content}             -> {messageId}
session/close   {sessionId}                      -> {}
```

Felix publishes `session.event` notifications:

```json
{"sessionId":"s-1","event":{"type":"user/message","data":{"messageId":"m-1","content":"hello"}}}
{"sessionId":"s-1","event":{"type":"assistant/message","data":{"messageId":"m-2","content":"mock reply"}}}
{"sessionId":"s-1","event":{"type":"turn/end","data":{"messageId":"m-1"}}}
```

Every event has a non-empty session ID, a non-empty type, and an object data payload. Unknown event types are preserved as generic `SessionEvent` values. Notifications for another session are still delivered by the transport but are filtered out by that session's `events()` iterator.

`session/prompt` is an enqueue operation, not a completion operation. The returned `messageId` identifies the accepted user message. Consumers observe assistant output and turn settlement through events. A prompt submitted after `close()` or with empty/whitespace content raises a local `SessionStateError` and does not send an RPC request.

## Python API

`KernelSession.create(client)` requests a session and returns an immutable session ID. `prompt(content)` validates local input and returns `PromptReceipt(message_id)`. `events()` is an async iterator that continuously consumes client notifications and yields only events for the session. `close()` sends `session/close` once and is idempotent; it then marks the facade closed even if the remote call fails.

The facade does not buffer an unbounded event history. It owns only a small notification demultiplexer task and a bounded per-session queue configured by `event_queue_size`; overflow fails the session with `SessionOverflowError` rather than silently dropping model-visible facts.

## CLI

`astraship run --prompt TEXT` starts Felix, creates one session, submits the prompt, consumes events until `turn/end`, prints assistant message content, then closes the session and kernel. The fixture used by tests is a deterministic mock LLM: it replies with `mock: <prompt>`. A real Felix implementation may use a real model without changing this CLI path.

## Failure semantics

Kernel RPC and process errors are preserved as `Kernel*` exceptions. Invalid session payloads, missing IDs, invalid event shapes, queue overflow, and use-after-close are `Session*` exceptions. A session close always releases local tasks and attempts remote cleanup; the original remote error is re-raised after cleanup.

## Verification

Tests cover session creation, prompt validation, event filtering, assistant event consumption, turn completion, remote failures, malformed session results, queue overflow, idempotent close, and the CLI mock-LMM end-to-end path. The full Astraship suite and static checks remain green.
