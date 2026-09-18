"""Durable local storage for Felix session event transcripts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from .errors import SessionPersistenceError

if TYPE_CHECKING:
    from .session import SessionEvent


class SessionStore(Protocol):
    """Storage contract required by the session event mirror."""

    def append(self, event: SessionEvent) -> None:
        """Durably append one session event."""


class JsonlSessionStore:
    """Append-only JSONL storage for platform-owned session event mirrors."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def append(self, event: SessionEvent) -> None:
        """Append one event and fsync it before returning."""

        _validate_session_id(event.session_id)
        if not event.type:
            raise SessionPersistenceError("session event type must be non-empty")
        if not isinstance(event.data, dict):
            raise SessionPersistenceError("session event data must be an object")
        record = {"sessionId": event.session_id, "type": event.type, "data": event.data}
        try:
            encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            self._root.mkdir(parents=True, exist_ok=True)
            with self._path(event.session_id).open("a", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        except (OSError, TypeError, ValueError) as exc:
            raise SessionPersistenceError(f"failed to append session event: {exc}") from exc

    def read(self, session_id: str) -> list[SessionEvent]:
        """Replay every event in one transcript, rejecting any corruption."""

        _validate_session_id(session_id)
        path = self._path(session_id)
        try:
            with path.open("r", encoding="utf-8") as stream:
                lines = list(stream)
        except FileNotFoundError:
            return []
        except (OSError, UnicodeError) as exc:
            raise SessionPersistenceError(f"failed to read session transcript: {exc}") from exc

        from .session import SessionEvent

        events: list[SessionEvent] = []
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                raise SessionPersistenceError(
                    f"blank line in session transcript at line {line_number}"
                )
            try:
                record: Any = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SessionPersistenceError(
                    f"malformed JSON in session transcript at line {line_number}"
                ) from exc
            if not isinstance(record, dict):
                raise SessionPersistenceError(
                    f"session record at line {line_number} must be an object"
                )
            record_session_id = record.get("sessionId")
            event_type = record.get("type")
            data = record.get("data")
            if record_session_id != session_id:
                raise SessionPersistenceError(
                    f"session ID mismatch in session transcript at line {line_number}"
                )
            if not isinstance(event_type, str) or not event_type:
                raise SessionPersistenceError(
                    f"session event type at line {line_number} must be non-empty"
                )
            if not isinstance(data, dict):
                raise SessionPersistenceError(
                    f"session event data object at line {line_number} must be a data object"
                )
            events.append(SessionEvent(session_id=session_id, type=event_type, data=data))
        return events

    def list_sessions(self) -> list[str]:
        """Return safe transcript IDs in deterministic order."""

        try:
            paths = self._root.glob("*.jsonl")
        except OSError as exc:
            raise SessionPersistenceError(f"failed to list session transcripts: {exc}") from exc
        return sorted(
            path.stem for path in paths if path.is_file() and _is_safe_session_id(path.stem)
        )

    def _path(self, session_id: str) -> Path:
        return self._root / f"{session_id}.jsonl"


def _validate_session_id(session_id: str) -> None:
    if not _is_safe_session_id(session_id):
        raise SessionPersistenceError("invalid session ID")


def _is_safe_session_id(session_id: str) -> bool:
    return (
        bool(session_id)
        and session_id not in {".", ".."}
        and "/" not in session_id
        and "\\" not in session_id
    )
