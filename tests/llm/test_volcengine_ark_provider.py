from __future__ import annotations

import json
from collections.abc import Iterable

import pytest

from bedding_order_parser.llm.contracts import LLMEnhancementRequest
from bedding_order_parser.llm.errors import LLMErrorCode, LLMProviderError
from bedding_order_parser.llm.service import LLMService
from bedding_order_parser.llm.settings import LLMSettings
from bedding_order_parser.llm.transport import (
    JSONHTTPRequest,
    JSONHTTPResponse,
    TransportConnectionError,
    TransportTimeout,
)
from bedding_order_parser.llm.volcengine_ark import (
    ADVISORY_FUNCTION_NAME,
    CONNECTIVITY_MAX_OUTPUT_TOKENS,
    VolcengineArkProvider,
)


SECRET = "ark-test-secret-never-log"


class FakeTransport:
    def __init__(
        self,
        results: Iterable[JSONHTTPResponse | Exception],
    ) -> None:
        self.results = list(results)
        self.requests: list[JSONHTTPRequest] = []

    def send(self, request: JSONHTTPRequest) -> JSONHTTPResponse:
        self.requests.append(request)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def settings(*, retries: int = 2) -> LLMSettings:
    return LLMSettings(
        enabled=True,
        provider="volcengine_ark",
        model="doubao-test-model",
        base_url="https://ark.test/api/v3",
        api_key=SECRET,
        timeout_seconds=9.0,
        max_retries=retries,
    )


def request() -> LLMEnhancementRequest:
    return LLMEnhancementRequest(
        source_record_id="PI.xlsx|PI|2",
        source_file="PI.xlsx",
        sheet_name="PI",
        source_row="2",
        raw_evidence={"B2": "White Duvet Cover"},
        parsed_record={"颜色": ""},
        parse_diagnostics={"颜色": "source_not_provided"},
        dictionary_validation={},
        top_candidates=[{"material_code": "F0001"}],
        enhancement_reason="user_requested",
    )


def advisory(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_record_id": "PI.xlsx|PI|2",
        "action": "suggest_review",
        "confidence": 0.8,
        "suggested_fields": [
            {
                "field_name": "颜色",
                "original_value": "",
                "suggested_value": "白色",
                "reason": "原始证据中明确出现White，可作为颜色判断依据。",
                "evidence_references": ["PI!B2"],
            }
        ],
        "material_assessment": {
            "status": "suggested",
            "suggested_material_code": "F0001",
            "reason": "候选F0001仅作为人工复核建议，不自动确认。",
        },
        "reasoning_summary": "源文本明确包含 White。",
        "warnings": ["物料编码必须人工确认。"],
        "evidence_references": ["PI!B2"],
    }
    payload.update(overrides)
    return payload


def ark_response(
    *,
    status_code: int = 200,
    advisory_payload: dict[str, object] | None = None,
    body: bytes | None = None,
    response_status: str = "completed",
    headers: dict[str, str] | None = None,
    error: dict[str, object] | None = None,
) -> JSONHTTPResponse:
    if body is None:
        payload: dict[str, object] = {
            "id": "resp_test_123",
            "model": "doubao-test-model",
            "status": response_status,
            "output": [
                {
                    "type": "function_call",
                    "name": ADVISORY_FUNCTION_NAME,
                    "arguments": json.dumps(
                        advisory_payload or advisory(),
                        ensure_ascii=False,
                    ),
                    "status": "completed",
                }
            ],
            "usage": {
                "input_tokens": 101,
                "output_tokens": 22,
                "total_tokens": 123,
            },
        }
        if error is not None:
            payload["error"] = error
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return JSONHTTPResponse(
        status_code=status_code,
        headers=headers or {"x-request-id": "header-request-id"},
        body=body,
        elapsed_ms=3,
    )


