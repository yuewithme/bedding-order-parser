from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest
from openpyxl import Workbook

from bedding_order_parser.ai_full_order import downstream
from bedding_order_parser.ai_full_order.downstream import (
    BUSINESS_NAME,
    CURRENT_ENTRY_NAME,
    DownstreamError,
    MaterialMatchOutput,
    MaterialSelection,
    PublicationError,
    publish_ready_v2_batch,
)
from bedding_order_parser.ai_full_order.fake_provider import FakeV2CandidateProvider
from bedding_order_parser.ai_full_order.orchestration import build_v2_extraction_units
from bedding_order_parser.ai_full_order.preprocessing import EvidenceItem, preprocess_workbook
from bedding_order_parser.ai_full_order.python_shadow import build_deterministic_python_shadow
from bedding_order_parser.ai_full_order.reliability_v2 import (
    V2ReliabilityStore,
    V2ReliableOrchestrator,
)
from bedding_order_parser.materials.match_writer import CANDIDATES_NAME, SUMMARY_NAME
from bedding_order_parser.models.final_result import FINAL_FIELD_NAMES


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: pytest.fail("network forbidden"),
    )


def _write_book(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "PI"
    sheet.append(["", "PROFORMA INVOICE", "", "", "Unit Price (USD)"])
    sheet.append(["BUYER:", "", "", "", ""])
    sheet.append(["Test Hotel", "", "", "", "Contact Person: Aaron Lee"])
    sheet.append(["Delivery date:", "2026-09-30", "", "", ""])
    sheet.append(["No.", "Item", "Size", "Specification", "Qty"])
    sheet.append(["1", "Duvet Cover", "200*240", "100% cotton white", "12"])
    workbook.save(path)


def _context(path: Path):
    preprocessed = preprocess_workbook(path)
    units = build_v2_extraction_units(preprocessed)
    evidence: dict[str, EvidenceItem] = {}
    for unit in units:
        evidence.update({item.evidence_id: item for item in unit.evidence_catalog})
    shadow = build_deterministic_python_shadow(
        path,
        preprocessed,
        target_records=[unit.target for unit in units],
        evidence_catalog=tuple(evidence.values()),
    )
    return preprocessed, units, shadow


def _execution(tmp_path: Path, payload=None, *, state_name: str = "state"):
    source = tmp_path / f"{state_name}.xlsx"
    _write_book(source)
    preprocessed, units, shadow = _context(source)
    provider = FakeV2CandidateProvider(payload or {"candidates": []})
    execution = V2ReliableOrchestrator(
        V2ReliabilityStore(tmp_path / state_name)
    ).run(
        preprocessed,
        provider,
        shadow,
        client_idempotency_key=f"client:{state_name}",
        business_key="business:synthetic-v2",
    )
    return preprocessed, units, provider, execution


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
            "records": [{"行号": record.line_number} for record in records],
        }


class _FakeMaterialMatcher:
    def __init__(
        self,
        calls: list[str],
        *,
        material_code: str = "MAT-001",
        score: float = 0.75,
    ) -> None:
        self.calls = calls
        self.material_code = material_code
        self.score = score

    def match(self, records, resolved):
        self.calls.append("matcher")
        assert all(record.values["物料编码"] == "" for record in records)
        assert all(record.values["相似分数"] == 0.0 for record in records)
        return MaterialMatchOutput(
            selections={
                record.source_record_id: MaterialSelection(
                    record.source_record_id, self.material_code, self.score
                )
                for record in resolved
            },
            candidates_payload={
                "mode": "manual_review_only",
                "record_count": len(records),
                "records": [
                    {"行号": record.values["行号"], "candidates": []}
                    for record in records
                ],
            },
            summary_payload={
                "mode": "manual_review_only",
                "record_count": len(records),
                "accuracy_statement": "相似分数不是准确率，候选只用于人工复核。",
            },
        )


def _publish(tmp_path: Path, payload=None, *, root_name: str = "published"):
    preprocessed, units, provider, execution = _execution(tmp_path, payload)
    calls: list[str] = []
    bundle = publish_ready_v2_batch(
        execution,
        preprocessed=preprocessed,
        dictionary_validator=_FakeDictionaryValidator(calls),
        material_matcher=_FakeMaterialMatcher(calls),
        publish_root=tmp_path / root_name,
    )
    return preprocessed, units, provider, execution, calls, bundle


