from __future__ import annotations

import json
import threading
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from openpyxl import Workbook

from bedding_order_parser.ai_full_order.downstream import (
    MaterialMatchOutput,
    MaterialSelection,
)
from bedding_order_parser.ai_full_order.fake_provider import FakeV2CandidateProvider
from bedding_order_parser.llm.settings import LLMSettings, VOLCENGINE_ARK_PROVIDER
from bedding_order_parser.models.final_result import FINAL_FIELD_NAMES
from bedding_order_parser.web.ai_full_order_service import AIEnhancedDependencies
from bedding_order_parser.web.app import create_server
from bedding_order_parser.web.services import JobService


WEB_ROOT = Path(__file__).resolve().parents[2] / "src" / "bedding_order_parser" / "web"


class _ImmediateExecutor:
    def submit(self, function, *args) -> None:
        function(*args)

    def shutdown(self, **_kwargs) -> None:
        return None


class _V2OnlyProvider(FakeV2CandidateProvider):
    def __init__(self, payload=None) -> None:
        super().__init__(payload or {"candidates": []})
        self.v1_extraction_call_count = 0

    def extract(self, _request):
        self.v1_extraction_call_count += 1
        raise AssertionError("new UI jobs must not call V1 extraction")

    def extract_v2(self, request):
        return FakeV2CandidateProvider.extract(self, request)


class _OrdinaryIssueProvider(_V2OnlyProvider):
    def extract_v2(self, request):
        evidence_id = request["evidence_catalog"][0]["evidence_id"]
        self.payload = {
            "candidates": [
                {
                    "field_name": "包装方式",
                    "candidate_value": "invented packaging",
                    "evidence_references": [evidence_id],
                    "interpretation": "direct",
                    "supporting_quote": "",
                }
            ]
        }
        return super().extract_v2(request)


class _HardFailureProvider(_V2OnlyProvider):
    def extract_v2(self, request):
        self.payload = {
            "candidates": [
                {
                    "field_name": "颜色",
                    "candidate_value": "white",
                    "evidence_references": ["unknown-evidence"],
                    "interpretation": "direct",
                    "supporting_quote": "",
                }
            ]
        }
        return super().extract_v2(request)


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
            record.source_record_id: MaterialSelection(
                record.source_record_id, "MAT-UI", 0.5
            )
            for record in resolved
        }
        return MaterialMatchOutput(
            selections=selections,
            candidates_payload={
                "mode": "manual_review_only",
                "record_count": len(records),
                "records": [],
            },
            summary_payload={
                "mode": "manual_review_only",
                "record_count": len(records),
                "accuracy_statement": "相似分数不是准确率，候选只用于人工复核。",
            },
        )


def _workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "PI"
    sheet.append(["", "PROFORMA INVOICE", "", "", "Unit Price (USD)"])
    sheet.append(["BUYER:", "", "", "", ""])
    sheet.append(["Synthetic Hotel", "", "", "", "Contact Person: Aaron Lee"])
    sheet.append(["Delivery date:", "2026-09-30", "", "", ""])
    sheet.append(["No.", "Item", "Size", "Specification", "Qty"])
    sheet.append(["1", "Duvet Cover", "200*240", "100% cotton white", "12"])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _service(tmp_path: Path, provider) -> tuple[JobService, _FakeDictionaryValidator, _FakeMaterialMatcher]:
    dictionary = _FakeDictionaryValidator()
    matcher = _FakeMaterialMatcher()
    return (
        JobService(
            tmp_path / "web",
            store_path=tmp_path / "material.sqlite3",
            index_dir=tmp_path / "index",
            executor=_ImmediateExecutor(),
            ai_enhanced_dependencies=AIEnhancedDependencies(
                provider=provider,
                dictionary_validator=dictionary,
                material_matcher=matcher,
            ),
        ),
        dictionary,
        matcher,
    )


def _server_url(service: JobService):
    server = create_server(port=0, service=service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        service.close()


def _json(url: str) -> dict:
    with urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _upload(url: str, content: bytes, *, mode: str) -> dict:
    boundary = "----D3B2DUIBoundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="synthetic.xlsx"\r\n'
        "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
    ).encode() + content + (
        f"\r\n--{boundary}\r\n"
        'Content-Disposition: form-data; name="parse_mode"\r\n\r\n'
        f"{mode}\r\n--{boundary}--\r\n"
    ).encode()
    request = Request(
        f"{url}/api/jobs",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )
    with urlopen(request, timeout=10) as response:
        assert response.status == 201
        return json.loads(response.read().decode("utf-8"))


def test_ui_source_keeps_v2_mode_selectable_when_configuration_is_not_ready() -> None:
    script = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'const AI_FULL_ORDER_UI_VERSION = "v2-ui-2026-08-05"' in script
    assert "const aiAvailable = state.aiPreflight.v2_backend_available === true;" in script
    assert "const aiReady = state.aiPreflight.provider_ready === true;" in script
    assert '内部合同：${escapeHtml(job.ai_contract_label || ai.contract_version || "未标记")}' in script
    assert "${aiAvailable ? \"\" : \"disabled\"}" in script
    assert "state.selectedParseMode = \"standard\"" not in script.split("function renderUpload()", 1)[1].split("function selectFile", 1)[0]
    assert "state.aiPreflight.v2_backend_available === true" in script
    assert "state.aiPreflight.provider_ready !== true" in script
    assert "unavailable_reason_text" in script
    assert "AI_V2_CONTRACT_FAILED" in script
    assert "AI_V2_STRUCTURE_MANIFEST_INVALID" in script
    assert "AI_V2_STRUCTURE_PROVIDER_FAILED" in script
    assert "@media (max-width: 600px)" in styles
    assert ".parse-mode-picker, .job-detail-grid, .confirm-list { grid-template-columns: 1fr; }" in styles