def connectivity_response(
    *,
    status_code: int = 200,
    body: bytes | None = None,
) -> JSONHTTPResponse:
    if body is None:
        body = json.dumps(
            {
                "id": "resp_connect_123",
                "model": "doubao-test-model",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "连接成功",
                            }
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 8,
                    "output_tokens": 3,
                    "total_tokens": 11,
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
    return JSONHTTPResponse(
        status_code=status_code,
        headers={"x-request-id": "header-connect-id"},
        body=body,
        elapsed_ms=3,
    )


def provider(
    transport: FakeTransport,
    *,
    retries: int = 2,
    sleeps: list[float] | None = None,
) -> VolcengineArkProvider:
    sink = sleeps if sleeps is not None else []
    return VolcengineArkProvider(
        settings(retries=retries),
        transport=transport,
        sleep=sink.append,
    )


def test_connectivity_uses_minimal_non_tool_request() -> None:
    transport = FakeTransport([connectivity_response()])

    result = provider(transport).check_connectivity()

    assert result.text == "连接成功"
    assert result.request_id == "resp_connect_123"
    assert result.usage.total_tokens == 11
    assert result.attempt_count == 1
    body = json.loads(transport.requests[0].body)
    assert body["store"] is False
    assert body["max_output_tokens"] == CONNECTIVITY_MAX_OUTPUT_TOKENS
    assert "tools" not in body
    assert "tool_choice" not in body


def test_connectivity_supports_top_level_output_text() -> None:
    payload = {
        "id": "resp_direct_text",
        "model": "doubao-test-model",
        "status": "completed",
        "output_text": "连接成功",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    transport = FakeTransport(
        [
            connectivity_response(
                body=json.dumps(payload, ensure_ascii=False).encode("utf-8")
            )
        ]
    )

    result = provider(transport).check_connectivity()

    assert result.text == "连接成功"
    assert result.usage.total_tokens == 2


def test_connectivity_401_is_not_retried() -> None:
    transport = FakeTransport(
        [connectivity_response(status_code=401, body=b"unauthorized")]
    )

    with pytest.raises(LLMProviderError) as caught:
        provider(transport).check_connectivity()

    assert caught.value.code == LLMErrorCode.AUTHENTICATION_ERROR
    assert caught.value.attempts == 1
    assert len(transport.requests) == 1


def test_connectivity_429_has_one_bounded_retry() -> None:
    rate_limit = JSONHTTPResponse(
        status_code=429,
        headers={"retry-after": "0"},
        body=b'{"error":{"type":"rate_limit_error"}}',
        elapsed_ms=1,
    )
    transport = FakeTransport([rate_limit, connectivity_response()])
    sleeps: list[float] = []

    result = provider(
        transport, retries=1, sleeps=sleeps
    ).check_connectivity()

    assert result.attempt_count == 2
    assert len(transport.requests) == 2
    assert sleeps == [0.0]


def test_successful_function_call_builds_strict_advisory() -> None:
    transport = FakeTransport([ark_response()])
    result = provider(transport).enhance_record(request())
    payload = result.to_dict()

    assert payload["provider"] == "volcengine_ark"
    assert payload["model"] == "doubao-test-model"
    assert payload["request_id"] == "resp_test_123"
    assert payload["source_record_id"] == "PI.xlsx|PI|2"
    assert payload["usage"] == {
        "input_tokens": 101,
        "output_tokens": 22,
        "total_tokens": 123,
    }
    assert payload["attempt_count"] == 1
    assert payload["advisory_only"] is True
    assert payload["material_assessment"]["status"] == "suggested"

    sent = transport.requests[0]
    request_body = json.loads(sent.body)
    assert sent.url == "https://ark.test/api/v3/responses"
    assert sent.timeout_seconds == 9.0
    assert sent.headers["Authorization"] == f"Bearer {SECRET}"
    assert SECRET not in sent.url
    assert SECRET not in repr(sent)
    assert request_body["store"] is False
    assert request_body["model"] == "doubao-test-model"
    assert request_body["tools"][0]["strict"] is True
    assert request_body["tools"][0]["parameters"][
        "additionalProperties"
    ] is False
    assert request_body["tool_choice"]["name"] == ADVISORY_FUNCTION_NAME
    developer_prompt = request_body["input"][0]["content"][0]["text"]
    assert "所有面向业务人员的动态说明必须使用简体中文" in developer_prompt
    assert "PI原始英文证据" in developer_prompt
    assert "保持原文" in developer_prompt
    assert "不是准确率或正确概率" in developer_prompt
    assert "不得仅凭分数判断候选正确或错误" in developer_prompt
    source_payload = json.loads(
        request_body["input"][1]["content"][0]["text"]
    )
    assert source_payload["source_record_id"] == "PI.xlsx|PI|2"
    assert source_payload["raw_evidence"]["B2"] == "White Duvet Cover"


def test_output_text_json_is_supported_as_structured_fallback() -> None:
    payload = {
        "id": "resp_text",
        "model": "doubao-test-model",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(advisory(), ensure_ascii=False),
                    }
                ],
            }
        ],
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }
    transport = FakeTransport(
        [
            ark_response(
                body=json.dumps(payload, ensure_ascii=False).encode("utf-8")
            )
        ]
    )

    result = provider(transport).enhance_record(request())

    assert result.request_id == "resp_text"
    assert result.usage.total_tokens == 3


