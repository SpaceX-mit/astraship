import json
from pathlib import Path

import pytest

from astraship.errors import SessionPersistenceError
from astraship.persistence import JsonlSessionStore
from astraship.session import SessionEvent


def event(session_id: str, event_type: str, content: str) -> SessionEvent:
    return SessionEvent(session_id=session_id, type=event_type, data={"content": content})


def test_append_and_reopen_recovers_events_in_order(tmp_path: Path) -> None:
    store = JsonlSessionStore(tmp_path)
    store.append(event("s-1", "user/message", "hello"))
    store.append(event("s-1", "assistant/message", "world"))

    reopened = JsonlSessionStore(tmp_path)
    assert reopened.read("s-1") == [
        event("s-1", "user/message", "hello"),
        event("s-1", "assistant/message", "world"),
    ]


def test_list_sessions_returns_sorted_session_ids(tmp_path: Path) -> None:
    store = JsonlSessionStore(tmp_path)
    store.append(event("s-2", "turn/end", ""))
    store.append(event("s-1", "turn/end", ""))

    assert store.list_sessions() == ["s-1", "s-2"]


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("{not json}\n", "malformed JSON"),
        ("\n", "blank line"),
        ('{"sessionId":"other","type":"x","data":{}}\n', "session ID"),
        ('{"sessionId":"s-1","type":"x","data":[] }\n', "data object"),
    ],
)
def test_read_rejects_corrupt_transcript(tmp_path: Path, contents: str, message: str) -> None:
    path = tmp_path / "s-1.jsonl"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(SessionPersistenceError, match=message):
        JsonlSessionStore(tmp_path).read("s-1")


@pytest.mark.parametrize("session_id", ["", ".", "..", "a/b", "a\\b", "../escape"])
def test_session_ids_cannot_escape_store_root(tmp_path: Path, session_id: str) -> None:
    store = JsonlSessionStore(tmp_path)

    with pytest.raises(SessionPersistenceError, match="session ID"):
        store.read(session_id)


def test_append_writes_jsonl_record(tmp_path: Path) -> None:
    store = JsonlSessionStore(tmp_path)
    store.append(event("s-1", "assistant/message", "hello"))

    record = json.loads((tmp_path / "s-1.jsonl").read_text(encoding="utf-8"))
    assert record == {
        "sessionId": "s-1",
        "type": "assistant/message",
        "data": {"content": "hello"},
    }


def test_query_filters_and_paginates_events(tmp_path: Path) -> None:
    store = JsonlSessionStore(tmp_path)
    store.append(event("s-1", "user/message", "one"))
    store.append(event("s-1", "assistant/message", "two"))
    store.append(event("s-1", "assistant/message", "three"))

    assert store.query("s-1", event_type="assistant/message") == [
        event("s-1", "assistant/message", "two"),
        event("s-1", "assistant/message", "three"),
    ]
    assert store.query("s-1", offset=1, limit=1) == [event("s-1", "assistant/message", "two")]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"event_type": ""},
        {"offset": -1},
        {"offset": True},
        {"limit": 0},
        {"limit": True},
    ],
)
def test_query_rejects_invalid_filters(tmp_path: Path, kwargs: dict[str, object]) -> None:
    with pytest.raises(SessionPersistenceError):
        JsonlSessionStore(tmp_path).query("s-1", **kwargs)  # type: ignore[arg-type]
