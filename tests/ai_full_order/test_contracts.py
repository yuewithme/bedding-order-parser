from __future__ import annotations

import copy
import socket
from pathlib import Path

import pytest
from openpyxl import Workbook

from bedding_order_parser.ai_full_order.contracts import (
    AI_BUSINESS_FIELD_NAMES,
    FORBIDDEN_MODEL_FIELD_NAMES,
    FullOrderContractError,
    ParseMode,
    parse_mode_from_value,
    safe_contract_diagnostic,
    validate_full_order_output,
    validate_full_order_request,
    validate_full_order_v2_output,
    validate_full_order_v2_request,
)
from bedding_order_parser.ai_full_order.fake_provider import FakeFullOrderProvider
from bedding_order_parser.ai_full_order.orchestration import (
    build_v2_extraction_request,
    build_v2_extraction_units,
)
from bedding_order_parser.ai_full_order.preprocessing import preprocess_workbook


def write_order_book(path: Path, *, second_scope: bool = False) -> None:
    workbook = Workbook()
    _add_order_sheet(workbook.active, "PI-A", "Duvet Cover")
    if second_scope:
        _add_order_sheet(workbook.create_sheet(), "PI-B", "Pillow Case")
    workbook.save(path)


def _add_order_sheet(sheet, title: str, item: str) -> None:
    sheet.title = title
    sheet.append(["No.", "Item", "Specification", "Qty"])
    sheet.append(["1", item, "White cotton", "12"])


def build_request(tmp_path: Path, *, second_scope: bool = False) -> dict[str, object]:
    path = tmp_path / ("two-scopes.xlsx" if second_scope else "one-scope.xlsx")
    write_order_book(path, second_scope=second_scope)
    return preprocess_workbook(path).to_request_dict()


def test_parse_mode_has_only_the_two_contract_values() -> None:
    assert {mode.value for mode in ParseMode} == {"standard", "ai_enhanced"}
    assert parse_mode_from_value("standard") is ParseMode.STANDARD
    with pytest.raises(FullOrderContractError, match="Unsupported parse_mode"):
        parse_mode_from_value("automatic")


def test_request_and_normal_fake_output_enforce_17_fields_and_local_line(tmp_path: Path) -> None:
    request = build_request(tmp_path)
    assert validate_full_order_request(request) is request
    provider = FakeFullOrderProvider()
    output = provider.extract(request)

    assert validate_full_order_output(output, request=request) is output
    assert tuple(output["records"][0]["fields"]) == AI_BUSINESS_FIELD_NAMES
    assert "行号" not in output["records"][0]["fields"]
    assert "物料编码" not in output["records"][0]["fields"]
    assert "相似分数" not in output["records"][0]["fields"]
    assert provider.network_call_count == 0


@pytest.mark.parametrize(
    ("scenario", "second_scope", "message"),
    [
        ("missing_field", False, "missing required fields"),
        ("extra_field", False, "extra fields"),
        ("wrong_type", False, "must be an integer"),
        ("invalid_enum", False, "unsupported value"),
        ("cross_scope", True, "outside its scope"),
        ("forged_cell", False, "missing evidence cell"),
        ("material_code_injection", False, "extra fields"),
        ("similarity_score_injection", False, "extra fields"),
    ],
)
def test_fake_provider_negative_scenarios_are_rejected(
    tmp_path: Path, scenario: str, second_scope: bool, message: str
) -> None:
    request = build_request(tmp_path, second_scope=second_scope)
    provider = FakeFullOrderProvider(scenario)

    with pytest.raises(FullOrderContractError, match=message):
        validate_full_order_output(provider.extract(request), request=request)

    assert provider.network_call_count == 0


def test_value_must_be_traceable_to_its_evidence(tmp_path: Path) -> None:
    request = build_request(tmp_path)
    output = FakeFullOrderProvider().extract(request)
    field = output["records"][0]["fields"]["物料名称"]
    field["value"] = "Invented material"
    field["original_value"] = "Invented material"

    with pytest.raises(FullOrderContractError, match="not traceable"):
        validate_full_order_output(output, request=request)


def test_null_is_rejected_by_the_strict_output_schema(tmp_path: Path) -> None:
    request = build_request(tmp_path)
    output = FakeFullOrderProvider().extract(request)
    output["model"] = None

    with pytest.raises(FullOrderContractError, match="must be a string"):
        validate_full_order_output(output, request=request)


def test_nonempty_field_requires_evidence_reference(tmp_path: Path) -> None:
    request = build_request(tmp_path)
    output = FakeFullOrderProvider().extract(request)
    output["records"][0]["fields"]["物料名称"]["evidence_references"] = []

    with pytest.raises(FullOrderContractError, match="requires value, original_value and evidence"):
        validate_full_order_output(output, request=request)


@pytest.mark.parametrize(
    ("scenario", "second_scope", "stage", "category"),
    [
        ("cross_scope", True, "evidence_validation", "evidence_cross_scope"),
        ("forged_cell", False, "evidence_validation", "evidence_id_missing"),
        ("invalid_enum", False, "output_schema", "enum_or_constant_mismatch"),
        ("wrong_type", False, "output_schema", "type_mismatch"),
        ("material_code_injection", False, "forbidden_fields", "extra_fields"),
    ],
)
def test_contract_error_exposes_only_fixed_diagnostic_categories(
    tmp_path: Path, scenario: str, second_scope: bool, stage: str, category: str
) -> None:
    request = build_request(tmp_path, second_scope=second_scope)
    with pytest.raises(FullOrderContractError) as raised:
        validate_full_order_output(FakeFullOrderProvider(scenario).extract(request), request=request)

    diagnostic = safe_contract_diagnostic(raised.value)
    assert diagnostic["stage"] == stage
    assert diagnostic["category"] == category
    assert "evidence_id" not in diagnostic
    assert "value" not in diagnostic


