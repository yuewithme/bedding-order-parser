from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

import pytest
from openpyxl import Workbook

from bedding_order_parser.ai_full_order.downstream import (
    MaterialMatchOutput,
    MaterialSelection,
)
from bedding_order_parser.ai_full_order.fake_provider import FakeFullOrderProvider
from bedding_order_parser.ai_full_order.volcengine_ark import (
    FULL_ORDER_EXTRACTION_FUNCTION,
)
from bedding_order_parser.llm.settings import LLMSettings
from bedding_order_parser.llm.transport import (
    JSONHTTPRequest,
    JSONHTTPResponse,
    UrllibJSONTransport,
)
from bedding_order_parser.models.final_result import FINAL_FIELD_NAMES
from bedding_order_parser.web.services import ARTIFACT_ROLES, JobService


_TEST_SECRET = "diagnostic-test-secret-never-log"
_SAFE_SHAPES = frozenset({"function_call", "top_level_output_text", "message_output_text", "none"})
_SAFE_STAGES = frozenset({"", "http_status", "strict_schema", "evidence_reference", "transport_failure"})
_SAFE_DIAGNOSTIC_KEYS = frozenset(
    {
        "stage", "category", "path", "expected_type", "actual_type",
        "missing_fixed_fields", "extra_field_count", "forbidden_fields",
    }
)


@pytest.fixture(autouse=True)
def _block_real_network(monkeypatch):
    monkeypatch.setattr(
        UrllibJSONTransport,
        "send",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("real network forbidden in D2B diagnostics")
        ),
    )


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
        assert evidence
        return {
            "validation_version": "1.0",
            "mode": "validation_only",
            "status": "completed",
            "records": [{"行号": record.line_number} for record in records],
        }


class _FakeMaterialMatcher:
    def __init__(self) -> None:
        self.calls = 0

    def match(self, records, resolved):
        self.calls += 1
        selections = {
            item.source_record_id: MaterialSelection(
                item.source_record_id, "SYN-MAT-001", 0.75
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


class _ClassifyingFakeTransport:
    """Classify synthetic responses in memory without retaining request or response bytes."""

    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.http_attempts = 0
        self.response_shape = "none"
        self.safe_parse_stage = ""

    def send(self, request: JSONHTTPRequest) -> JSONHTTPResponse:
        self.http_attempts += 1
        request_body = json.loads(request.body.decode("utf-8"))
        assert request_body["store"] is False
        assert request_body.get("stream", False) is False
        assert request_body["tool_choice"]["name"] == FULL_ORDER_EXTRACTION_FUNCTION
        source = json.loads(request_body["input"][1]["content"][0]["text"])
        assert source["parse_mode"] == "ai_enhanced"
        assert source["structure_status"] == "locally_resolved"
        assert source["record_count"] == 1
        serialized = json.dumps(request_body, ensure_ascii=False)
        assert _TEST_SECRET not in serialized
        assert "Authorization" not in serialized
        assert "C:\\" not in serialized and "D:\\" not in serialized
        assert "PK\\x03\\x04" not in serialized

        if self.scenario == "http_failure":
            self.safe_parse_stage = "http_status"
            return JSONHTTPResponse(
                400,
                {"x-request-id": "synthetic-http-failure"},
                b'{"error":{"type":"invalid_request"}}',
                1,
            )

        payload = FakeFullOrderProvider().extract(source)
        response_usage: object = {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}
        if self.scenario == "strict_schema_failure":
            payload["records"][0]["fields"]["物料编码"] = {}
            self.safe_parse_stage = "strict_schema"
        elif self.scenario == "missing_required":
            payload["records"][0]["fields"].pop("物料名称")
        elif self.scenario == "unknown_extra":
            payload["records"][0]["fields"]["untrusted_generated_field"] = {}
        elif self.scenario == "wrong_type":
            payload["record_count"] = "not-a-count"
        elif self.scenario == "invalid_enum":
            payload["records"][0]["fields"]["物料名称"]["extraction_status"] = "guessed"
        elif self.scenario == "source_sha":
            payload["source_file_sha256"] = "synthetic-mismatch"
        elif self.scenario == "record_identity":
            payload["records"][0]["record_local_id"] = "synthetic-other-record"
        elif self.scenario == "scope":
            payload["records"][0]["scope_id"] = "synthetic-other-scope"
        elif self.scenario == "evidence_failure":
            payload["records"][0]["fields"]["物料名称"]["evidence_references"] = [
                "forged:evidence"
            ]
            self.safe_parse_stage = "evidence_reference"
        elif self.scenario == "untraceable_evidence":
            field = payload["records"][0]["fields"]["物料名称"]
            field["value"] = field["original_value"] = "untraceable-generated-value"
        elif self.scenario == "invalid_usage":
            response_usage = "not-an-object"
        self.response_shape = "function_call"
        response = {
            "id": "synthetic-response-id",
            "model": "synthetic-ark-model",
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": FULL_ORDER_EXTRACTION_FUNCTION,
                    "arguments": json.dumps(payload, ensure_ascii=False),
                }
            ],
            "usage": response_usage,
        }
        return JSONHTTPResponse(
            200,
            {"x-request-id": "synthetic-header-id"},
            json.dumps(response, ensure_ascii=False).encode("utf-8"),
            1,
        )


