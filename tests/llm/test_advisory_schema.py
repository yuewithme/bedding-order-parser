from __future__ import annotations

import copy

import pytest

from bedding_order_parser.llm.advisory_schema import (
    SchemaValidationError,
    validate_model_advisory,
)


def advisory() -> dict[str, object]:
    return {
        "source_record_id": "PI.xlsx|PI|2",
        "action": "suggest_review",
        "confidence": 0.75,
        "suggested_fields": [
            {
                "field_name": "颜色",
                "original_value": "",
                "suggested_value": "白色",
                "reason": "B2 contains White.",
                "evidence_references": ["PI!B2"],
            }
        ],
        "material_assessment": {
            "status": "suggested",
            "suggested_material_code": "F0001",
            "reason": "Candidate evidence supports a review suggestion.",
        },
        "reasoning_summary": "源文本提供了颜色证据。",
        "warnings": ["物料编码仍需人工确认。"],
        "evidence_references": ["PI!B2"],
    }


def test_valid_advisory_passes_strict_schema() -> None:
    payload = advisory()

    assert validate_model_advisory(
        payload, expected_source_record_id="PI.xlsx|PI|2"
    ) is payload


def test_extra_field_is_rejected() -> None:
    payload = advisory()
    payload["formal_erp_write"] = True

    with pytest.raises(SchemaValidationError, match="extra fields"):
        validate_model_advisory(
            payload, expected_source_record_id="PI.xlsx|PI|2"
        )


def test_source_record_mismatch_is_rejected() -> None:
    with pytest.raises(SchemaValidationError, match="does not match"):
        validate_model_advisory(
            advisory(), expected_source_record_id="different"
        )


def test_unconfirmed_material_code_must_be_empty() -> None:
    payload = advisory()
    assessment = copy.deepcopy(payload["material_assessment"])
    assessment["status"] = "insufficient_evidence"
    payload["material_assessment"] = assessment

    with pytest.raises(SchemaValidationError, match="must be empty"):
        validate_model_advisory(
            payload, expected_source_record_id="PI.xlsx|PI|2"
        )


def test_insufficient_evidence_is_a_valid_answer() -> None:
    payload = advisory()
    payload.update(
        action="insufficient_evidence",
        confidence=0.0,
        suggested_fields=[],
        reasoning_summary="证据不足，不能安全建议字段。",
    )
    payload["material_assessment"] = {
        "status": "insufficient_evidence",
        "suggested_material_code": "",
        "reason": "No source evidence supports a material suggestion.",
    }

    validate_model_advisory(
        payload, expected_source_record_id="PI.xlsx|PI|2"
    )
