from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from bedding_order_parser.ai_full_order import revisions
from bedding_order_parser.ai_full_order.revisions import (
    RevisionAction,
    RevisionConflict,
    RevisionRequest,
    RevisionValidationError,
)
from bedding_order_parser.web.ai_full_order_service import AIEnhancedDependencies
from tests.web.test_ai_full_order_jobs import (
    _FakeDictionaryValidator,
    _FakeMaterialMatcher,
    _candidate,
    _job_units,
    _service,
    _single_workbook_bytes,
)


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: pytest.fail("network forbidden"),
    )


def _completed_review_job(tmp_path: Path):
    service, provider, dictionary, matcher = _service(tmp_path)
    job = service.create_job(
        "revision.xlsx", _single_workbook_bytes(), parse_mode="ai_enhanced"
    )
    _preprocessed, units = _job_units(service, job["id"])
    evidence = next(
        item for item in units[0].evidence_catalog if "Aaron Lee" in item.original_text
    )
    provider.payload = {
        "candidates": [_candidate("客户", "Aaron Lee", evidence.evidence_id)]
    }
    service._run_job(job["id"])
    return service, provider, dictionary, matcher, job["id"]


def _revision_request(review, item, action, manual_value=""):
    return {
        "expected_current_revision": review["revision"]["current_revision"],
        "source_record_id": item["source_record_id"],
        "field_name": item["field_name"],
        "action": action,
        "manual_value": manual_value,
    }


def test_completed_v2_initializes_immutable_revision_zero(tmp_path: Path) -> None:
    service, provider, dictionary, matcher, job_id = _completed_review_job(tmp_path)

    job = service.get_job(job_id)
    review = service.get_ai_review(job_id)
    root = service.jobs_root / job_id / "ai-bundle"
    revision_id = job["result_revision"]["current_revision"]
    initial_bundle = root / "revisions" / revision_id
    before = {path.name: path.read_bytes() for path in initial_bundle.glob("*.json")}

    assert job["status"] == "completed"
    assert job["result_revision"] == {
        "supported": True,
        "initial_revision": revision_id,
        "current_revision": revision_id,
        "revision_number": 0,
        "revision_count": 1,
    }
    assert review["revision"]["supported"] is True
    assert (root / "INITIAL").read_text(encoding="utf-8").strip() == revision_id
    assert (root / "CURRENT").read_text(encoding="utf-8").strip() == revision_id
    assert len(before) == 5
    assert provider.extraction_call_count == 1
    assert dictionary.calls == matcher.calls == 1


