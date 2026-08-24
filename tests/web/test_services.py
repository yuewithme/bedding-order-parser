from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from bedding_order_parser.materials import hybrid_matcher, match_writer
from bedding_order_parser.materials.query_embedding_runner import (
    QueryEmbeddingProcessError,
)
from bedding_order_parser.pipeline import order_parser
from bedding_order_parser.web.services import JobService, WebJobError


class DeferredExecutor:
    def __init__(self) -> None:
        self.submissions: list[tuple[object, tuple[object, ...]]] = []

    def submit(self, function, *args):
        self.submissions.append((function, args))
        return None


def build_service(tmp_path: Path) -> JobService:
    return JobService(
        tmp_path / "web",
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=DeferredExecutor(),
    )


def seed_job(
    root: Path,
    job_id: str,
    status: str,
    *,
    owner_pid: int | None = None,
) -> tuple[Path, Path]:
    job_root = root / "jobs" / job_id
    job_root.mkdir(parents=True)
    artifact = job_root / "partial.json"
    artifact.write_text('{"partial": true}\n', encoding="utf-8")
    payload = {
        "id": job_id,
        "file_name": "stale.xlsx",
        "file_size": 10,
        "created_at": (
            datetime.now().astimezone() - timedelta(hours=2)
        ).isoformat(timespec="seconds"),
        "completed_at": "",
        "elapsed_seconds": 0.0,
        "status": status,
        "progress": 70,
        "current_stage": "处理中",
        "stages": [],
        "error": "",
        "sheet": "",
        "record_count": 0,
        "summary": {},
        "artifacts": {"partial": artifact.name},
        "input_sha256": "",
    }
    if owner_pid is not None:
        payload["owner_session_id"] = "earlier-session"
        payload["owner_pid"] = owner_pid
    metadata = job_root / "job.json"
    metadata.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata, artifact


