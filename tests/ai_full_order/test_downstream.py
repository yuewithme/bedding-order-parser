from __future__ import annotations

import json
import os
import socket
from dataclasses import replace
from pathlib import Path

import pytest
from openpyxl import Workbook

from bedding_order_parser.ai_full_order import downstream
from bedding_order_parser.ai_full_order.contracts import AI_BUSINESS_FIELD_NAMES
from bedding_order_parser.ai_full_order.downstream import (
    BUSINESS_NAME,
    CURRENT_ENTRY_NAME,
    DownstreamError,
    MaterialMatchOutput,
    MaterialSelection,
    publish_ready_batch,
)
from bedding_order_parser.ai_full_order.fake_provider import FakeFullOrderProvider
from bedding_order_parser.ai_full_order.orchestration import BatchAggregate, BatchStatus, formal_line_number_from_request
from bedding_order_parser.ai_full_order.preprocessing import PreprocessedWorkbook, preprocess_workbook
from bedding_order_parser.ai_full_order.reliability import OfflineReliabilityStore, OfflineReliableOrchestrator
from bedding_order_parser.ai_full_order.resolution import PythonShadowRecord, adapt_python_shadow_records
from bedding_order_parser.materials.match_writer import CANDIDATES_NAME, SUMMARY_NAME
from bedding_order_parser.models.final_result import FINAL_FIELD_NAMES


def _write_book(path: Path) -> None:
    workbook = Workbook()
    for index, (title, line_number) in enumerate((("PI-A", "1"), ("PI-B", "2"))):
        sheet = workbook.active if index == 0 else workbook.create_sheet()
        sheet.title = title
        sheet.append(["No.", "Item", "Specification", "Qty"])
        sheet.append([line_number, "Duvet Cover", "White cotton", "12"])
    workbook.save(path)


def _shadow_for(preprocessed: PreprocessedWorkbook) -> tuple[PythonShadowRecord, ...]:
    request = preprocessed.to_request_dict()
    formal_records = [
        {
            **{field: "" for field in AI_BUSINESS_FIELD_NAMES},
            "行号": formal_line_number_from_request(record, request["evidence_catalog"]),
        }
        for record in request["records"]
    ]
    return adapt_python_shadow_records(preprocessed, formal_records)


def _ready_execution(tmp_path: Path):
    source = tmp_path / "synthetic.xlsx"
    _write_book(source)
    preprocessed = preprocess_workbook(source)
    provider = FakeFullOrderProvider()
    execution = OfflineReliableOrchestrator(OfflineReliabilityStore(tmp_path / "state")).run(
        preprocessed,
        provider,
        _shadow_for(preprocessed),
        client_idempotency_key="b3-client",
        business_key="b3-business",
    )
    assert execution.batch.ready_for_downstream
    return preprocessed, provider, execution


class _FakeDictionaryValidator:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def validate(self, records, evidence):
        self.calls.append("dictionary")
        assert evidence
        return {
            "validation_version": "1.0",
            "mode": "validation_only",
            "status": "completed",
            "records": [{"行号": item.line_number} for item in records],
        }


class _FakeMaterialMatcher:
    def __init__(self, calls: list[str], *, no_candidate: bool = False, integer_score: bool = False) -> None:
        self.calls, self.no_candidate, self.integer_score = calls, no_candidate, integer_score

    def match(self, records, resolved):
        self.calls.append("matcher")
        assert all(record.values["物料编码"] == "" for record in records)
        assert all(record.values["相似分数"] == 0.0 for record in records)
        score = 0 if self.integer_score else (0.0 if self.no_candidate else 0.75)
        code = "" if self.no_candidate else "MAT-001"
        selections = {
            item.source_record_id: MaterialSelection(item.source_record_id, code, score)
            for item in resolved
        }
        candidates = {
            "mode": "manual_review_only",
            "record_count": len(records),
            "records": [{"行号": item.values["行号"], "candidates": []} for item in records],
        }
        summary = {
            "mode": "manual_review_only",
            "record_count": len(records),
            "accuracy_statement": "相似分数不是准确率，候选只用于人工复核。",
        }
        return MaterialMatchOutput(selections, candidates, summary)


def _publish(tmp_path: Path, *, no_candidate: bool = False):
    preprocessed, provider, execution = _ready_execution(tmp_path)
    calls: list[str] = []
    bundle = publish_ready_batch(
        execution,
        preprocessed=preprocessed,
        dictionary_validator=_FakeDictionaryValidator(calls),
        material_matcher=_FakeMaterialMatcher(calls, no_candidate=no_candidate),
        publish_root=tmp_path / "published",
    )
    return preprocessed, provider, execution, calls, bundle


