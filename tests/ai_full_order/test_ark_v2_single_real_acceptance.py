from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener, getproxies

from openpyxl import Workbook
import pytest

from bedding_order_parser.ai_full_order.contracts import (
    V2_CONTRACT_VERSION,
    validate_full_order_v2_request,
)
from bedding_order_parser.ai_full_order.downstream import (
    MaterialMatchOutput,
    MaterialSelection,
)
from bedding_order_parser.ai_full_order.orchestration import (
    build_v2_extraction_request,
    build_v2_extraction_units,
)
from bedding_order_parser.ai_full_order.preprocessing import preprocess_workbook
from bedding_order_parser.ai_full_order.python_shadow import (
    build_deterministic_python_shadow,
)
from bedding_order_parser.ai_full_order.volcengine_ark import (
    FULL_ORDER_V2_EXTRACTION_FUNCTION,
    VolcengineArkFullOrderProvider,
)
from bedding_order_parser.llm.settings import (
    DEFAULT_ARK_BASE_URL,
    LLMSettings,
    VOLCENGINE_ARK_PROVIDER,
)
from bedding_order_parser.llm.transport import (
    JSONHTTPRequest,
    JSONHTTPResponse,
    JSONTransport,
    TransportConnectionError,
    TransportTimeout,
)
from bedding_order_parser.models.final_result import FINAL_FIELD_NAMES
from bedding_order_parser.web.ai_full_order_service import AIEnhancedDependencies
from bedding_order_parser.web.services import ARTIFACT_ROLES, JobService


APPROVED_MODEL = "doubao-seed-2-0-lite-260428"
MAX_OUTPUT_TOKENS = 2048
AUTHORIZATION_VALUE = "CONFIRMED_SINGLE_CALL"
_SYNTHETIC_CELL_VALUES = frozenset(
    {
        "PROFORMA INVOICE",
        "Unit Price (USD)",
        "BUYER:",
        "TEST CUSTOMER",
        "Contact Person: TEST USER",
        "Delivery date:",
        "2026-12-31",
        "Currency: 美元",
        "No.",
        "Item",
        "Size",
        "Specification",
        "Qty",
        "Remarks",
        "1",
        "Duvet Cover",
        "50X75CM",
        "100% COTTON WHITE",
        "10",
    }
)
_SAFE_DIAGNOSTIC_KEYS = frozenset(
    {
        "stage",
        "category",
        "path",
        "expected_type",
        "actual_type",
        "missing_fields",
        "extra_field_count",
        "forbidden_fields",
    }
)


class AcceptanceGateError(RuntimeError):
    """Stop the acceptance run before an unsafe or over-budget request."""


class _DeferredExecutor:
    def submit(self, _function, *_args) -> None:
        return None

    def shutdown(self, **_kwargs) -> None:
        return None


class _FakeDictionaryValidator:
    def __init__(self) -> None:
        self.calls = 0

    def validate(self, records, evidence):
        self.calls += 1
        return {
            "validation_version": "1.0",
            "mode": "validation_only",
            "status": "completed",
            "records": [{"行号": item.line_number} for item in records],
        }


class _FakeMaterialMatcher:
    def __init__(self) -> None:
        self.calls = 0

    def match(self, records, resolved):
        self.calls += 1
        selections = {
            item.source_record_id: MaterialSelection(
                item.source_record_id, "", 0.0
            )
            for item in resolved
        }
        return MaterialMatchOutput(
            selections=selections,
            candidates_payload={
                "mode": "manual_review_only",
                "record_count": len(records),
                "records": [
                    {"行号": item.values["行号"], "candidates": []}
                    for item in records
                ],
            },
            summary_payload={
                "mode": "manual_review_only",
                "record_count": len(records),
                "accuracy_statement": "相似分数不是准确率，候选只用于人工复核。",
            },
        )