def test_create_job_persists_safe_local_metadata(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    job = service.create_job("../订单测试.xlsx", b"PK\x03\x04workbook")

    assert job["file_name"] == "订单测试.xlsx"
    assert job["status"] == "queued"
    assert job["progress"] == 0
    assert len(job["stages"]) == 5
    input_path = service.jobs_root / job["id"] / "input" / "订单测试.xlsx"
    assert input_path.read_bytes() == b"PK\x03\x04workbook"
    stored = service._read_job(job["id"])
    assert stored["owner_session_id"] == service.session_id
    assert stored["owner_pid"] == os.getpid()
    assert "ai_allowed" not in stored


@pytest.mark.parametrize(
    ("file_name", "content", "message"),
    [
        ("订单.xls", b"PK\x03\x04data", "仅支持 .xlsx"),
        ("订单.xlsx", b"", "上传文件为空"),
        ("订单.xlsx", b"not-a-workbook", "不是有效的 .xlsx"),
    ],
)
def test_create_job_rejects_invalid_uploads(
    tmp_path: Path, file_name: str, content: bytes, message: str
) -> None:
    service = build_service(tmp_path)

    with pytest.raises(WebJobError, match=message):
        service.create_job(file_name, content)


def test_history_is_newest_first_and_does_not_expose_paths(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    first = service.create_job("first.xlsx", b"PK\x03\x04one")
    second = service.create_job("second.xlsx", b"PK\x03\x04two")
    second_payload = service._read_job(second["id"])
    second_payload["created_at"] = "2026-07-28T11:30:00+08:00"
    service._write_job(second_payload)
    first_payload = service._read_job(first["id"])
    first_payload["created_at"] = "2026-07-27T11:30:00+08:00"
    service._write_job(first_payload)

    history = service.list_jobs()

    assert [job["file_name"] for job in history] == ["second.xlsx", "first.xlsx"]
    assert "input_sha256" not in history[0]
    assert history[0]["artifacts"] == {
        "business": False,
        "diagnostic": False,
        "validation": False,
        "zip": False,
    }


def test_match_detail_translates_internal_statuses_to_business_terms(
    tmp_path: Path,
) -> None:
    service = build_service(tmp_path)
    job = service.create_job("detail.xlsx", b"PK\x03\x04detail")
    job_root = service.jobs_root / job["id"]
    match_path = job_root / "match-output" / "material_match_candidates.json"
    match_path.parent.mkdir()
    match_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "source_file": "detail.xlsx",
                        "sheet": "PI",
                        "行号": "2",
                        "query": {
                            "product_category": "被套",
                            "spec": "200*230cm",
                        },
                        "decision": {"status": "insufficient_evidence"},
                        "candidates": [
                            {
                                "rank": 1,
                                "material_code": "F0903012570",
                                "prototype_match_score": 0.78,
                                "fields": {
                                    "spec": {
                                        "query_value": "200*230cm",
                                        "candidate_value": "200*230cm",
                                        "status": "exact_match",
                                    },
                                    "color": {
                                        "query_value": "白色",
                                        "candidate_value": "漂白色",
                                        "status": "partial_match",
                                    },
                                    "fabric": {
                                        "query_value": "全棉",
                                        "candidate_value": "涤棉",
                                        "status": "no_match",
                                    },
                                },
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    metadata = service._read_job(job["id"])
    metadata["status"] = "completed"
    metadata["sheet"] = "PI"
    metadata["artifacts"] = {
        "matches": match_path.relative_to(job_root).as_posix()
    }
    service._write_job(metadata)

    detail = service.match_detail(job["id"], 0)

    assert detail["recommended_code"] == "F0903012570"
    assert detail["score"] == 78.0
    assert detail["reference_score"] == 0.78
    assert detail["candidates"][0]["reference_score"] == 0.78
    assert detail["status"] == {"key": "insufficient", "label": "证据不足"}
    assert [row["status"]["label"] for row in detail["comparisons"][:3]] == [
        "一致",
        "部分匹配",
        "冲突",
    ]


def test_artifact_preview_and_bundle_are_scoped_to_job(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    job = service.create_job("result.xlsx", b"PK\x03\x04result")
    job_root = service.jobs_root / job["id"]
    result = job_root / "results" / "result_gate2d.json"
    result.write_text('[{"客户": "测试客户"}]', encoding="utf-8")
    bundle = job_root / "result.zip"
    bundle.write_bytes(b"zip")
    metadata = service._read_job(job["id"])
    metadata["artifacts"] = {
        "business": result.relative_to(job_root).as_posix(),
        "zip": bundle.relative_to(job_root).as_posix(),
    }
    service._write_job(metadata)

    assert service.get_preview(job["id"], "business") == [{"客户": "测试客户"}]
    assert service.bundle_path(job["id"]) == bundle

    metadata = service._read_job(job["id"])
    metadata["artifacts"]["business"] = "../../outside.json"
    service._write_job(metadata)
    with pytest.raises(WebJobError, match="结果文件不存在"):
        service.artifact_path(job["id"], "business")


def test_interrupted_job_propagates_cancel_before_faiss_output(
    tmp_path: Path, monkeypatch
) -> None:
    service = build_service(tmp_path)
    job = service.create_job("cancel.xlsx", b"PK\x03\x04cancel")
    writes: list[str] = []

    def fake_parse(input_path, result_path, **kwargs):
        del input_path
        Path(result_path).write_text("[]", encoding="utf-8")
        Path(kwargs["report_path"]).write_text(
            json.dumps(
                {
                    "input": {"file_name": "cancel.xlsx", "sheet_name": "PI"},
                    "records": [],
                }
            ),
            encoding="utf-8",
        )
        Path(kwargs["validation_path"]).write_text("{}", encoding="utf-8")
        return type("Summary", (), {"record_count": 0})()

    def fake_match(*args, **kwargs):
        del args
        assert kwargs["embedding_runtime_dir"].parts[-2:] == (
            "runtime",
            "embedding",
        )
        service.interrupt_active_jobs()
        kwargs["cancel_check"]()
        pytest.fail("cancel check did not interrupt matching")

    monkeypatch.setattr(order_parser, "parse_order", fake_parse)
    monkeypatch.setattr(hybrid_matcher, "match_orders", fake_match)
    monkeypatch.setattr(
        match_writer,
        "write_match_outputs",
        lambda *args, **kwargs: writes.append("written"),
    )

    service._run_job(job["id"])

    assert service._read_job(job["id"])["status"] == "interrupted"
    assert writes == []


def test_worker_failure_diagnostics_are_persisted_in_job(
    tmp_path: Path, monkeypatch
) -> None:
    service = build_service(tmp_path)
    job = service.create_job("failure.xlsx", b"PK\x03\x04failure")

    def fake_parse(input_path, result_path, **kwargs):
        del input_path
        Path(result_path).write_text("[]", encoding="utf-8")
        Path(kwargs["report_path"]).write_text(
            json.dumps(
                {
                    "input": {
                        "file_name": "failure.xlsx",
                        "sheet_name": "PI",
                    },
                    "records": [],
                }
            ),
            encoding="utf-8",
        )
        Path(kwargs["validation_path"]).write_text("{}", encoding="utf-8")
        return type(
            "Summary",
            (),
            {"record_count": 0, "input_sha256_before": "abc"},
        )()

    diagnostics = {
        "diagnostics_version": "1.0",
        "status": "failed",
        "attempt_count": 1,
        "retry_count": 0,
        "attempts": [{"failure_kind": "python_exception"}],
    }

    def fake_match(*args, **kwargs):
        del args
        assert kwargs["embedding_diagnostics_path"].name == (
            "embedding_diagnostics.json"
        )
        raise QueryEmbeddingProcessError(
            "controlled worker failure", diagnostics=diagnostics
        )

    monkeypatch.setattr(order_parser, "parse_order", fake_parse)
    monkeypatch.setattr(hybrid_matcher, "match_orders", fake_match)
    service._run_job(job["id"])

    stored = service._read_job(job["id"])
    assert stored["status"] == "failed"
    assert stored["completed_at"]
    assert stored["error"] == "controlled worker failure"
    assert stored["worker_diagnostics"] == diagnostics
    assert service.get_job(job["id"])["worker_diagnostics"] == diagnostics


@pytest.mark.parametrize("status", ["queued", "running", "processing"])
def test_desktop_startup_recovers_stale_legacy_active_jobs(
    tmp_path: Path, status: str
) -> None:
    root = tmp_path / "web"
    job_id = uuid_for_status(status)
    metadata, artifact = seed_job(root, job_id, status)

    service = JobService(
        root,
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=DeferredExecutor(),
        desktop_mode=True,
    )

    recovered = json.loads(metadata.read_text(encoding="utf-8"))
    assert recovered["status"] == "interrupted"
    assert recovered["previous_status"] == status
    assert recovered["interruption_reason"] == "application_restarted"
    assert recovered["recovery_session_id"] == service.session_id
    assert recovered["recovered_at"]
    assert recovered["error"] == (
        "上次运行异常结束，任务已标记为中断，请重新提交。"
    )
    assert artifact.is_file()
    first_recovered_at = recovered["recovered_at"]

    assert service.recover_stale_jobs() == 0
    assert service._read_job(job_id)["recovered_at"] == first_recovered_at


@pytest.mark.parametrize("status", ["completed", "failed", "interrupted"])
def test_desktop_startup_preserves_terminal_jobs(
    tmp_path: Path, status: str
) -> None:
    root = tmp_path / "web"
    job_id = uuid_for_status(status)
    metadata, _artifact = seed_job(root, job_id, status)
    before = metadata.read_bytes()

    JobService(
        root,
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=DeferredExecutor(),
        desktop_mode=True,
    )

    assert metadata.read_bytes() == before


def test_recovery_skips_current_session_and_live_owner(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    current = service.create_job("current.xlsx", b"PK\x03\x04current")
    assert service.recover_stale_jobs() == 0
    assert service._read_job(current["id"])["status"] == "queued"

    root = tmp_path / "owned-web"
    job_id = "a" * 32
    metadata, _artifact = seed_job(root, job_id, "processing", owner_pid=os.getpid())
    JobService(
        root,
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=DeferredExecutor(),
        desktop_mode=True,
    )
    assert json.loads(metadata.read_text(encoding="utf-8"))["status"] == "processing"


def test_recovery_isolates_corrupt_metadata(tmp_path: Path) -> None:
    root = tmp_path / "web"
    valid_id = "b" * 32
    corrupt_id = "c" * 32
    seed_job(root, valid_id, "processing")
    corrupt_root = root / "jobs" / corrupt_id
    corrupt_root.mkdir(parents=True)
    (corrupt_root / "job.json").write_text("{broken", encoding="utf-8")

    service = JobService(
        root,
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=DeferredExecutor(),
        desktop_mode=True,
    )

    assert service._read_job(valid_id)["status"] == "interrupted"
    assert service.recovery_errors == [f"{corrupt_id}: JSONDecodeError"]
    assert [row["id"] for row in service.list_jobs()] == [valid_id]


def test_concurrent_updates_keep_valid_json_and_terminal_status(
    tmp_path: Path,
) -> None:
    service = build_service(tmp_path)
    job = service.create_job("concurrent.xlsx", b"PK\x03\x04concurrent")
    errors: list[Exception] = []

    def update(progress: int) -> None:
        try:
            service._set_progress(job["id"], progress, f"进度 {progress}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=update, args=(value,)) for value in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    metadata_path = service.jobs_root / job["id"] / "job.json"
    assert errors == []
    assert json.loads(metadata_path.read_text(encoding="utf-8"))["status"] == "processing"
    assert list(metadata_path.parent.glob(".job.json.*.tmp")) == []

    service.interrupt_active_jobs()
    service._set_progress(job["id"], 90, "不应倒退")
    assert service._read_job(job["id"])["status"] == "interrupted"


@pytest.mark.parametrize("terminal_status", ["completed", "failed", "interrupted"])
def test_terminal_status_cannot_regress_to_processing(
    tmp_path: Path, terminal_status: str
) -> None:
    service = build_service(tmp_path)
    job = service.create_job("terminal.xlsx", b"PK\x03\x04terminal")
    metadata = service._read_job(job["id"])
    metadata["status"] = terminal_status
    service._write_job(metadata)

    service._set_progress(job["id"], 90, "迟到的进度")

    assert service._read_job(job["id"])["status"] == terminal_status


def uuid_for_status(status: str) -> str:
    return {
        "queued": "1" * 32,
        "running": "2" * 32,
        "processing": "3" * 32,
        "completed": "4" * 32,
        "failed": "5" * 32,
        "interrupted": "6" * 32,
    }[status]
