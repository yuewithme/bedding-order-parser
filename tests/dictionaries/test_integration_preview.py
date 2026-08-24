import hashlib
import json
from copy import deepcopy

import pytest

from bedding_order_parser.dictionaries.integration_preview import (
    INTEGRATION_ACTIONS,
    build_integration_preview,
    decide_integration_action,
    load_and_build_integration_preview,
    write_integration_preview,
)
from bedding_order_parser.dictionaries.shadow_models import SHADOW_FIELDS
from bedding_order_parser.exceptions import BeddingOrderParserError, OutputFileError


def comparison(
    *,
    status="exact_match",
    python_value="正式值",
    python_status="normalized",
    candidates=None,
    source_text="explicit PI evidence",
    source_cells=None,
    matched_components=None,
    missing_components=None,
    conflicting_components=None,
    detailed_candidates=None,
):
    return {
        "field_name": "颜色",
        "source_text": source_text,
        "source_cells": ["A1"] if source_cells is None else source_cells,
        "python_value": python_value,
        "python_status": python_status,
        "dictionary_candidates": ["正式值"] if candidates is None else candidates,
        "detailed_candidates": (
            [] if detailed_candidates is None else detailed_candidates
        ),
        "matched_rules": ["rule:1"],
        "comparison_status": status,
        "matched_components": (
            ["component"] if matched_components is None else matched_components
        ),
        "missing_components": (
            [] if missing_components is None else missing_components
        ),
        "conflicting_components": (
            [] if conflicting_components is None else conflicting_components
        ),
        "reason": "test evidence",
    }


def shadow_report(file_record_counts=(1,)):
    files = []
    for file_index, record_count in enumerate(file_record_counts, start=1):
        records = []
        for line_number in range(1, record_count + 1):
            fields = {}
            for field_name in SHADOW_FIELDS:
                field_comparison = comparison()
                field_comparison["field_name"] = field_name
                fields[field_name] = field_comparison
            records.append(
                {
                    "line_number": str(line_number),
                    "fields": fields,
                }
            )
        files.append(
            {
                "source_file": f"pi-{file_index}.xlsx",
                "source_sha256": f"pi-sha-{file_index}",
                "result_json": f"result-{file_index}.json",
                "result_json_sha256": f"result-sha-{file_index}",
                "parse_report_json": f"report-{file_index}.json",
                "parse_report_sha256": f"report-sha-{file_index}",
                "records": records,
            }
        )
    record_count = sum(file_record_counts)
    return {
        "summary": {
            "file_count": len(files),
            "record_count": record_count,
            "field_count": record_count * len(SHADOW_FIELDS),
        },
        "files": files,
    }


@pytest.mark.parametrize("status", ["exact_match", "equivalent_match"])
def test_exact_and_equivalent_keep_python(status) -> None:
    action, candidate, _ = decide_integration_action(
        comparison(status=status, candidates=["字典表达"])
    )

    assert action == "keep_python"
    assert candidate == "字典表达"


def test_empty_value_with_unique_candidate_and_source_proposes_fill() -> None:
    action, candidate, _ = decide_integration_action(
        comparison(
            status="equivalent_match",
            python_value="",
            python_status="unrecognized",
            candidates=["安全补值"],
        )
    )

    assert action == "propose_fill"
    assert candidate == "安全补值"


def test_default_with_unique_candidate_and_source_proposes_replacement() -> None:
    action, candidate, _ = decide_integration_action(
        comparison(
            python_value="N",
            python_status="defaulted",
            candidates=["Y"],
        )
    )

    assert action == "propose_replace_default"
    assert candidate == "Y"


def test_default_without_source_evidence_is_kept() -> None:
    action, candidate, _ = decide_integration_action(
        comparison(
            status="source_not_provided",
            python_value="N",
            python_status="defaulted",
            candidates=[],
            source_text="",
            source_cells=[],
            matched_components=[],
        )
    )

    assert action == "keep_default"
    assert candidate == ""


@pytest.mark.parametrize("status", ["ambiguous", "conflict"])
def test_ambiguous_and_conflict_require_manual_review(status) -> None:
    action, _, _ = decide_integration_action(
        comparison(status=status, candidates=["A", "B"])
    )

    assert action == "manual_review"


