"""Environment-backed LLM settings without secret persistence."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlsplit


TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
VOLCENGINE_ARK_PROVIDER = "volcengine_ark"
SUPPORTED_PROVIDERS = frozenset({VOLCENGINE_ARK_PROVIDER})
DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 2


@dataclass(frozen=True, repr=False)
class LLMSettings:
    """Runtime settings; api_key and validation details stay private."""

    enabled: bool = False
    provider: str = ""
    model: str = ""
    base_url: str = DEFAULT_ARK_BASE_URL
    api_key: str = ""
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    parsing_errors: tuple[str, ...] = field(default=(), repr=False)

    def __repr__(self) -> str:
        masked_key = "***" if self.api_key else ""
        return (
            "LLMSettings("
            f"enabled={self.enabled!r}, "
            f"provider={self.provider!r}, "
            f"model={self.model!r}, "
            f"base_url={self.base_url!r}, "
            f"api_key={masked_key!r}, "
            f"timeout_seconds={self.timeout_seconds!r}, "
            f"max_retries={self.max_retries!r}"
            ")"
        )

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "LLMSettings":
        values = environment if environment is not None else os.environ
        timeout, timeout_error = _parse_timeout(
            values.get("LLM_TIMEOUT_SECONDS", "")
        )
        retries, retries_error = _parse_retries(
            values.get("LLM_MAX_RETRIES", "")
        )
        errors = tuple(
            message
            for message in (timeout_error, retries_error)
            if message
        )
        return cls(
            enabled=values.get("LLM_ENABLED", "").strip().lower()
            in TRUE_VALUES,
            provider=values.get("LLM_PROVIDER", "").strip().lower(),
            model=values.get("LLM_MODEL", "").strip(),
            base_url=(
                values.get("LLM_BASE_URL", "").strip()
                or DEFAULT_ARK_BASE_URL
            ),
            api_key=values.get("ARK_API_KEY", "").strip(),
            timeout_seconds=timeout,
            max_retries=retries,
            parsing_errors=errors,
        )

    @property
    def provider_supported(self) -> bool:
        return self.provider in SUPPORTED_PROVIDERS

    @property
    def api_key_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def model_configured(self) -> bool:
        return bool(self.model)

    def configuration_errors(self) -> tuple[str, ...]:
        errors = list(self.parsing_errors)
        parsed = urlsplit(self.base_url)
        if not parsed.scheme or not parsed.netloc:
            errors.append("LLM_BASE_URL must be an absolute URL.")
        elif parsed.scheme != "https" and parsed.hostname not in {
            "127.0.0.1",
            "localhost",
        }:
            errors.append("LLM_BASE_URL must use HTTPS.")
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            errors.append(
                "LLM_BASE_URL cannot contain credentials, query or fragment."
            )
        return tuple(errors)

    def configuration_status(self) -> str:
        if not self.enabled:
            return "disabled"
        if self.configuration_errors():
            return "configuration_error"
        if not self.provider:
            return "provider_not_configured"
        if not self.provider_supported:
            return "unsupported_provider"
        if not self.api_key_configured:
            return "api_key_missing"
        if not self.model_configured:
            return "model_missing"
        return "ready"

    def is_ready(self) -> bool:
        return self.configuration_status() == "ready"

    def public_capabilities(self) -> dict[str, object]:
        status = self.configuration_status()
        return {
            "enabled": self.enabled,
            "configured": status == "ready",
            "status": status,
            "provider": self.provider or None,
            "provider_supported": self.provider_supported,
            "model": self.model or None,
            "model_configured": self.model_configured,
            "api_key_configured": self.api_key_configured,
            "real_call_allowed": status == "ready",
            "business_integration": False,
            "mode": "provider_foundation_only",
        }


def _parse_timeout(value: str) -> tuple[float, str]:
    if not value.strip():
        return DEFAULT_TIMEOUT_SECONDS, ""
    try:
        parsed = float(value)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS, (
            "LLM_TIMEOUT_SECONDS must be a number."
        )
    if not 0 < parsed <= 600:
        return DEFAULT_TIMEOUT_SECONDS, (
            "LLM_TIMEOUT_SECONDS must be between 0 and 600."
        )
    return parsed, ""


def _parse_retries(value: str) -> tuple[int, str]:
    if not value.strip():
        return DEFAULT_MAX_RETRIES, ""
    try:
        parsed = int(value)
    except ValueError:
        return DEFAULT_MAX_RETRIES, (
            "LLM_MAX_RETRIES must be an integer."
        )
    if not 0 <= parsed <= 5:
        return DEFAULT_MAX_RETRIES, (
            "LLM_MAX_RETRIES must be between 0 and 5."
        )
    return parsed, ""
