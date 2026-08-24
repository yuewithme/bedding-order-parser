from __future__ import annotations

from bedding_order_parser.ai_full_order.comparison import (
    V2ComparisonStatus,
    V2ReviewSeverity,
    V2TechnicalCandidateStatus,
)
from bedding_order_parser.ai_full_order.contracts import AI_BUSINESS_FIELD_NAMES
from bedding_order_parser.ai_full_order.field_policy import (
    V2DecisionReason,
    V2DecisionStatus,
    V2_DESCRIPTION_FIELDS,
    V2_HIGH_REVIEW_FIELDS,
    V2_REMARK_FIELDS,
    resolve_v2_record,
    validate_v2_field_policy,
)
from bedding_order_parser.ai_full_order.normalization import (
    NormalizationStatus,
    build_business_value_view,
    formal_value_for_field,
)
from bedding_order_parser.ai_full_order.preprocessing import EvidenceItem, LocalRecord
from bedding_order_parser.ai_full_order.provenance import bind_v2_candidates
from bedding_order_parser.ai_full_order.resolution import (
    PythonFieldCandidate,
    PythonShadowRecord,
)


TARGET = LocalRecord(
    record_local_id="s1:scope-1:record-1",
    source_record_id="sha256:synthetic-record",
    scope_id="s1:scope-1",
    sheet_id="s1",
    source_row=5,
    local_line_number="s1:5",
    evidence_ids=("e1", "e2", "e3"),
)
EVIDENCE = (
    EvidenceItem(
        evidence_id="e1",
        scope_id=TARGET.scope_id,
        sheet_id=TARGET.sheet_id,
        sheet_name="PI",
        cell_range="B5",
        original_text="Duvet Cover White cotton 12 13 Ship soon",
        normalized_text="Duvet Cover White cotton 12 13 Ship soon",
    ),
    EvidenceItem(
        evidence_id="e2",
        scope_id=TARGET.scope_id,
        sheet_id=TARGET.sheet_id,
        sheet_name="PI",
        cell_range="C5",
        original_text="Pillow Case Polyester Test Hotel",
        normalized_text="Pillow Case Polyester Test Hotel",
    ),
    EvidenceItem(
        evidence_id="e3",
        scope_id=TARGET.scope_id,
        sheet_id=TARGET.sheet_id,
        sheet_name="PI",
        cell_range="D5",
        original_text="美元 USD US Dollar 10 10.0 2026年12月31日 2026-12-31",
        normalized_text="美元 USD US Dollar 10 10.0 2026年12月31日 2026-12-31",
    ),
)


def _shadow(**fields: PythonFieldCandidate) -> PythonShadowRecord:
    values = {name: PythonFieldCandidate() for name in AI_BUSINESS_FIELD_NAMES}
    values.update(fields)
    return PythonShadowRecord(
        record_local_id=TARGET.record_local_id,
        source_record_id=TARGET.source_record_id,
        scope_id=TARGET.scope_id,
        line_number="1",
        fields=values,
    )


def _candidate(
    field_name: str,
    value: str,
    *,
    interpretation: str = "direct",
    quote: str = "",
    evidence_id: str = "e1",
):
    return bind_v2_candidates(
        {
            "candidates": [
                {
                    "field_name": field_name,
                    "candidate_value": value,
                    "evidence_references": [evidence_id],
                    "interpretation": interpretation,
                    "supporting_quote": quote,
                }
            ]
        },
        target=TARGET,
        evidence_catalog=EVIDENCE,
    )


def _direct_python(value: str, evidence_id: str = "e1") -> PythonFieldCandidate:
    return PythonFieldCandidate(value=value, evidence_ids=(evidence_id,), status="extracted")


def test_field_policy_covers_all_17_fields_once() -> None:
    validate_v2_field_policy()

    groups = (V2_HIGH_REVIEW_FIELDS, V2_DESCRIPTION_FIELDS, V2_REMARK_FIELDS)
    assert frozenset().union(*groups) == frozenset(AI_BUSINESS_FIELD_NAMES)
    assert sum(len(group) for group in groups) == len(AI_BUSINESS_FIELD_NAMES) == 17