@pytest.mark.parametrize(
    "status",
    ["partial_match", "dictionary_no_match", "source_not_provided"],
)
def test_unsafe_shadow_statuses_never_override_python(status) -> None:
    action, candidate, _ = decide_integration_action(
        comparison(status=status, candidates=["different value"])
    )

    assert action == "keep_python"
    assert candidate == ""


def test_dictionary_row_detail_without_source_support_cannot_enrich() -> None:
    action, candidate, _ = decide_integration_action(
        comparison(
            status="dictionary_more_specific",
            python_value="贡缎/100C",
            candidates=["贡缎/T600/100C"],
            detailed_candidates=["贡缎/JC120S/2*JC120S/2/200*100/缎纹"],
            matched_components=["category", "composition"],
            missing_components=["density"],
        )
    )

    assert action == "keep_python"
    assert candidate == ""


def test_source_supported_more_specific_candidate_can_be_proposed() -> None:
    action, candidate, _ = decide_integration_action(
        comparison(
            status="dictionary_more_specific",
            python_value="贡缎/100C",
            candidates=["贡缎/T600/100C"],
            matched_components=["category", "composition", "density"],
        )
    )

    assert action == "propose_enrich"
    assert candidate == "贡缎/T600/100C"


def test_all_12_files_49_records_and_490_fields_are_evaluated() -> None:
    report = shadow_report((11, 5, 4, 4, 4, 4, 4, 3, 3, 3, 2, 2))

    preview = build_integration_preview(report)

    assert preview["summary"]["file_count"] == 12
    assert preview["summary"]["record_count"] == 49
    assert preview["summary"]["evaluated_field_count"] == 490
    assert sum(preview["summary"]["action_counts"].values()) == 490
    assert set(preview["summary"]["action_counts"]) == set(INTEGRATION_ACTIONS)
    assert all(
        assessment["observation_count"] == 49
        for assessment in preview["field_assessments"].values()
    )


def test_missing_shadow_field_fails_closed() -> None:
    report = shadow_report()
    del report["files"][0]["records"][0]["fields"]["颜色"]

    with pytest.raises(BeddingOrderParserError, match="contract mismatch"):
        build_integration_preview(report)


def test_preview_writer_does_not_modify_official_json(tmp_path) -> None:
    official_path = tmp_path / "official.json"
    official_path.write_text(
        json.dumps({"结果": "正式"}, ensure_ascii=False),
        encoding="utf-8",
    )
    before = hashlib.sha256(official_path.read_bytes()).hexdigest()
    shadow_path = tmp_path / "shadow.json"
    shadow_path.write_text(
        json.dumps(shadow_report(), ensure_ascii=False),
        encoding="utf-8",
    )

    preview = load_and_build_integration_preview(shadow_path)
    output_path = write_integration_preview(preview, tmp_path / "preview.json")

    assert output_path.exists()
    assert hashlib.sha256(official_path.read_bytes()).hexdigest() == before
    assert json.loads(output_path.read_text(encoding="utf-8"))["summary"][
        "evaluated_field_count"
    ] == 10


def test_preview_writer_refuses_overwrite(tmp_path) -> None:
    output_path = tmp_path / "preview.json"
    output_path.write_text("existing", encoding="utf-8")

    with pytest.raises(OutputFileError, match="already exists"):
        write_integration_preview(build_integration_preview(shadow_report()), output_path)


def test_manual_review_entry_preserves_source_trace() -> None:
    report = shadow_report()
    target = report["files"][0]["records"][0]["fields"]["颜色"]
    target.update(
        comparison(
            status="ambiguous",
            python_value="浅灰色",
            candidates=["灰色", "蓝色"],
            source_text="light grey with blue embroidery",
            source_cells=["D13"],
        )
    )

    preview = build_integration_preview(deepcopy(report))

    assert preview["summary"]["manual_review_count"] == 1
    assert preview["manual_reviews"] == [
        {
            "source_file": "pi-1.xlsx",
            "line_number": "1",
            "field": "颜色",
            "python_value": "浅灰色",
            "python_status": "normalized",
            "dictionary_candidate": "",
            "dictionary_candidates": ["灰色", "蓝色"],
            "shadow_status": "ambiguous",
            "proposed_action": "manual_review",
            "source_cells": ["D13"],
            "source_text": "light grey with blue embroidery",
            "reason": "ambiguous cannot safely change the official Python result.",
            "risk_level": "not_ready",
        }
    ]
