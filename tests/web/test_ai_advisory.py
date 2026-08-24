from __future__ import annotations

import hashlib
import json
import threading
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from bedding_order_parser.llm.contracts import (
    LLMEnhancementResponse,
    LLMUsage,
    MaterialAssessment,
)
from bedding_order_parser.llm.errors import LLMErrorCode, LLMProviderError
from bedding_order_parser.web.ai_advisory import (
    AIAdvisoryConflict,
    AIAdvisoryManager,
    AIAdvisoryUnavailable,
)
from bedding_order_parser.web.app import create_server
from bedding_order_parser.web.services import JobService


class DeferredExecutor:
    def __init__(self) -> None:
        self.submissions: list[tuple[object, tuple[object, ...]]] = []

    def submit(self, function, *args) -> None:
        self.submissions.append((function, args))

    def run_next(self) -> None:
        function, args = self.submissions.pop(0)
        function(*args)

    def shutdown(self, **_kwargs) -> None:
        return None


class FakeSettings:
    def __init__(self, ready: bool = True) -> None:
        self.ready = ready

    def is_ready(self) -> bool:
        return self.ready


class FakeLLMService:
    def __init__(self, *, ready: bool = True, fail: bool = False) -> None:
        self.settings = FakeSettings(ready)
        self.fail = fail
        self.requests = []

    def capabilities(self) -> dict[str, object]:
        return {
            "enabled": self.settings.ready,
            "configured": self.settings.ready,
            "status": "ready" if self.settings.ready else "disabled",
            "provider": "volcengine_ark",
            "provider_supported": True,
            "model": "doubao-test",
            "model_configured": True,
            "api_key_configured": self.settings.ready,
            "real_call_allowed": self.settings.ready,
        }

    def enhance_record(self, request):
        self.requests.append(request)
        if self.fail:
            raise LLMProviderError(
                LLMErrorCode.AUTHENTICATION_ERROR,
                "secret-provider-detail",
                request_id="resp-sensitive-request-id",
                attempts=1,
            )
        return LLMEnhancementResponse(
            provider="volcengine_ark",
            model="doubao-test",
            request_id="resp-test-advisory",
            source_record_id=request.source_record_id,
            status="succeeded",
            finish_status="completed",
            action="insufficient_evidence",
            confidence=0.24,
            material_assessment=MaterialAssessment(
                status="insufficient_evidence",
                suggested_material_code="",
                reason="现有证据不足，建议人工确认。",
            ),
            reasoning_summary="保持确定性结果，不自动写回。",
            warnings=("仅供人工复核。",),
            evidence_references=("F39",),
            usage=LLMUsage(100, 30, 130),
            latency_ms=125,
            attempt_count=1,
        )

    def close(self) -> None:
        return None


class DiagnosticFailingLLMService(FakeLLMService):
    def enhance_record(self, request):
        self.requests.append(request)
        raise LLMProviderError(
            LLMErrorCode.STRUCTURED_OUTPUT_ERROR,
            "raw provider details must stay hidden",
            request_id="resp-diagnostic-sensitive-id",
            attempts=1,
            diagnostics={
                "error_stage": "schema_validation",
                "schema_path": "$.confidence",
                "expected_type": "number",
                "actual_type": "string",
                "response_item_types": ["function_call"],
                "has_function_call": True,
                "has_output_text": False,
                "unsafe_raw_response": "must-not-persist",
            },
        )


def build_service(
    tmp_path: Path,
    *,
    ready: bool = True,
    fail: bool = False,
) -> tuple[JobService, DeferredExecutor, FakeLLMService]:
    executor = DeferredExecutor()
    llm = FakeLLMService(ready=ready, fail=fail)
    service = JobService(
        tmp_path / "web",
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=executor,
        llm_service=llm,
    )
    return service, executor, llm