def test_top_level_output_text_json_is_supported() -> None:
    payload = {
        "id": "resp_direct_text",
        "model": "doubao-test-model",
        "status": "completed",
        "output_text": json.dumps(advisory(), ensure_ascii=False),
        "usage": {"input_tokens": "10", "output_tokens": "5"},
    }
    transport = FakeTransport(
        [
            ark_response(
                body=json.dumps(payload, ensure_ascii=False).encode("utf-8")
            )
        ]
    )

    result = provider(transport).enhance_record(request())

    assert result.request_id == "resp_direct_text"
    assert result.usage.total_tokens == 15


def test_nested_function_call_shape_is_supported() -> None:
    payload = {
        "id": "resp_nested_function",
        "model": "doubao-test-model",
        "status": "completed",
        "output": [
            {
                "type": "function_call",
                "function": {
                    "name": ADVISORY_FUNCTION_NAME,
                    "arguments": json.dumps(advisory(), ensure_ascii=False),
                },
            }
        ],
    }
    transport = FakeTransport(
        [
            ark_response(
                body=json.dumps(payload, ensure_ascii=False).encode("utf-8")
            )
        ]
    )

    result = provider(transport).enhance_record(request())

    assert result.request_id == "resp_nested_function"


def test_numeric_strings_are_safely_normalized() -> None:
    payload = advisory(confidence="0.67")
    transport = FakeTransport(
        [
            ark_response(
                advisory_payload=payload,
                body=json.dumps(
                    {
                        "id": "resp_numeric_strings",
                        "model": "doubao-test-model",
                        "status": "completed",
                        "output": [
                            {
                                "type": "function_call",
                                "name": ADVISORY_FUNCTION_NAME,
                                "arguments": json.dumps(
                                    payload, ensure_ascii=False
                                ),
                            }
                        ],
                        "usage": {
                            "input_tokens": "101",
                            "output_tokens": "22",
                            "total_tokens": "123",
                        },
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )
        ]
    )

    result = provider(transport).enhance_record(request())

    assert result.confidence == 0.67
    assert result.usage.total_tokens == 123


@pytest.mark.parametrize(
    ("bad_advisory", "schema_path", "diagnostic_key"),
    [
        (
            {k: v for k, v in advisory().items() if k != "warnings"},
            "$",
            "missing_keys",
        ),
        (advisory(extra_field=True), "$", "extra_keys"),
        (advisory(confidence="not-a-number"), "$.confidence", "actual_type"),
        (advisory(action="not-an-action"), "$.action", "invalid_enum_value"),
        (
            advisory(source_record_id="wrong-record"),
            "$.source_record_id",
            "source_record_id_match",
        ),
    ],
)
def test_structured_output_errors_include_safe_diagnostics(
    bad_advisory: dict[str, object],
    schema_path: str,
    diagnostic_key: str,
) -> None:
    transport = FakeTransport(
        [ark_response(advisory_payload=bad_advisory)]
    )

    with pytest.raises(LLMProviderError) as caught:
        provider(transport).enhance_record(request())

    diagnostics = caught.value.diagnostics
    assert caught.value.code == LLMErrorCode.STRUCTURED_OUTPUT_ERROR
    assert diagnostics["schema_path"] == schema_path
    assert diagnostic_key in diagnostics
    assert diagnostics["has_function_call"] is True
    serialized = json.dumps(diagnostics, ensure_ascii=False)
    assert SECRET not in serialized


def test_invalid_output_text_json_reports_parse_stage() -> None:
    payload = {
        "id": "resp_bad_text",
        "status": "completed",
        "output_text": "{not-json",
    }
    transport = FakeTransport(
        [ark_response(body=json.dumps(payload).encode("utf-8"))]
    )

    with pytest.raises(LLMProviderError) as caught:
        provider(transport).enhance_record(request())

    assert caught.value.diagnostics["error_stage"] == "output_text_json_parse"
    assert caught.value.diagnostics["schema_path"] == "$.output_text"


@pytest.mark.parametrize(
    "failure",
    [
        TransportTimeout("timeout"),
        TransportConnectionError("connection"),
    ],
)
def test_transient_transport_failure_retries_then_succeeds(
    failure: Exception,
) -> None:
    transport = FakeTransport([failure, ark_response()])
    sleeps: list[float] = []

    result = provider(transport, sleeps=sleeps).enhance_record(request())

    assert result.attempt_count == 2
    assert len(transport.requests) == 2
    assert sleeps == [0.25]


def test_429_retries_then_succeeds_with_bounded_retry_after() -> None:
    rate_limit = ark_response(
        status_code=429,
        body=b'{"error":{"type":"rate_limit_error"}}',
        headers={"retry-after": "99", "x-request-id": "rate-id"},
    )
    transport = FakeTransport([rate_limit, ark_response()])
    sleeps: list[float] = []

    result = provider(transport, sleeps=sleeps).enhance_record(request())

    assert result.attempt_count == 2
    assert sleeps == [5.0]


def test_continuous_429_stops_after_configured_attempts() -> None:
    responses = [
        ark_response(status_code=429, body=b"rate limited"),
        ark_response(status_code=429, body=b"rate limited"),
        ark_response(status_code=429, body=b"rate limited"),
    ]
    transport = FakeTransport(responses)

    with pytest.raises(LLMProviderError) as caught:
        provider(transport, sleeps=[]).enhance_record(request())

    assert caught.value.code == LLMErrorCode.RATE_LIMITED
    assert caught.value.retryable is True
    assert caught.value.attempts == 3
    assert len(transport.requests) == 3


def test_500_retries_then_succeeds() -> None:
    transport = FakeTransport(
        [ark_response(status_code=500, body=b"server error"), ark_response()]
    )

    result = provider(transport, sleeps=[]).enhance_record(request())

    assert result.attempt_count == 2


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (400, LLMErrorCode.INVALID_REQUEST),
        (401, LLMErrorCode.AUTHENTICATION_ERROR),
        (403, LLMErrorCode.PERMISSION_ERROR),
        (404, LLMErrorCode.MODEL_NOT_FOUND),
    ],
)
def test_non_retryable_http_errors_stop_immediately(
    status_code: int, expected_code: LLMErrorCode
) -> None:
    transport = FakeTransport(
        [ark_response(status_code=status_code, body=b"not-json")]
    )

    with pytest.raises(LLMProviderError) as caught:
        provider(transport).enhance_record(request())

    assert caught.value.code == expected_code
    assert caught.value.retryable is False
    assert caught.value.attempts == 1
    assert len(transport.requests) == 1


