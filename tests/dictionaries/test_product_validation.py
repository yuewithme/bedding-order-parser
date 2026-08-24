import hashlib
import json

import pytest
from openpyxl import Workbook

from bedding_order_parser.cli import build_parser
from bedding_order_parser.diagnostics.models import (
    DERIVED,
    FieldDiagnostic,
    ParseReport,
    RecordDiagnostic,
    SourceEvidence,
)
from bedding_order_parser.dictionaries.models import (
    DictionaryBundle,
    DictionarySource,
    RuleRow,
)
from bedding_order_parser.dictionaries.product_validation import (
    VALIDATION_FIELDS,
    build_product_validation_report,
    default_validation_path,
    write_product_validation_report,
)
from bedding_order_parser.excel.workbook_reader import compute_sha256
from bedding_order_parser.models.final_result import FINAL_FIELD_NAMES, FinalResult
from bedding_order_parser.pipeline import order_parser
from bedding_order_parser.pipeline.order_parser import parse_order


def _bundle() -> DictionaryBundle:
    return DictionaryBundle(
        sources=[
            DictionarySource(
                file_name="PI单提取规则.xlsx",
                sha256="rules-sha",
                sheet_name="被套 提取规则",
            )
        ],
        rules=[
            RuleRow(
                source_row=2,
                source_cells={"关键描述": "C2"},
                field_name="产品名称",
                rule_description="duvet cover",
                standard_value="被套",
                notes="",
                raw_values={
                    "字段名": "产品名称",
                    "可能值": "被套",
                    "关键描述": "duvet cover",
                },
            )
        ],
        fabrics=[],
        styles=[],
        summary={"rule_rows": 1, "fabric_rows": 0, "style_rows": 0},
    )


def _final_result(
    material_name: str = "Test Hotel 被套",
    *,
    currency: str = "美元",
    size: str = "240*200cm",
    color: str = "漂白色",
) -> FinalResult:
    values = {field: "" for field in FINAL_FIELD_NAMES}
    values["行号"] = "1"
    values["物料名称"] = material_name
    values["币种"] = currency
    values["规格"] = size
    values["颜色"] = color
    values["相似分数"] = 0.0
    return FinalResult.from_mapping(values)


def _diagnostic(sheet: str, cells: tuple[str, ...]) -> FieldDiagnostic:
    return FieldDiagnostic(
        value="",
        status=DERIVED,
        source=SourceEvidence(
            sheet=sheet,
            cells=cells,
            region="derived",
        ),
    )


def _parse_report(
    *,
    material_cells: tuple[str, ...] = ("B5",),
    currency_cells: tuple[str, ...] = ("E1",),
    size_cells: tuple[str, ...] = ("C5",),
    color_cells: tuple[str, ...] = ("D5",),
    line_note_cells: tuple[str, ...] = ("D5",),
) -> ParseReport:
    fields = {
        "物料名称": _diagnostic("PI", material_cells),
        "币种": _diagnostic("PI", currency_cells),
        "规格": _diagnostic("PI", size_cells),
        "颜色": _diagnostic("PI", color_cells),
        "行备注": _diagnostic("PI", line_note_cells),
    }
    return ParseReport(
        input_file_name="sample.xlsx",
        input_sha256="input-sha",
        sheet_name="PI",
        result_json="result.json",
        parse_report_json="result_parse_report.json",
        records=(
            RecordDiagnostic(
                line_number="1",
                fields=fields,
            ),
        ),
    )


def _source_workbook(
    path,
    *,
    product_text: str = "Duvet Cover",
    currency_text: str = "Unit Price (USD)",
    size_text: str = "200*240cm",
    description_text: str = "white",
) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "PI"
    worksheet["E1"] = currency_text
    worksheet["B5"] = product_text
    worksheet["C5"] = size_text
    worksheet["D5"] = description_text
    workbook.save(path)


def _write_pi(path, product_text: str = "Duvet Cover") -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "PI"
    worksheet.append(["", "PROFORMA INVOICE", "", "", "Unit Price (USD)"])
    worksheet.append(["BUYER:", "", "", "", ""])
    worksheet.append(["Test Hotel", "", "", "", "Contact Person: Aaron Lee"])
    worksheet.append(["No.", "Item", "Size W*L", "Specification", "QTY"])
    worksheet.append(
        ["1", product_text, "200*240", "100% cotton white after wash", "12"]
    )
    workbook.save(path)


