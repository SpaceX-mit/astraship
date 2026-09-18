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
