from __future__ import annotations

import json

from bedding_order_parser.llm.contracts import (
    LLMConnectivityResult,
    LLMEnhancementResponse,
    LLMUsage,
    MaterialAssessment,
)
from bedding_order_parser.llm.diagnostics import main


class FakeService:
    def __init__(self) -> None:
        self.closed = False
        self.request = None

    def check_connectivity(self) -> LLMConnectivityResult:
        return LLMConnectivityResult(
            provider="volcengine_ark",
            model="doubao-test",
            request_id="resp-connect",
            status="succeeded",
            finish_status="completed",
            text="连接成功",
            usage=LLMUsage(3, 2, 5),
            latency_ms=10,
            attempt_count=1,
        )

    def enhance_record(self, request):
        self.request = request
        return LLMEnhancementResponse(
            provider="volcengine_ark",
            model="doubao-test",
            request_id="resp-advisory",
            source_record_id=request.source_record_id,
            status="succeeded",
            finish_status="completed",
            action="insufficient_evidence",
            confidence=0.0,
            material_assessment=MaterialAssessment(
                status="insufficient_evidence",
                suggested_material_code="",
                reason="Evidence is insufficient.",
            ),
            attempt_count=1,
        )

    def close(self) -> None:
        self.closed = True


def test_connectivity_diagnostic_writes_bounded_result(tmp_path) -> None:
    output = tmp_path / "connectivity.json"
    service = FakeService()

    exit_code = main(
        ["connectivity", "--output", str(output)],
        service=service,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["expected_text_match"] is True
    assert payload["result"]["usage"]["total_tokens"] == 5
    assert service.closed is True


def test_advisory_diagnostic_preserves_source_record_id(tmp_path) -> None:
    source = tmp_path / "request.json"
    output = tmp_path / "advisory.json"
    source.write_text(
        json.dumps(
            {
                "source_record_id": "stable-record-39",
                "source_file": "H-Hotel.xlsx",
                "sheet_name": "PI",
                "source_row": "39",
                "raw_evidence": {"description": "Duvet Cover"},
                "parsed_record": {"物料名称": "被套"},
                "parse_diagnostics": {},
                "dictionary_validation": {},
                "top_candidates": [],
                "enhancement_reason": "insufficient_evidence",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service = FakeService()

    exit_code = main(
        ["advisory", "--input", str(source), "--output", str(output)],
        service=service,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert service.request.source_record_id == "stable-record-39"
    assert payload["result"]["source_record_id"] == "stable-record-39"
    assert payload["result"]["advisory_only"] is True
    assert service.closed is True