def test_v2_ready_batch_publishes_exactly_five_validated_roles_and_twenty_fields(
    tmp_path: Path,
) -> None:
    _preprocessed, _units, provider, execution, calls, bundle = _publish(tmp_path)

    assert calls == ["dictionary", "matcher"]
    assert provider.network_call_count == 0
    assert len(list(bundle.bundle_dir.glob("*.json"))) == 5
    assert set(bundle.paths) == {
        BUSINESS_NAME,
        "ai_full_order_parse_report.json",
        "ai_full_order_dictionary_validation.json",
        CANDIDATES_NAME,
        SUMMARY_NAME,
    }
    business = json.loads(bundle.paths[BUSINESS_NAME].read_text(encoding="utf-8"))
    assert tuple(business[0]) == FINAL_FIELD_NAMES
    assert all(isinstance(business[0][name], str) for name in FINAL_FIELD_NAMES[:-1])
    assert isinstance(business[0]["相似分数"], float)
    assert business[0]["行号"] == "1"
    assert business[0]["物料编码"] == "MAT-001"
    assert business[0]["相似分数"] == 0.75
    assert "物料编码" not in execution.batch.records[0].business_fields()
    assert "相似分数" not in execution.batch.records[0].business_fields()


def test_v2_diagnostics_hold_only_controlled_v2_metadata(tmp_path: Path) -> None:
    _preprocessed, _units, _provider, execution, _calls, bundle = _publish(tmp_path)
    diagnostic = json.loads(
        bundle.paths["ai_full_order_parse_report.json"].read_text(encoding="utf-8")
    )
    envelope = diagnostic["ai_enhanced"]
    serialized = json.dumps(diagnostic, ensure_ascii=False).casefold()

    assert envelope["protocol"] == "v2"
    assert envelope["cache_key"] == execution.cache_key
    assert "cache_identity" not in envelope
    assert envelope["contract_versions"]["field_policy_version"] == "3.0"
    assert envelope["contract_versions"]["normalization_version"] == "1.0"
    assert envelope["contract_versions"]["comparison_version"] == "1.0"
    assert envelope["technical_readiness"] == {
        "technical_ready": True,
        "failure_reasons": [],
    }
    assert envelope["unit_states"] == ["validated"]
    assert envelope["review_summary"]["review_required"] is True
    assert len(envelope["provider_telemetry"]) == 1
    field = envelope["field_decisions"][0]["fields"]["客户"]
    assert set(field) == {
        "field_name",
        "formal_value",
        "ai_display_value",
        "ai_normalized_value",
        "ai_evidence_ids",
        "ai_supporting_quote",
        "python_display_value",
        "python_normalized_value",
        "python_evidence_ids",
        "comparison_status",
        "status",
        "selected_source",
        "review_required",
        "review_severity",
        "reason_codes",
        "technical_candidate_status",
        "candidate_issue_code",
    }
    referenced = {
        evidence_id
        for row in envelope["field_decisions"]
        for item in row["fields"].values()
        for key in ("ai_evidence_ids", "python_evidence_ids")
        for evidence_id in item[key]
    }
    assert set(envelope["evidence_display"]) == referenced
    assert all(
        set(item) == {
            "sheet_id",
            "sheet_name",
            "cell_range",
            "source_row",
            "excerpt",
        }
        for item in envelope["evidence_display"].values()
    )
    assert all(item["cell_range"] for item in envelope["evidence_display"].values())
    assert all(len(item["excerpt"]) <= 180 for item in envelope["evidence_display"].values())
    assert not any(
        forbidden in serialized
        for forbidden in ("authorization", "api_key", "raw_response", "system_prompt")
    )


