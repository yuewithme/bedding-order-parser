from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bedding_order_parser.materials import hybrid_matcher, match_writer
from bedding_order_parser.models.final_result import FINAL_FIELD_NAMES
from bedding_order_parser.pipeline import order_parser
from bedding_order_parser.web.services import JobService, WebJobError


class _DeferredExecutor:
    def __init__(self) -> None:
        self.submissions: list[tuple[object, tuple[object, ...]]] = []

    def submit(self, function, *args) -> None:
        self.submissions.append((function, args))


def _service(tmp_path: Path) -> tuple[JobService, _DeferredExecutor]:
    executor = _DeferredExecutor()
    return (
        JobService(
            tmp_path / "web",
            store_path=tmp_path / "material.sqlite3",
            index_dir=tmp_path / "index",
            executor=executor,
        ),
        executor,
    )


def _awaiting_ai_job(service: JobService, content: bytes) -> dict:
    original = service.create_job("original.xlsx", content)
    stored = service._read_job(original["id"])
    stored.update(
        {
            "parse_mode": "ai_enhanced",
            "requested_parse_mode": "ai_enhanced",
            "effective_parse_mode": "ai_enhanced",
            "status": "awaiting_user_decision",
            "current_stage": "awaiting_user_decision",
            "error": "订单结构未能安全完成。",
            "ai_execution": {
                **stored["ai_execution"],
                "logical_call_count": 3,
                "http_attempt_count": 3,
                "token_summary": {
                    "input_tokens": 12,
                    "output_tokens": 8,
                    "total_tokens": 20,
                },
                "safe_error_code": "AI_V2_STRUCTURE_UNRESOLVED",
            },
        }
    )
    service._write_job(stored)
    return service.get_job(original["id"])


def _standard_record() -> dict[str, object]:
    values = {name: "" for name in FINAL_FIELD_NAMES[:-1]}
    values.update({"客户": "标准客户", "物料名称": "标准物料", "行号": "2"})
    values[FINAL_FIELD_NAMES[-1]] = 0.0
    return values


