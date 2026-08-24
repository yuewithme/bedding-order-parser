"""Firewalled Ark Responses provider for the existing whole-order contract."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from bedding_order_parser.ai_full_order.contracts import (
    FULL_ORDER_OUTPUT_SCHEMA,
    FULL_ORDER_V2_OUTPUT_SCHEMA,
    FullOrderContractError,
    safe_contract_diagnostic,
    validate_full_order_output,
    validate_full_order_request,
    validate_full_order_v2_output,
    validate_full_order_v2_request,
)
from bedding_order_parser.ai_full_order.reliability import TransientProviderError
from bedding_order_parser.ai_full_order.structure_manifest import (
    LAYOUT_PROMPT_VERSION,
    provider_structure_payload,
)
from bedding_order_parser.ai_full_order.structure_resolution import (
    LAYOUT_OUTPUT_SCHEMA,
    StructureDecisionValidationError,
    validate_layout_output_shape,
)
from bedding_order_parser.llm.errors import LLMErrorCode, LLMProviderError
from bedding_order_parser.llm.settings import LLMSettings, VOLCENGINE_ARK_PROVIDER
from bedding_order_parser.llm.transport import JSONTransport
from bedding_order_parser.llm.volcengine_ark import (
    VolcengineArkProvider,
    _request_id,
    _usage,
    extract_structured_output,
)


FULL_ORDER_EXTRACTION_FUNCTION = "submit_bedding_order_full_order"
FULL_ORDER_V2_EXTRACTION_FUNCTION = "submit_bedding_order_candidates_v2"
FULL_ORDER_LAYOUT_FUNCTION = "submit_bedding_order_layout"
FULL_ORDER_PROMPT_VERSION = "1.0"
FULL_ORDER_V2_PROMPT_VERSION = "2.0"
FULL_ORDER_LAYOUT_PROMPT_VERSION = LAYOUT_PROMPT_VERSION
_LAYOUT_SCHEMA = LAYOUT_OUTPUT_SCHEMA
_EXTRACTION_INSTRUCTION = (
    "你是床品订单整单提取助手。只能使用用户消息中的坐标化证据；不得补造信息，"
    "不得生成行号、物料编码或相似分数。严格返回函数参数中的完整既有合同对象，"
    "所有非空字段必须引用同scope的输入证据。不得输出私有思维链。"
)
_V2_EXTRACTION_INSTRUCTION = (
    "你是床品订单单记录候选提取助手。只返回稀疏candidates；field_name只能来自固定17字段。"
    "direct必须能在引用证据原文中直接定位；semantic和source_summary必须提供可定位原文quote。"
    "不得回显或生成record/source/scope/SHA、行号、物料编码、相似分数、Provider元数据、"
    "usage、延迟、尝试次数、验证结论或私有思维链。不得补造信息。"
)
_LAYOUT_INSTRUCTION = (
    "你是床品订单表格结构识别助手。已确认区块仅供上下文，不得改写。"
    "对每个unresolved sheet必须且只能选择输入中的本地candidate_id，或标记unresolved；"
    "不得生成区块、记录、scope、坐标或系统身份。严格返回函数参数，不得输出额外内容或私有思维链。"
)


@dataclass(frozen=True)
class FullOrderCallTelemetry:
    provider: str = ""
    model: str = ""
    request_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    attempt_count: int = 0

    def to_dict(self) -> dict[str, str | int]:
        return {
            "provider": self.provider,
            "model": self.model,
            "request_id": self.request_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "attempt_count": self.attempt_count,
        }


class VolcengineArkFullOrderProvider:
    """Whole-order adapter that preserves B1-B3 request and response contracts."""

    def __init__(
        self,
        settings: LLMSettings,
        *,
        transport: JSONTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self._responses = VolcengineArkProvider(
            settings, transport=transport, sleep=sleep, monotonic=monotonic
        )
        self.extraction_call_count = 0
        self.structure_call_count = 0
        self.http_attempt_count = 0
        self.latest_telemetry = FullOrderCallTelemetry()
        self.usage_summary = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        self.latest_contract_diagnostic: dict[str, Any] = {}

    @property
    def provider_name(self) -> str:
        return VOLCENGINE_ARK_PROVIDER

    @property
    def model_name(self) -> str:
        return self.settings.model

    def is_configured(self) -> bool:
        return self.settings.is_ready()

    def health_check(self) -> dict[str, object]:
        return self._responses.health_check()

    def resolve_structure(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        try:
            safe_manifest = provider_structure_payload(manifest)
        except ValueError as exc:
            error = FullOrderContractError(
                "Structure context failed local request validation.",
                diagnostic={
                    "stage": "request_validation",
                    "category": "structure_context_invalid",
                    "path": "$",
                },
            )
            self._remember_contract_error(error)
            raise error from exc
        self.structure_call_count += 1
        payload, raw, attempt, latency_ms = self._send(
            _responses_body(
                model=self.model_name,
                instruction=_LAYOUT_INSTRUCTION,
                payload=safe_manifest,
                function_name=FULL_ORDER_LAYOUT_FUNCTION,
                schema=_LAYOUT_SCHEMA,
            )
        )
        result = self._structured_result(
            payload, raw.headers, attempt, latency_ms, FULL_ORDER_LAYOUT_FUNCTION
        )
        try:
            return validate_layout_output_shape(result)
        except StructureDecisionValidationError as exc:
            error = FullOrderContractError(
                "Ark structure result violates the strict layout contract.",
                diagnostic={
                    "stage": "output_schema",
                    "category": "layout_contract_invalid",
                    "path": "$",
                },
            )
            self._remember_contract_error(error)
            raise error from exc

    def extract(self, request: Mapping[str, Any]) -> dict[str, Any]:
        self.latest_contract_diagnostic = {}
        try:
            validated_request = validate_full_order_request(dict(request))
        except FullOrderContractError as exc:
            self._remember_contract_error(exc)
            raise
        self.extraction_call_count += 1
        payload, raw, attempt, latency_ms = self._send(
            _responses_body(
                model=self.model_name,
                instruction=_EXTRACTION_INSTRUCTION,
                payload=validated_request,
                function_name=FULL_ORDER_EXTRACTION_FUNCTION,
                schema=FULL_ORDER_OUTPUT_SCHEMA,
            )
        )
        output = self._structured_result(
            payload, raw.headers, attempt, latency_ms, FULL_ORDER_EXTRACTION_FUNCTION
        )
        usage = self.latest_telemetry
        # These values are transport facts, never trusted model-generated metadata.
        result = dict(output)
        result.update(
            {
                "provider": self.provider_name,
                "model": self.model_name,
                "request_id": usage.request_id or "ark-response-without-id",
                "usage": {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                },
                "latency_ms": usage.latency_ms,
                "attempt_count": usage.attempt_count,
            }
        )
        try:
            return validate_full_order_output(result, request=validated_request)
        except FullOrderContractError as exc:
            self._remember_contract_error(exc)
            raise

    def extract_v2(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Run the explicit sparse-candidate V2 boundary without V1 shape inference."""

        self.latest_contract_diagnostic = {}
        try:
            validated_request = validate_full_order_v2_request(dict(request))
        except FullOrderContractError as exc:
            self._remember_contract_error(exc)
            raise
        self.extraction_call_count += 1
        payload, raw, attempt, latency_ms = self._send(
            _responses_body(
                model=self.model_name,
                instruction=_V2_EXTRACTION_INSTRUCTION,
                payload=validated_request,
                function_name=FULL_ORDER_V2_EXTRACTION_FUNCTION,
                schema=FULL_ORDER_V2_OUTPUT_SCHEMA,
            )
        )
        output = self._structured_result(
            payload,
            raw.headers,
            attempt,
            latency_ms,
            FULL_ORDER_V2_EXTRACTION_FUNCTION,
        )
        try:
            return validate_full_order_v2_output(output)
        except FullOrderContractError as exc:
            self._remember_contract_error(exc)
            raise

    def close(self) -> None:
        self._responses.close()

    def _send(self, body: Mapping[str, Any]):
        try:
            payload, raw, attempt, latency_ms = self._responses.send_responses_body(body)
        except LLMProviderError as exc:
            self.http_attempt_count += exc.attempts
            self.latest_telemetry = FullOrderCallTelemetry(
                provider=self.provider_name,
                model=self.model_name,
                request_id=exc.request_id,
                latency_ms=0,
                attempt_count=exc.attempts,
            )
            if exc.retryable:
                raise TransientProviderError(f"ark_{exc.code.value}") from exc
            raise FullOrderContractError(f"Ark provider failed safely: {exc.code.value}.") from exc
        self.http_attempt_count += attempt
        return payload, raw, attempt, latency_ms

    def _structured_result(
        self,
        payload: Mapping[str, Any],
        headers: Mapping[str, str],
        attempt: int,
        latency_ms: int,
        function_name: str,
    ) -> dict[str, Any]:
        if str(payload.get("status", "")) not in {"completed", "succeeded"}:
            error = FullOrderContractError(
                "Ark response was not completed.",
                diagnostic={"stage": "response_parsing", "category": "response_parse", "path": "$.status"},
            )
            self._remember_contract_error(error)
            raise error
        try:
            result = extract_structured_output(payload, function_name=function_name)
        except (TypeError, ValueError) as exc:
            error = FullOrderContractError(
                "Ark response did not contain valid strict JSON.",
                diagnostic={"stage": "response_parsing", "category": "response_parse"},
            )
            self._remember_contract_error(error)
            raise error from exc
        try:
            _validate_transport_metadata(payload)
        except FullOrderContractError as exc:
            self._remember_contract_error(exc)
            raise
        usage = _usage(payload.get("usage"))
        self.latest_telemetry = FullOrderCallTelemetry(
            provider=self.provider_name,
            model=str(payload.get("model") or self.model_name),
            request_id=_request_id(payload, headers),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            latency_ms=latency_ms,
            attempt_count=attempt,
        )
        for name in self.usage_summary:
            self.usage_summary[name] += int(getattr(usage, name))
        return result

    def _remember_contract_error(self, error: FullOrderContractError) -> None:
        self.latest_contract_diagnostic = safe_contract_diagnostic(error)


