import json
import subprocess
import sys
from pathlib import Path


def test_help_is_available_without_starting_felix() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "astraship.cli", "--help"],
        cwd=Path(__file__).parents[1],
        env={"PYTHONPATH": "src"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Astraship Agent OS" in result.stdout


def test_kernel_check_reports_negotiated_felix() -> None:
    fixture = Path(__file__).parent / "fixtures" / "fake_felix.py"
    command = f'{sys.executable} "{fixture}" --mode normal'
    result = subprocess.run(
        [sys.executable, "-m", "astraship.cli", "kernel", "check"],
        cwd=Path(__file__).parents[1],
        env={"PYTHONPATH": "src", "ASTRASHIP_FELIX_COMMAND": command},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "Felix fake-felix 9.8.7 (protocol 1)"
    assert result.stderr == ""


def test_kernel_check_reports_failure_without_traceback() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "astraship.cli", "kernel", "check"],
        cwd=Path(__file__).parents[1],
        env={"PYTHONPATH": "src", "ASTRASHIP_FELIX_COMMAND": "missing-felix-server"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("astraship: ")
    assert "Traceback" not in result.stderr


def test_run_prints_mock_assistant_response() -> None:
    fixture = Path(__file__).parent / "fixtures" / "fake_felix.py"
    command = f'{sys.executable} "{fixture}" --mode session'
    result = subprocess.run(
        [sys.executable, "-m", "astraship.cli", "run", "--prompt", "hello"],
        cwd=Path(__file__).parents[1],
        env={"PYTHONPATH": "src", "ASTRASHIP_FELIX_COMMAND": command},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "mock: hello"
    assert result.stderr == ""


def test_run_with_store_persists_session_events(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "fake_felix.py"
    command = f'{sys.executable} "{fixture}" --mode session'
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "astraship.cli",
            "run",
            "--prompt",
            "hello",
            "--store",
            str(tmp_path),
        ],
        cwd=Path(__file__).parents[1],
        env={"PYTHONPATH": "src", "ASTRASHIP_FELIX_COMMAND": command},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    transcripts = sorted(tmp_path.glob("*.jsonl"))
    assert len(transcripts) == 1
    records = [json.loads(line) for line in transcripts[0].read_text().splitlines()]
    assert [record["type"] for record in records] == [
        "user/message",
        "future/event",
        "assistant/message",
        "turn/end",
    ]


def test_session_list_and_replay_show_persisted_transcript(tmp_path: Path) -> None:
    transcript = tmp_path / "s-1.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps(
                    {"sessionId": "s-1", "type": "user/message", "data": {"content": "hello"}}
                ),
                json.dumps(
                    {"sessionId": "s-1", "type": "assistant/message", "data": {"content": "world"}}
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = {"PYTHONPATH": "src"}

    listed = subprocess.run(
        [sys.executable, "-m", "astraship.cli", "session", "list", "--store", str(tmp_path)],
        cwd=Path(__file__).parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    replayed = subprocess.run(
        [
            sys.executable,
            "-m",
            "astraship.cli",
            "session",
            "replay",
            "s-1",
            "--store",
            str(tmp_path),
            "--type",
            "assistant/message",
        ],
        cwd=Path(__file__).parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert listed.returncode == 0
    assert listed.stdout == "s-1\n"
    assert replayed.returncode == 0
    assert json.loads(replayed.stdout) == [
        {"sessionId": "s-1", "type": "assistant/message", "data": {"content": "world"}}
    ]
