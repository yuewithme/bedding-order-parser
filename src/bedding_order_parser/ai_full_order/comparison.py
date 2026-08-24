"""Stable AI/Python comparison facts for Contract V2 field resolution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from bedding_order_parser.ai_full_order.normalization import BusinessValueView


COMPARISON_VERSION = "1.0"


class V2ComparisonStatus(StrEnum):
    AGREE = "agree"
    EQUIVALENT_AFTER_NORMALIZATION = "equivalent_after_normalization"
    DIFFERENT = "different"
    AI_ONLY = "ai_only"
    PYTHON_FILL = "python_fill"
    BOTH_MISSING = "both_missing"


class V2ReviewSeverity(StrEnum):
    NONE = "none"
    MEDIUM = "medium"
    HIGH = "high"


class V2TechnicalCandidateStatus(StrEnum):
    NOT_PROVIDED = "not_provided"
    BOUND = "bound"
    CONTENT_ISSUE = "content_issue"


@dataclass(frozen=True)
class V2FieldComparison:
    status: V2ComparisonStatus
    review_required: bool
    review_severity: V2ReviewSeverity


def compare_ai_and_python(
    ai: BusinessValueView | None,
    python: BusinessValueView | None,
    *,
    high_review: bool,
    interpretation_requires_review: bool = False,
    technical_issue: bool = False,
) -> V2FieldComparison:
    """Compare already-local value views without making a business guess."""
    severity = V2ReviewSeverity.HIGH if high_review else V2ReviewSeverity.MEDIUM
    if ai is not None and python is not None:
        if ai.normalized_value == python.normalized_value:
            status = (
                V2ComparisonStatus.AGREE
                if ai.display_value == python.display_value
                else V2ComparisonStatus.EQUIVALENT_AFTER_NORMALIZATION
            )
            return V2FieldComparison(
                status=status,
                review_required=interpretation_requires_review,
                review_severity=(severity if interpretation_requires_review else V2ReviewSeverity.NONE),
            )
        return V2FieldComparison(
            status=V2ComparisonStatus.DIFFERENT,
            review_required=True,
            review_severity=severity,
        )
    if ai is not None:
        return V2FieldComparison(
            status=V2ComparisonStatus.AI_ONLY,
            review_required=interpretation_requires_review,
            review_severity=(severity if interpretation_requires_review else V2ReviewSeverity.NONE),
        )
    if python is not None:
        return V2FieldComparison(
            status=V2ComparisonStatus.PYTHON_FILL,
            review_required=True,
            review_severity=severity,
        )
    return V2FieldComparison(
        status=V2ComparisonStatus.BOTH_MISSING,
        review_required=True,
        review_severity=severity if technical_issue or high_review else V2ReviewSeverity.MEDIUM,
    )