def _validate_transport_metadata(payload: Mapping[str, Any]) -> None:
    """Reject malformed Ark metadata without retaining its values in diagnostics."""
    model = payload.get("model")
    if model is not None and not isinstance(model, str):
        raise FullOrderContractError(
            "Ark response model metadata must be a string.",
            diagnostic={
                "stage": "provider_metadata",
                "category": "provider_metadata_or_usage",
                "path": "$.model",
                "expected_type": "string",
                "actual_type": _json_type(model),
            },
        )
    usage = payload.get("usage")
    if usage is not None and not isinstance(usage, Mapping):
        raise FullOrderContractError(
            "Ark response usage metadata must be an object.",
            diagnostic={
                "stage": "provider_metadata",
                "category": "provider_metadata_or_usage",
                "path": "$.usage",
                "expected_type": "object",
                "actual_type": _json_type(usage),
            },
        )


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
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
    return "other"


def _responses_body(
    *, model: str, instruction: str, payload: Mapping[str, Any], function_name: str, schema: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "model": model,
        "store": False,
        "input": [
            {"role": "developer", "content": [{"type": "input_text", "text": instruction}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]},
        ],
        "tools": [{"type": "function", "name": function_name, "description": "返回严格合同JSON。", "parameters": dict(schema), "strict": True}],
        "tool_choice": {"type": "function", "name": function_name},
    }
