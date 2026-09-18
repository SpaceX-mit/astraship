"""Stable errors exposed by the Astraship platform boundary."""


class AstrashipError(Exception):
    """Base class for expected Astraship failures."""


class KernelConfigError(AstrashipError):
    """Kernel configuration is invalid."""


class KernelNotFoundError(AstrashipError):
    """The configured Felix executable cannot be resolved."""


class KernelProtocolError(AstrashipError):
    """Felix emitted a message outside the supported wire protocol."""


class KernelVersionMismatchError(KernelProtocolError):
    """Felix and Astraship do not share a supported protocol version."""


class KernelStateError(AstrashipError):
    """An operation was attempted in an invalid client state."""


class KernelTimeoutError(AstrashipError):
    """A kernel operation exceeded its configured timeout."""


class KernelProcessError(AstrashipError):
    """The Felix process exited or its transport failed unexpectedly."""


class KernelRemoteError(KernelProtocolError):
    """Felix rejected a request with a JSON-RPC error response."""

    def __init__(self, code: int, message: str, data: object = None) -> None:
        super().__init__(f"Felix JSON-RPC error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class SessionStateError(AstrashipError):
    """A session operation is invalid for its current state."""


class SessionOverflowError(AstrashipError):
    """A session event queue filled before its consumer drained it."""