def test_current_local_server_serves_v2_ui_assets_without_provider_calls(tmp_path: Path) -> None:
    provider = _V2OnlyProvider()
    service, _dictionary, _matcher = _service(tmp_path, provider)

    for base_url in _server_url(service):
        with urlopen(f"{base_url}/", timeout=5) as response:
            page = response.read().decode("utf-8")
        with urlopen(f"{base_url}/static/app.js", timeout=5) as response:
            script = response.read().decode("utf-8")
        capabilities = _json(f"{base_url}/api/capabilities")
        preflight = _json(f"{base_url}/api/ai-enhanced/preflight")

    assert 'src="/static/app.js"' in page
    assert "v2-ui-2026-08-05" in script
    assert capabilities["ai_full_order"]["v2_backend_available"] is True
    assert preflight["provider_ready"] is True
    assert provider.extraction_call_count == provider.structure_call_count == 0
    assert provider.network_call_count == 0


def test_ready_ui_submission_creates_v2_job_and_publishes_five_roles(tmp_path: Path) -> None:
    provider = _V2OnlyProvider()
    service, dictionary, matcher = _service(tmp_path, provider)

    for base_url in _server_url(service):
        created = _upload(base_url, _workbook_bytes(), mode="ai_enhanced")
        job = _json(f"{base_url}/api/jobs/{created['id']}")
        review = _json(f"{base_url}/api/jobs/{created['id']}/ai-review")
        official = _json(f"{base_url}/api/jobs/{created['id']}/artifacts/official_result/preview")
        history = _json(f"{base_url}/api/jobs")
        _json(f"{base_url}/api/jobs/{created['id']}/artifacts/material_summary/preview")
        for role in (
            "official_result",
            "parse_diagnostics",
            "dictionary_validation",
            "material_candidates",
            "material_summary",
        ):
            with urlopen(
                f"{base_url}/api/jobs/{created['id']}/artifacts/{role}/download",
                timeout=5,
            ) as response:
                assert response.status == 200

    assert created["parse_mode"] == "ai_enhanced"
    assert created["ai_contract_version"] == "2.0"
    assert job["status"] == "completed"
    assert job["ai_contract_version"] == job["ai_execution"]["contract_version"] == "2.0"
    assert job["has_complete_five_results"] is True
    assert all(job["artifact_roles"].values())
    assert job["ai_review_summary"]["available"] is True
    assert review["available"] is True
    assert review["summary"]["technical_ready"] is True
    assert len(review["items"]) == len(FINAL_FIELD_NAMES) - 3
    assert list(official[0]) == list(FINAL_FIELD_NAMES)
    assert provider.extraction_call_count == 1
    assert provider.v1_extraction_call_count == 0
    assert provider.structure_call_count == provider.network_call_count == 0
    assert dictionary.calls == matcher.calls == 1
    assert history["jobs"][0]["parse_mode"] == "ai_enhanced"


def test_not_ready_ui_state_allows_selection_but_api_blocks_ai_submission(tmp_path: Path) -> None:
    settings = LLMSettings(
        enabled=True,
        provider=VOLCENGINE_ARK_PROVIDER,
        model="synthetic-model",
        api_key="",
    )
    service = JobService(
        tmp_path / "web",
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=_ImmediateExecutor(),
        ai_enhanced_settings=settings,
    )

    for base_url in _server_url(service):
        preflight = _json(f"{base_url}/api/ai-enhanced/preflight")
        with pytest.raises(HTTPError) as caught:
            _upload(base_url, _workbook_bytes(), mode="ai_enhanced")
        failure = json.loads(caught.value.read().decode("utf-8"))

    assert preflight["v2_backend_available"] is True
    assert preflight["provider_configured"] is False
    assert preflight["provider_ready"] is False
    assert preflight["unavailable_reason_code"] == "AI_API_KEY_MISSING"
    assert "API Key" in preflight["unavailable_reason_text"]
    assert failure["error"] == preflight["unavailable_reason_text"]
    assert service.list_jobs() == []


@pytest.mark.parametrize(
    ("provider_type", "expected_status", "expected_isolated", "downstream_calls"),
    [
        (_HardFailureProvider, "awaiting_user_decision", 0, 0),
        (_OrdinaryIssueProvider, "completed", 1, 1),
    ],
)
def test_ui_job_states_keep_hard_failure_and_field_isolation_distinct(
    tmp_path: Path,
    provider_type,
    expected_status: str,
    expected_isolated: int,
    downstream_calls: int,
) -> None:
    provider = provider_type()
    service, dictionary, matcher = _service(tmp_path, provider)

    for base_url in _server_url(service):
        created = _upload(base_url, _workbook_bytes(), mode="ai_enhanced")
        job = _json(f"{base_url}/api/jobs/{created['id']}")

    assert job["status"] == expected_status
    assert job["ai_execution"]["isolated_field_count"] == expected_isolated
    assert dictionary.calls == matcher.calls == downstream_calls
    if expected_status == "awaiting_user_decision":
        assert job["ai_execution"]["safe_error_code"] == "AI_V2_CONTRACT_FAILED"
        assert job["has_complete_five_results"] is False
    else:
        assert job["has_complete_five_results"] is True
