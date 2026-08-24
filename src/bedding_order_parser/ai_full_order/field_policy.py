"""AI-first V2 field resolution with local comparison and safe Python fallback."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Sequence

from bedding_order_parser.ai_full_order.comparison import (
    V2ComparisonStatus,
    V2ReviewSeverity,
    V2TechnicalCandidateStatus,
    compare_ai_and_python,
)
from bedding_order_parser.ai_full_order.contracts import AI_BUSINESS_FIELD_NAMES
from bedding_order_parser.ai_full_order.normalization import (
    BusinessValueView,
    build_business_value_view,
    formal_value_for_field,
    note_layout_equivalent,
)
from bedding_order_parser.ai_full_order.preprocessing import LocalRecord
from bedding_order_parser.ai_full_order.provenance import (
    BoundCandidate,
    CandidateValidationStatus,
)
from bedding_order_parser.ai_full_order.resolution import PythonFieldCandidate, PythonShadowRecord


V2_FIELD_POLICY_VERSION = "3.0"

V2_HIGH_REVIEW_FIELDS = frozenset({"客户", "币种", "业务员", "数量", "计划发货日期"})
# Compatibility export for callers that only need the stable five-field grouping.
V2_HIGH_RISK_FIELDS = V2_HIGH_REVIEW_FIELDS
V2_DESCRIPTION_FIELDS = frozenset(
    {
        "物料名称",
        "规格",
        "颜色",
        "面料",
        "面料-涤棉成分",
        "款式",
        "加标方式",
        "尺寸类型",
        "包装方式",
        "是否绣花",
    }
)
V2_REMARK_FIELDS = frozenset({"表头备注", "行备注"})


class V2DecisionStatus(StrEnum):
    AI_SELECTED = "ai_selected"
    PYTHON_FALLBACK = "python_fallback"
    MISSING = "missing"
    # Legacy values remain defined for readers of historical diagnostics only.
    AI_ISOLATED = "ai_isolated"
    PYTHON_PRESERVED = "python_preserved"
    BLOCKING_CONFLICT = "blocking_conflict"


class V2DecisionReason(StrEnum):
    AI_DIRECT_SELECTED = "ai_direct_selected"
    AI_SEMANTIC_SELECTED = "ai_semantic_selected"
    AI_SOURCE_SUMMARY_SELECTED = "ai_source_summary_selected"
    AI_PYTHON_AGREE = "ai_python_agree"
    AI_PYTHON_NORMALIZED_EQUIVALENT = "ai_python_normalized_equivalent"
    AI_PYTHON_DIFFERENT = "ai_python_different"
    AI_ONLY = "ai_only"
    PYTHON_FALLBACK_AI_MISSING = "python_fallback_ai_missing"
    PYTHON_FALLBACK_AI_ISSUE = "python_fallback_ai_issue"
    BOTH_MISSING = "both_missing"
    AI_CANDIDATE_CONTENT_ISSUE = "ai_candidate_content_issue"
    AI_INTERPRETATION_NOT_ALLOWED = "ai_interpretation_not_allowed"
    REMARK_EXPANSION_REJECTED = "remark_expansion_rejected"
    # Legacy reason values are retained for reading earlier persisted diagnostics.
    AI_DIRECT_ACCEPTED = "ai_direct_accepted"
    AI_SEMANTIC_ACCEPTED = "ai_semantic_accepted"
    AI_SOURCE_SUMMARY_ACCEPTED = "ai_source_summary_accepted"
    PYTHON_PRESERVED_AI_MISSING = "python_preserved_ai_missing"
    PYTHON_PRESERVED_AI_ISSUE = "python_preserved_ai_issue"
    PYTHON_PRESERVED_POLICY_REJECTION = "python_preserved_policy_rejection"
    PYTHON_PRESERVED_ORDINARY_CONFLICT = "python_preserved_ordinary_conflict"
    AI_CANDIDATE_ISSUE = "ai_candidate_issue"
    AI_INTERPRETATION_REJECTED = "ai_interpretation_rejected"
    AI_BUSINESS_CONSTRAINT_REJECTED = "ai_business_constraint_rejected"
    HIGH_RISK_DIRECT_CONFLICT = "high_risk_direct_conflict"
    HIGH_RISK_MISSING = "high_risk_missing"
    FIELD_MISSING = "field_missing"


class V2FieldPolicyError(ValueError):
    """Raised when locally-bound identities or policy completeness are invalid."""


@dataclass(frozen=True)
class V2FieldDecision:
    field_name: str
    value: str
    status: V2DecisionStatus
    selected_source: str
    comparison_status: V2ComparisonStatus
    review_required: bool
    review_severity: V2ReviewSeverity
    reason_codes: tuple[V2DecisionReason, ...]
    ai_display_value: str = ""
    ai_normalized_value: str = ""
    ai_evidence_ids: tuple[str, ...] = ()
    python_display_value: str = ""
    python_normalized_value: str = ""
    python_evidence_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    candidate_issue_code: str = ""
    technical_candidate_status: V2TechnicalCandidateStatus = (
        V2TechnicalCandidateStatus.NOT_PROVIDED
    )
    blocking: bool = False
    ai_isolated: bool = False
    ai_candidate: BoundCandidate | None = None

    @property
    def reason_code(self) -> V2DecisionReason:
        """Compatibility view for current downstream diagnostics."""
        return self.reason_codes[0]


@dataclass(frozen=True)
class V2CanonicalRecord:
    record_local_id: str
    source_record_id: str
    scope_id: str
    line_number: str
    decisions: dict[str, V2FieldDecision]

    @property
    def technical_ready(self) -> bool:
        """Return whether the locally resolved canonical shape is complete.

        Hard identity and provenance failures prevent this object from being built.
        Business review metadata, including legacy ``blocking`` flags, is deliberately
        not part of this structural readiness contract.
        """

        return tuple(self.decisions) == AI_BUSINESS_FIELD_NAMES and all(
            isinstance(decision.value, str) for decision in self.decisions.values()
        )

    @property
    def review_required(self) -> bool:
        return any(decision.review_required for decision in self.decisions.values())

    @property
    def ready_for_downstream(self) -> bool:
        """Compatibility alias for callers migrating to ``technical_ready``."""

        return self.technical_ready

    def business_fields(self) -> dict[str, str]:
        return {name: self.decisions[name].value for name in AI_BUSINESS_FIELD_NAMES}


def validate_v2_field_policy() -> None:
    groups = (V2_HIGH_REVIEW_FIELDS, V2_DESCRIPTION_FIELDS, V2_REMARK_FIELDS)
    union = frozenset().union(*groups)
    if union != frozenset(AI_BUSINESS_FIELD_NAMES):
        raise V2FieldPolicyError("V2 field policy does not cover exactly the 17 fields.")
    if any(left & right for index, left in enumerate(groups) for right in groups[index + 1 :]):
        raise V2FieldPolicyError("V2 field policy groups must be mutually exclusive.")


def resolve_v2_record(
    target: LocalRecord,
    candidates: Sequence[BoundCandidate],
    python_shadow: PythonShadowRecord,
) -> V2CanonicalRecord:
    validate_v2_field_policy()
    if (
        python_shadow.record_local_id != target.record_local_id
        or python_shadow.source_record_id != target.source_record_id
        or python_shadow.scope_id != target.scope_id
    ):
        raise V2FieldPolicyError("Python shadow identity does not match the V2 target.")

    candidate_by_field: dict[str, BoundCandidate] = {}
    for candidate in candidates:
        if (
            candidate.target_record_local_id != target.record_local_id
            or candidate.target_source_record_id != target.source_record_id
            or candidate.target_scope_id != target.scope_id
            or candidate.target_sheet_id != target.sheet_id
            or candidate.target_source_row != target.source_row
        ):
            raise V2FieldPolicyError("Bound candidate identity does not match the V2 target.")
        if candidate.field_name in candidate_by_field:
            raise V2FieldPolicyError("Duplicate bound candidate field.")
        candidate_by_field[candidate.field_name] = candidate

    decisions = {
        field_name: _resolve_field(
            field_name,
            candidate_by_field.get(field_name),
            python_shadow.fields[field_name],
        )
        for field_name in AI_BUSINESS_FIELD_NAMES
    }
    if tuple(decisions) != AI_BUSINESS_FIELD_NAMES or any(
        not isinstance(decision.value, str) for decision in decisions.values()
    ):
        raise V2FieldPolicyError("Canonical V2 record must contain exactly 17 string fields.")
    return V2CanonicalRecord(
        record_local_id=target.record_local_id,
        source_record_id=target.source_record_id,
        scope_id=target.scope_id,
        line_number=python_shadow.line_number,
        decisions=decisions,
    )


def _resolve_field(
    field_name: str,
    ai: BoundCandidate | None,
    python: PythonFieldCandidate,
) -> V2FieldDecision:
    python_view = _python_view(field_name, python)
    high_review = field_name in V2_HIGH_REVIEW_FIELDS
    ai_issue_reason = _candidate_content_issue(field_name, ai)
    if ai is None:
        return _fallback_or_missing(
            field_name,
            python,
            python_view,
            high_review=high_review,
            ai=ai,
            issue_reason=None,
        )
    if ai_issue_reason is not None:
        return _fallback_or_missing(
            field_name,
            python,
            python_view,
            high_review=high_review,
            ai=ai,
            issue_reason=ai_issue_reason,
        )

    ai_view = build_business_value_view(field_name, ai.candidate_value)
    comparison = compare_ai_and_python(
        ai_view,
        python_view,
        high_review=high_review,
        interpretation_requires_review=ai.interpretation in {"semantic", "source_summary"},
    )
    reasons = [_selection_reason(ai.interpretation), *_comparison_reasons(comparison.status)]
    return V2FieldDecision(
        field_name=field_name,
        value=formal_value_for_field(field_name, ai_view),
        status=V2DecisionStatus.AI_SELECTED,
        selected_source="ai",
        comparison_status=comparison.status,
        review_required=comparison.review_required,
        review_severity=comparison.review_severity,
        reason_codes=tuple(reasons),
        ai_display_value=ai_view.display_value,
        ai_normalized_value=ai_view.normalized_value,
        ai_evidence_ids=ai.evidence_references,
        python_display_value=python_view.display_value if python_view else "",
        python_normalized_value=python_view.normalized_value if python_view else "",
        python_evidence_ids=python.evidence_ids if python_view else (),
        evidence_ids=ai.evidence_references,
        technical_candidate_status=V2TechnicalCandidateStatus.BOUND,
        ai_candidate=ai,
    )


def _fallback_or_missing(
    field_name: str,
    python: PythonFieldCandidate,
    python_view: BusinessValueView | None,
    *,
    high_review: bool,
    ai: BoundCandidate | None,
    issue_reason: V2DecisionReason | None,
) -> V2FieldDecision:
    technical_issue = issue_reason is not None
    comparison = compare_ai_and_python(
        None,
        python_view,
        high_review=high_review,
        technical_issue=technical_issue,
    )
    issue_code = ai.issue_code.value if ai and ai.issue_code else ""
    if python_view is not None:
        reasons = [
            (
                V2DecisionReason.PYTHON_FALLBACK_AI_ISSUE
                if technical_issue
                else V2DecisionReason.PYTHON_FALLBACK_AI_MISSING
            )
        ]
        if issue_reason is not None:
            reasons.append(issue_reason)
        return V2FieldDecision(
            field_name=field_name,
            value=formal_value_for_field(field_name, python_view),
            status=V2DecisionStatus.PYTHON_FALLBACK,
            selected_source="python_fallback",
            comparison_status=comparison.status,
            review_required=True,
            review_severity=comparison.review_severity,
            reason_codes=tuple(reasons),
            ai_display_value=ai.candidate_value if ai else "",
            ai_normalized_value=(
                build_business_value_view(field_name, ai.candidate_value).normalized_value if ai else ""
            ),
            ai_evidence_ids=ai.evidence_references if ai else (),
            python_display_value=python_view.display_value,
            python_normalized_value=python_view.normalized_value,
            python_evidence_ids=python.evidence_ids,
            evidence_ids=python.evidence_ids,
            candidate_issue_code=issue_code,
            technical_candidate_status=(
                V2TechnicalCandidateStatus.CONTENT_ISSUE
                if technical_issue
                else V2TechnicalCandidateStatus.NOT_PROVIDED
            ),
            ai_isolated=technical_issue,
            ai_candidate=ai,
        )

    reasons = [V2DecisionReason.BOTH_MISSING]
    if issue_reason is not None:
        reasons.append(issue_reason)
    return V2FieldDecision(
        field_name=field_name,
        value="",
        status=V2DecisionStatus.MISSING,
        selected_source="none",
        comparison_status=comparison.status,
        review_required=True,
        review_severity=comparison.review_severity,
        reason_codes=tuple(reasons),
        ai_display_value=ai.candidate_value if ai else "",
        ai_normalized_value=(
            build_business_value_view(field_name, ai.candidate_value).normalized_value if ai else ""
        ),
        ai_evidence_ids=ai.evidence_references if ai else (),
        candidate_issue_code=issue_code,
        technical_candidate_status=(
            V2TechnicalCandidateStatus.CONTENT_ISSUE
            if technical_issue
            else V2TechnicalCandidateStatus.NOT_PROVIDED
        ),
        ai_isolated=technical_issue,
        ai_candidate=ai,
    )


def _python_view(field_name: str, candidate: PythonFieldCandidate) -> BusinessValueView | None:
    if not candidate.has_direct_evidence:
        return None
    return build_business_value_view(field_name, candidate.value)


def _candidate_content_issue(
    field_name: str, candidate: BoundCandidate | None
) -> V2DecisionReason | None:
    if candidate is None:
        return None
    if candidate.validation_status is CandidateValidationStatus.ISSUE:
        return V2DecisionReason.AI_CANDIDATE_CONTENT_ISSUE
    if candidate.interpretation == "source_summary" and field_name not in V2_REMARK_FIELDS:
        return V2DecisionReason.AI_INTERPRETATION_NOT_ALLOWED
    if candidate.interpretation not in {"direct", "semantic", "source_summary"}:
        return V2DecisionReason.AI_INTERPRETATION_NOT_ALLOWED
    if (
        field_name in V2_REMARK_FIELDS
        and candidate.interpretation == "source_summary"
        and not note_layout_equivalent(candidate.candidate_value, candidate.supporting_quote)
    ):
        return V2DecisionReason.REMARK_EXPANSION_REJECTED
    return None


def _selection_reason(interpretation: str) -> V2DecisionReason:
    return {
        "direct": V2DecisionReason.AI_DIRECT_SELECTED,
        "semantic": V2DecisionReason.AI_SEMANTIC_SELECTED,
        "source_summary": V2DecisionReason.AI_SOURCE_SUMMARY_SELECTED,
    }[interpretation]


def _comparison_reasons(status: V2ComparisonStatus) -> tuple[V2DecisionReason, ...]:
    return {
        V2ComparisonStatus.AGREE: (V2DecisionReason.AI_PYTHON_AGREE,),
        V2ComparisonStatus.EQUIVALENT_AFTER_NORMALIZATION: (
            V2DecisionReason.AI_PYTHON_NORMALIZED_EQUIVALENT,
        ),
        V2ComparisonStatus.DIFFERENT: (V2DecisionReason.AI_PYTHON_DIFFERENT,),
        V2ComparisonStatus.AI_ONLY: (V2DecisionReason.AI_ONLY,),
        V2ComparisonStatus.PYTHON_FILL: (),
        V2ComparisonStatus.BOTH_MISSING: (),
    }[status]