def test_high_review_conflict_reaches_downstream_and_publishes(tmp_path: Path) -> None:
    source = tmp_path / "blocking.xlsx"
    _write_book(source)
    preprocessed, units, shadow = _context(source)
    evidence = next(item for item in units[0].evidence_catalog if "Aaron Lee" in item.original_text)
    payload = {
        "candidates": [
            {
                "field_name": "客户",
                "candidate_value": "Aaron Lee",
                "evidence_references": [evidence.evidence_id],
                "interpretation": "direct",
                "supporting_quote": "",
            }
        ]
    }
    execution = V2ReliableOrchestrator(V2ReliabilityStore(tmp_path / "state")).run(
        preprocessed,
        FakeV2CandidateProvider(payload),
        shadow,
        client_idempotency_key="blocking",
        business_key="business:blocking",
    )
    calls: list[str] = []

    bundle = publish_ready_v2_batch(
        execution,
        preprocessed=preprocessed,
        dictionary_validator=_FakeDictionaryValidator(calls),
        material_matcher=_FakeMaterialMatcher(calls),
        publish_root=tmp_path / "published",
    )

    decision = execution.batch.records[0].decisions["客户"]
    assert execution.batch.ready_for_downstream
    assert execution.batch.technical_ready
    assert execution.batch.review_required
    assert execution.batch.high_review_count >= 1
    assert decision.value == "Aaron Lee"
    assert decision.selected_source == "ai"
    assert decision.blocking is False
    assert calls == ["dictionary", "matcher"]
    assert len(bundle.paths) == 5
    business = json.loads(bundle.paths[BUSINESS_NAME].read_text(encoding="utf-8"))
    diagnostic = json.loads(
        bundle.paths["ai_full_order_parse_report.json"].read_text(encoding="utf-8")
    )
    field = diagnostic["ai_enhanced"]["field_decisions"][0]["fields"]["客户"]
    assert field["formal_value"] == "Aaron Lee"
    assert field["comparison_status"] == "different"
    assert field["selected_source"] == "ai"
    assert field["review_required"] is True
    assert field["review_severity"] == "high"
    assert "ai_display_value" in field and "python_display_value" in field
    assert tuple(business[0]) == FINAL_FIELD_NAMES
    assert not ({"ai_value", "python_value", "review_status", "evidence"} & set(business[0]))


@pytest.mark.parametrize(
    ("field_name", "expected_status"),
    [("规格", "different"), ("包装方式", "ai_only")],
)
def test_ordinary_review_and_ai_only_are_technically_ready_and_publish(
    tmp_path: Path, field_name: str, expected_status: str
) -> None:
    source = tmp_path / f"review-{expected_status}.xlsx"
    _write_book(source)
    preprocessed, units, shadow = _context(source)
    evidence = next(item for item in units[0].evidence_catalog if "cotton" in item.original_text)
    payload = {
        "candidates": [
            {
                "field_name": field_name,
                "candidate_value": evidence.original_text,
                "evidence_references": [evidence.evidence_id],
                "interpretation": "direct",
                "supporting_quote": evidence.original_text,
            }
        ]
    }
    execution = V2ReliableOrchestrator(V2ReliabilityStore(tmp_path / expected_status)).run(
        preprocessed,
        FakeV2CandidateProvider(payload),
        shadow,
        client_idempotency_key=f"client:{expected_status}",
        business_key=f"business:{expected_status}",
    )
    calls: list[str] = []
    bundle = publish_ready_v2_batch(
        execution,
        preprocessed=preprocessed,
        dictionary_validator=_FakeDictionaryValidator(calls),
        material_matcher=_FakeMaterialMatcher(calls),
        publish_root=tmp_path / f"published-{expected_status}",
    )
    diagnostic = json.loads(
        bundle.paths["ai_full_order_parse_report.json"].read_text(encoding="utf-8")
    )
    field = diagnostic["ai_enhanced"]["field_decisions"][0]["fields"][field_name]

    assert execution.batch.technical_ready
    assert execution.disposition.value == "executed"
    assert calls == ["dictionary", "matcher"]
    assert field["comparison_status"] == expected_status
    assert field["selected_source"] == "ai"
    assert field["review_required"] is (expected_status == "different")


