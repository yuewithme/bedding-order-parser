import json

import pytest

from bedding_order_parser.exceptions import OutputFileError
from bedding_order_parser.models.final_result import FINAL_FIELD_NAMES, FinalResult
from bedding_order_parser.serialization.json_writer import write_final_json


def _record() -> FinalResult:
    values = {field: "" for field in FINAL_FIELD_NAMES}
    values.update(
        {
            "客户": "测试客户",
            "行号": "1",
            "数量": "2",
            "相似分数": 0.0,
        }
    )
    return FinalResult.from_mapping(values)


def test_json_writer_uses_utf8_and_field_order(tmp_path) -> None:
    output = tmp_path / "result.json"

    write_final_json([_record()], output)

    text = output.read_text(encoding="utf-8")
    assert "测试客户" in text
    assert "\\u6d4b" not in text
    payload = json.loads(text)
    assert list(payload[0].keys()) == list(FINAL_FIELD_NAMES)
    assert isinstance(payload[0]["相似分数"], float)


def test_json_writer_refuses_overwrite(tmp_path) -> None:
    output = tmp_path / "result.json"
    write_final_json([_record()], output)

    with pytest.raises(OutputFileError):
        write_final_json([_record()], output)
