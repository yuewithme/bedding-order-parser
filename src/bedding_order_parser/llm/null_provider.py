"""Deterministic offline provider for disabled or unsupported configuration."""

from __future__ import annotations

from bedding_order_parser.llm.contracts import (
    LLMConnectivityResult,
    LLMEnhancementRequest,
    LLMEnhancementResponse,
    MaterialAssessment,
)


class NullLLMProvider:
    """A provider that never performs network access."""

    @property
    def provider_name(self) -> str:
        return "null"

    @property
    def model_name(self) -> str:
        return ""

    def is_configured(self) -> bool:
        return False

    def health_check(self) -> dict[str, object]:
        return {
            "status": "not_configured",
            "configured": False,
            "network_check_performed": False,
            "provider": self.provider_name,
            "model_configured": False,
            "api_key_configured": False,
        }

    def check_connectivity(self) -> LLMConnectivityResult:
        return LLMConnectivityResult(
            provider=self.provider_name,
            model=self.model_name,
            request_id="",
            status="not_configured",
            finish_status="not_called",
            text="",
        )

    def enhance_record(
        self, request: LLMEnhancementRequest
    ) -> LLMEnhancementResponse:
        return LLMEnhancementResponse(
            provider=self.provider_name,
            model=self.model_name,
            request_id="",
            source_record_id=request.source_record_id,
            status="not_configured",
            finish_status="not_called",
            action="insufficient_evidence",
            confidence=0.0,
            material_assessment=MaterialAssessment(
                status="insufficient_evidence",
                suggested_material_code="",
                reason="No LLM provider is configured.",
            ),
            reasoning_summary="AI增强未配置，保留确定性结果。",
            warnings=("继续使用确定性解析和人工复核。",),
            attempt_count=0,
        )

    def close(self) -> None:
        return
