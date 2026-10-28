"""Typed errors (blueprint §13.7). The API maps them to ``{"error": {"code", "message"}}``."""


class MoiraError(Exception):
    """Base class. ``code`` is stable and machine-readable; ``status`` is the HTTP status."""

    code = "internal"
    status = 500

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.code)
        self.message = message or self.code


class ConfigError(MoiraError):
    code = "config"


class AiUnavailable(MoiraError):
    """The circuit breaker is open (or AI is switched off)."""

    code = "ai_unavailable"
    status = 503

    def __init__(self, message: str = "", retry_after_s: float = 120.0) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class AiBudgetExceeded(MoiraError):
    """A cap of §9.6 would be exceeded. ``lifetime`` means CAP_TOTAL_USD was reached."""

    code = "ai_budget_exceeded"
    status = 503

    def __init__(self, message: str = "", lifetime: bool = False) -> None:
        super().__init__(message)
        self.lifetime = lifetime


class ValidationFailed(MoiraError):
    code = "validation_failed"
    status = 422


class ReaderBlocked(MoiraError):
    code = "reader_blocked"
    status = 422


class SsrfBlocked(ReaderBlocked):
    code = "ssrf_blocked"


class NotFound(MoiraError):
    code = "not_found"
    status = 404


class Forbidden(MoiraError):
    code = "forbidden"
    status = 403


class AiTransient(MoiraError):
    """429, 5xx, timeout or reset: retry with backoff; counts toward the circuit breaker."""

    code = "ai_transient"
    status = 503

    def __init__(self, message: str = "", retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class AiInvalidOutput(MoiraError):
    """The output did not validate even after one repair attempt."""

    code = "ai_invalid_output"
    status = 502


class AiRejected(MoiraError):
    """400 from the API: no retry."""

    code = "ai_rejected"
    status = 502


class Reschedule(MoiraError):
    """A job asks to run again later without using an attempt (e.g. a precondition)."""

    code = "reschedule"

    def __init__(self, delay_s: float, message: str = "") -> None:
        super().__init__(message or f"reschedule in {delay_s}s")
        self.delay_s = delay_s