def test_keep_ai_use_python_and_manual_create_auditable_local_revisions(
    tmp_path: Path,
) -> None:
    service, provider, dictionary, matcher, job_id = _completed_review_job(tmp_path)
    original_calls = provider.extraction_call_count
    original_tokens = service.get_job(job_id)["ai_execution"]["token_summary"]
    initial_review = service.get_ai_review(job_id)
    initial_revision = initial_review["revision"]["current_revision"]
    root = service.jobs_root / job_id / "ai-bundle"
    initial_bytes = {
        path.name: path.read_bytes()
        for path in (root / "revisions" / initial_revision).glob("*.json")
    }
    customer = next(item for item in initial_review["items"] if item["field_name"] == "客户")
    assert customer["comparison_status"] == "different"
    assert customer["available_actions"] == {
        "keep_ai": True,
        "use_python": True,
        "manual_override": True,
    }

    kept = service.revise_ai_result(
        job_id, _revision_request(initial_review, customer, "keep_ai")
    )
    revision_one = kept["revision"]["current_revision"]
    kept_customer = next(
        item for item in kept["review"]["items"] if item["field_name"] == "客户"
    )
    assert revision_one != initial_revision
    assert kept_customer["formal_value"] == "Aaron Lee"
    assert kept_customer["comparison_status"] == "different"
    assert kept_customer["review_status"] == "confirmed_ai"
    assert kept_customer["review_required"] is False

    duplicate = service.revise_ai_result(
        job_id, _revision_request(initial_review, customer, "keep_ai")
    )
    assert duplicate["revision"]["reused"] is True
    assert duplicate["revision"]["current_revision"] == revision_one

    with pytest.raises(RevisionConflict, match="刷新"):
        service.revise_ai_result(
            job_id, _revision_request(initial_review, customer, "use_python")
        )

    current_review = service.get_ai_review(job_id)
    current_customer = next(
        item for item in current_review["items"] if item["field_name"] == "客户"
    )
    selected = service.revise_ai_result(
        job_id, _revision_request(current_review, current_customer, "use_python")
    )
    selected_customer = next(
        item for item in selected["review"]["items"] if item["field_name"] == "客户"
    )
    assert selected_customer["formal_value"] == current_customer["python_normalized_value"]
    assert selected_customer["selected_source"] == "user_selected_python"
    assert selected_customer["review_status"] == "selected_python"
    assert selected_customer["comparison_status"] == "different"

    current_review = service.get_ai_review(job_id)
    missing = next(
        item for item in current_review["items"] if item["comparison_status"] == "both_missing"
    )
    manual = service.revise_ai_result(
        job_id,
        _revision_request(
            current_review, missing, "manual_override", "  user value  "
        ),
    )
    revised_missing = next(
        item
        for item in manual["review"]["items"]
        if item["field_name"] == missing["field_name"]
    )
    assert revised_missing["formal_value"] == "  user value  "
    assert revised_missing["selected_source"] == "user_override"
    assert revised_missing["review_status"] == "manual_override"
    assert revised_missing["ai_evidence"] == []
    assert manual["revision"]["revision_number"] == 3
    assert provider.extraction_call_count == original_calls
    assert service.get_job(job_id)["ai_execution"]["token_summary"] == original_tokens
    assert dictionary.calls == matcher.calls == 4
    assert service.get_job(job_id)["status"] == "completed"

    assert initial_bytes == {
        path.name: path.read_bytes()
        for path in (root / "revisions" / initial_revision).glob("*.json")
    }
    assert len(list((root / "revision-metadata").glob("*.json"))) == 4
    assert len(list((root / "revisions").iterdir())) == 4
    assert all(
        len(list(path.glob("*.json"))) == 5
        for path in (root / "revisions").iterdir()
    )
    official = service.get_preview(job_id, "official_result")
    assert official[0][missing["field_name"]] == "  user value  "


def test_manual_normalization_and_matcher_authority_are_preserved(tmp_path: Path) -> None:
    service, provider, dictionary, matcher, job_id = _completed_review_job(tmp_path)
    review = service.get_ai_review(job_id)
    quantity = next(item for item in review["items"] if item["field_name"] == "数量")
    result = service.revise_ai_result(
        job_id,
        _revision_request(review, quantity, "manual_override", "10.0"),
    )
    revised = next(
        item for item in result["review"]["items"] if item["field_name"] == "数量"
    )
    official = service.get_preview(job_id, "official_result")[0]
    diagnostic = service.get_preview(job_id, "parse_diagnostics")

    assert revised["formal_value"] == "10"
    assert revised["user_revision"] == {
        "action": "manual_override",
        "selected_source": "user_override",
        "user_display_value": "10.0",
        "user_normalized_value": "10",
        "normalization_rule": "decimal_quantity",
    }
    assert official["物料编码"] == "MAT-001"
    assert official["相似分数"] == 0.75
    lineage = diagnostic["ai_enhanced"]["publication_revision"]
    assert lineage["action"] == "manual_override"
    assert lineage["user_display_value"] == "10.0"
    assert lineage["user_normalized_value"] == "10"
    assert provider.extraction_call_count == 1
    assert dictionary.calls == matcher.calls == 2


class _WarningDictionaryValidator(_FakeDictionaryValidator):
    def validate(self, records, evidence):
        payload = super().validate(records, evidence)
        payload["status"] = "completed_with_warnings"
        payload["warnings"] = ["synthetic unknown value"]
        return payload


def test_dictionary_warning_does_not_override_or_block_manual_value(tmp_path: Path) -> None:
    service, provider, _dictionary, matcher, job_id = _completed_review_job(tmp_path)
    warning_dictionary = _WarningDictionaryValidator()
    service.ai_enhanced_dependencies = AIEnhancedDependencies(
        provider=provider,
        dictionary_validator=warning_dictionary,
        material_matcher=matcher,
    )
    review = service.get_ai_review(job_id)
    missing = next(
        item for item in review["items"] if item["comparison_status"] == "both_missing"
    )

    service.revise_ai_result(
        job_id,
        _revision_request(review, missing, "manual_override", "字典未知但用户确认"),
    )

    assert service.get_preview(job_id, "official_result")[0][missing["field_name"]] == "字典未知但用户确认"
    validation = service.get_preview(job_id, "dictionary_validation")
    assert validation["status"] == "completed_with_warnings"
    assert validation["warnings"] == ["synthetic unknown value"]
    assert warning_dictionary.calls == 1
    assert provider.extraction_call_count == 1