def _build_report(
    monkeypatch,
    tmp_path,
    *,
    source_product: str = "Duvet Cover",
    source_currency: str = "Unit Price (USD)",
    source_size: str = "200*240cm",
    source_description: str = "white",
    material_name: str = "Test Hotel 被套",
    currency: str = "美元",
    size: str = "240*200cm",
    color: str = "漂白色",
    parse_report: ParseReport | None = None,
):
    input_path = tmp_path / "sample.xlsx"
    _source_workbook(
        input_path,
        product_text=source_product,
        currency_text=source_currency,
        size_text=source_size,
        description_text=source_description,
    )
    monkeypatch.setattr(
        "bedding_order_parser.dictionaries.product_validation.load_dictionary_bundle",
        lambda *_args, **_kwargs: _bundle(),
    )
    return build_product_validation_report(
        input_path=input_path,
        records=[
            _final_result(
                material_name,
                currency=currency,
                size=size,
                color=color,
            )
        ],
        parse_report=parse_report or _parse_report(),
        rules_path=tmp_path / "rules.xlsx",
        styles_path=tmp_path / "styles.xlsx",
    )


def _field(report: dict, name: str) -> dict:
    return report["records"][0]["fields"][name]


def test_cli_parse_flag_is_optional() -> None:
    parser = build_parser()

    without_flag = parser.parse_args(
        ["parse", "input.xlsx", "--output", "result.json"]
    )
    with_flag = parser.parse_args(
        [
            "parse",
            "input.xlsx",
            "--output",
            "result.json",
            "--dictionary-validate",
        ]
    )

    assert without_flag.dictionary_validate is False
    assert with_flag.dictionary_validate is True


def test_validation_report_contains_four_core_fields(monkeypatch, tmp_path) -> None:
    report = _build_report(monkeypatch, tmp_path)
    record = report["records"][0]

    assert tuple(record["fields"]) == VALIDATION_FIELDS
    assert report["summary"]["record_count"] == 1
    assert report["summary"]["field_count"] == 4
    assert set(report["summary"]["fields"]) == set(VALIDATION_FIELDS)


@pytest.mark.parametrize(
    "source_text",
    ["Duvet Cover King", "酒店被套", "Dubet cover TWIN"],
)
def test_approved_product_terms_validate_as_duvet_cover(
    monkeypatch,
    tmp_path,
    source_text,
) -> None:
    report = _build_report(monkeypatch, tmp_path, source_product=source_text)
    field = _field(report, "物料名称")

    assert field["validation_status"] == "equivalent_match"
    assert field["detected_category"] == "被套"
    assert field["dictionary_candidates"] == ["被套"]
    assert field["action"] == "keep_python"


def test_python_cover_text_cannot_validate_without_source_evidence(
    monkeypatch,
    tmp_path,
) -> None:
    report = _build_report(monkeypatch, tmp_path, source_product="")
    field = _field(report, "物料名称")

    assert field["python_value"] == "Test Hotel 被套"
    assert field["validation_status"] == "source_not_provided"
    assert field["dictionary_candidates"] == []
    assert field["action"] == "keep_python"


def test_dictionary_no_match_keeps_python(monkeypatch, tmp_path) -> None:
    report = _build_report(monkeypatch, tmp_path, source_product="Bed linen item")
    field = _field(report, "物料名称")

    assert field["validation_status"] == "dictionary_no_match"
    assert field["detected_category"] == ""
    assert field["action"] == "keep_python"


def test_dictionary_conflict_requires_manual_review(monkeypatch, tmp_path) -> None:
    report = _build_report(
        monkeypatch,
        tmp_path,
        source_product="Duvet Cover",
        material_name="Test Hotel Sheet",
    )
    field = _field(report, "物料名称")

    assert field["validation_status"] == "conflict"
    assert field["dictionary_candidates"] == ["被套"]
    assert field["action"] == "manual_review"