class _SingleAttemptDirectTransport:
    """One urlopen call with environment/system proxies explicitly bypassed."""

    def __init__(self) -> None:
        self.calls = 0
        self._opener = build_opener(ProxyHandler({}))

    def send(self, request: JSONHTTPRequest) -> JSONHTTPResponse:
        if self.calls:
            raise AcceptanceGateError("Direct transport allows exactly one HTTP attempt.")
        self.calls += 1
        started = time.monotonic()
        raw_request = Request(
            request.url,
            data=request.body,
            headers=dict(request.headers),
            method=request.method,
        )
        try:
            with self._opener.open(
                raw_request, timeout=request.timeout_seconds
            ) as response:
                return JSONHTTPResponse(
                    status_code=int(response.status),
                    headers=_normalized_headers(response.headers),
                    body=response.read(),
                    elapsed_ms=_elapsed_ms(started),
                )
        except HTTPError as exc:
            return JSONHTTPResponse(
                status_code=int(exc.code),
                headers=_normalized_headers(exc.headers),
                body=exc.read(),
                elapsed_ms=_elapsed_ms(started),
            )
        except (TimeoutError, socket.timeout) as exc:
            raise TransportTimeout("The bounded Ark request timed out.") from exc
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise TransportTimeout("The bounded Ark request timed out.") from exc
            raise TransportConnectionError(
                "The bounded Ark connection failed."
            ) from exc
        except OSError as exc:
            raise TransportConnectionError(
                "The bounded Ark connection failed."
            ) from exc


class _StaticArkTransport:
    """Offline inner transport used to prove the bounded harness."""

    def __init__(self) -> None:
        self.calls = 0

    def send(self, _request: JSONHTTPRequest) -> JSONHTTPResponse:
        self.calls += 1
        payload = {
            "id": "offline-d3c-request",
            "model": APPROVED_MODEL,
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": FULL_ORDER_V2_EXTRACTION_FUNCTION,
                    "arguments": json.dumps({"candidates": []}),
                }
            ],
            "usage": {
                "input_tokens": 101,
                "output_tokens": 3,
                "total_tokens": 104,
            },
        }
        return JSONHTTPResponse(
            200,
            {"x-request-id": "offline-d3c-header"},
            json.dumps(payload).encode("utf-8"),
            1,
        )