def test_non_json_success_response_is_invalid() -> None:
    transport = FakeTransport([ark_response(body=b"<html>error</html>")])

    with pytest.raises(LLMProviderError) as caught:
        provider(transport).enhance_record(request())

    assert caught.value.code == LLMErrorCode.INVALID_RESPONSE
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "bad_advisory",
    [
        advisory(extra_field=True),
        advisory(source_record_id="wrong-record"),
        advisory(action="not-an-action"),
    ],
)
def test_invalid_structured_output_is_not_retried(
    bad_advisory: dict[str, object],
) -> None:
    transport = FakeTransport(
        [ark_response(advisory_payload=bad_advisory)]
    )

    with pytest.raises(LLMProviderError) as caught:
        provider(transport).enhance_record(request())

    assert caught.value.code == LLMErrorCode.STRUCTURED_OUTPUT_ERROR
    assert caught.value.retryable is False
    assert len(transport.requests) == 1


def test_non_json_function_arguments_are_structured_output_error() -> None:
    payload = {
        "id": "resp_bad_arguments",
        "status": "completed",
        "output": [
            {
                "type": "function_call",
                "name": ADVISORY_FUNCTION_NAME,
                "arguments": "{not-json",
            }
        ],
    }
    transport = FakeTransport(
        [ark_response(body=json.dumps(payload).encode("utf-8"))]
    )

    with pytest.raises(LLMProviderError) as caught:
        provider(transport).enhance_record(request())

    assert caught.value.code == LLMErrorCode.STRUCTURED_OUTPUT_ERROR