class _FailingMatcher(_FakeMaterialMatcher):
    def match(self, records, resolved):
        self.calls += 1
        raise RuntimeError("injected matcher failure")


def test_revision_failure_keeps_old_current_and_rejects_forbidden_fields(
    tmp_path: Path,
) -> None:
    service, provider, dictionary, matcher, job_id = _completed_review_job(tmp_path)
    review = service.get_ai_review(job_id)
    current = review["revision"]["current_revision"]
    customer = next(item for item in review["items"] if item["field_name"] == "客户")
    failing = _FailingMatcher()
    service.ai_enhanced_dependencies = AIEnhancedDependencies(
        provider=provider,
        dictionary_validator=dictionary,
        material_matcher=failing,
    )

    with pytest.raises(RuntimeError, match="injected matcher failure"):
        service.revise_ai_result(
            job_id, _revision_request(review, customer, "use_python")
        )
    assert service.get_job(job_id)["result_revision"]["current_revision"] == current
    assert service.get_preview(job_id, "official_result")[0]["客户"] == "Aaron Lee"
    assert provider.extraction_call_count == 1

    forbidden = _revision_request(review, customer, "manual_override", "MAT-X")
    forbidden["field_name"] = "物料编码"
    with pytest.raises(RevisionValidationError, match="17"):
        service.revise_ai_result(job_id, forbidden)
    injected = _revision_request(review, customer, "keep_ai")
    injected["material_code"] = "MAT-X"
    with pytest.raises(Exception, match="不允许"):
        service.revise_ai_result(job_id, injected)


def test_current_switch_failure_leaves_old_revision_visible_and_cleans_new_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, provider, _dictionary, _matcher, job_id = _completed_review_job(tmp_path)
    review = service.get_ai_review(job_id)
    current = review["revision"]["current_revision"]
    customer = next(item for item in review["items"] if item["field_name"] == "客户")
    root = service.jobs_root / job_id / "ai-bundle"
    before_revisions = {path.name for path in (root / "revisions").iterdir()}
    monkeypatch.setattr(
        revisions,
        "switch_bundle_current",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("locked")),
    )

    with pytest.raises(PermissionError, match="locked"):
        service.revise_ai_result(
            job_id, _revision_request(review, customer, "use_python")
        )

    assert (root / "CURRENT").read_text(encoding="utf-8").strip() == current
    assert {path.name for path in (root / "revisions").iterdir()} == before_revisions
    assert len(list((root / "revision-metadata").glob("*.json"))) == 1
    assert service.get_preview(job_id, "official_result")[0]["客户"] == "Aaron Lee"
    assert provider.extraction_call_count == 1


def test_standard_job_does_not_gain_whole_order_revision(tmp_path: Path) -> None:
    service, *_ = _service(tmp_path)
    job = service.create_job(
        "standard.xlsx", _single_workbook_bytes(), parse_mode="standard"
    )
    with pytest.raises(Exception, match="AI Enhanced V2"):
        service.revise_ai_result(
            job["id"],
            {
                "expected_current_revision": "0" * 64,
                "source_record_id": "record",
                "field_name": "客户",
                "action": RevisionAction.KEEP_AI.value,
            },
        )


def test_pre_revision_v2_bundle_remains_readable_but_not_revision_eligible(
    tmp_path: Path,
) -> None:
    service, _provider, _dictionary, _matcher, job_id = _completed_review_job(tmp_path)
    root = service.jobs_root / job_id / "ai-bundle"
    extraction_id = next((root / "bundles").iterdir()).name
    (root / "INITIAL").unlink()
    (root / "CURRENT").write_text(extraction_id + "\n", encoding="utf-8")

    job = service.get_job(job_id)
    review = service.get_ai_review(job_id)

    assert job["result_revision"]["supported"] is False
    assert review["available"] is True
    assert review["revision"]["supported"] is False
    assert service.get_preview(job_id, "official_result")[0]["客户"] == "Aaron Lee"
    with pytest.raises(Exception, match="不支持"):
        service.revise_ai_result(
            job_id,
            {
                "expected_current_revision": "0" * 64,
                "source_record_id": review["items"][0]["source_record_id"],
                "field_name": review["items"][0]["field_name"],
                "action": "keep_ai",
            },
        )