@pytest.mark.parametrize(
    "field_name,evidence_id",
    [("颜色", "unknown-evidence"), ("物料编码", "unknown-evidence")],
    ids=["unknown_evidence", "forbidden_material_field"],
)
def test_hard_contract_failure_never_calls_downstream(
    tmp_path: Path, field_name: str, evidence_id: str
) -> None:
    payload = {
        "candidates": [
            {
                "field_name": field_name,
                "candidate_value": "MODEL-CODE",
                "evidence_references": [evidence_id],
                "interpretation": "direct",
                "supporting_quote": "",
            }
        ]
    }
    preprocessed, _units, _provider, execution = _execution(
        tmp_path, payload, state_name=f"hard-{field_name}"
    )
    calls: list[str] = []

    with pytest.raises(DownstreamError):
        publish_ready_v2_batch(
            execution,
            preprocessed=preprocessed,
            dictionary_validator=_FakeDictionaryValidator(calls),
            material_matcher=_FakeMaterialMatcher(calls),
            publish_root=tmp_path / "published",
        )
    assert calls == []
    assert not (tmp_path / "published").exists()


def test_candidate_content_issue_can_publish_and_is_diagnostic_only(tmp_path: Path) -> None:
    source = tmp_path / "ordinary.xlsx"
    _write_book(source)
    preprocessed, units, shadow = _context(source)
    evidence = next(item for item in units[0].evidence_catalog if "cotton" in item.original_text)
    payload = {
        "candidates": [
            {
                "field_name": "包装方式",
                "candidate_value": "invented packaging",
                "evidence_references": [evidence.evidence_id],
                "interpretation": "direct",
                "supporting_quote": "",
            }
        ]
    }
    execution = V2ReliableOrchestrator(V2ReliabilityStore(tmp_path / "state")).run(
        preprocessed,
        FakeV2CandidateProvider(payload),
        shadow,
        client_idempotency_key="ordinary",
        business_key="business:ordinary",
    )
    calls: list[str] = []
    bundle = publish_ready_v2_batch(
        execution,
        preprocessed=preprocessed,
        dictionary_validator=_FakeDictionaryValidator(calls),
        material_matcher=_FakeMaterialMatcher(calls),
        publish_root=tmp_path / "published",
    )
    business = json.loads(bundle.paths[BUSINESS_NAME].read_text(encoding="utf-8"))
    diagnostic = json.loads(
        bundle.paths["ai_full_order_parse_report.json"].read_text(encoding="utf-8")
    )

    assert calls == ["dictionary", "matcher"]
    assert business[0]["包装方式"] == ""
    envelope = diagnostic["ai_enhanced"]
    assert envelope["unit_states"] == ["validated_with_content_issue"]
    assert envelope["review_summary"]["content_issue_field_count"] == 1


def test_bound_content_issue_uses_python_fallback_and_still_publishes(tmp_path: Path) -> None:
    source = tmp_path / "content-fallback.xlsx"
    _write_book(source)
    preprocessed, units, shadow = _context(source)
    evidence = next(item for item in units[0].evidence_catalog if "cotton" in item.original_text)
    payload = {
        "candidates": [
            {
                "field_name": "规格",
                "candidate_value": "invented item",
                "evidence_references": [evidence.evidence_id],
                "interpretation": "direct",
                "supporting_quote": "",
            }
        ]
    }
    execution = V2ReliableOrchestrator(V2ReliabilityStore(tmp_path / "fallback-state")).run(
        preprocessed,
        FakeV2CandidateProvider(payload),
        shadow,
        client_idempotency_key="content-fallback",
        business_key="business:content-fallback",
    )
    calls: list[str] = []
    bundle = publish_ready_v2_batch(
        execution,
        preprocessed=preprocessed,
        dictionary_validator=_FakeDictionaryValidator(calls),
        material_matcher=_FakeMaterialMatcher(calls),
        publish_root=tmp_path / "published-fallback",
    )
    diagnostic = json.loads(
        bundle.paths["ai_full_order_parse_report.json"].read_text(encoding="utf-8")
    )
    field = diagnostic["ai_enhanced"]["field_decisions"][0]["fields"]["规格"]

    assert execution.batch.technical_ready
    assert calls == ["dictionary", "matcher"]
    assert field["selected_source"] == "python_fallback"
    assert field["technical_candidate_status"] == "content_issue"
    assert field["review_required"] is True