def test_insufficient_evidence_response_is_valid() -> None:
    insufficient = advisory(
        action="insufficient_evidence",
        confidence=0.0,
        suggested_fields=[],
        material_assessment={
            "status": "insufficient_evidence",
            "suggested_material_code": "",
            "reason": "No evidence supports a suggestion.",
        },
        reasoning_summary="证据不足。",
    )
    transport = FakeTransport(
        [ark_response(advisory_payload=insufficient)]
    )

    result = provider(transport).enhance_record(request())

    assert result.action == "insufficient_evidence"
    assert result.material_assessment.suggested_material_code == ""


def test_api_key_is_redacted_from_error_metadata() -> None:
    response = ark_response(
        status_code=401,
        body=json.dumps(
            {"error": {"type": f"invalid_{SECRET}"}}
        ).encode("utf-8"),
    )
    transport = FakeTransport([response])

    with pytest.raises(LLMProviderError) as caught:
        provider(transport).enhance_record(request())

    serialized = json.dumps(caught.value.to_dict())
    assert SECRET not in serialized
    assert "<redacted>" in caught.value.provider_error_type


def test_health_check_is_configuration_only_and_offline() -> None:
    transport = FakeTransport([])
    health = provider(transport).health_check()

    assert health == {
        "status": "ready",
        "configured": True,
        "network_check_performed": False,
        "provider": "volcengine_ark",
        "model_configured": True,
        "api_key_configured": True,
    }
    assert transport.requests == []


def test_ready_capabilities_are_safe_and_do_not_call_transport() -> None:
    transport = FakeTransport([])
    service = LLMService(settings=settings(), transport=transport)

    capabilities = service.capabilities()

    assert capabilities["status"] == "ready"
    assert capabilities["configured"] is True
    assert capabilities["real_call_allowed"] is True
    assert capabilities["business_integration"] is False
    assert capabilities["api_key_configured"] is True
    assert SECRET not in json.dumps(capabilities)
    assert transport.requests == []


@pytest.mark.parametrize(
    ("configured_settings", "configuration_status"),
    [
        (
            LLMSettings(
                enabled=True,
                provider="volcengine_ark",
                model="doubao-test-model",
                base_url="https://ark.test/api/v3",
                api_key="",
            ),
            "api_key_missing",
        ),
        (
            LLMSettings(
                enabled=True,
                provider="volcengine_ark",
                model="",
                base_url="https://ark.test/api/v3",
                api_key=SECRET,
            ),
            "model_missing",
        ),
    ],
)
def test_missing_required_configuration_never_calls_transport(
    configured_settings: LLMSettings, configuration_status: str
) -> None:
    transport = FakeTransport([])
    ark = VolcengineArkProvider(
        configured_settings,
        transport=transport,
        sleep=lambda _seconds: None,
    )

    with pytest.raises(LLMProviderError) as caught:
        ark.enhance_record(request())

    assert caught.value.code == LLMErrorCode.CONFIGURATION_ERROR
    assert caught.value.provider_error_type == configuration_status
    assert transport.requests == []


def test_cancelled_request_never_calls_transport() -> None:
    transport = FakeTransport([])
    ark = VolcengineArkProvider(
        settings(),
        transport=transport,
        sleep=lambda _seconds: None,
        cancel_check=lambda: True,
    )

    with pytest.raises(LLMProviderError) as caught:
        ark.enhance_record(request())

    assert caught.value.code == LLMErrorCode.CANCELLED
    assert caught.value.retryable is False
    assert caught.value.attempts == 0
    assert transport.requests == []