def test_reprocess_creates_independent_standard_job_from_original_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, executor = _service(tmp_path)
    content = b"PK\x03\x04synthetic-original-workbook"
    original = _awaiting_ai_job(service, content)
    original_path = service._job_root(original["id"]) / "job.json"
    original_bundle = service._job_root(original["id"]) / "ai-bundle"
    original_bundle.mkdir()
    for name, payload in {"INITIAL": "revision-0\n", "CURRENT": "revision-1\n"}.items():
        (original_bundle / name).write_text(payload, encoding="utf-8")
    revision = original_bundle / "revisions" / "revision-1"
    revision.mkdir(parents=True)
    (revision / "official_result.json").write_text("[]\n", encoding="utf-8")
    original_bytes = original_path.read_bytes()
    revision_bytes = (revision / "official_result.json").read_bytes()

    response = service.reprocess_ai_job_as_standard(
        original["id"], operation_id="reprocess-operation-001"
    )
    child_id = response["new_job_id"]
    child = service._read_job(child_id)

    assert response["reused"] is False
    assert child_id != original["id"]
    assert child["parse_mode"] == child["requested_parse_mode"] == child["effective_parse_mode"] == "standard"
    assert child["reprocess"]["origin_job_id"] == original["id"]
    assert child["reprocess"]["reason"] == "standard_reprocess"
    assert child["source_identity"]["sha256"] == original["source_identity"]["sha256"]
    assert (service._job_root(child_id) / "input" / "original.xlsx").read_bytes() == content
    assert child["ai_execution"]["logical_call_count"] == 0
    assert child["ai_execution"]["http_attempt_count"] == 0
    assert child["ai_execution"]["token_summary"]["total_tokens"] == 0
    assert executor.submissions == [(service._run_job, (child_id,))]

    assert original_path.read_bytes() == original_bytes
    assert (revision / "official_result.json").read_bytes() == revision_bytes
    assert service.get_job(original["id"]) == original

    repeated = service.reprocess_ai_job_as_standard(
        original["id"], operation_id="reprocess-operation-001"
    )
    assert repeated["new_job_id"] == child_id
    assert repeated["reused"] is True
    assert len(executor.submissions) == 1

    repeated_active = service.reprocess_ai_job_as_standard(
        original["id"], operation_id="reprocess-operation-002"
    )
    assert repeated_active["new_job_id"] == child_id
    assert repeated_active["reused"] is True
    assert len(executor.submissions) == 1

    observed_input: list[bytes] = []

    def fake_parse(input_path, result_path, **kwargs):
        observed_input.append(Path(input_path).read_bytes())
        Path(result_path).write_text(
            json.dumps([_standard_record()], ensure_ascii=False), encoding="utf-8"
        )
        Path(kwargs["report_path"]).write_text("{}", encoding="utf-8")
        Path(kwargs["validation_path"]).write_text("{}", encoding="utf-8")
        return SimpleNamespace(
            record_count=1,
            input_sha256_before=hashlib.sha256(content).hexdigest(),
        )

    def fake_match(*_args, **_kwargs):
        return SimpleNamespace(
            candidates_payload={
                "records": [{"decision": {"status": "unique_best_candidate"}}]
            }
        )

    def fake_write(_result, target):
        target = Path(target)
        target.mkdir(parents=True, exist_ok=True)
        candidates = target / "material_match_candidates.json"
        summary = target / "material_match_summary.json"
        candidates.write_text('{"records": []}', encoding="utf-8")
        summary.write_text('{"record_count": 1}', encoding="utf-8")
        return SimpleNamespace(candidates_path=candidates, summary_path=summary)

    monkeypatch.setattr(order_parser, "parse_order", fake_parse)
    monkeypatch.setattr(hybrid_matcher, "match_orders", fake_match)
    monkeypatch.setattr(match_writer, "write_match_outputs", fake_write)
    service._run_job(child_id)

    completed = service.get_job(child_id)
    assert observed_input == [content]
    assert completed["status"] == "completed"
    assert completed["parse_mode"] == completed["effective_parse_mode"] == "standard"
    assert completed["has_complete_five_results"] is True
    assert completed["ai_review_summary"]["applicable"] is False
    assert all(completed["artifact_roles"].values())

    later = service.reprocess_ai_job_as_standard(
        original["id"], operation_id="reprocess-operation-003"
    )
    assert later["new_job_id"] != child_id
    assert later["job"]["status"] == "queued"


def test_reprocess_rejects_missing_or_tampered_source_without_mutating_original(
    tmp_path: Path,
) -> None:
    service, _executor = _service(tmp_path)
    original = _awaiting_ai_job(service, b"PK\x03\x04synthetic-original-workbook")
    metadata_path = service._job_root(original["id"]) / "job.json"
    before = metadata_path.read_bytes()
    (service._job_root(original["id"]) / "input" / "original.xlsx").write_bytes(b"PK\x03\x04tampered")

    with pytest.raises(WebJobError, match="身份不一致"):
        service.reprocess_ai_job_as_standard(
            original["id"], operation_id="reprocess-operation-002"
        )

    assert metadata_path.read_bytes() == before
    assert len(list(service.jobs_root.glob("*/job.json"))) == 1


def test_historical_same_job_fallback_remains_readable_but_new_reprocess_rejects_it(
    tmp_path: Path,
) -> None:
    service, _executor = _service(tmp_path)
    original = _awaiting_ai_job(service, b"PK\x03\x04synthetic-original-workbook")
    stored = service._read_job(original["id"])
    stored.update(
        {
            "status": "completed",
            "effective_parse_mode": "standard",
            "fallback": {
                "status": "confirmed",
                "reason": "user_confirmed_fallback_to_standard",
                "user_confirmed_at": "2026-08-09T00:00:00+08:00",
            },
        }
    )
    service._write_job(stored)

    historical = service.get_job(original["id"])
    assert historical["parse_mode"] == "ai_enhanced"
    assert historical["effective_parse_mode"] == "standard"
    assert historical["fallback"]["status"] == "confirmed"
    with pytest.raises(WebJobError, match="只有等待处理的AI增强任务"):
        service.reprocess_ai_job_as_standard(
            original["id"], operation_id="reprocess-operation-003"
        )