@dataclass(frozen=True)
class AcceptanceSummary:
    payload: dict[str, Any]
    exception_type: str = ""


def _settings() -> LLMSettings:
    return LLMSettings(
        enabled=True,
        provider="volcengine_ark",
        model="synthetic-ark-model",
        base_url="https://ark.test/api/v3",
        api_key=_TEST_SECRET,
        max_retries=0,
    )


def _workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "SYNTHETIC"
    sheet.append(["No.", "Item", "Specification", "Qty"])
    sheet.append(["1", "Duvet Cover", "White cotton", "12"])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _service(root: Path, scenario: str) -> tuple[JobService, _ClassifyingFakeTransport, _FakeDictionaryValidator, _FakeMaterialMatcher]:
    transport = _ClassifyingFakeTransport(scenario)
    dictionary = _FakeDictionaryValidator()
    matcher = _FakeMaterialMatcher()
    service = JobService(
        root / "web",
        store_path=root / "unused-material.sqlite3",
        index_dir=root / "unused-index",
        executor=_DeferredExecutor(),
        ai_enhanced_settings=_settings(),
        ai_enhanced_transport=transport,
        ai_enhanced_dictionary_validator=dictionary,
        ai_enhanced_material_matcher=matcher,
        desktop_mode=True,
    )
    return service, transport, dictionary, matcher


