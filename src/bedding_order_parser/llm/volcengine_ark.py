"""Firewalled Volcengine Ark Responses API provider."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any, Mapping

from bedding_order_parser.llm.advisory_schema import (
    MODEL_ADVISORY_SCHEMA,
    validate_model_advisory,
)
from bedding_order_parser.llm.contracts import (
    LLMConnectivityResult,
    LLMEnhancementRequest,
    LLMEnhancementResponse,
    LLMUsage,
    MaterialAssessment,
    SuggestedField,
)
from bedding_order_parser.llm.errors import (
    LLMErrorCode,
    LLMProviderError,
    SchemaValidationError,
)
from bedding_order_parser.llm.settings import (
    LLMSettings,
    VOLCENGINE_ARK_PROVIDER,
)
from bedding_order_parser.llm.transport import (
    JSONHTTPRequest,
    JSONHTTPResponse,
    JSONTransport,
    TransportConnectionError,
    TransportTimeout,
    UrllibJSONTransport,
)


ADVISORY_FUNCTION_NAME = "submit_bedding_order_advisory"
DEVELOPER_INSTRUCTION = (
    "你是床品订单单记录复核助手，只能使用请求中提供的证据。不得补造缺失值、"
    "确认物料编码、写入ERP或覆盖确定性解析结果。reasoning_summary、"
    "suggested_fields.reason、warnings、material_assessment.reason、人工核查建议等所有"
    "面向业务人员的动态说明必须使用简体中文，内容应简洁、可操作，不得输出"
    "私有思维链。PI原始英文证据、客户原名、产品描述、物料编码、型号和专有"
    "名词保持原文，不要强行翻译；Schema字段名和枚举值保持合同规定的英文。"
    "prototype_match_score只是未经业务真值标定的参考匹配分数，不是准确率或"
    "正确概率，不得使用高、中、低置信等级，也不得仅凭分数判断候选正确或"
    "错误。结论应主要依据可比较字段数量、字段级一致/缺失/冲突、原始PI证据、"
    "字典验证和候选物料实际属性。描述分数时使用类似“第一候选的参考匹配分数"
    "为0.767，但可比较字段较少，并存在关键字段缺失或冲突”的表述。"
    "source_record_id必须原样返回。证据不足时使用"
    "action=insufficient_evidence。"
)
MAX_ERROR_TYPE_LENGTH = 120
CONNECTIVITY_PROMPT = "只返回以下四个汉字，不要添加其他内容：连接成功"
CONNECTIVITY_MAX_OUTPUT_TOKENS = 64


class VolcengineArkProvider:
    """Non-streaming Ark provider with strict sidecar output validation."""

    def __init__(
        self,
        settings: LLMSettings,
        *,
        transport: JSONTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport or UrllibJSONTransport()
        self._sleep = sleep
        self._monotonic = monotonic
        self._cancel_check = cancel_check

    @property
    def provider_name(self) -> str:
        return VOLCENGINE_ARK_PROVIDER

    @property
    def model_name(self) -> str:
        return self.settings.model

    def is_configured(self) -> bool:
        return self.settings.is_ready()

    def health_check(self) -> dict[str, object]:
        return {
            "status": self.settings.configuration_status(),
            "configured": self.is_configured(),
            "network_check_performed": False,
            "provider": self.provider_name,
            "model_configured": self.settings.model_configured,
            "api_key_configured": self.settings.api_key_configured,
        }

    def enhance_record(
        self, request: LLMEnhancementRequest
    ) -> LLMEnhancementResponse:
        self._require_ready()
        body = _request_body(request, self.settings.model)
        payload, raw_response, attempt, latency_ms = self._send_body(body)
        try:
            response = self._build_response(
                request,
                payload,
                raw_response,
                attempt=attempt,
                latency_ms=latency_ms,
            )
            response.to_dict()
        except LLMProviderError as exc:
            exc.attempts = attempt
            raise
        except SchemaValidationError as exc:
            raise LLMProviderError(
                LLMErrorCode.STRUCTURED_OUTPUT_ERROR,
                "The local advisory response failed schema validation.",
                request_id=response.request_id,
                attempts=attempt,
            ) from exc
        return response

    def check_connectivity(self) -> LLMConnectivityResult:
        self._require_ready()
        payload, raw_response, attempt, latency_ms = self._send_body(
            _connectivity_request_body(self.settings.model)
        )
        provider_status = str(payload.get("status", ""))
        if provider_status not in {"completed", "succeeded"}:
            raise LLMProviderError(
                LLMErrorCode.INVALID_RESPONSE,
                "Volcengine Ark returned a non-completed response.",
                request_id=_request_id(payload, raw_response.headers),
                attempts=attempt,
            )
        try:
            text = _extract_output_text(payload).strip()
        except SchemaValidationError as exc:
            raise LLMProviderError(
                LLMErrorCode.INVALID_RESPONSE,
                "Volcengine Ark returned no connectivity output text.",
                request_id=_request_id(payload, raw_response.headers),
                attempts=attempt,
            ) from exc
        return LLMConnectivityResult(
            provider=self.provider_name,
            model=str(payload.get("model") or self.settings.model),
            request_id=_request_id(payload, raw_response.headers),
            status="succeeded",
            finish_status=provider_status,
            text=text,
            usage=_usage(payload.get("usage")),
            latency_ms=latency_ms,
            attempt_count=attempt,
        )

    def _send_body(
        self, body: Mapping[str, Any]
    ) -> tuple[dict[str, Any], JSONHTTPResponse, int, int]:
        encoded = json.dumps(
            body, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        http_request = JSONHTTPRequest(
            method="POST",
            url=f"{self.settings.base_url.rstrip('/')}/responses",
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "bedding-order-parser/0.1",
            },
            body=encoded,
            timeout_seconds=self.settings.timeout_seconds,
        )

        started = self._monotonic()
        max_attempts = self.settings.max_retries + 1
        for attempt in range(1, max_attempts + 1):
            self._ensure_not_cancelled(attempts=attempt - 1)
            try:
                raw_response = self.transport.send(http_request)
                payload = _decode_response(
                    raw_response,
                    require_json=(
                        200 <= raw_response.status_code < 300
                    ),
                )
                if not 200 <= raw_response.status_code < 300:
                    raise _http_error(
                        raw_response,
                        payload,
                        secret=self.settings.api_key,
                    )
                return (
                    payload,
                    raw_response,
                    attempt,
                    max(
                        0,
                        round((self._monotonic() - started) * 1000),
                    ),
                )
            except TransportTimeout as exc:
                error = LLMProviderError(
                    LLMErrorCode.TIMEOUT,
                    "Volcengine Ark request timed out.",
                    retryable=True,
                    attempts=attempt,
                )
                error.__cause__ = exc
            except TransportConnectionError as exc:
                error = LLMProviderError(
                    LLMErrorCode.CONNECTION_ERROR,
                    "Volcengine Ark connection failed.",
                    retryable=True,
                    attempts=attempt,
                )
                error.__cause__ = exc
            except LLMProviderError as exc:
                error = exc
                error.attempts = attempt

            if not error.retryable or attempt >= max_attempts:
                raise error
            self._ensure_not_cancelled(attempts=attempt)
            self._sleep(_retry_delay(error, attempt))

        raise LLMProviderError(
            LLMErrorCode.UNKNOWN_PROVIDER_ERROR,
            "Volcengine Ark request ended unexpectedly.",
            attempts=max_attempts,
        )

    def send_responses_body(
        self, body: Mapping[str, Any]
    ) -> tuple[dict[str, Any], JSONHTTPResponse, int, int]:
        """Send another strict Responses payload through the same safe transport."""
        self._require_ready()
        return self._send_body(body)

    def close(self) -> None:
        return

    def _require_ready(self) -> None:
        status = self.settings.configuration_status()
        if status == "ready":
            return
        code = (
            LLMErrorCode.DISABLED
            if status == "disabled"
            else LLMErrorCode.CONFIGURATION_ERROR
        )
        raise LLMProviderError(
            code,
            f"LLM provider is not callable: {status}.",
            provider_error_type=status,
            attempts=0,
        )

    def _ensure_not_cancelled(self, *, attempts: int) -> None:
        if self._cancel_check is None or not self._cancel_check():
            return
        raise LLMProviderError(
            LLMErrorCode.CANCELLED,
            "Volcengine Ark request was cancelled.",
            retryable=False,
            attempts=attempts,
        )

    def _build_response(
        self,
        request: LLMEnhancementRequest,
        payload: dict[str, Any],
        raw_response: JSONHTTPResponse,
        *,
        attempt: int,
        latency_ms: int,
    ) -> LLMEnhancementResponse:
        provider_status = str(payload.get("status", ""))
        if provider_status not in {"completed", "succeeded"}:
            raise LLMProviderError(
                LLMErrorCode.INVALID_RESPONSE,
                "Volcengine Ark returned a non-completed response.",
                request_id=_request_id(payload, raw_response.headers),
            )
        response_diagnostics = _response_shape_diagnostics(payload)
        try:
            raw_advisory = _extract_advisory(payload)
            advisory = validate_model_advisory(
                _normalize_model_advisory(raw_advisory),
                expected_source_record_id=request.source_record_id,
            )
        except (SchemaValidationError, TypeError, ValueError) as exc:
            raise LLMProviderError(
                LLMErrorCode.STRUCTURED_OUTPUT_ERROR,
                "Volcengine Ark returned invalid structured advisory output.",
                request_id=_request_id(payload, raw_response.headers),
                diagnostics=_merge_diagnostics(response_diagnostics, exc),
            ) from exc

        usage = _usage(payload.get("usage"))
        response = LLMEnhancementResponse(
            provider=self.provider_name,
            model=str(payload.get("model") or self.settings.model),
            request_id=_request_id(payload, raw_response.headers),
            source_record_id=advisory["source_record_id"],
            status="succeeded",
            finish_status=provider_status,
            action=advisory["action"],
            confidence=float(advisory["confidence"]),
            suggested_fields=tuple(
                SuggestedField(
                    field_name=item["field_name"],
                    original_value=item["original_value"],
                    suggested_value=item["suggested_value"],
                    reason=item["reason"],
                    evidence_references=tuple(
                        item["evidence_references"]
                    ),
                )
                for item in advisory["suggested_fields"]
            ),
            material_assessment=MaterialAssessment(
                status=advisory["material_assessment"]["status"],
                suggested_material_code=advisory[
                    "material_assessment"
                ]["suggested_material_code"],
                reason=advisory["material_assessment"]["reason"],
            ),
            reasoning_summary=advisory["reasoning_summary"],
            warnings=tuple(advisory["warnings"]),
            evidence_references=tuple(
                advisory["evidence_references"]
            ),
            usage=usage,
            latency_ms=latency_ms,
            attempt_count=attempt,
        )
        return response


def _request_body(
    request: LLMEnhancementRequest, model: str
) -> dict[str, Any]:
    return {
        "model": model,
        "store": False,
        "input": [
            {
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": DEVELOPER_INSTRUCTION,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            request.to_dict(),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    }
                ],
            },
        ],
        "tools": [
            {
                "type": "function",
                "name": ADVISORY_FUNCTION_NAME,
                "description": (
                    "为当前单条订单记录返回严格Schema的简体中文复核建议。"
                ),
                "parameters": MODEL_ADVISORY_SCHEMA,
                "strict": True,
            }
        ],
        "tool_choice": {
            "type": "function",
            "name": ADVISORY_FUNCTION_NAME,
        },
    }


def _connectivity_request_body(model: str) -> dict[str, Any]:
    return {
        "model": model,
        "store": False,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": CONNECTIVITY_PROMPT,
                    }
                ],
            }
        ],
        "max_output_tokens": CONNECTIVITY_MAX_OUTPUT_TOKENS,
    }


def _decode_response(
    response: JSONHTTPResponse, *, require_json: bool
) -> dict[str, Any]:
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        if not require_json:
            return {}
        raise LLMProviderError(
            LLMErrorCode.INVALID_RESPONSE,
            "Volcengine Ark returned a non-JSON response.",
            status_code=response.status_code,
            request_id=_request_id({}, response.headers),
        ) from exc
    if not isinstance(payload, dict):
        if not require_json:
            return {}
        raise LLMProviderError(
            LLMErrorCode.INVALID_RESPONSE,
            "Volcengine Ark returned an invalid response object.",
            status_code=response.status_code,
            request_id=_request_id({}, response.headers),
        )
    return payload


def _extract_advisory(payload: Mapping[str, Any]) -> dict[str, Any]:
    return extract_structured_output(payload, function_name=ADVISORY_FUNCTION_NAME)


def extract_structured_output(
    payload: Mapping[str, Any], *, function_name: str
) -> dict[str, Any]:
    """Read compatible Ark Responses function-call or JSON-text output shapes."""
    direct_text = payload.get("output_text")
    if isinstance(direct_text, str) and direct_text.strip():
        return _decode_arguments(
            direct_text,
            stage="output_text_json_parse",
            path="$.output_text",
        )
    output = payload.get("output")
    if not isinstance(output, list):
        raise SchemaValidationError(
            "$.output must be an array.",
            path="$.output",
            diagnostic={
                "error_stage": "responses_output_extraction",
                "schema_path": "$.output",
                "expected_type": "array",
                "actual_type": _json_type(output),
            },
        )
    for item in output:
        call = _function_call_payload(item, function_name=function_name)
        if call is not None:
            return _decode_arguments(
                call.get("arguments"),
                stage="function_call_arguments_parse",
                path="$.output[].arguments",
            )
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "output_text":
                return _decode_arguments(
                    part.get("text"),
                    stage="output_text_json_parse",
                    path="$.output[].content[].text",
                )
    raise SchemaValidationError(
        "The response did not contain the advisory function call.",
        diagnostic={
            "error_stage": "function_call_extraction",
            "schema_path": "$.output",
            **_response_shape_diagnostics(payload),
        },
    )


def _extract_output_text(payload: Mapping[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    output = payload.get("output")
    if not isinstance(output, list):
        raise SchemaValidationError("$.output must be an array.")
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str) and text:
                    return text
    raise SchemaValidationError(
        "The response did not contain output text."
    )


def _decode_arguments(
    value: Any,
    *,
    stage: str = "function_call_arguments_parse",
    path: str = "$.output[].arguments",
) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise SchemaValidationError(
            "Function arguments must be JSON.",
            path=path,
            diagnostic={
                "error_stage": stage,
                "schema_path": path,
                "expected_type": "string_or_object",
                "actual_type": _json_type(value),
            },
        )
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(
            "Function arguments must be valid JSON.",
            path=path,
            diagnostic={
                "error_stage": stage,
                "schema_path": path,
                "expected_type": "json_object_text",
                "actual_type": "invalid_json_text",
            },
        ) from exc
    if not isinstance(payload, dict):
        raise SchemaValidationError(
            "Function arguments must be a JSON object.",
            path=path,
            diagnostic={
                "error_stage": stage,
                "schema_path": path,
                "expected_type": "object",
                "actual_type": _json_type(payload),
            },
        )
    return payload


def _function_call_payload(
    item: Any, *, function_name: str = ADVISORY_FUNCTION_NAME
) -> Mapping[str, Any] | None:
    if not isinstance(item, dict):
        return None
    if item.get("type") == "function_call":
        if item.get("name") == function_name:
            return item
        nested = item.get("function")
        if isinstance(nested, dict) and nested.get("name") == function_name:
            return nested
    if item.get("type") in {"tool_call", "function"}:
        nested = item.get("function")
        if isinstance(nested, dict) and nested.get("name") == function_name:
            return nested
    return None


def _normalize_model_advisory(value: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(value)
    confidence = normalized.get("confidence")
    if isinstance(confidence, str):
        text = confidence.strip()
        try:
            normalized["confidence"] = float(text)
        except ValueError:
            pass
    return normalized


def _response_shape_diagnostics(payload: Mapping[str, Any]) -> dict[str, Any]:
    output = payload.get("output")
    items = output if isinstance(output, list) else []
    response_item_types = [
        str(item.get("type", "")) if isinstance(item, dict) else _json_type(item)
        for item in items
    ]
    has_function_call = any(_function_call_payload(item) is not None for item in items)
    has_output_text = isinstance(payload.get("output_text"), str) and bool(
        str(payload.get("output_text", "")).strip()
    )
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        has_output_text = has_output_text or any(
            isinstance(part, dict)
            and part.get("type") == "output_text"
            and isinstance(part.get("text"), str)
            and bool(str(part.get("text", "")).strip())
            for part in content
        )
    return {
        "response_item_types": response_item_types,
        "has_function_call": has_function_call,
        "has_output_text": has_output_text,
    }


def _merge_diagnostics(
    response_diagnostics: Mapping[str, Any], exc: Exception
) -> dict[str, Any]:
    direct = getattr(exc, "diagnostic", {})
    direct = direct if isinstance(direct, dict) else {}
    return {
        "error_stage": direct.get("error_stage", "schema_validation"),
        **response_diagnostics,
        **direct,
    }


def _json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__


def _usage(value: Any) -> LLMUsage:
    payload = value if isinstance(value, dict) else {}
    input_tokens = _non_negative_int(payload.get("input_tokens"))
    output_tokens = _non_negative_int(payload.get("output_tokens"))
    total_tokens = _non_negative_int(payload.get("total_tokens"))
    if not total_tokens:
        total_tokens = input_tokens + output_tokens
    return LLMUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return 0
    if not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


def _request_id(
    payload: Mapping[str, Any], headers: Mapping[str, str]
) -> str:
    return str(
        payload.get("id")
        or headers.get("x-request-id")
        or headers.get("request-id")
        or ""
    )


def _http_error(
    response: JSONHTTPResponse,
    payload: Mapping[str, Any],
    *,
    secret: str,
) -> LLMProviderError:
    status = response.status_code
    error_payload = payload.get("error")
    error_payload = error_payload if isinstance(error_payload, dict) else {}
    provider_type = _provider_error_type(error_payload, secret=secret)
    request_id = _request_id(payload, response.headers)
    retry_after = _retry_after(response.headers)

    if status == 401:
        code, retryable = LLMErrorCode.AUTHENTICATION_ERROR, False
    elif status == 403:
        code, retryable = LLMErrorCode.PERMISSION_ERROR, False
    elif status == 404:
        code, retryable = LLMErrorCode.MODEL_NOT_FOUND, False
    elif status == 408:
        code, retryable = LLMErrorCode.TIMEOUT, True
    elif status == 429:
        code, retryable = LLMErrorCode.RATE_LIMITED, True
    elif status in {500, 502, 503, 504}:
        code, retryable = LLMErrorCode.PROVIDER_SERVER_ERROR, True
    elif 400 <= status < 500:
        code, retryable = LLMErrorCode.INVALID_REQUEST, False
    elif status >= 500:
        code, retryable = LLMErrorCode.PROVIDER_SERVER_ERROR, False
    else:
        code, retryable = LLMErrorCode.UNKNOWN_PROVIDER_ERROR, False

    return LLMProviderError(
        code,
        f"Volcengine Ark request failed with HTTP {status} ({code.value}).",
        retryable=retryable,
        status_code=status,
        provider_error_type=provider_type,
        request_id=request_id,
        retry_after_seconds=retry_after,
    )


def _provider_error_type(
    payload: Mapping[str, Any], *, secret: str
) -> str:
    value = payload.get("type") or payload.get("code") or ""
    text = str(value).replace("\r", " ").replace("\n", " ")
    if secret:
        text = text.replace(secret, "<redacted>")
    return text[:MAX_ERROR_TYPE_LENGTH]


def _retry_after(headers: Mapping[str, str]) -> float | None:
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return max(0.0, min(parsed, 5.0))


def _retry_delay(error: LLMProviderError, attempt: int) -> float:
    if error.retry_after_seconds is not None:
        return error.retry_after_seconds
    return min(0.25 * (2 ** (attempt - 1)), 2.0)