def test_high_review_direct_conflict_selects_ai_and_never_blocks() -> None:
    record = resolve_v2_record(
        TARGET,
        _candidate("数量", "13"),
        _shadow(数量=_direct_python("12")),
    )

    decision = record.decisions["数量"]
    assert decision.value == "13"
    assert decision.selected_source == "ai"
    assert decision.comparison_status is V2ComparisonStatus.DIFFERENT
    assert decision.review_required is True
    assert decision.review_severity is V2ReviewSeverity.HIGH
    assert V2DecisionReason.AI_PYTHON_DIFFERENT in decision.reason_codes
    assert decision.blocking is False
    assert record.ready_for_downstream


def test_ordinary_direct_conflict_selects_ai_and_records_comparison() -> None:
    record = resolve_v2_record(
        TARGET,
        _candidate("物料名称", "Duvet Cover"),
        _shadow(物料名称=_direct_python("Pillow Case", "e2")),
    )

    decision = record.decisions["物料名称"]
    assert decision.value == "Duvet Cover"
    assert decision.status is V2DecisionStatus.AI_SELECTED
    assert decision.selected_source == "ai"
    assert decision.comparison_status is V2ComparisonStatus.DIFFERENT
    assert decision.review_severity is V2ReviewSeverity.MEDIUM
    assert decision.blocking is False


def test_same_value_still_has_ai_as_the_selected_source() -> None:
    record = resolve_v2_record(
        TARGET,
        _candidate("物料名称", "Duvet Cover"),
        _shadow(物料名称=_direct_python("Duvet Cover")),
    )

    decision = record.decisions["物料名称"]
    assert decision.value == "Duvet Cover"
    assert decision.selected_source == "ai"
    assert decision.comparison_status is V2ComparisonStatus.AGREE
    assert decision.review_required is False


def test_currency_quantity_and_date_use_ai_derived_deterministic_normalization() -> None:
    currency = resolve_v2_record(
        TARGET,
        _candidate("币种", "美元", evidence_id="e3"),
        _shadow(币种=_direct_python("USD", "e3")),
    ).decisions["币种"]
    quantity = resolve_v2_record(
        TARGET,
        _candidate("数量", "10.0", evidence_id="e3"),
        _shadow(数量=_direct_python("10", "e3")),
    ).decisions["数量"]
    delivery_date = resolve_v2_record(
        TARGET,
        _candidate("计划发货日期", "2026年12月31日", evidence_id="e3"),
        _shadow(计划发货日期=_direct_python("2026-12-31", "e3")),
    ).decisions["计划发货日期"]

    assert (currency.value, currency.ai_display_value, currency.ai_normalized_value) == (
        "USD",
        "美元",
        "USD",
    )
    assert (quantity.value, quantity.ai_display_value, quantity.ai_normalized_value) == (
        "10",
        "10.0",
        "10",
    )
    assert (delivery_date.value, delivery_date.ai_display_value, delivery_date.ai_normalized_value) == (
        "2026-12-31",
        "2026年12月31日",
        "2026-12-31",
    )
    assert all(item.selected_source == "ai" for item in (currency, quantity, delivery_date))
    assert all(
        item.comparison_status is V2ComparisonStatus.EQUIVALENT_AFTER_NORMALIZATION
        for item in (currency, quantity, delivery_date)
    )


def test_text_normalization_keeps_display_value_when_no_formal_format_exists() -> None:
    view = build_business_value_view("物料名称", "  Duvet\u3000Cover ")

    assert view.normalized_value == "Duvet Cover"
    assert view.normalization_status is NormalizationStatus.NORMALIZED
    assert formal_value_for_field("物料名称", view) == "  Duvet\u3000Cover "


def test_uncertain_customer_difference_is_not_normalized_away() -> None:
    record = resolve_v2_record(
        TARGET,
        _candidate("客户", "Test Hotel", evidence_id="e2"),
        _shadow(客户=_direct_python("Test Hotel Group", "e2")),
    )

    decision = record.decisions["客户"]
    assert decision.value == "Test Hotel"
    assert decision.comparison_status is V2ComparisonStatus.DIFFERENT
    assert decision.review_severity is V2ReviewSeverity.HIGH
    assert decision.blocking is False


