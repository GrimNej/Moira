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
    code = "ai_unavailable"
    status = 503


class AiBudgetExceeded(MoiraError):
    code = "ai_budget_exceeded"
    status = 503


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