def test_usd_currency_code_is_equivalent_to_chinese_currency(
    monkeypatch,
    tmp_path,
) -> None:
    report = _build_report(monkeypatch, tmp_path, source_currency="Amount USD 12.00")
    field = _field(report, "币种")

    assert field["validation_status"] == "equivalent_match"
    assert field["dictionary_candidates"] == ["美元"]
    assert field["action"] == "keep_python"


def test_missing_currency_source_evidence_is_reported(monkeypatch, tmp_path) -> None:
    report = _build_report(
        monkeypatch,
        tmp_path,
        parse_report=_parse_report(currency_cells=()),
    )
    field = _field(report, "币种")

    assert field["validation_status"] == "source_not_provided"
    assert field["action"] == "keep_python"


def test_size_width_length_order_is_equivalent(monkeypatch, tmp_path) -> None:
    report = _build_report(
        monkeypatch,
        tmp_path,
        source_size="205*273cm",
        size="273*205cm",
    )
    field = _field(report, "规格")

    assert field["validation_status"] == "equivalent_match"
    assert field["dictionary_candidates"] == ["273*205"]


def test_size_uses_legal_flap_extension_from_same_row(monkeypatch, tmp_path) -> None:
    report = _build_report(
        monkeypatch,
        tmp_path,
        source_size="340*260cm",
        source_description="inner flap 15cm white",
        size="260*340+15cm",
    )
    field = _field(report, "规格")

    assert field["validation_status"] == "equivalent_match"
    assert "D5" in field["source_cells"]


def test_hand_hole_number_does_not_become_size_extension(monkeypatch, tmp_path) -> None:
    report = _build_report(
        monkeypatch,
        tmp_path,
        source_size="340*260cm",
        source_description="hand hole 20cm white",
        size="260*340+20cm",
    )
    field = _field(report, "规格")

    assert field["validation_status"] == "partial_match"
    assert field["dictionary_candidates"] == ["260*340"]
    assert field["action"] == "keep_python"


def test_color_ignores_identification_thread_as_main_color(monkeypatch, tmp_path) -> None:
    report = _build_report(
        monkeypatch,
        tmp_path,
        source_description="white duvet cover with blue ID thread",
        color="漂白色",
    )
    field = _field(report, "颜色")

    assert field["validation_status"] == "exact_match"
    assert field["dictionary_candidates"] == ["漂白色"]
    assert "blue ID thread" in field["source_text"]


def test_multiple_main_color_candidates_are_ambiguous(monkeypatch, tmp_path) -> None:
    report = _build_report(
        monkeypatch,
        tmp_path,
        source_description="white and beige duvet cover",
        color="漂白色",
    )
    field = _field(report, "颜色")

    assert field["validation_status"] == "ambiguous"
    assert field["action"] == "manual_review"

def test_light_grey_is_equivalent_to_official_light_grey(monkeypatch, tmp_path) -> None:
    report = _build_report(
        monkeypatch,
        tmp_path,
        source_description="light grey with size color coding: Blue",
        color="浅灰色",
    )
    field = _field(report, "颜色")

    assert field["validation_status"] == "equivalent_match"
    assert field["dictionary_candidates"] == ["浅灰色"]
    assert field["action"] == "keep_python"


def test_validation_report_is_utf8_chinese_and_atomic(monkeypatch, tmp_path) -> None:
    report = _build_report(monkeypatch, tmp_path, source_product="酒店被套")
    output_path = tmp_path / "result_dictionary_validation.json"

    written = write_product_validation_report(report, output_path)

    text = written.read_text(encoding="utf-8")
    assert "被套" in text
    assert "\\u88ab" not in text
    assert json.loads(text)["mode"] == "validation_only"


def test_parse_without_flag_does_not_invoke_dictionary_or_create_report(
    monkeypatch,
    tmp_path,
) -> None:
    input_path = tmp_path / "sample.xlsx"
    output_path = tmp_path / "result.json"
    _write_pi(input_path)

    def fail_if_called(**_kwargs):
        raise AssertionError("dictionary validation must not run")

    monkeypatch.setattr(
        order_parser,
        "build_product_validation_report",
        fail_if_called,
    )

    summary = parse_order(input_path, output_path)

    assert summary.validation_report_path is None
    assert summary.validation_status == ""
    assert not default_validation_path(output_path).exists()


