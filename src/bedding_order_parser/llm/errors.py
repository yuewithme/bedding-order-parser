"""Safe, provider-neutral LLM error taxonomy."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class LLMErrorCode(StrEnum):
    DISABLED = "disabled"
    CONFIGURATION_ERROR = "configuration_error"
    AUTHENTICATION_ERROR = "authentication_error"
    PERMISSION_ERROR = "permission_error"
    MODEL_NOT_FOUND = "model_not_found"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    INVALID_REQUEST = "invalid_request"
    INVALID_RESPONSE = "invalid_response"
    STRUCTURED_OUTPUT_ERROR = "structured_output_error"
    PROVIDER_SERVER_ERROR = "provider_server_error"
    CANCELLED = "cancelled"
    UNKNOWN_PROVIDER_ERROR = "unknown_provider_error"


class LLMProviderError(RuntimeError):
    """An observable failure that never includes credentials or request bodies."""

    def __init__(
        self,
        code: LLMErrorCode,
        summary: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
        provider_error_type: str = "",
        request_id: str = "",
        attempts: int = 1,
        retry_after_seconds: float | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(summary)
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.provider_error_type = provider_error_type
        self.request_id = request_id
        self.attempts = attempts
        self.retry_after_seconds = retry_after_seconds
        self.diagnostics = diagnostics or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "summary": str(self),
            "retryable": self.retryable,
            "status_code": self.status_code,
            "provider_error_type": self.provider_error_type,
            "request_id": self.request_id,
            "attempts": self.attempts,
            "retry_after_seconds": self.retry_after_seconds,
            "diagnostics": self.diagnostics,
        }


class SchemaValidationError(ValueError):
    """Raised when a local value violates the strict advisory JSON Schema."""

    def __init__(
        self,
        message: str,
        *,
        path: str = "",
        diagnostic: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.path = path
        self.diagnostic = diagnostic or {}