def test_ai_only_python_fill_and_both_missing_are_explicit() -> None:
    ai_only = resolve_v2_record(TARGET, _candidate("物料名称", "Duvet Cover"), _shadow())
    python_fill = resolve_v2_record(
        TARGET,
        (),
        _shadow(物料名称=_direct_python("Duvet Cover")),
    )
    both_missing = resolve_v2_record(TARGET, (), _shadow())

    assert ai_only.decisions["物料名称"].comparison_status is V2ComparisonStatus.AI_ONLY
    assert ai_only.decisions["物料名称"].selected_source == "ai"
    assert python_fill.decisions["物料名称"].value == "Duvet Cover"
    assert python_fill.decisions["物料名称"].selected_source == "python_fallback"
    assert python_fill.decisions["物料名称"].comparison_status is V2ComparisonStatus.PYTHON_FILL
    assert V2DecisionReason.PYTHON_FALLBACK_AI_MISSING in python_fill.decisions["物料名称"].reason_codes
    assert both_missing.decisions["物料名称"].value == ""
    assert both_missing.decisions["物料名称"].selected_source == "none"
    assert both_missing.decisions["物料名称"].comparison_status is V2ComparisonStatus.BOTH_MISSING
    assert both_missing.decisions["物料名称"].review_required is True


def test_content_issue_uses_python_fallback_or_empty_without_blocking() -> None:
    issue = _candidate("颜色", "Invented color")
    with_python = resolve_v2_record(
        TARGET,
        issue,
        _shadow(颜色=_direct_python("White")),
    ).decisions["颜色"]
    without_python = resolve_v2_record(TARGET, issue, _shadow()).decisions["颜色"]

    assert with_python.value == "White"
    assert with_python.selected_source == "python_fallback"
    assert with_python.technical_candidate_status is V2TechnicalCandidateStatus.CONTENT_ISSUE
    assert with_python.ai_isolated is True
    assert without_python.value == ""
    assert without_python.comparison_status is V2ComparisonStatus.BOTH_MISSING
    assert without_python.technical_candidate_status is V2TechnicalCandidateStatus.CONTENT_ISSUE
    assert without_python.blocking is False


def test_provenance_valid_semantic_candidate_is_ai_first_and_reviewable() -> None:
    record = resolve_v2_record(
        TARGET,
        _candidate("数量", "12", interpretation="semantic", quote="12"),
        _shadow(数量=_direct_python("12")),
    )

    decision = record.decisions["数量"]
    assert decision.value == "12"
    assert decision.selected_source == "ai"
    assert decision.status is V2DecisionStatus.AI_SELECTED
    assert decision.review_required is True
    assert decision.review_severity is V2ReviewSeverity.HIGH
    assert V2DecisionReason.AI_SEMANTIC_SELECTED in decision.reason_codes


def test_note_layout_cleanup_is_allowed_but_expansion_is_not() -> None:
    cleanup = resolve_v2_record(
        TARGET,
        _candidate("行备注", "Ship soon!", interpretation="source_summary", quote="Ship soon"),
        _shadow(),
    ).decisions["行备注"]
    expanded = resolve_v2_record(
        TARGET,
        _candidate(
            "行备注",
            "Ship soon with invented detail",
            interpretation="source_summary",
            quote="Ship soon",
        ),
        _shadow(),
    ).decisions["行备注"]

    assert cleanup.value == "Ship soon!"
    assert cleanup.selected_source == "ai"
    assert cleanup.review_required is True
    assert expanded.value == ""
    assert expanded.technical_candidate_status is V2TechnicalCandidateStatus.CONTENT_ISSUE
    assert V2DecisionReason.REMARK_EXPANSION_REJECTED in expanded.reason_codes
    assert expanded.blocking is False


def test_all_17_fields_are_resolved_without_system_generated_fields() -> None:
    record = resolve_v2_record(TARGET, (), _shadow())

    assert tuple(record.business_fields()) == AI_BUSINESS_FIELD_NAMES
    assert all(isinstance(value, str) for value in record.business_fields().values())
    assert "行号" not in record.business_fields()
    assert "物料编码" not in record.business_fields()
    assert "相似分数" not in record.business_fields()