def _redact_request_id(value: object) -> str:
    text = str(value)
    if not text:
        return ""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _safe_summary(
    service: JobService,
    job_id: str,
    transport: _ClassifyingFakeTransport,
    *,
    exception: BaseException | None = None,
) -> AcceptanceSummary:
    job = service.get_job(job_id)
    execution = job["ai_execution"]
    provider = service.ai_enhanced_dependencies.provider
    roles = job["artifact_roles"]
    status = str(job["status"])
    summary = {
        "harness": {
            "exception_type": type(exception).__name__ if exception else "",
        },
        "job": {
            "status": status,
            "ai_stage": str(execution["stage"]),
            "safe_error_code": str(execution["safe_error_code"]),
            "display_message": str(job["error"])[:180],
            "fallback_status": str(job["fallback"]["status"]),
        },
        "provider": {
            "provider": str(execution["provider"]),
            "model": str(execution["model"]),
            "request_id_redacted": _redact_request_id(execution["request_id"]),
            "logical_calls": int(execution["logical_call_count"]),
            "http_attempts": int(execution["http_attempt_count"]),
            "usage": dict(execution["token_summary"]),
            "latency_ms": int(getattr(provider.latest_telemetry, "latency_ms", 0)),
            "response_shape": transport.response_shape,
            "safe_parse_stage": transport.safe_parse_stage,
            "contract_diagnostic": dict(execution.get("contract_diagnostic", {})),
        },
        "chunks": {
            "completed": int(execution["completed_chunks"]),
            "total": int(execution["total_chunks"]),
            "failed_or_unvalidated": max(
                0, int(execution["total_chunks"]) - int(execution["completed_chunks"])
            ),
        },
        "gates": {
            "ready_for_downstream": status == "completed" and job["has_complete_five_results"],
            "five_roles_complete": all(bool(roles[name]) for name in ARTIFACT_ROLES),
            "schema_failure": transport.safe_parse_stage == "strict_schema",
            "identity_failure": False,
            "scope_failure": False,
            "evidence_failure": transport.safe_parse_stage == "evidence_reference",
            "field_resolution_failure": False,
            "downstream_failure": str(execution["safe_error_code"]) == "AI_DOWNSTREAM_FAILED",
            "publication_failure": str(execution["safe_error_code"]) == "AI_DOWNSTREAM_FAILED",
        },
    }
    assert summary["provider"]["response_shape"] in _SAFE_SHAPES
    assert summary["provider"]["safe_parse_stage"] in _SAFE_STAGES
    assert set(summary["provider"]["contract_diagnostic"]).issubset(_SAFE_DIAGNOSTIC_KEYS)
    serialized = json.dumps(summary, ensure_ascii=False)
    for forbidden in (_TEST_SECRET, "Authorization", '"arguments"', '"output"', '"input"'):
        assert forbidden not in serialized
    return AcceptanceSummary(summary, type(exception).__name__ if exception else "")


@pytest.mark.parametrize(
    ("scenario", "stage", "category"),
    [
        ("missing_required", "output_schema", "missing_required_fields"),
        ("unknown_extra", "output_schema", "extra_fields"),
        ("strict_schema_failure", "forbidden_fields", "extra_fields"),
        ("wrong_type", "output_schema", "type_mismatch"),
        ("invalid_enum", "output_schema", "enum_or_constant_mismatch"),
        ("source_sha", "identity_validation", "source_file_sha256_mismatch"),
        ("record_identity", "identity_validation", "record_identity_mismatch"),
        ("scope", "identity_validation", "scope_mismatch"),
        ("evidence_failure", "evidence_validation", "evidence_id_missing"),
        ("untraceable_evidence", "evidence_validation", "evidence_untraceable"),
        ("invalid_usage", "provider_metadata", "provider_metadata_or_usage"),
    ],
)
def test_contract_fault_matrix_pauses_before_downstream_and_keeps_only_whitelisted_diagnostics(
    scenario: str, stage: str, category: str
) -> None:
    with tempfile.TemporaryDirectory(prefix="bedding-d2d-contract-") as raw:
        root = Path(raw)
        service, transport, dictionary, matcher = _service(root, scenario)
        try:
            job = service.create_job("synthetic.xlsx", _workbook_bytes(), parse_mode="ai_enhanced")
            summary = _run_with_summary(service, job["id"], transport)
            diagnostic = summary.payload["provider"]["contract_diagnostic"]
            assert summary.payload["job"]["status"] == "awaiting_user_decision"
            assert diagnostic["stage"] == stage
            assert diagnostic["category"] == category
            assert summary.payload["gates"]["five_roles_complete"] is False
            assert dictionary.calls == matcher.calls == 0
            assert transport.http_attempts == 1
            serialized = json.dumps(summary.payload, ensure_ascii=False)
            assert "untrusted_generated_field" not in serialized
            assert "untraceable-generated-value" not in serialized
            assert '"arguments"' not in serialized
            if scenario == "strict_schema_failure":
                assert diagnostic["forbidden_fields"] == ["物料编码"]
            if scenario == "unknown_extra":
                assert diagnostic["extra_field_count"] == 1
                assert "forbidden_fields" not in diagnostic
        finally:
            service.close()
    assert not root.exists()