class _BoundedAcceptanceTransport:
    """Validate the exact synthetic V2 request, then permit one inner send."""

    def __init__(
        self,
        inner: JSONTransport,
        *,
        expected_fixture_sha256: str,
        expected_model: str,
        expected_base_url: str,
    ) -> None:
        self.inner = inner
        self.expected_fixture_sha256 = expected_fixture_sha256
        self.expected_model = expected_model
        self.expected_url = f"{expected_base_url.rstrip('/')}/responses"
        self.http_attempts = 0
        self.response_shape = "not_called"
        self.safe_parse_stage = "not_called"
        self.request_audit: dict[str, Any] = {}
        self.response_metadata: dict[str, Any] = {}

    def send(self, request: JSONHTTPRequest) -> JSONHTTPResponse:
        if self.http_attempts:
            raise AcceptanceGateError("Acceptance transport budget is already exhausted.")
        body = _validated_bounded_body(
            request,
            expected_url=self.expected_url,
            expected_model=self.expected_model,
            expected_fixture_sha256=self.expected_fixture_sha256,
        )
        body["max_output_tokens"] = MAX_OUTPUT_TOKENS
        bounded = JSONHTTPRequest(
            method=request.method,
            url=request.url,
            headers=request.headers,
            body=json.dumps(
                body, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8"),
            timeout_seconds=request.timeout_seconds,
        )
        self.request_audit = {
            "responses_api": request.url.endswith("/responses"),
            "store": body["store"],
            "stream": bool(body.get("stream", False)),
            "strict_function": body["tools"][0]["strict"] is True,
            "function_name": body["tool_choice"]["name"],
            "max_output_tokens": body["max_output_tokens"],
            "synthetic_evidence_only": True,
        }
        self.http_attempts = 1
        response = self.inner.send(bounded)
        self.response_shape = _response_shape(response)
        self.response_metadata = _safe_response_metadata(
            response, expected_model=self.expected_model
        )
        self.safe_parse_stage = "outer_response_classified"
        return response


def synthetic_workbook_bytes() -> bytes:
    workbook = Workbook()
    workbook.properties.created = datetime(2026, 1, 1)
    workbook.properties.modified = datetime(2026, 1, 1)
    sheet = workbook.active
    sheet.title = "PI"
    sheet.append(["", "PROFORMA INVOICE", "", "", "Unit Price (USD)", ""])
    sheet.append(["BUYER:", "", "", "", "", ""])
    sheet.append(
        ["TEST CUSTOMER", "", "", "", "Contact Person: TEST USER", ""]
    )
    sheet.append(
        ["Delivery date:", "2026-12-31", "", "", "Currency: 美元", ""]
    )
    sheet.append(["No.", "Item", "Size", "Specification", "Qty", "Remarks"])
    sheet.append(
        ["1", "Duvet Cover", "50X75CM", "100% COTTON WHITE", "10", ""]
    )
    raw = BytesIO()
    workbook.save(raw)
    workbook.close()
    return _stable_xlsx(raw.getvalue())


def offline_preflight(content: bytes) -> dict[str, Any]:
    fixture_sha256 = hashlib.sha256(content).hexdigest()
    with TemporaryDirectory(prefix="bedding-d3c-preflight-") as raw:
        path = Path(raw) / "synthetic.xlsx"
        path.write_bytes(content)
        preprocessed = preprocess_workbook(path)
        units = build_v2_extraction_units(preprocessed)
        if preprocessed.structure_status != "locally_resolved":
            raise AcceptanceGateError("Synthetic structure is not locally resolved.")
        if len(preprocessed.records) != 1 or len(units) != 1:
            raise AcceptanceGateError("Synthetic fixture must produce one record and one unit.")
        request = validate_full_order_v2_request(
            build_v2_extraction_request(units[0])
        )
        _validate_synthetic_request(request, fixture_sha256)
        evidence = {
            item.evidence_id: item
            for unit in units
            for item in unit.evidence_catalog
        }
        shadow = build_deterministic_python_shadow(
            path,
            preprocessed,
            target_records=[unit.target for unit in units],
            evidence_catalog=tuple(evidence.values()),
        )
        direct = {
            name
            for name, candidate in shadow[0].fields.items()
            if candidate.has_direct_evidence
        }
        required = {"客户", "币种", "业务员", "数量", "计划发货日期"}
        if not required <= direct:
            raise AcceptanceGateError(
                "Synthetic Python shadow lacks required direct high-risk evidence."
            )
        return {
            "fixture_sha256": fixture_sha256,
            "structure_status": preprocessed.structure_status,
            "record_count": len(preprocessed.records),
            "extraction_unit_count": len(units),
            "expected_progress": "0/1",
            "layout_calls": 0,
            "evidence_count": len(evidence),
            "request_schema_valid": True,
            "identity_scope_evidence_valid": True,
            "python_shadow_valid": True,
            "required_direct_field_count": len(required),
            "provider_calls": 0,
            "http_attempts": 0,
        }


def run_acceptance(
    settings: LLMSettings,
    inner_transport: JSONTransport,
    *,
    require_user_authorization: bool,
) -> dict[str, Any]:
    configuration = _configuration_audit(
        settings, require_user_authorization=require_user_authorization
    )
    content = synthetic_workbook_bytes()
    preflight = offline_preflight(content)
    transport = _BoundedAcceptanceTransport(
        inner_transport,
        expected_fixture_sha256=preflight["fixture_sha256"],
        expected_model=settings.model,
        expected_base_url=settings.base_url,
    )
    provider = VolcengineArkFullOrderProvider(settings, transport=transport)
    dictionary = _FakeDictionaryValidator()
    matcher = _FakeMaterialMatcher()
    summary: dict[str, Any] = {}
    root: Path
    with TemporaryDirectory(prefix="bedding-d3c-real-") as raw:
        root = Path(raw)
        service = JobService(
            root / "web",
            store_path=root / "unused-material.sqlite3",
            index_dir=root / "unused-index",
            executor=_DeferredExecutor(),
            ai_enhanced_settings=settings,
            ai_enhanced_dependencies=AIEnhancedDependencies(
                provider=provider,
                dictionary_validator=dictionary,
                material_matcher=matcher,
                provider_name=VOLCENGINE_ARK_PROVIDER,
                model_name=settings.model,
                max_logical_calls=1,
                contract_version=V2_CONTRACT_VERSION,
            ),
        )
        job_id = ""
        exception_type = ""
        try:
            if service.ai_enhanced_preflight()["ready"] is not True:
                raise AcceptanceGateError("Formal JobService V2 preflight is not ready.")
            if transport.http_attempts or provider.extraction_call_count:
                raise AcceptanceGateError("Provider was called before Job creation.")
            job = service.create_job(
                "synthetic-contract-v2.xlsx", content, parse_mode="ai_enhanced"
            )
            job_id = job["id"]
            if transport.http_attempts or provider.extraction_call_count:
                raise AcceptanceGateError("Provider was called during Job creation.")
            stored = service._read_job(job_id)
            stored["ai_user_decision"] = {
                "status": "confirmed",
                "action": "run_ai_enhanced",
                "decided_at": service._now(),
            }
            service._write_job(stored)
            service._run_job(job_id)
        except BaseException as exc:
            exception_type = type(exc).__name__
        finally:
            summary = _safe_summary(
                service,
                job_id,
                provider,
                transport,
                dictionary,
                matcher,
                preflight,
                configuration,
                exception_type=exception_type,
            )
            _assert_no_secret_or_raw_payload_files(root, settings.api_key)
            service.close()
    summary["cleanup"] = {
        "temporary_root_removed": not root.exists(),
        "synthetic_workbook_removed": not root.exists(),
        "raw_provider_payload_files": 0,
        "secret_files": 0,
    }
    return summary


def _configuration_audit(
    settings: LLMSettings, *, require_user_authorization: bool
) -> dict[str, Any]:
    if require_user_authorization:
        import os

        if os.environ.get("ARK_V2_D3C_AUTHORIZATION") != AUTHORIZATION_VALUE:
            raise AcceptanceGateError("Explicit one-call authorization marker is missing.")
    if settings.configuration_status() != "ready":
        raise AcceptanceGateError("Ark configuration is not ready.")
    if settings.provider != VOLCENGINE_ARK_PROVIDER:
        raise AcceptanceGateError("Unexpected Ark provider configuration.")
    if settings.model != APPROVED_MODEL:
        raise AcceptanceGateError("Configured model is not the approved D3C model.")
    if settings.base_url.rstrip("/") != DEFAULT_ARK_BASE_URL:
        raise AcceptanceGateError("Configured Base URL is not the approved Ark endpoint.")
    if settings.max_retries != 0:
        raise AcceptanceGateError("LLM_MAX_RETRIES must be zero.")
    return {
        "provider_enabled": settings.enabled,
        "api_key_present": settings.api_key_configured,
        "model": settings.model,
        "base_url_id": "ark-cn-beijing-api-v3",
        "responses_api": True,
        "stream": False,
        "store": False,
        "provider_retries": settings.max_retries,
        "transport_max_http_attempts": 1,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "sdk_used": False,
        "system_proxy_configured": bool(getproxies()),
        "system_proxy_bypassed": True,
        "transport_auto_retry": False,
    }


def _safe_summary(
    service: JobService,
    job_id: str,
    provider: VolcengineArkFullOrderProvider,
    transport: _BoundedAcceptanceTransport,
    dictionary: _FakeDictionaryValidator,
    matcher: _FakeMaterialMatcher,
    preflight: Mapping[str, Any],
    configuration: Mapping[str, Any],
    *,
    exception_type: str,
) -> dict[str, Any]:
    if not job_id:
        raise AcceptanceGateError("No Job identity exists for a post-run summary.")
    job = service.get_job(job_id)
    execution = job["ai_execution"]
    diagnostic = dict(execution.get("contract_diagnostic", {}))
    if not set(diagnostic) <= _SAFE_DIAGNOSTIC_KEYS:
        raise AcceptanceGateError("Contract diagnostic exceeded its whitelist.")
    roles_complete = all(bool(job["artifact_roles"].get(role)) for role in ARTIFACT_ROLES)
    formal_result_valid = False
    bundle_json_count = 0
    if job["status"] == "completed" and roles_complete:
        official = service.get_preview(job_id, "official_result")
        formal_result_valid = (
            isinstance(official, list)
            and len(official) == 1
            and tuple(official[0]) == FINAL_FIELD_NAMES
            and all(isinstance(official[0][name], str) for name in FINAL_FIELD_NAMES[:-1])
            and isinstance(official[0][FINAL_FIELD_NAMES[-1]], float)
        )
        artifact_paths = [service.artifact_path(job_id, role) for role in ARTIFACT_ROLES]
        if len({path.parent for path in artifact_paths}) == 1:
            bundle_json_count = len(list(artifact_paths[0].parent.glob("*.json")))
    telemetry = provider.latest_telemetry
    request_id_hash = _hash_request_id(telemetry.request_id) or str(
        transport.response_metadata.get("request_id_redacted", "")
    )
    usage = {
        name: int(getattr(telemetry, name, 0))
        for name in ("input_tokens", "output_tokens", "total_tokens")
    }
    if not any(usage.values()):
        usage = {
            name: int(transport.response_metadata.get(name, 0))
            for name in ("input_tokens", "output_tokens", "total_tokens")
        }
    completed = int(execution["completed_chunks"])
    total = int(execution["total_chunks"])
    ready = job["status"] == "completed" and bool(job["has_complete_five_results"])
    safe_stage = (
        "strict_contract_passed"
        if ready
        else str(diagnostic.get("stage") or transport.safe_parse_stage)
    )
    return {
        "configuration": dict(configuration),
        "preflight": dict(preflight),
        "request": dict(transport.request_audit),
        "provider": {
            "provider": VOLCENGINE_ARK_PROVIDER,
            "model": provider.model_name,
            "request_id_redacted": request_id_hash,
            "response_shape": transport.response_shape,
            "safe_parse_stage": safe_stage,
            "logical_extraction_calls": provider.extraction_call_count,
            "layout_calls": provider.structure_call_count,
            "http_attempts": transport.http_attempts,
            "retries": max(0, provider.http_attempt_count - transport.http_attempts),
            "usage": usage,
            "latency_ms": telemetry.latency_ms
            or int(transport.response_metadata.get("latency_ms", 0)),
        },
        "job": {
            "status": job["status"],
            "ai_stage": execution["stage"],
            "safe_error_code": execution["safe_error_code"],
            "contract_diagnostic": diagnostic,
            "completed_chunks": completed,
            "total_chunks": total,
            "ready_for_downstream": ready,
            "fallback_status": job["fallback"]["status"],
            "five_roles_complete": roles_complete,
            "formal_20_fields_valid": formal_result_valid,
            "bundle_json_count": bundle_json_count,
            "sixth_business_json_present": bundle_json_count not in {0, 5},
        },
        "downstream": {
            "fake_dictionary_calls": dictionary.calls,
            "fake_material_calls": matcher.calls,
        },
        "harness": {
            "exception_type": exception_type,
            "safe_summary_created_before_cleanup": True,
        },
    }


def _validated_bounded_body(
    request: JSONHTTPRequest,
    *,
    expected_url: str,
    expected_model: str,
    expected_fixture_sha256: str,
) -> dict[str, Any]:
    if request.method != "POST" or request.url != expected_url:
        raise AcceptanceGateError("Unexpected Ark HTTP target.")
    if "Authorization" not in request.headers:
        raise AcceptanceGateError("Ark authentication header is missing.")
    try:
        body = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceGateError("Ark request body is not JSON.") from exc
    if not isinstance(body, dict):
        raise AcceptanceGateError("Ark request body must be an object.")
    if body.get("model") != expected_model:
        raise AcceptanceGateError("Ark request model changed before transport.")
    if body.get("store") is not False or body.get("stream", False) is not False:
        raise AcceptanceGateError("Ark request must be non-streaming with store=false.")
    if "max_output_tokens" in body:
        value = body["max_output_tokens"]
        if isinstance(value, bool) or not isinstance(value, int) or value > MAX_OUTPUT_TOKENS:
            raise AcceptanceGateError("Ark output budget exceeds the D3C limit.")
    tools = body.get("tools")
    choice = body.get("tool_choice")
    if (
        not isinstance(tools, list)
        or len(tools) != 1
        or tools[0].get("strict") is not True
        or tools[0].get("name") != FULL_ORDER_V2_EXTRACTION_FUNCTION
        or not isinstance(choice, dict)
        or choice.get("name") != FULL_ORDER_V2_EXTRACTION_FUNCTION
    ):
        raise AcceptanceGateError("Ark request is not the strict V2 extraction function.")
    inputs = body.get("input")
    try:
        user_text = inputs[1]["content"][0]["text"]
        payload = json.loads(user_text)
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise AcceptanceGateError("Ark V2 user payload is not safely readable.") from exc
    validate_full_order_v2_request(payload)
    _validate_synthetic_request(payload, expected_fixture_sha256)
    serialized = json.dumps(body, ensure_ascii=False)
    if "C:\\" in serialized or "job_id" in serialized or "ARK_API_KEY" in serialized:
        raise AcceptanceGateError("Ark request contains forbidden local or secret metadata.")
    return body


def _validate_synthetic_request(
    payload: Mapping[str, Any], expected_fixture_sha256: str
) -> None:
    if payload.get("source_file_sha256") != expected_fixture_sha256:
        raise AcceptanceGateError("V2 request does not match the synthetic fixture SHA.")
    evidence = payload.get("evidence_catalog")
    if not isinstance(evidence, list) or not evidence:
        raise AcceptanceGateError("Synthetic V2 evidence catalog is empty.")
    original_texts = {str(item.get("original_text", "")) for item in evidence}
    if not original_texts <= _SYNTHETIC_CELL_VALUES:
        raise AcceptanceGateError("V2 request contains non-synthetic evidence text.")
    forbidden = ("bank", "account", "iban", "swift", "payment", "地址", "银行", "付款")
    combined = " ".join(original_texts).casefold()
    if any(token in combined for token in forbidden):
        raise AcceptanceGateError("Synthetic request contains a forbidden data category.")


def _response_shape(response: JSONHTTPResponse) -> str:
    if not 200 <= response.status_code < 300:
        return "http_error"
    try:
        payload = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "invalid_json"
    if not isinstance(payload, dict):
        return "non_object_json"
    output = payload.get("output")
    if isinstance(output, list) and any(
        isinstance(item, dict)
        and item.get("type") == "function_call"
        and item.get("name") == FULL_ORDER_V2_EXTRACTION_FUNCTION
        for item in output
    ):
        return "function_call"
    if isinstance(payload.get("output_text"), str):
        return "output_text"
    return "other_completed_shape"


def _safe_response_metadata(
    response: JSONHTTPResponse, *, expected_model: str
) -> dict[str, Any]:
    try:
        payload = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    payload = payload if isinstance(payload, dict) else {}
    usage = payload.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    request_id = str(
        payload.get("id")
        or response.headers.get("x-request-id")
        or response.headers.get("request-id")
        or ""
    )
    model = payload.get("model")
    return {
        "request_id_redacted": _hash_request_id(request_id),
        "model": expected_model if model == expected_model else "unexpected_or_missing",
        "input_tokens": _safe_non_negative_int(usage.get("input_tokens")),
        "output_tokens": _safe_non_negative_int(usage.get("output_tokens")),
        "total_tokens": _safe_non_negative_int(usage.get("total_tokens")),
        "latency_ms": max(0, int(response.elapsed_ms)),
    }


def _hash_request_id(value: str) -> str:
    if not value:
        return ""
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]}"


