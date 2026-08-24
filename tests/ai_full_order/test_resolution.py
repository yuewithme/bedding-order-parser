from __future__ import annotations

from copy import deepcopy

import pytest

from bedding_order_parser.ai_full_order.contracts import AI_BUSINESS_FIELD_NAMES
from bedding_order_parser.ai_full_order.resolution import (
    PythonFieldCandidate,
    ResolutionReason,
    resolve_field,
)


def empty_ai_field() -> dict[str, object]:
    return {
        "value": "",
        "original_value": "",
        "evidence_references": [],
        "extraction_status": "source_not_provided",
        "reason": "",
    }


def ai_field(value: str, *, evidence: tuple[str, ...] = ("ev1",)) -> dict[str, object]:
    return {
        "value": value,
        "original_value": value,
        "evidence_references": list(evidence),
        "extraction_status": "extracted",
        "reason": "fixture",
    }


def py_field(
    value: str,
    *,
    evidence: tuple[str, ...] = ("evp1",),
    status: str = "extracted",
) -> PythonFieldCandidate:
    return PythonFieldCandidate(value=value, evidence_ids=evidence, status=status)


@pytest.mark.parametrize("field_name", AI_BUSINESS_FIELD_NAMES)
def test_all_17_fields_support_both_missing_branch(field_name: str) -> None:
    decision = resolve_field(field_name, empty_ai_field(), PythonFieldCandidate())

    assert decision.value == ""
    assert decision.reason_code is ResolutionReason.BOTH_MISSING
    assert decision.blocking is False


def test_ai_and_python_agree() -> None:
    decision = resolve_field("物料名称", ai_field("Duvet Cover"), py_field("Duvet Cover"))

    assert decision.value == "Duvet Cover"
    assert decision.selected_source == "both"
    assert decision.reason_code is ResolutionReason.AI_PYTHON_AGREE


def test_ai_valid_evidence_fills_python_blank_for_description() -> None:
    decision = resolve_field("物料名称", ai_field("Duvet Cover"), PythonFieldCandidate())

    assert decision.value == "Duvet Cover"
    assert decision.selected_source == "ai"
    assert decision.reason_code is ResolutionReason.AI_FILLS_PYTHON_BLANK


def test_python_value_is_retained_when_ai_omits_it() -> None:
    decision = resolve_field("规格", empty_ai_field(), py_field("240*200cm"))

    assert decision.value == "240*200cm"
    assert decision.selected_source == "python"
    assert decision.reason_code is ResolutionReason.PYTHON_RETAINED_AI_OMITTED


def test_only_ai_direct_evidence_wins_over_python_default() -> None:
    decision = resolve_field(
        "颜色",
        ai_field("灰色"),
        py_field("漂白色", evidence=(), status="defaulted"),
    )

    assert decision.value == "灰色"
    assert decision.reason_code is ResolutionReason.DIRECT_EVIDENCE_SELECTED_AI


def test_only_python_direct_evidence_wins_over_ai_non_direct_candidate() -> None:
    ai = ai_field("灰色")
    ai["evidence_references"] = []
    decision = resolve_field("颜色", ai, py_field("漂白色"))

    assert decision.value == "漂白色"
    assert decision.reason_code is ResolutionReason.DIRECT_EVIDENCE_SELECTED_PYTHON


def test_high_risk_direct_conflict_blocks_batch() -> None:
    decision = resolve_field("数量", ai_field("12"), py_field("10"))

    assert decision.value == ""
    assert decision.reason_code is ResolutionReason.UNRESOLVED_DIRECT_EVIDENCE_CONFLICT
    assert decision.blocking is True


def test_description_direct_conflict_is_unresolved_without_high_risk_block() -> None:
    decision = resolve_field("物料名称", ai_field("Duvet Cover"), py_field("Pillow"))

    assert decision.value == ""
    assert decision.reason_code is ResolutionReason.UNRESOLVED_DIRECT_EVIDENCE_CONFLICT
    assert decision.blocking is False


def test_both_present_without_direct_evidence_has_machine_reason() -> None:
    decision = resolve_field(
        "颜色",
        ai_field("灰色", evidence=()),
        py_field("漂白色", evidence=(), status="defaulted"),
    )

    assert decision.value == ""
    assert decision.reason_code is ResolutionReason.NO_DIRECT_EVIDENCE_CONFLICT


def test_ai_business_constraint_violation_uses_python_when_available() -> None:
    decision = resolve_field("数量", ai_field("twelve"), py_field("12"))

    assert decision.value == "12"
    assert decision.selected_source == "python"
    assert decision.reason_code is ResolutionReason.AI_REJECTED_BUSINESS_CONSTRAINT
    assert decision.blocking is False


def test_ai_business_constraint_violation_blocks_high_risk_without_python() -> None:
    decision = resolve_field("数量", ai_field("twelve"), PythonFieldCandidate())

    assert decision.value == ""
    assert decision.reason_code is ResolutionReason.AI_REJECTED_BUSINESS_CONSTRAINT
    assert decision.blocking is True


def test_invalid_ai_field_is_rejected_without_private_reasoning() -> None:
    ai = ai_field("Duvet Cover")
    ai["extraction_status"] = "invalid"
    decision = resolve_field("物料名称", ai, py_field("Python Cover"))

    assert decision.value == "Python Cover"
    assert decision.reason_code is ResolutionReason.AI_CONTRACT_FAILURE
    assert "思维链" not in decision.message


def test_remark_is_not_expanded_when_direct_python_conflicts() -> None:
    decision = resolve_field("行备注", ai_field("Ship soon with invented detail"), py_field("Ship soon"))

    assert decision.value == ""
    assert decision.reason_code is ResolutionReason.UNRESOLVED_DIRECT_EVIDENCE_CONFLICT


def test_no_material_code_or_similarity_field_is_part_of_ai_resolution() -> None:
    assert "物料编码" not in AI_BUSINESS_FIELD_NAMES
    assert "相似分数" not in AI_BUSINESS_FIELD_NAMES