def test_parse_with_flag_generates_third_report_without_changing_pair(
    monkeypatch,
    tmp_path,
) -> None:
    input_path = tmp_path / "sample.xlsx"
    output_path = tmp_path / "result.json"
    _write_pi(input_path, "Dubet cover TWIN")

    baseline = parse_order(input_path, output_path)
    result_hash = compute_sha256(baseline.output_path)
    report_hash = compute_sha256(baseline.report_path)
    result_keys = list(
        json.loads(output_path.read_text(encoding="utf-8"))[0]
    )
    monkeypatch.setattr(
        "bedding_order_parser.dictionaries.product_validation.load_dictionary_bundle",
        lambda *_args, **_kwargs: _bundle(),
    )

    validated = parse_order(
        input_path,
        output_path,
        dictionary_validate=True,
        dictionary_rules_path=tmp_path / "rules.xlsx",
        dictionary_styles_path=tmp_path / "styles.xlsx",
        overwrite=True,
    )

    assert validated.validation_status == "completed"
    assert validated.validation_report_path == default_validation_path(output_path)
    assert compute_sha256(output_path) == result_hash
    assert compute_sha256(validated.report_path) == report_hash
    assert list(json.loads(output_path.read_text(encoding="utf-8"))[0]) == result_keys
    validation = json.loads(
        validated.validation_report_path.read_text(encoding="utf-8")
    )
    assert validation["summary"]["record_count"] == 1
    assert validation["summary"]["field_count"] == 4
    assert set(validation["records"][0]["fields"]) == set(VALIDATION_FIELDS)


def test_dictionary_failure_preserves_successful_official_outputs(tmp_path) -> None:
    input_path = tmp_path / "sample.xlsx"
    output_path = tmp_path / "result.json"
    _write_pi(input_path)

    summary = parse_order(
        input_path,
        output_path,
        dictionary_validate=True,
        dictionary_rules_path=tmp_path / "missing-rules.xlsx",
        dictionary_styles_path=tmp_path / "missing-styles.xlsx",
    )

    assert summary.output_path.exists()
    assert summary.report_path.exists()
    assert summary.validation_report_path.exists()
    validation = json.loads(
        summary.validation_report_path.read_text(encoding="utf-8")
    )
    assert summary.validation_status == "failed"
    assert validation["status"] == "failed"
    assert validation["summary"]["attempted_record_count"] == 1
    assert "does not exist" in validation["failure_reason"]
    assert list(
        json.loads(summary.output_path.read_text(encoding="utf-8"))[0]
    ) == list(FINAL_FIELD_NAMES)


def test_unexpected_validation_failure_isolated_after_official_outputs(
    monkeypatch,
    tmp_path,
) -> None:
    input_path = tmp_path / "sample.xlsx"
    output_path = tmp_path / "result.json"
    _write_pi(input_path)

    def fail_validation(**_kwargs):
        raise RuntimeError("validation-side failure")

    monkeypatch.setattr(
        order_parser,
        "build_product_validation_report",
        fail_validation,
    )

    summary = parse_order(
        input_path,
        output_path,
        dictionary_validate=True,
    )

    assert summary.output_path.exists()
    assert summary.report_path.exists()
    validation = json.loads(
        summary.validation_report_path.read_text(encoding="utf-8")
    )
    assert validation["status"] == "failed"
    assert validation["failure_reason"] == "validation-side failure"


def test_validation_does_not_modify_source_workbook(monkeypatch, tmp_path) -> None:
    input_path = tmp_path / "sample.xlsx"
    _source_workbook(input_path, product_text="Duvet Cover")
    before = hashlib.sha256(input_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "bedding_order_parser.dictionaries.product_validation.load_dictionary_bundle",
        lambda *_args, **_kwargs: _bundle(),
    )

    build_product_validation_report(
        input_path=input_path,
        records=[_final_result()],
        parse_report=_parse_report(),
        rules_path=tmp_path / "rules.xlsx",
        styles_path=tmp_path / "styles.xlsx",
    )

    assert hashlib.sha256(input_path.read_bytes()).hexdigest() == before