def _safe_non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return 0
    if not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


def _stable_xlsx(content: bytes) -> bytes:
    source = BytesIO(content)
    target = BytesIO()
    with zipfile.ZipFile(source, "r") as archive, zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as stable:
        for original in sorted(archive.infolist(), key=lambda item: item.filename):
            info = zipfile.ZipInfo(original.filename, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = original.create_system
            info.external_attr = original.external_attr
            data = archive.read(original.filename)
            if original.filename == "docProps/core.xml":
                data = _canonical_core_properties(data)
            stable.writestr(info, data)
    return target.getvalue()


def _canonical_core_properties(data: bytes) -> bytes:
    fixed = b"2026-01-01T00:00:00Z"
    for name in (b"created", b"modified"):
        pattern = re.compile(
            rb"(<dcterms:" + name + rb"[^>]*>)[^<]*(</dcterms:" + name + rb">)"
        )
        data, count = pattern.subn(
            lambda match: match.group(1) + fixed + match.group(2), data
        )
        if count != 1:
            raise AcceptanceGateError("Synthetic workbook core timestamp is not canonical.")
    return data


def _assert_no_secret_or_raw_payload_files(root: Path, api_key: str) -> None:
    forbidden_names = ("raw_response", "provider_response", "request_body", "authorization")
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(name in path.name.casefold() for name in forbidden_names):
            raise AcceptanceGateError("A raw provider payload file was created.")
        content = path.read_bytes()
        if api_key and api_key.encode("utf-8") in content:
            raise AcceptanceGateError("An API key was persisted in the temporary root.")
        if b"Authorization" in content:
            raise AcceptanceGateError("An Authorization header was persisted.")


def _normalized_headers(headers: object) -> dict[str, str]:
    items = getattr(headers, "items", None)
    if not callable(items):
        return {}
    return {str(key).lower(): str(value) for key, value in items()}


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def test_synthetic_fixture_is_deterministic_and_passes_the_local_hard_gate() -> None:
    first = synthetic_workbook_bytes()
    second = synthetic_workbook_bytes()
    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
    preflight = offline_preflight(first)
    assert preflight["structure_status"] == "locally_resolved"
    assert preflight["record_count"] == preflight["extraction_unit_count"] == 1
    assert preflight["required_direct_field_count"] == 5
    assert preflight["layout_calls"] == preflight["http_attempts"] == 0


def test_synthetic_fixture_sha_is_stable_across_python_processes() -> None:
    command = (
        "import hashlib,runpy;"
        "ns=runpy.run_path(r'tests\\ai_full_order\\test_ark_v2_single_real_acceptance.py');"
        "print(hashlib.sha256(ns['synthetic_workbook_bytes']()).hexdigest())"
    )
    first = subprocess.check_output([sys.executable, "-c", command], text=True).strip()
    second = subprocess.check_output([sys.executable, "-c", command], text=True).strip()
    assert first == second


def test_bounded_harness_completes_formal_v2_job_with_fake_transport() -> None:
    settings = LLMSettings(
        enabled=True,
        provider=VOLCENGINE_ARK_PROVIDER,
        model=APPROVED_MODEL,
        base_url=DEFAULT_ARK_BASE_URL,
        api_key="offline-only-secret",
        max_retries=0,
    )
    inner = _StaticArkTransport()
    summary = run_acceptance(
        settings,
        inner,
        require_user_authorization=False,
    )
    assert summary["job"]["status"] == "completed"
    assert summary["provider"]["logical_extraction_calls"] == 1
    assert summary["provider"]["layout_calls"] == 0
    assert summary["provider"]["http_attempts"] == 1
    assert summary["request"]["max_output_tokens"] == MAX_OUTPUT_TOKENS
    assert summary["downstream"] == {
        "fake_dictionary_calls": 1,
        "fake_material_calls": 1,
    }
    assert summary["job"]["formal_20_fields_valid"] is True
    assert summary["job"]["bundle_json_count"] == 5
    assert summary["job"]["sixth_business_json_present"] is False
    assert summary["cleanup"]["temporary_root_removed"] is True
    assert inner.calls == 1


def test_retry_configuration_is_rejected_before_any_transport_call() -> None:
    settings = LLMSettings(
        enabled=True,
        provider=VOLCENGINE_ARK_PROVIDER,
        model=APPROVED_MODEL,
        base_url=DEFAULT_ARK_BASE_URL,
        api_key="offline-only-secret",
        max_retries=1,
    )
    inner = _StaticArkTransport()
    with pytest.raises(AcceptanceGateError, match="must be zero"):
        run_acceptance(
            settings,
            inner,
            require_user_authorization=False,
        )
    assert inner.calls == 0


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true")
    args = parser.parse_args()
    if not args.real:
        raise AcceptanceGateError("Manual harness requires the explicit --real flag.")
    summary = run_acceptance(
        LLMSettings.from_environment(),
        _SingleAttemptDirectTransport(),
        require_user_authorization=True,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
