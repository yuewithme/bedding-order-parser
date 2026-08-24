import json

import pytest

from bedding_order_parser.diagnostics.models import ParseReport
from bedding_order_parser.exceptions import OutputFileError
from bedding_order_parser.models.final_result import FINAL_FIELD_NAMES, FinalResult
from bedding_order_parser.serialization.diagnostic_writer import (
    default_report_path,
    write_parse_outputs,
)


def _record() -> FinalResult:
    values = {field: "" for field in FINAL_FIELD_NAMES}
    values["相似分数"] = 0.0
    return FinalResult.from_mapping(values)


def _report(file_name: str = "sample.xlsx") -> ParseReport:
    return ParseReport(
        input_file_name=file_name,
        input_sha256="test",
        sheet_name="PI",
        result_json="result.json",
        parse_report_json="result_parse_report.json",
    )


def test_default_report_path_uses_result_stem() -> None:
    assert default_report_path("order_result.json").name == "order_result_parse_report.json"


def test_writer_refuses_when_either_output_exists(tmp_path) -> None:
    result_path = tmp_path / "result.json"
    report_path = default_report_path(result_path)
    report_path.write_text("existing", encoding="utf-8")

    with pytest.raises(OutputFileError):
        write_parse_outputs([_record()], _report(), result_path, report_path)

    assert not result_path.exists()
    assert report_path.read_text(encoding="utf-8") == "existing"


def test_overwrite_replaces_both_outputs_and_preserves_chinese(tmp_path) -> None:
    result_path = tmp_path / "result.json"
    report_path = default_report_path(result_path)
    result_path.write_text("old-result", encoding="utf-8")
    report_path.write_text("old-report", encoding="utf-8")

    write_parse_outputs(
        [_record()],
        _report(file_name="中文订单.xlsx"),
        result_path,
        report_path,
        overwrite=True,
    )

    assert json.loads(result_path.read_text(encoding="utf-8"))[0]["物料编码"] == ""
    report_text = report_path.read_text(encoding="utf-8")
    assert "中文订单.xlsx" in report_text
    assert "\\u4e2d" not in report_text
