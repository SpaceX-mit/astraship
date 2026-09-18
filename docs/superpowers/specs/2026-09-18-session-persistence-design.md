# Session Persistence Design

## Scope

Astraship mirrors Felix `session.event` notifications into an append-only JSONL store. The store is platform-owned and independent of Felix's in-memory Session; it provides recovery and inspection without changing the kernel protocol. The first implementation is local filesystem storage. SQLite indexing, compression, migration, and remote stores remain later capabilities.

## Store contract

`JsonlSessionStore(root)` stores one file per opaque session ID at `<root>/<session-id>.jsonl`. A session ID must be non-empty and contain no path separator, `.` or `..` component. Each line is one UTF-8 JSON object:

```json
{"sessionId":"s-1","type":"assistant/message","data":{"content":"hello"}}
```

`append(event)` creates the directory and file if needed, writes one newline-terminated record, flushes, and calls `fsync` before returning. A write failure raises `SessionPersistenceError`. The store never rewrites or truncates an existing file.

`read(session_id)` returns events in file order. Blank lines are invalid. Invalid UTF-8, malformed JSON, non-object records, mismatched session IDs, empty types, and non-object data raise `SessionPersistenceError`; callers never receive a partial successful result. `list_sessions()` returns sorted IDs for valid filenames only.

## KernelSession integration

`KernelSession.create(..., store=None)` accepts an optional store. The demultiplexer persists a matching event before putting it on the consumer queue. If persistence fails, the event stream receives the persistence exception and stops; the kernel remains owned by the caller and can be closed normally. Existing sessions without a store retain current behavior.

`KernelSession.replay(session_id)` is a pure store operation returning the stored tuple; it does not create or reconnect a Felix runtime session. This distinction prevents a local transcript from being mistaken for a live kernel handle.

## Verification

Tests cover append/reopen recovery, ordering, fsync-backed writes through a real temporary directory, malformed records, path traversal, mismatched IDs, sorted listing, and KernelSession persistence before delivery. Existing tests and static checks remain green.