def test_ready_batch_adapts_in_order_and_publishes_exactly_five_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network forbidden")))
    _preprocessed, provider, execution, calls, bundle = _publish(tmp_path)

    assert calls == ["dictionary", "matcher"]
    assert provider.network_call_count == 0
    assert len(list(bundle.bundle_dir.glob("*.json"))) == 5
    assert {path.name for path in bundle.paths.values()} == {
        BUSINESS_NAME,
        "ai_full_order_parse_report.json",
        "ai_full_order_dictionary_validation.json",
        CANDIDATES_NAME,
        SUMMARY_NAME,
    }
    business = json.loads(bundle.paths[BUSINESS_NAME].read_text(encoding="utf-8"))
    assert all(tuple(record) == FINAL_FIELD_NAMES for record in business)
    assert all(record["物料编码"] == "MAT-001" and record["相似分数"] == 0.75 for record in business)
    assert all("parse_mode" not in record and "cache_key" not in record for record in business)
    assert all("物料编码" not in record.business_fields() for record in execution.batch.records)
    diagnostic = json.loads(bundle.paths["ai_full_order_parse_report.json"].read_text(encoding="utf-8"))
    assert diagnostic["ai_enhanced"]["parse_mode"] == "ai_enhanced"
    assert (tmp_path / "published" / CURRENT_ENTRY_NAME).read_text(encoding="utf-8").strip() == execution.cache_key


def test_nonready_batch_does_not_invoke_downstream_ports(tmp_path: Path) -> None:
    preprocessed, _provider, execution = _ready_execution(tmp_path)
    isolated = replace(execution, batch=BatchAggregate(BatchStatus.ISOLATED, ("missing_chunks",), ()))
    calls: list[str] = []

    with pytest.raises(DownstreamError, match="ready_for_downstream"):
        publish_ready_batch(
            isolated,
            preprocessed=preprocessed,
            dictionary_validator=_FakeDictionaryValidator(calls),
            material_matcher=_FakeMaterialMatcher(calls),
            publish_root=tmp_path / "published",
        )

    assert calls == []
    assert not (tmp_path / "published").exists()


def test_no_candidate_keeps_empty_code_and_float_zero(tmp_path: Path) -> None:
    _preprocessed, _provider, _execution, _calls, bundle = _publish(tmp_path, no_candidate=True)
    business = json.loads(bundle.paths[BUSINESS_NAME].read_text(encoding="utf-8"))

    assert all(record["物料编码"] == "" for record in business)
    assert all(record["相似分数"] == 0.0 and isinstance(record["相似分数"], float) for record in business)


def test_matcher_requires_float_score_from_its_own_boundary(tmp_path: Path) -> None:
    preprocessed, _provider, execution = _ready_execution(tmp_path)
    calls: list[str] = []

    with pytest.raises(DownstreamError, match="float"):
        publish_ready_batch(
            execution,
            preprocessed=preprocessed,
            dictionary_validator=_FakeDictionaryValidator(calls),
            material_matcher=_FakeMaterialMatcher(calls, integer_score=True),
            publish_root=tmp_path / "published",
        )

    assert calls == ["dictionary", "matcher"]


def test_third_artifact_failure_keeps_final_location_empty(tmp_path: Path, monkeypatch) -> None:
    preprocessed, _provider, execution = _ready_execution(tmp_path)
    original = downstream._write_json
    count = 0

    def fail_third(path, payload, retries):
        nonlocal count
        count += 1
        if count == 3:
            raise OSError("injected third artifact failure")
        original(path, payload, retries)

    monkeypatch.setattr(downstream, "_write_json", fail_third)
    with pytest.raises(OSError, match="third artifact"):
        publish_ready_batch(
            execution,
            preprocessed=preprocessed,
            dictionary_validator=_FakeDictionaryValidator([]),
            material_matcher=_FakeMaterialMatcher([]),
            publish_root=tmp_path / "published",
        )

    root = tmp_path / "published"
    assert not (root / "bundles" / execution.cache_key).exists()
    assert not (root / CURRENT_ENTRY_NAME).exists()
    assert not list(root.rglob("*.json"))


def test_same_content_is_stable_different_cache_is_isolated_and_windows_retry_is_bounded(tmp_path: Path, monkeypatch) -> None:
    preprocessed, _provider, execution = _ready_execution(tmp_path)
    root = tmp_path / "published"
    first = publish_ready_batch(
        execution,
        preprocessed=preprocessed,
        dictionary_validator=_FakeDictionaryValidator([]),
        material_matcher=_FakeMaterialMatcher([]),
        publish_root=root,
    )
    original_replace = os.replace
    failed_once = False

    def busy_current(source, target):
        nonlocal failed_once
        if Path(target).name == CURRENT_ENTRY_NAME and not failed_once:
            failed_once = True
            raise PermissionError("simulated Windows file lock")
        return original_replace(source, target)

    monkeypatch.setattr(downstream.os, "replace", busy_current)
    repeated = publish_ready_batch(
        execution,
        preprocessed=preprocessed,
        dictionary_validator=_FakeDictionaryValidator([]),
        material_matcher=_FakeMaterialMatcher([]),
        publish_root=root,
    )
    other = publish_ready_batch(
        replace(execution, cache_key="other-cache-key"),
        preprocessed=preprocessed,
        dictionary_validator=_FakeDictionaryValidator([]),
        material_matcher=_FakeMaterialMatcher([]),
        publish_root=root,
    )

    assert failed_once
    assert repeated.reused
    assert first.content_sha256 == repeated.content_sha256
    assert first.bundle_dir.exists() and other.bundle_dir.exists()
    assert first.bundle_dir != other.bundle_dir
    assert (root / CURRENT_ENTRY_NAME).read_text(encoding="utf-8").strip() == "other-cache-key"