def _run_with_summary(
    service: JobService,
    job_id: str,
    transport: _ClassifyingFakeTransport,
    *,
    after_run: Callable[[], None] | None = None,
) -> AcceptanceSummary:
    exception: BaseException | None = None
    try:
        stored = service._read_job(job_id)
        stored["ai_contract_version"] = "1.0"
        stored["ai_contract_source"] = "explicit_legacy_v1_test"
        service._write_job(stored)
        service._run_job(job_id)
        if after_run is not None:
            after_run()
    except BaseException as exc:  # The acceptance harness must survive assertion failures.
        exception = exc
    finally:
        summary = _safe_summary(service, job_id, transport, exception=exception)
    return summary


def test_synthetic_fixture_completes_real_provider_boundary_and_five_role_publication() -> None:
    with tempfile.TemporaryDirectory(prefix="bedding-d2b-success-") as raw:
        root = Path(raw)
        service, transport, dictionary, matcher = _service(root, "success")
        try:
            job = service.create_job("synthetic.xlsx", _workbook_bytes(), parse_mode="ai_enhanced")
            summary = _run_with_summary(service, job["id"], transport)
            official = service.get_preview(job["id"], "official_result")
            assert summary.exception_type == ""
            assert summary.payload["job"]["status"] == "completed"
            assert summary.payload["provider"]["response_shape"] == "function_call"
            assert summary.payload["provider"]["logical_calls"] == 1
            assert summary.payload["provider"]["http_attempts"] == 1
            assert summary.payload["provider"]["usage"] == {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}
            assert summary.payload["gates"]["ready_for_downstream"] is True
            assert summary.payload["gates"]["five_roles_complete"] is True
            assert dictionary.calls == matcher.calls == 1
            assert list(official[0]) == list(FINAL_FIELD_NAMES)
            assert isinstance(official[0]["相似分数"], float)
        finally:
            service.close()
        assert root.exists()
    assert not root.exists()


def test_http_failure_forms_safe_awaiting_summary_before_cleanup() -> None:
    with tempfile.TemporaryDirectory(prefix="bedding-d2b-http-") as raw:
        root = Path(raw)
        service, transport, dictionary, matcher = _service(root, "http_failure")
        try:
            job = service.create_job("synthetic.xlsx", _workbook_bytes(), parse_mode="ai_enhanced")
            summary = _run_with_summary(service, job["id"], transport)
            assert summary.payload["job"]["status"] == "awaiting_user_decision"
            assert summary.payload["job"]["safe_error_code"] == "AI_SCHEMA_OR_EVIDENCE_FAILED"
            assert summary.payload["provider"]["provider"] == "volcengine_ark"
            assert summary.payload["provider"]["model"] == "synthetic-ark-model"
            assert summary.payload["provider"]["request_id_redacted"].startswith("sha256:")
            assert summary.payload["provider"]["http_attempts"] == 1
            assert summary.payload["provider"]["usage"] == {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }
            assert summary.payload["provider"]["safe_parse_stage"] == "http_status"
            assert summary.payload["gates"]["five_roles_complete"] is False
            assert dictionary.calls == matcher.calls == 0
        finally:
            service.close()
    assert not root.exists()