def seed_completed_job(
    service: JobService,
    *,
    record_count: int = 1,
    decision_status: str = "insufficient_evidence",
) -> tuple[dict[str, object], dict[str, Path]]:
    job = service.create_job(
        "H Hotel.xlsx",
        b"PK\x03\x04workbook",
    )
    job_root = service.jobs_root / str(job["id"])
    results = job_root / "results"
    match_output = job_root / "match-output"
    match_output.mkdir()

    business_records = []
    diagnostic_records = []
    validation_records = []
    match_records = []
    for offset in range(record_count):
        line = str(39 + offset)
        business_records.append(
            {
                "行号": line,
                "物料名称": "H Hotel 被套",
                "规格": "273*205cm",
                "颜色": "白色",
                "面料": "全棉",
                "面料-涤棉成分": "",
                "款式": "",
                "加标方式": "",
                "尺寸类型": "",
                "行备注": (
                    "联系人 test@example.com 电话 13800138000 "
                    "地址 Customer Street"
                ),
                "包装方式": "",
                "是否绣花": "否",
            }
        )
        diagnostic_records.append(
            {
                "行号": line,
                "fields": {
                    "规格": {
                        "status": "parsed",
                        "rule": "same_row_dimension",
                        "source": {"cells": [f"F{line}"]},
                    }
                },
            }
        )
        validation_records.append(
            {
                "行号": line,
                "fields": {
                    "物料名称": {
                        "source_cells": [f"B{line}"],
                        "source_text": "Duvet Cover 205*273cm",
                        "detected_category": "被套",
                    },
                    "规格": {
                        "source_cells": [f"F{line}"],
                        "source_text": "205*273cm",
                    },
                    "颜色": {
                        "source_cells": [f"G{line}"],
                        "source_text": "White",
                    },
                },
            }
        )
        match_records.append(
            {
                "source_file": "H Hotel.xlsx",
                "sheet": "PI",
                "行号": line,
                "query": {
                    "product_category": "被套",
                    "spec": "273*205cm",
                    "color": "白色",
                },
                "decision": {"status": decision_status},
                "candidates": [
                    {
                        "rank": 1,
                        "material_code": f"F09030125{70 + offset}",
                        "prototype_match_score": 0.78,
                        "comparable_field_count": 3,
                        "fields": {
                            "spec": {
                                "candidate_value": "273*205cm",
                                "status": "exact_match",
                            }
                        },
                    }
                ],
            }
        )

    paths = {
        "business": results / "H Hotel_gate2d.json",
        "diagnostic": results / "H Hotel_gate2d_parse_report.json",
        "validation": results / "H Hotel_gate2d_dictionary_validation.json",
        "matches": match_output / "material_match_candidates.json",
        "match_summary": match_output / "material_match_summary.json",
        "zip": job_root / "H Hotel_全部结果.zip",
    }
    paths["business"].write_text(
        json.dumps(business_records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["diagnostic"].write_text(
        json.dumps({"records": diagnostic_records}, ensure_ascii=False),
        encoding="utf-8",
    )
    paths["validation"].write_text(
        json.dumps({"records": validation_records}, ensure_ascii=False),
        encoding="utf-8",
    )
    paths["matches"].write_text(
        json.dumps({"records": match_records}, ensure_ascii=False),
        encoding="utf-8",
    )
    paths["match_summary"].write_text(
        json.dumps({"record_count": record_count}),
        encoding="utf-8",
    )
    archive_names = {
        "H Hotel_正式业务.json": paths["business"],
        "H Hotel_解析诊断.json": paths["diagnostic"],
        "H Hotel_字典验证.json": paths["validation"],
        "H Hotel_匹配候选.json": paths["matches"],
        "H Hotel_匹配摘要.json": paths["match_summary"],
    }
    with zipfile.ZipFile(paths["zip"], "w") as archive:
        for name, path in archive_names.items():
            archive.write(path, arcname=name)

    metadata = service._read_job(str(job["id"]))
    metadata.update(
        {
            "status": "completed",
            "record_count": record_count,
            "sheet": "PI",
            "artifacts": {
                key: path.relative_to(job_root).as_posix()
                for key, path in paths.items()
            },
        }
    )
    service._write_job(metadata)
    return metadata, paths


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def start_identity(service: JobService, job_id: str, index: int) -> dict:
    status = service.ai_advisory_status(job_id, index)
    return {
        "job_id": job_id,
        "record_index": index,
        "source_record_id": status["source_record_id"],
        "source_file": status["source_file"],
        "sheet": status["sheet"],
        "line_number": status["line_number"],
    }


def sidecar_path(
    service: JobService, job_id: str, source_record_id: str
) -> Path:
    safe_id = source_record_id.replace(":", "_")
    return (
        service.jobs_root
        / job_id
        / "ai-advisory"
        / f"{safe_id}.json"
    )


def status_path(
    service: JobService, job_id: str, source_record_id: str
) -> Path:
    safe_id = source_record_id.replace(":", "_")
    return (
        service.jobs_root
        / job_id
        / "ai-advisory"
        / f"{safe_id}.status.json"
    )


def write_historical_english_sidecar(
    service: JobService,
    executor: DeferredExecutor,
    job_id: str,
    identity: dict[str, object],
) -> tuple[Path, dict[str, object]]:
    service.start_ai_advisory(job_id, 0, identity)
    executor.run_next()
    path = sidecar_path(
        service, job_id, str(identity["source_record_id"])
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["reasoning_summary"] = (
        "The available evidence does not establish a unique material."
    )
    payload["material_assessment"]["reason"] = (
        "Comparable material fields are incomplete."
    )
    payload["warnings"] = ["Manual review is required."]
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path, payload


def test_advisory_uses_server_artifacts_and_preserves_main_results(
    tmp_path: Path,
) -> None:
    service, executor, llm = build_service(tmp_path)
    job, paths = seed_completed_job(service)
    job_id = str(job["id"])
    before = {
        name: sha256(paths[name])
        for name in ("business", "diagnostic", "validation", "matches")
    }
    before_zip = sha256(paths["zip"])
    identity = start_identity(service, job_id, 0)

    started = service.start_ai_advisory(
        job_id,
        0,
        {
            **identity,
            "物料名称": "前端伪造内容",
            "api_key": "must-be-ignored",
        },
    )

    assert started["state"] == "running"
    assert len(executor.submissions) == 1
    executor.run_next()

    result = service.ai_advisory_status(job_id, 0)
    assert result["state"] == "completed"
    assert result["result"]["source_record_id"] == identity["source_record_id"]
    assert result["result"]["advisory_only"] is True
    assert result["result"]["usage"]["total_tokens"] == 130
    assert llm.requests[0].job_id == job_id
    assert llm.requests[0].parsed_record["物料名称"] == "H Hotel 被套"
    assert "前端伪造内容" not in json.dumps(
        llm.requests[0].to_dict(), ensure_ascii=False
    )
    assert "Duvet Cover 205*273cm" in json.dumps(
        llm.requests[0].to_dict(), ensure_ascii=False
    )
    request_text = json.dumps(
        llm.requests[0].to_dict(), ensure_ascii=False
    )
    assert "test@example.com" not in request_text
    assert "13800138000" not in request_text
    assert "Customer Street" not in request_text
    assert llm.requests[0].parsed_record["行备注"] == "[redacted]"
    assert service.get_job(job_id)["status"] == "completed"
    assert before == {
        name: sha256(paths[name])
        for name in ("business", "diagnostic", "validation", "matches")
    }
    assert sha256(paths["zip"]) != before_zip
    with zipfile.ZipFile(paths["zip"]) as archive:
        names = archive.namelist()
    assert len(names) == 5
    assert not any(name.startswith("AI建议/") for name in names)
    assert list(
        (service.jobs_root / job_id / "ai-advisory").glob("*.json")
    )
    assert not list(
        (service.jobs_root / job_id / "ai-advisory").glob(".*.tmp")
    )
    assert result["language_status"] == "zh_cn"
    assert result["historical_english"] is False
    assert result["technical_details"]["raw_evidence"][0]["source_text"]
    assert "Duvet Cover 205*273cm" in json.dumps(
        result["technical_details"], ensure_ascii=False
    )


@pytest.mark.parametrize(
    "decision_status",
    [
        "unique_best_candidate",
        "ranked_candidates",
        "ambiguous_tie",
        "insufficient_evidence",
        "no_candidate",
    ],
)
def test_every_completed_match_status_can_start_manual_review(
    tmp_path: Path,
    decision_status: str,
) -> None:
    service, executor, _ = build_service(tmp_path / decision_status)
    job, _ = seed_completed_job(
        service,
        decision_status=decision_status,
    )
    job_id = str(job["id"])

    status = service.ai_advisory_status(job_id, 0)
    started = service.start_ai_advisory(
        job_id,
        0,
        start_identity(service, job_id, 0),
    )

    assert status["eligible"] is True
    assert status["decision_status"] == decision_status
    assert started["state"] == "running"
    assert len(executor.submissions) == 1


def test_duplicate_click_is_idempotent_and_other_record_is_serialized(
    tmp_path: Path,
) -> None:
    service, executor, _ = build_service(tmp_path)
    job, _ = seed_completed_job(service, record_count=2)
    job_id = str(job["id"])
    first = start_identity(service, job_id, 0)
    second = start_identity(service, job_id, 1)

    service.start_ai_advisory(job_id, 0, first)
    duplicate = service.start_ai_advisory(job_id, 0, first)

    assert duplicate["state"] == "running"
    assert len(executor.submissions) == 1
    with pytest.raises(AIAdvisoryConflict):
        service.start_ai_advisory(job_id, 1, second)


def test_cached_sidecar_prevents_a_second_provider_call(
    tmp_path: Path,
) -> None:
    service, executor, llm = build_service(tmp_path)
    job, _ = seed_completed_job(service)
    job_id = str(job["id"])
    identity = start_identity(service, job_id, 0)
    service.start_ai_advisory(job_id, 0, identity)
    executor.run_next()
    assert len(llm.requests) == 1

    restarted, restarted_executor, restarted_llm = build_service(tmp_path)
    cached = restarted.ai_advisory_status(job_id, 0)
    returned = restarted.start_ai_advisory(job_id, 0, identity)

    assert cached["state"] == "cached"
    assert returned["state"] == "cached"
    assert restarted_executor.submissions == []
    assert restarted_llm.requests == []


@pytest.mark.parametrize(
    ("reasoning", "material_reason", "field_reasons", "warnings", "expected"),
    [
        (
            "建议人工核查，原始证据为 F39 and G39。",
            "物料信息基本一致，型号 ABC-205 保留原文。",
            ["规格需要人工确认。"],
            ["请核对 PI evidence。"],
            True,
        ),
        (
            "建议保留原始产品描述 Duvet Cover Luxury Collection "
            "Hotel Bedding Set 205*273cm，并人工核对规格。",
            "候选物料证据不足，暂不确认编码。",
            [],
            [],
            True,
        ),
        (
            "The evidence is insufficient for a reliable decision.",
            "Manual material review is required.",
            ["Check the product specification."],
            ["Do not write the result automatically."],
            False,
        ),
        ("", "", [], [], False),
        (
            "当前建议以中文业务解释为主，Duvet Cover、SKU ABC-205 "
            "和 Hotel Collection 均为应保留的英文原文。",
            "可比较字段较少，建议人工核查 material specification。",
            ["原值 White 与标准颜色白色需要人工确认。"],
            ["型号 Model-X9 不应自动写回。"],
            True,
        ),
    ],
)
def test_chinese_advisory_detection_allows_verbatim_english_evidence(
    reasoning: str,
    material_reason: str,
    field_reasons: list[str],
    warnings: list[str],
    expected: bool,
) -> None:
    payload = {
        "reasoning_summary": reasoning,
        "material_assessment": {"reason": material_reason},
        "suggested_fields": [
            {"reason": reason} for reason in field_reasons
        ],
        "warnings": warnings,
    }

    assert (
        AIAdvisoryManager._is_simplified_chinese_advisory(payload)
        is expected
    )


def test_legacy_status_without_new_fields_reads_cached_sidecar(
    tmp_path: Path,
) -> None:
    service, executor, _ = build_service(tmp_path)
    job, _ = seed_completed_job(service)
    job_id = str(job["id"])
    identity = start_identity(service, job_id, 0)
    service.start_ai_advisory(job_id, 0, identity)
    executor.run_next()
    path = status_path(service, job_id, identity["source_record_id"])
    path.write_text(
        json.dumps(
            {
                "state": "completed",
                "job_id": job_id,
                "source_record_id": identity["source_record_id"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    restarted, restarted_executor, restarted_llm = build_service(tmp_path)
    cached = restarted.ai_advisory_status(job_id, 0)

    assert cached["state"] == "cached"
    assert cached["language_status"] == "zh_cn"
    assert restarted_executor.submissions == []
    assert restarted_llm.requests == []


def test_historical_english_sidecar_requires_explicit_regeneration(
    tmp_path: Path,
) -> None:
    service, executor, _ = build_service(tmp_path)
    job, _ = seed_completed_job(service)
    job_id = str(job["id"])
    identity = start_identity(service, job_id, 0)
    path, old_payload = write_historical_english_sidecar(
        service, executor, job_id, identity
    )

    restarted, restarted_executor, restarted_llm = build_service(tmp_path)
    cached = restarted.ai_advisory_status(job_id, 0)
    without_confirmation = restarted.start_ai_advisory(
        job_id,
        0,
        identity,
    )

    assert cached["state"] == "cached"
    assert cached["historical_english"] is True
    assert cached["can_regenerate_chinese"] is True
    assert without_confirmation["state"] == "cached"
    assert restarted_executor.submissions == []
    assert restarted_llm.requests == []
    assert json.loads(path.read_text(encoding="utf-8")) == old_payload

    started = restarted.start_ai_advisory(
        job_id,
        0,
        {**identity, "regenerate_chinese": True},
    )
    assert started["state"] == "running"
    assert len(restarted_executor.submissions) == 1
    restarted_executor.run_next()

    completed = restarted.ai_advisory_status(job_id, 0)
    assert completed["state"] == "completed"
    assert completed["language_status"] == "zh_cn"
    assert completed["historical_english"] is False
    assert len(restarted_llm.requests) == 1
    assert (
        json.loads(path.read_text(encoding="utf-8"))[
            "reasoning_summary"
        ]
        == "保持确定性结果，不自动写回。"
    )


def test_failed_chinese_regeneration_preserves_historical_sidecar(
    tmp_path: Path,
) -> None:
    service, executor, _ = build_service(tmp_path)
    job, paths = seed_completed_job(service)
    job_id = str(job["id"])
    identity = start_identity(service, job_id, 0)
    path, old_payload = write_historical_english_sidecar(
        service, executor, job_id, identity
    )
    before = {
        name: sha256(paths[name])
        for name in ("business", "matches", "zip")
    }

    failing, failing_executor, failing_llm = build_service(
        tmp_path, fail=True
    )
    failing.start_ai_advisory(
        job_id,
        0,
        {**identity, "regenerate_chinese": True},
    )
    failing_executor.run_next()

    status = failing.ai_advisory_status(job_id, 0)
    assert status["state"] == "cached"
    assert status["historical_english"] is True
    assert status["error"]["code"] == "authentication_error"
    assert len(failing_llm.requests) == 1
    assert json.loads(path.read_text(encoding="utf-8")) == old_payload
    assert before == {
        name: sha256(paths[name])
        for name in ("business", "matches", "zip")
    }


def test_failure_is_safe_and_does_not_change_completed_job(
    tmp_path: Path,
) -> None:
    service, executor, _ = build_service(tmp_path, fail=True)
    job, paths = seed_completed_job(service)
    job_id = str(job["id"])
    original_hashes = {
        name: sha256(paths[name])
        for name in ("business", "matches", "zip")
    }

    service.start_ai_advisory(
        job_id,
        0,
        start_identity(service, job_id, 0),
    )
    executor.run_next()

    result = service.ai_advisory_status(job_id, 0)
    assert result["state"] == "failed"
    assert result["error"]["code"] == "authentication_error"
    assert result["error"]["attempt_count"] == 1
    assert result["error"]["request_id"] == "resp-s...t-id"
    assert "secret-provider-detail" not in json.dumps(
        result, ensure_ascii=False
    )
    assert "resp-sensitive-request-id" not in json.dumps(result)
    assert service.get_job(job_id)["status"] == "completed"
    assert original_hashes == {
        name: sha256(paths[name])
        for name in ("business", "matches", "zip")
    }


def test_structured_failure_persists_only_safe_diagnostics(
    tmp_path: Path,
) -> None:
    executor = DeferredExecutor()
    llm = DiagnosticFailingLLMService()
    service = JobService(
        tmp_path / "web",
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=executor,
        llm_service=llm,
    )
    job, _ = seed_completed_job(service)
    job_id = str(job["id"])
    identity = start_identity(service, job_id, 0)

    service.start_ai_advisory(job_id, 0, identity)
    executor.run_next()

    status = service.ai_advisory_status(job_id, 0)
    error = status["error"]
    assert error["code"] == "structured_output_error"
    assert error["error_stage"] == "schema_validation"
    assert error["schema_path"] == "$.confidence"
    assert error["expected_type"] == "number"
    assert error["actual_type"] == "string"
    assert error["response_item_types"] == ["function_call"]
    assert error["has_function_call"] is True
    assert error["has_output_text"] is False
    serialized = json.dumps(status, ensure_ascii=False)
    assert "raw provider details must stay hidden" not in serialized
    assert "resp-diagnostic-sensitive-id" not in serialized
    assert "unsafe_raw_response" not in serialized
    assert "must-not-persist" not in serialized


def test_unready_job_cannot_start_advisory(
    tmp_path: Path,
) -> None:
    service, _, _ = build_service(tmp_path, ready=False)
    job, _ = seed_completed_job(service)
    job_id = str(job["id"])
    with pytest.raises(AIAdvisoryUnavailable, match="尚未配置"):
        service.start_ai_advisory(
            job_id,
            0,
            start_identity(service, job_id, 0),
        )

def test_incomplete_job_cannot_read_or_start_advisory(
    tmp_path: Path,
) -> None:
    service, _, _ = build_service(tmp_path)
    job = service.create_job(
        "queued.xlsx",
        b"PK\x03\x04workbook",
    )

    with pytest.raises(AIAdvisoryUnavailable, match="尚未完成"):
        service.ai_advisory_status(str(job["id"]), 0)


def test_route_starts_and_reads_single_record_advisory(
    tmp_path: Path,
) -> None:
    service, executor, _ = build_service(tmp_path)
    job, _ = seed_completed_job(service)
    job_id = str(job["id"])
    identity = start_identity(service, job_id, 0)
    server = create_server(port=0, service=service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base_url = f"http://{host}:{port}"
    request = Request(
        f"{base_url}/api/tasks/{job_id}/ai-enhance",
        data=json.dumps(identity).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=3) as response:
            started = json.loads(response.read().decode("utf-8"))
            assert response.status == 202
        assert started["state"] == "running"
        executor.run_next()
        with urlopen(
            f"{base_url}/api/jobs/{job_id}/matches/0/ai-advisory",
            timeout=3,
        ) as response:
            completed = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        service.close()
        thread.join(timeout=3)

    assert completed["state"] == "completed"
    assert completed["result"]["advisory_only"] is True
