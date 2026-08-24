from __future__ import annotations

import json

import pytest

from bedding_order_parser.llm.contracts import (
    LLMEnhancementRequest,
)
from bedding_order_parser.llm.errors import LLMErrorCode, LLMProviderError
from bedding_order_parser.llm.null_provider import NullLLMProvider
from bedding_order_parser.llm.service import LLMService
from bedding_order_parser.llm.settings import LLMSettings


def request(reason: str = "user_requested") -> LLMEnhancementRequest:
    return LLMEnhancementRequest(
        source_record_id="PI.xlsx|PI|2",
        source_file="PI.xlsx",
        sheet_name="PI",
        source_row="2",
        raw_evidence={"A2": "Duvet Cover"},
        parsed_record={"物料名称": "测试客户 被套"},
        parse_diagnostics={},
        dictionary_validation={},
        top_candidates=[],
        enhancement_reason=reason,
    )


def test_request_contract_rejects_unapproved_reason() -> None:
    with pytest.raises(ValueError, match="enhancement_reason"):
        request("automatic_low_score")


def test_request_contract_requires_source_record_id() -> None:
    with pytest.raises(ValueError, match="source_record_id"):
        LLMEnhancementRequest(
            source_record_id="",
            source_file="PI.xlsx",
            sheet_name="PI",
            source_row="2",
            raw_evidence={},
            parsed_record={},
            parse_diagnostics={},
            dictionary_validation={},
            top_candidates=[],
            enhancement_reason="user_requested",
        )


def test_null_provider_is_offline_and_advisory_only() -> None:
    provider = NullLLMProvider()

    assert provider.is_configured() is False
    assert provider.health_check()["network_check_performed"] is False
    payload = provider.enhance_record(request()).to_dict()
    assert payload["status"] == "not_configured"
    assert payload["action"] == "insufficient_evidence"
    assert payload["source_record_id"] == "PI.xlsx|PI|2"
    assert payload["advisory_only"] is True
    assert payload["material_assessment"]["suggested_material_code"] == ""
    assert "formal_result" not in payload


def test_llm_service_disabled_never_calls_injected_provider() -> None:
    class ExplodingProvider:
        provider_name = "fake"
        model_name = "fake"

        def is_configured(self) -> bool:
            return True

        def enhance_record(self, _request):
            raise AssertionError("provider must not be called")

        def health_check(self):
            return {}

        def close(self) -> None:
            return

    service = LLMService(
        settings=LLMSettings(enabled=False, api_key="secret"),
        provider=ExplodingProvider(),
    )

    with pytest.raises(LLMProviderError) as caught:
        service.enhance_record(request())

    assert caught.value.code == LLMErrorCode.DISABLED


def test_capabilities_and_repr_never_expose_api_key() -> None:
    settings = LLMSettings(
        enabled=True,
        provider="volcengine_ark",
        model="test-model",
        api_key="super-secret-key",
    )
    public = settings.public_capabilities()

    assert "super-secret-key" not in repr(settings)
    assert "super-secret-key" not in json.dumps(public)
    assert "api_key" not in public
    assert public["api_key_configured"] is True
    assert public["business_integration"] is False
