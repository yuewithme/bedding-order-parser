"""Provider-independent orchestration for optional LLM enhancement."""

from __future__ import annotations

from bedding_order_parser.llm.contracts import (
    LLMConnectivityResult,
    LLMEnhancementRequest,
    LLMEnhancementResponse,
)
from bedding_order_parser.llm.errors import LLMErrorCode, LLMProviderError
from bedding_order_parser.llm.factory import build_provider
from bedding_order_parser.llm.provider import LLMProvider
from bedding_order_parser.llm.settings import LLMSettings
from bedding_order_parser.llm.transport import JSONTransport


class LLMService:
    """Expose safe capabilities while keeping AI outside formal results."""

    def __init__(
        self,
        settings: LLMSettings | None = None,
        provider: LLMProvider | None = None,
        *,
        transport: JSONTransport | None = None,
    ) -> None:
        self.settings = settings or LLMSettings.from_environment()
        self.provider = provider or build_provider(
            self.settings, transport=transport
        )

    def capabilities(self) -> dict[str, object]:
        return self.settings.public_capabilities()

    def health_check(self) -> dict[str, object]:
        return self.provider.health_check()

    def check_connectivity(self) -> LLMConnectivityResult:
        self._require_ready()
        return self.provider.check_connectivity()

    def enhance_record(
        self, request: LLMEnhancementRequest
    ) -> LLMEnhancementResponse:
        self._require_ready()
        return self.provider.enhance_record(request)

    def _require_ready(self) -> None:
        status = self.settings.configuration_status()
        if status != "ready":
            code = (
                LLMErrorCode.DISABLED
                if status == "disabled"
                else LLMErrorCode.CONFIGURATION_ERROR
            )
            raise LLMProviderError(
                code,
                f"LLM enhancement is unavailable: {status}.",
                provider_error_type=status,
                attempts=0,
            )

    def close(self) -> None:
        self.provider.close()
