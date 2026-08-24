from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from bedding_order_parser.ai_full_order.fake_provider import FakeFullOrderProvider
from bedding_order_parser.web.ai_full_order_service import AIEnhancedDependencies
from bedding_order_parser.web.app import create_server
from bedding_order_parser.web.services import JobService


class DeferredExecutor:
    def submit(self, _function, *_args) -> None:
        return None


class FakeDictionaryValidator:
    def validate(self, _records, _evidence):
        return {}


class FakeMaterialMatcher:
    def match(self, _records, _resolved):
        return {}


@pytest.fixture
def local_server(tmp_path: Path):
    service = JobService(
        tmp_path / "web",
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=DeferredExecutor(),
    )
    server = create_server(port=0, service=service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}", service
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _read_json(url: str) -> tuple[int, dict]:
    with urlopen(url, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _post_json(
    url: str, payload: dict | None = None, *, headers: dict[str, str] | None = None
) -> tuple[int, dict]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(data)),
            **(headers or {}),
        },
    )
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _awaiting_ai_job(service: JobService) -> dict:
    job = service.create_job("waiting.xlsx", b"PK\x03\x04fixture")
    stored = service._read_job(job["id"])
    stored["parse_mode"] = "ai_enhanced"
    stored["requested_parse_mode"] = "ai_enhanced"
    stored["effective_parse_mode"] = "ai_enhanced"
    stored.pop("ai_contract_version", None)
    stored.pop("ai_contract_source", None)
    stored["status"] = "awaiting_user_decision"
    stored["current_stage"] = "awaiting_user_decision"
    service._write_job(stored)
    return service.get_job(job["id"])


def test_preflight_without_dependencies_exposes_only_safe_ui_fields(local_server) -> None:
    base_url, _ = local_server

    status, payload = _read_json(f"{base_url}/api/ai-enhanced/preflight")

    assert status == 200
    assert payload["v2_backend_available"] is True
    assert payload["provider_ready"] is False
    assert payload["real_call_requires_user_confirmation"] is True
    assert payload["unavailable_reason_code"]
    assert payload["unavailable_reason_text"] == payload["reason"]
    assert payload["provider"] == payload["model"] == ""
    assert payload["max_logical_calls"] == 0
    assert payload["token_estimate"] is payload["cost_estimate"] is None


def test_preflight_with_fake_dependencies_is_ready_and_safe(tmp_path: Path) -> None:
    service = JobService(
        tmp_path / "web",
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=DeferredExecutor(),
        ai_enhanced_dependencies=AIEnhancedDependencies(
            provider=FakeFullOrderProvider(),
            dictionary_validator=FakeDictionaryValidator(),
            material_matcher=FakeMaterialMatcher(),
            provider_name="fake_provider",
            model_name="offline-test",
            max_logical_calls=7,
        ),
    )

    payload = service.ai_enhanced_preflight()

    assert payload["ready"] is True
    assert payload["v2_backend_available"] is True
    assert payload["provider_configured"] is True
    assert payload["provider_ready"] is True
    assert payload["real_call_requires_user_confirmation"] is True
    assert payload["unavailable_reason_code"] == payload["unavailable_reason_text"] == ""
    assert payload["provider"] == "fake_provider"
    assert payload["model"] == "offline-test"
    assert payload["max_logical_calls"] == 7
    assert all("key" not in field.lower() for field in payload)


def test_retry_keep_failed_and_standard_reprocess_routes(local_server) -> None:
    base_url, service = local_server
    retry = _awaiting_ai_job(service)

    status, retry_payload = _post_json(
        f"{base_url}/api/jobs/{retry['id']}/ai-actions/retry"
    )
    assert status == 200
    assert retry_payload["status"] == "awaiting_user_decision"
    assert retry_payload["ai_execution"]["safe_error_code"] == "AI_NOT_READY"

    keep = _awaiting_ai_job(service)
    status, keep_payload = _post_json(
        f"{base_url}/api/jobs/{keep['id']}/ai-actions/keep-failed"
    )
    assert status == 200
    assert keep_payload["status"] == "failed"

    original = _awaiting_ai_job(service)
    original_before = copy.deepcopy(service._read_job(original["id"]))
    status, reprocessed = _post_json(
        f"{base_url}/api/jobs/{original['id']}/reprocess-standard",
        headers={"X-Idempotency-Key": "route-reprocess-operation-001"},
    )
    assert status == 200
    assert reprocessed["new_job_id"] != original["id"]
    assert reprocessed["job"]["parse_mode"] == "standard"
    assert reprocessed["job"]["ai_execution"]["logical_call_count"] == 0
    assert service._read_job(original["id"]) == original_before

    status, repeated = _post_json(
        f"{base_url}/api/jobs/{original['id']}/reprocess-standard",
        headers={"X-Idempotency-Key": "route-reprocess-operation-001"},
    )
    assert status == 200
    assert repeated["new_job_id"] == reprocessed["new_job_id"]
    assert repeated["reused"] is True

    with pytest.raises(HTTPError) as legacy_fallback:
        _post_json(f"{base_url}/api/jobs/{original['id']}/ai-actions/fallback")
    assert legacy_fallback.value.code == 400


@pytest.mark.parametrize("suffix", ["unknown", "retry"])
def test_ai_action_routes_reject_unknown_action_and_missing_job(local_server, suffix: str) -> None:
    base_url, _ = local_server
    job_id = "f" * 32 if suffix == "retry" else "missing"
    with pytest.raises(HTTPError) as caught:
        _post_json(f"{base_url}/api/jobs/{job_id}/ai-actions/{suffix}")

    payload = json.loads(caught.value.read().decode("utf-8"))
    assert caught.value.code == 400
    assert isinstance(payload["error"], str)
    assert "Traceback" not in payload["error"]
