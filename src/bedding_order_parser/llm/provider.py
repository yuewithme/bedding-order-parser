"""Provider protocol for optional advisory-only LLM implementations."""

from __future__ import annotations

from typing import Protocol

from bedding_order_parser.llm.contracts import (
    LLMConnectivityResult,
    LLMEnhancementRequest,
    LLMEnhancementResponse,
)


class LLMProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def is_configured(self) -> bool: ...

    def health_check(self) -> dict[str, object]: ...

    def check_connectivity(self) -> LLMConnectivityResult: ...

    def enhance_record(
        self, request: LLMEnhancementRequest
    ) -> LLMEnhancementResponse: ...

    def close(self) -> None: ...