def test_cache_hit_republish_has_zero_provider_calls_and_stable_five_hashes(tmp_path: Path) -> None:
    source = tmp_path / "cached.xlsx"
    _write_book(source)
    preprocessed, _units, shadow = _context(source)
    root = tmp_path / "state"
    publish_root = tmp_path / "published"
    first_provider = FakeV2CandidateProvider({"candidates": []})
    orchestrator = V2ReliableOrchestrator(V2ReliabilityStore(root))
    first = orchestrator.run(
        preprocessed,
        first_provider,
        shadow,
        client_idempotency_key="cached",
        business_key="business:cached",
    )
    first_bundle = publish_ready_v2_batch(
        first,
        preprocessed=preprocessed,
        dictionary_validator=_FakeDictionaryValidator([]),
        material_matcher=_FakeMaterialMatcher([]),
        publish_root=publish_root,
    )
    cached_provider = FakeV2CandidateProvider({"candidates": []})
    cached = orchestrator.run(
        preprocessed,
        cached_provider,
        shadow,
        client_idempotency_key="cached",
        business_key="business:cached",
    )
    cached_bundle = publish_ready_v2_batch(
        cached,
        preprocessed=preprocessed,
        dictionary_validator=_FakeDictionaryValidator([]),
        material_matcher=_FakeMaterialMatcher([]),
        publish_root=publish_root,
    )

    assert cached.provider_calls == cached_provider.extraction_call_count == 0
    assert cached_bundle.reused
    assert first_bundle.content_sha256 == cached_bundle.content_sha256


@pytest.mark.parametrize("failure_index", [1, 3, 5])
def test_each_bundle_write_failure_keeps_v2_result_fully_invisible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_index: int
) -> None:
    preprocessed, _units, _provider, execution = _execution(
        tmp_path, state_name=f"failure-{failure_index}"
    )
    original = downstream._write_json
    count = 0

    def injected(path, payload, retries):
        nonlocal count
        count += 1
        if count == failure_index:
            raise OSError(f"injected artifact {failure_index} failure")
        return original(path, payload, retries)

    monkeypatch.setattr(downstream, "_write_json", injected)
    root = tmp_path / f"published-{failure_index}"
    with pytest.raises(OSError, match="injected artifact"):
        publish_ready_v2_batch(
            execution,
            preprocessed=preprocessed,
            dictionary_validator=_FakeDictionaryValidator([]),
            material_matcher=_FakeMaterialMatcher([]),
            publish_root=root,
        )

    assert not (root / "bundles" / execution.cache_key).exists()
    assert not (root / CURRENT_ENTRY_NAME).exists()
    assert not list(root.rglob("*.json"))


def test_failed_conflicting_republish_preserves_existing_bundle_and_current(tmp_path: Path) -> None:
    preprocessed, _units, _provider, execution = _execution(tmp_path)
    root = tmp_path / "published"
    first = publish_ready_v2_batch(
        execution,
        preprocessed=preprocessed,
        dictionary_validator=_FakeDictionaryValidator([]),
        material_matcher=_FakeMaterialMatcher([], material_code="MAT-001"),
        publish_root=root,
    )
    with pytest.raises(PublicationError, match="contract mismatch|different result identity"):
        publish_ready_v2_batch(
            execution,
            preprocessed=preprocessed,
            dictionary_validator=_FakeDictionaryValidator([]),
            material_matcher=_FakeMaterialMatcher([], material_code="MAT-002"),
            publish_root=root,
        )

    business = json.loads(first.paths[BUSINESS_NAME].read_text(encoding="utf-8"))
    assert business[0]["物料编码"] == "MAT-001"
    assert (root / CURRENT_ENTRY_NAME).read_text(encoding="utf-8").strip() == execution.cache_key


def test_v2_publication_retries_windows_current_lock_boundedly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preprocessed, _units, _provider, execution = _execution(tmp_path)
    root = tmp_path / "published"
    publish_ready_v2_batch(
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
            raise PermissionError("simulated Windows lock")
        return original_replace(source, target)

    monkeypatch.setattr(downstream.os, "replace", busy_current)
    reused = publish_ready_v2_batch(
        execution,
        preprocessed=preprocessed,
        dictionary_validator=_FakeDictionaryValidator([]),
        material_matcher=_FakeMaterialMatcher([]),
        publish_root=root,
    )

    assert failed_once
    assert reused.reused
    assert (root / CURRENT_ENTRY_NAME).read_text(encoding="utf-8").strip() == execution.cache_key
