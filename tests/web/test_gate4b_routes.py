from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from bedding_order_parser.llm.service import LLMService
from bedding_order_parser.llm.settings import LLMSettings
from bedding_order_parser.web.app import create_server
from bedding_order_parser.web.services import JobService


class DeferredExecutor:
    def submit(self, _function, *_args) -> None:
        return None

    def shutdown(self, **_kwargs) -> None:
        return None


@pytest.fixture
def gate4b_server(tmp_path: Path):
    service = JobService(
        tmp_path / "web",
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=DeferredExecutor(),
        llm_service=LLMService(
            settings=LLMSettings(
                enabled=False,
                provider="volcengine_ark",
                model="test-model",
                api_key="never-expose-this",
            )
        ),
        desktop_mode=True,
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
        service.close()
        thread.join(timeout=3)


def test_health_and_capabilities_contract(gate4b_server) -> None:
    base_url, _ = gate4b_server
    with urlopen(f"{base_url}/health", timeout=3) as response:
        health = json.loads(response.read().decode("utf-8"))
    with urlopen(f"{base_url}/api/capabilities", timeout=3) as response:
        capabilities = json.loads(response.read().decode("utf-8"))

    assert health == {"status": "ok", "accepting_jobs": True}
    assert capabilities["llm"] == {
        "enabled": False,
        "configured": False,
        "status": "disabled",
        "provider": "volcengine_ark",
        "provider_supported": True,
        "model": "test-model",
        "model_configured": True,
        "api_key_configured": True,
        "real_call_allowed": False,
        "business_integration": True,
        "mode": "single_record_advisory",
        "manual_confirmation_required": True,
        "automatic_calls": False,
    }
    assert capabilities["desktop"] == {"mode": True}
    assert capabilities["ai_full_order"]["v2_backend_available"] is True
    assert capabilities["ai_full_order"]["provider_ready"] is False
    assert capabilities["ai_full_order"]["real_call_requires_user_confirmation"] is True
    assert "never-expose-this" not in json.dumps(capabilities)


def test_ai_enhance_rejects_incomplete_identity_without_provider_call(
    gate4b_server,
) -> None:
    base_url, service = gate4b_server
    job = service.create_job("ai.xlsx", b"PK\x03\x04workbook")
    request = Request(
        f"{base_url}/api/tasks/{job['id']}/ai-enhance",
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    with pytest.raises(HTTPError) as caught:
        urlopen(request, timeout=3)

    payload = json.loads(caught.value.read().decode("utf-8"))
    assert caught.value.code == 400
    assert payload == {
        "error": {
            "code": "INVALID_REQUEST",
            "message": "AI建议请求格式不正确。",
        }
    }
    assert "never-expose-this" not in json.dumps(payload)


def test_ready_provider_rejects_incomplete_identity_without_call(
    tmp_path: Path,
) -> None:
    class NoCallProvider:
        provider_name = "volcengine_ark"
        model_name = "test-model"
        calls = 0

        def is_configured(self) -> bool:
            return True

        def health_check(self) -> dict[str, object]:
            return {}

        def enhance_record(self, _request):
            self.calls += 1
            raise AssertionError("invalid identity must not call provider")

        def close(self) -> None:
            return

    provider = NoCallProvider()
    service = JobService(
        tmp_path / "ready-web",
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=DeferredExecutor(),
        llm_service=LLMService(
            settings=LLMSettings(
                enabled=True,
                provider="volcengine_ark",
                model="test-model",
                api_key="configured-but-never-exposed",
            ),
            provider=provider,
        ),
    )
    job = service.create_job("ai.xlsx", b"PK\x03\x04workbook")
    server = create_server(port=0, service=service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    request = Request(
        f"http://{host}:{port}/api/tasks/{job['id']}/ai-enhance",
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with pytest.raises(HTTPError) as caught:
            urlopen(request, timeout=3)
        payload = json.loads(caught.value.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        service.close()
        thread.join(timeout=3)

    assert caught.value.code == 400
    assert payload == {
        "error": {
            "code": "INVALID_REQUEST",
            "message": "AI建议请求格式不正确。",
        }
    }
    assert provider.calls == 0


def test_history_reads_interrupted_recovery_status(gate4b_server) -> None:
    base_url, service = gate4b_server
    job = service.create_job("recovered.xlsx", b"PK\x03\x04workbook")
    metadata = service._read_job(job["id"])
    metadata.update(
        {
            "status": "interrupted",
            "current_stage": "任务已中断",
            "error": "上次运行异常结束，任务已标记为中断，请重新提交。",
            "interruption_reason": "application_restarted",
            "previous_status": "processing",
            "recovered_at": "2026-07-29T15:00:00+08:00",
        }
    )
    service._write_job(metadata)

    with urlopen(f"{base_url}/api/jobs", timeout=3) as response:
        payload = json.loads(response.read().decode("utf-8"))

    recovered = next(
        row for row in payload["jobs"] if row["id"] == job["id"]
    )
    assert recovered["status"] == "interrupted"
    assert recovered["error"] == "上次运行异常结束，任务已标记为中断，请重新提交。"
