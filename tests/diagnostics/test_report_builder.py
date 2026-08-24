from collections import OrderedDict

from bedding_order_parser.diagnostics.models import (
    AMBIGUOUS,
    DEFAULTED,
    DERIVED,
    EXTRACTED,
    NORMALIZED,
    NOT_IMPLEMENTED,
    SOURCE_NOT_PROVIDED,
    UNRECOGNIZED,
    FieldDiagnostic,
    SourceEvidence,
)
from bedding_order_parser.diagnostics.report_builder import build_parse_report
from bedding_order_parser.models.final_result import FINAL_FIELD_NAMES, FinalResult


def _result() -> FinalResult:
    values = {field: "" for field in FINAL_FIELD_NAMES}
    values.update(
        {
            "客户": "测试客户",
            "物料名称": "测试客户 被套",
            "规格": "240*200cm",
            "颜色": "漂白色",
            "加标方式": "客标",
            "尺寸类型": "洗涤尺寸",
            "数量": "12",
            "包装方式": "纸箱",
            "是否绣花": "N",
            "相似分数": 0.0,
        }
    )
    return FinalResult.from_mapping(values)


def test_report_contains_all_statuses_and_twenty_ordered_fields(tmp_path) -> None:
    result = _result()
    statuses = (
        EXTRACTED,
        NORMALIZED,
        DERIVED,
        DEFAULTED,
        SOURCE_NOT_PROVIDED,
        UNRECOGNIZED,
        AMBIGUOUS,
        NOT_IMPLEMENTED,
    )
    fields = OrderedDict()
    for index, field in enumerate(FINAL_FIELD_NAMES):
        status = statuses[index % len(statuses)]
        fields[field] = FieldDiagnostic(
            value=result.values[field],
            status=status,
            source=SourceEvidence(sheet="PI", cells=(f"A{index + 1}",), region="item"),
            rule=f"test.{field}",
            message="测试诊断",
        )

    report = build_parse_report(
        input_file_name="sample.xlsx",
        input_sha256="abc",
        sheet_name="PI",
        result_path=tmp_path / "result.json",
        report_path=tmp_path / "result_parse_report.json",
        records=[result],
        record_fields=[fields],
    )
    payload = report.to_json_dict()

    assert list(payload["records"][0]["fields"]) == list(FINAL_FIELD_NAMES)
    assert len(payload["records"][0]["fields"]) == 20
    for field in FINAL_FIELD_NAMES:
        assert payload["records"][0]["fields"][field]["value"] == result.values[field]
    assert set(payload["summary"]["field_status_counts"]) == set(statuses)


def test_report_marks_material_code_and_similarity_not_implemented(tmp_path) -> None:
    result = _result()
    fields = OrderedDict(
        (
            field,
            FieldDiagnostic(
                value=result.values[field],
                status=NOT_IMPLEMENTED if field in {"物料编码", "相似分数"} else SOURCE_NOT_PROVIDED,
                rule="test",
            ),
        )
        for field in FINAL_FIELD_NAMES
    )
    report = build_parse_report(
        input_file_name="sample.xlsx",
        input_sha256="abc",
        sheet_name="PI",
        result_path=tmp_path / "result.json",
        report_path=tmp_path / "result_parse_report.json",
        records=[result],
        record_fields=[fields],
    ).to_json_dict()

    assert report["records"][0]["fields"]["物料编码"]["status"] == NOT_IMPLEMENTED
    assert report["records"][0]["fields"]["相似分数"]["status"] == NOT_IMPLEMENTED