def test_fake_provider_makes_zero_socket_requests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = build_request(tmp_path)

    def explode(*_args, **_kwargs):
        raise AssertionError("network access is forbidden in this test")

    monkeypatch.setattr(socket, "create_connection", explode)
    provider = FakeFullOrderProvider()
    output = provider.extract(request)

    validate_full_order_output(output, request=request)
    assert provider.extraction_call_count == 1
    assert provider.network_call_count == 0


def test_v2_sparse_candidate_contract_allows_an_empty_list() -> None:
    output = {"candidates": []}

    assert validate_full_order_v2_output(output) is output


def test_v2_request_binds_exactly_one_local_target_and_allowed_evidence(tmp_path: Path) -> None:
    path = tmp_path / "v2-request.xlsx"
    write_order_book(path)
    unit = build_v2_extraction_units(preprocess_workbook(path))[0]
    request = build_v2_extraction_request(unit)

    assert validate_full_order_v2_request(request) is request
    assert set(request["target"]) == {
        "record_local_id",
        "source_record_id",
        "scope_id",
        "sheet_id",
        "source_row",
        "evidence_ids",
    }
    assert set(request["target"]["evidence_ids"]) == {
        item["evidence_id"] for item in request["evidence_catalog"]
    }
    assert "records" not in request
    assert not ({"行号", "物料编码", "相似分数"} & set(request))


def test_v2_request_rejects_catalog_outside_the_target(tmp_path: Path) -> None:
    path = tmp_path / "v2-request-extra.xlsx"
    write_order_book(path)
    request = build_v2_extraction_request(
        build_v2_extraction_units(preprocess_workbook(path))[0]
    )
    forged = copy.deepcopy(request["evidence_catalog"][0])
    forged["evidence_id"] = "forged:extra"
    request["evidence_catalog"].append(forged)

    with pytest.raises(FullOrderContractError) as raised:
        validate_full_order_v2_request(request)

    assert safe_contract_diagnostic(raised.value)["category"] == "evidence_not_in_target"


def test_v2_candidate_field_enum_is_exactly_the_17_business_fields() -> None:
    output = {
        "candidates": [
            {
                "field_name": field_name,
                "candidate_value": "synthetic value",
                "evidence_references": [f"evidence:{index}"],
                "interpretation": "direct",
                "supporting_quote": "",
            }
            for index, field_name in enumerate(AI_BUSINESS_FIELD_NAMES)
        ]
    }

    assert validate_full_order_v2_output(output) is output
    assert set(AI_BUSINESS_FIELD_NAMES).isdisjoint(FORBIDDEN_MODEL_FIELD_NAMES)


@pytest.mark.parametrize(
    ("output", "stage", "category", "path"),
    [
        ({"candidates": [{"field_name": "物料名称", "candidate_value": "Item", "evidence_references": ["e1"], "interpretation": "direct", "supporting_quote": "", "untrusted": "x"}]}, "v2_output_schema", "extra_fields", "$.candidates[]"),
        ({"candidates": [], "物料编码": "M-1"}, "forbidden_fields", "extra_fields", "$"),
        ({"candidates": [{"field_name": "物料编码", "candidate_value": "M-1", "evidence_references": ["e1"], "interpretation": "direct", "supporting_quote": ""}]}, "v2_output_schema", "enum_or_constant_mismatch", "$.candidates[].field_name"),
        ({"candidates": [{"field_name": "物料名称", "candidate_value": "Item", "evidence_references": [], "interpretation": "direct", "supporting_quote": ""}]}, "v2_output_schema", "length_or_range_mismatch", "$.candidates[].evidence_references"),
        ({"candidates": [{"field_name": "物料名称", "candidate_value": "Item", "evidence_references": ["e1", "e1"], "interpretation": "direct", "supporting_quote": ""}]}, "v2_hard_contract", "duplicate_evidence_reference", "$.candidates[].evidence_references"),
        ({"candidates": [{"field_name": "物料名称", "candidate_value": "Item", "evidence_references": ["e1"], "interpretation": "direct", "supporting_quote": ""}, {"field_name": "物料名称", "candidate_value": "Other", "evidence_references": ["e2"], "interpretation": "direct", "supporting_quote": ""}]}, "v2_hard_contract", "duplicate_field_name", "$.candidates[].field_name"),
    ],
)
def test_v2_contract_rejects_hard_envelope_errors(
    output: dict[str, object], stage: str, category: str, path: str
) -> None:
    with pytest.raises(FullOrderContractError) as raised:
        validate_full_order_v2_output(output)

    diagnostic = safe_contract_diagnostic(raised.value)
    assert {key: diagnostic[key] for key in ("stage", "category", "path")} == {
        "stage": stage,
        "category": category,
        "path": path,
    }
    if category == "extra_fields":
        assert diagnostic["extra_field_count"] == 1


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "$.records[].untrusted_generated_field",
        "$.records[].fields.any_model_generated_key",
        "$.evidence_catalog[].arbitrary_suffix",
        "$.candidates[].arbitrary_model_key",
    ],
)
def test_safe_contract_diagnostic_rejects_arbitrary_path_suffixes(unsafe_path: str) -> None:
    diagnostic = safe_contract_diagnostic(
        {
            "stage": "output_schema",
            "category": "extra_fields",
            "path": unsafe_path,
            "extra_field_count": 1,
        }
    )

    assert "path" not in diagnostic
    assert diagnostic["extra_field_count"] == 1
