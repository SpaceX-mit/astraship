"""Astraship platform configuration and Felix executable discovery."""

from __future__ import annotations

import os
import shlex
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .errors import KernelConfigError, KernelNotFoundError


@dataclass(frozen=True, slots=True)
class KernelConfig:
    """Configuration owned by the Felix process client."""

    command: tuple[str, ...] | None = None
    request_timeout: float = 30.0
    shutdown_timeout: float = 2.0
    stderr_tail_lines: int = 40

    def __post_init__(self) -> None:
        if self.request_timeout <= 0:
            raise KernelConfigError("request_timeout must be greater than zero")
        if self.shutdown_timeout <= 0:
            raise KernelConfigError("shutdown_timeout must be greater than zero")
        if self.stderr_tail_lines <= 0:
            raise KernelConfigError("stderr_tail_lines must be greater than zero")


def resolve_kernel_command(
    config: KernelConfig,
    *,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> tuple[str, ...]:
    """Resolve Felix using explicit config, environment, then PATH."""

    environment = os.environ if environ is None else environ
    if config.command is not None:
        if not config.command or not all(config.command):
            raise KernelConfigError("kernel.command cannot be empty")
        return config.command

    raw = environment.get("ASTRASHIP_FELIX_COMMAND")
    if raw is not None:
        if not raw.strip():
            raise KernelConfigError("ASTRASHIP_FELIX_COMMAND cannot be empty")
        try:
            command = tuple(shlex.split(raw, posix=(os.name != "nt")))
        except ValueError as exc:
            raise KernelConfigError(f"invalid ASTRASHIP_FELIX_COMMAND: {exc}") from exc
        if not command:
            raise KernelConfigError("ASTRASHIP_FELIX_COMMAND cannot be empty")
        return command

    executable = which("felix-server")
    if executable is not None:
        return (executable,)

    raise KernelNotFoundError(
        "Felix kernel not found; configure kernel.command, set "
        "ASTRASHIP_FELIX_COMMAND, or install felix-server on PATH"
    )