def test_strict_response_failure_forms_schema_summary_before_cleanup() -> None:
    with tempfile.TemporaryDirectory(prefix="bedding-d2b-schema-") as raw:
        root = Path(raw)
        service, transport, dictionary, matcher = _service(root, "strict_schema_failure")
        try:
            provider = service.ai_enhanced_dependencies.provider
            provider.usage_summary.update(
                input_tokens=600,
                output_tokens=400,
                total_tokens=1000,
            )
            job = service.create_job("synthetic.xlsx", _workbook_bytes(), parse_mode="ai_enhanced")
            summary = _run_with_summary(service, job["id"], transport)
            assert summary.payload["job"]["status"] == "awaiting_user_decision"
            assert summary.payload["provider"]["response_shape"] == "function_call"
            assert summary.payload["provider"]["safe_parse_stage"] == "strict_schema"
            assert summary.payload["provider"]["request_id_redacted"].startswith("sha256:")
            assert summary.payload["provider"]["usage"] == {
                "input_tokens": 11,
                "output_tokens": 7,
                "total_tokens": 18,
            }
            assert provider.usage_summary["total_tokens"] == 1018
            assert summary.payload["gates"]["schema_failure"] is True
            assert summary.payload["gates"]["ready_for_downstream"] is False
            assert dictionary.calls == matcher.calls == 0
        finally:
            service.close()
    assert not root.exists()


def test_forged_evidence_forms_evidence_summary_before_cleanup() -> None:
    with tempfile.TemporaryDirectory(prefix="bedding-d2b-evidence-") as raw:
        root = Path(raw)
        service, transport, dictionary, matcher = _service(root, "evidence_failure")
        try:
            job = service.create_job("synthetic.xlsx", _workbook_bytes(), parse_mode="ai_enhanced")
            summary = _run_with_summary(service, job["id"], transport)
            assert summary.payload["job"]["status"] == "awaiting_user_decision"
            assert summary.payload["provider"]["safe_parse_stage"] == "evidence_reference"
            assert summary.payload["gates"]["evidence_failure"] is True
            assert summary.payload["gates"]["five_roles_complete"] is False
            assert dictionary.calls == matcher.calls == 0
        finally:
            service.close()
    assert not root.exists()


def test_summary_survives_assertion_then_captures_failed_and_interrupted_states() -> None:
    with tempfile.TemporaryDirectory(prefix="bedding-d2b-states-") as raw:
        root = Path(raw)
        service, transport, _dictionary, _matcher = _service(root, "http_failure")
        try:
            job = service.create_job("synthetic.xlsx", _workbook_bytes(), parse_mode="ai_enhanced")
            awaiting = _run_with_summary(service, job["id"], transport)
            assert awaiting.payload["job"]["status"] == "awaiting_user_decision"
            service.keep_failed(job["id"])
            failed = _safe_summary(service, job["id"], transport)
            assert failed.payload["job"]["status"] == "failed"

            interrupted_job = service.create_job("interrupted.xlsx", _workbook_bytes(), parse_mode="ai_enhanced")
            interrupted_stored = service._read_job(interrupted_job["id"])
            interrupted_stored["ai_contract_version"] = "1.0"
            interrupted_stored["ai_contract_source"] = "explicit_legacy_v1_test"
            service._write_job(interrupted_stored)
            service._set_ai_progress(interrupted_job["id"], "preprocessing", 0, 1, 0)
            service.interrupt_active_jobs()
            interrupted = _safe_summary(service, interrupted_job["id"], transport)
            assert interrupted.payload["job"]["status"] == "interrupted"

            success_service, success_transport, _dictionary, _matcher = _service(root / "assertion", "success")
            try:
                success_job = success_service.create_job("synthetic.xlsx", _workbook_bytes(), parse_mode="ai_enhanced")
                assertion_summary = _run_with_summary(
                    success_service,
                    success_job["id"],
                    success_transport,
                    after_run=lambda: (_ for _ in ()).throw(AssertionError("injected assertion")),
                )
                assert assertion_summary.exception_type == "AssertionError"
                assert assertion_summary.payload["harness"]["exception_type"] == "AssertionError"
                assert assertion_summary.payload["job"]["status"] == "completed"
                assert assertion_summary.payload["gates"]["five_roles_complete"] is True
            finally:
                success_service.close()
        finally:
            service.close()
        assert root.exists()
    assert not root.exists()
