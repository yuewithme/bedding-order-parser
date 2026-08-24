"""Explainable field comparison and the versioned hybrid_score_v1 contract."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Literal

from bedding_order_parser.dictionaries.shadow_matcher import (
    _fabric_components,
    _parse_size,
)
from bedding_order_parser.materials.candidate_filter import (
    MaterialCandidate,
    OrderQuery,
)
from bedding_order_parser.materials.normalizer import (
    normalize_color,
    normalize_composition,
    normalize_density,
    normalize_text,
)


FieldStatus = Literal[
    "exact_match",
    "equivalent_match",
    "partial_match",
    "missing_query",
    "missing_candidate",
    "not_comparable",
    "no_match",
    "hard_conflict",
]

FIELD_STATUSES: tuple[FieldStatus, ...] = (
    "exact_match",
    "equivalent_match",
    "partial_match",
    "missing_query",
    "missing_candidate",
    "not_comparable",
    "no_match",
    "hard_conflict",
)

STRUCTURED_FIELD_WEIGHTS: dict[str, float] = {
    "spec": 0.25,
    "composition": 0.18,
    "fabric": 0.17,
    "density": 0.15,
    "color": 0.10,
    "style": 0.08,
    "label_method": 0.04,
    "size_type": 0.03,
}

STATUS_SCORES: dict[FieldStatus, float | None] = {
    "exact_match": 1.0,
    "equivalent_match": 0.95,
    "partial_match": 0.60,
    "missing_query": None,
    "missing_candidate": None,
    "not_comparable": None,
    "no_match": 0.0,
    "hard_conflict": 0.0,
}

HARD_CONFLICT_FIELDS = {
    "product_category",
    "spec",
    "color",
    "fabric",
    "composition",
    "density",
}


@dataclass(frozen=True)
class FieldComparison:
    query_value: str
    candidate_value: str
    status: FieldStatus
    score: float | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_value": self.query_value,
            "candidate_value": self.candidate_value,
            "status": self.status,
            "score": self.score,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CandidateEvaluation:
    material_code: str
    structured_score: float | None
    prototype_match_score: float
    vector_score: float
    vector_score_normalized: float
    comparable_field_count: int
    hard_conflict_fields: tuple[str, ...]
    fields: dict[str, FieldComparison]


def compare_candidate(
    query: OrderQuery,
    candidate: MaterialCandidate,
    *,
    vector_score: float,
) -> CandidateEvaluation:
    """Compare one candidate without mutating either source record."""
    fields = {
        "product_category": compare_exact_field(
            query.product_category,
            candidate.product_category,
            hard_conflict=True,
            equivalent_normalizer=normalize_text,
            label="product category",
        ),
        "spec": compare_spec(query.spec, candidate.spec),
        "color": compare_color(query.color, candidate.color),
        "fabric": compare_fabric(
            query.fabric_category or query.fabric,
            candidate.fabric_category or candidate.fabric,
        ),
        "composition": compare_composition(
            query.composition,
            candidate.composition,
        ),
        "density": compare_density(query.density, candidate.density),
        "style": compare_style(query.style, candidate.style),
        "label_method": compare_exact_field(
            query.label_method,
            candidate.label_method,
            hard_conflict=False,
            equivalent_normalizer=normalize_text,
            label="label method",
        ),
        "size_type": compare_exact_field(
            query.size_type,
            candidate.size_type,
            hard_conflict=False,
            equivalent_normalizer=normalize_text,
            label="size type",
        ),
        "vector": compare_vector(vector_score),
    }
    hard_conflicts = tuple(
        field_name
        for field_name, comparison in fields.items()
        if comparison.status == "hard_conflict"
    )
    structured_score, comparable_count = structured_score_v1(fields)
    normalized_vector = normalize_vector_score(vector_score)
    prototype_score = prototype_match_score_v1(
        structured_score=structured_score,
        vector_score_normalized=normalized_vector,
    )
    return CandidateEvaluation(
        material_code=candidate.material_code,
        structured_score=structured_score,
        prototype_match_score=prototype_score,
        vector_score=float(vector_score),
        vector_score_normalized=normalized_vector,
        comparable_field_count=comparable_count,
        hard_conflict_fields=hard_conflicts,
        fields=fields,
    )


def compare_spec(query_value: str, candidate_value: str) -> FieldComparison:
    missing = _missing(query_value, candidate_value)
    if missing:
        return missing
    query_size = _parse_size(query_value, raw_order="length_width")
    candidate_size = _parse_size(candidate_value, raw_order="length_width")
    if not query_size or not candidate_size:
        return _comparison(
            query_value,
            candidate_value,
            "not_comparable",
            "At least one specification cannot be parsed by the approved size rule.",
        )

    query_dimensions = sorted(
        (query_size.raw_first_dimension, query_size.raw_second_dimension)
    )
    candidate_dimensions = sorted(
        (candidate_size.raw_first_dimension, candidate_size.raw_second_dimension)
    )
    if not all(
        math.isclose(left, right, abs_tol=0.01)
        for left, right in zip(query_dimensions, candidate_dimensions, strict=True)
    ):
        return _comparison(
            query_value,
            candidate_value,
            "hard_conflict",
            "The normalized base dimensions are explicitly different.",
        )

    query_extension = query_size.structural_extension_cm
    candidate_extension = candidate_size.structural_extension_cm
    if query_extension and candidate_extension:
        if not math.isclose(query_extension, candidate_extension, abs_tol=0.01):
            return _comparison(
                query_value,
                candidate_value,
                "no_match",
                "Base dimensions match but explicit structural extensions differ.",
            )
    elif bool(query_extension) != bool(candidate_extension):
        return _comparison(
            query_value,
            candidate_value,
            "partial_match",
            "Base dimensions match; one side lacks confirmed structural extension evidence.",
        )

    exact = _compact(query_value) == _compact(candidate_value)
    return _comparison(
        query_value,
        candidate_value,
        "exact_match" if exact else "equivalent_match",
        (
            "Specifications are identical."
            if exact
            else "Dimensions are equivalent after separator, unit, or direction normalization."
        ),
    )


def compare_color(query_value: str, candidate_value: str) -> FieldComparison:
    missing = _missing(query_value, candidate_value)
    if missing:
        return missing
    query_color = normalize_color(query_value)
    candidate_color = normalize_color(candidate_value)
    if not query_color or not candidate_color:
        return _comparison(
            query_value,
            candidate_value,
            "not_comparable",
            "A main product color could not be normalized.",
        )
    if query_color != candidate_color:
        return _comparison(
            query_value,
            candidate_value,
            "hard_conflict",
            "Approved main product colors are explicitly different.",
        )
    exact = normalize_text(query_value) == normalize_text(candidate_value)
    return _comparison(
        query_value,
        candidate_value,
        "exact_match" if exact else "equivalent_match",
        "Main product colors match under the approved normalization.",
    )


def compare_composition(query_value: str, candidate_value: str) -> FieldComparison:
    missing = _missing(query_value, candidate_value)
    if missing:
        return missing
    query_composition = normalize_composition(query_value)
    candidate_composition = normalize_composition(candidate_value)
    if not query_composition or not candidate_composition:
        return _comparison(
            query_value,
            candidate_value,
            "not_comparable",
            "A standard cotton/polyester composition could not be normalized.",
        )
    if query_composition != candidate_composition:
        return _comparison(
            query_value,
            candidate_value,
            "hard_conflict",
            "Standard cotton/polyester compositions are explicitly different.",
        )
    exact = normalize_text(query_value) == normalize_text(candidate_value)
    return _comparison(
        query_value,
        candidate_value,
        "exact_match" if exact else "equivalent_match",
        "Compositions are equivalent under the approved normalization.",
    )


def compare_density(query_value: str, candidate_value: str) -> FieldComparison:
    missing = _missing(query_value, candidate_value)
    if missing:
        return missing
    query_density = normalize_density(query_value)
    candidate_density = normalize_density(candidate_value)
    if not query_density or not candidate_density:
        return _comparison(
            query_value,
            candidate_value,
            "not_comparable",
            "A standard thread-count density could not be normalized.",
        )
    if query_density != candidate_density:
        return _comparison(
            query_value,
            candidate_value,
            "hard_conflict",
            "Standard thread-count densities are explicitly different.",
        )
    exact = normalize_text(query_value) == normalize_text(candidate_value)
    return _comparison(
        query_value,
        candidate_value,
        "exact_match" if exact else "equivalent_match",
        "Densities are equivalent under the approved normalization.",
    )


def compare_fabric(query_value: str, candidate_value: str) -> FieldComparison:
    missing = _missing(query_value, candidate_value)
    if missing:
        return missing
    query_family = _fabric_components(query_value).get("category", "")
    candidate_family = _fabric_components(candidate_value).get("category", "")
    if not query_family or not candidate_family:
        return _comparison(
            query_value,
            candidate_value,
            "not_comparable",
            "One side has no mutually exclusive approved fabric family.",
        )
    if query_family != candidate_family:
        return _comparison(
            query_value,
            candidate_value,
            "hard_conflict",
            "Approved mutually exclusive fabric families are different.",
        )
    exact = normalize_text(query_value).casefold() == normalize_text(
        candidate_value
    ).casefold()
    return _comparison(
        query_value,
        candidate_value,
        "exact_match" if exact else "equivalent_match",
        "Fabric descriptions map to the same approved hierarchy family.",
    )


def compare_style(query_value: str, candidate_value: str) -> FieldComparison:
    missing = _missing(query_value, candidate_value)
    if missing:
        return missing
    query = normalize_text(query_value)
    candidate = normalize_text(candidate_value)
    if query == candidate:
        return _comparison(
            query_value,
            candidate_value,
            "exact_match",
            "Style descriptions are identical.",
        )
    query_features = _style_features(query)
    candidate_features = _style_features(candidate)
    if not query_features or not candidate_features:
        return _comparison(
            query_value,
            candidate_value,
            "not_comparable",
            "Style descriptions do not expose approved comparable components.",
        )
    shared = query_features & candidate_features
    if shared:
        return _comparison(
            query_value,
            candidate_value,
            "partial_match",
            f"Styles share components: {', '.join(sorted(shared))}.",
        )
    return _comparison(
        query_value,
        candidate_value,
        "no_match",
        "Comparable style components do not match.",
    )


def compare_exact_field(
    query_value: str,
    candidate_value: str,
    *,
    hard_conflict: bool,
    equivalent_normalizer,
    label: str,
) -> FieldComparison:
    missing = _missing(query_value, candidate_value)
    if missing:
        return missing
    query = equivalent_normalizer(query_value)
    candidate = equivalent_normalizer(candidate_value)
    if not query or not candidate:
        return _comparison(
            query_value,
            candidate_value,
            "not_comparable",
            f"The {label} cannot be normalized.",
        )
    if query == candidate:
        exact = str(query_value) == str(candidate_value)
        return _comparison(
            query_value,
            candidate_value,
            "exact_match" if exact else "equivalent_match",
            f"The {label} matches.",
        )
    return _comparison(
        query_value,
        candidate_value,
        "hard_conflict" if hard_conflict else "no_match",
        f"The {label} is explicitly different.",
    )


def compare_vector(vector_score: float) -> FieldComparison:
    if not math.isfinite(vector_score):
        return _comparison(
            "",
            "",
            "not_comparable",
            "The raw vector score is not finite.",
        )
    normalized = normalize_vector_score(vector_score)
    status: FieldStatus = (
        "exact_match" if vector_score >= 0.999999 else "partial_match"
    )
    return FieldComparison(
        query_value="query_embedding",
        candidate_value="candidate_embedding",
        status=status,
        score=normalized,
        reason=(
            "Raw normalized-vector inner product retained separately; "
            "fixed mapping is (clamp(score, -1, 1) + 1) / 2."
        ),
    )


def structured_score_v1(
    fields: dict[str, FieldComparison],
) -> tuple[float | None, int]:
    weighted_sum = 0.0
    available_weight = 0.0
    comparable_count = 0
    for field_name, weight in STRUCTURED_FIELD_WEIGHTS.items():
        comparison = fields[field_name]
        status_score = STATUS_SCORES[comparison.status]
        if status_score is None:
            continue
        weighted_sum += weight * status_score
        available_weight += weight
        comparable_count += 1
    if available_weight == 0:
        return None, 0
    return round(weighted_sum / available_weight, 6), comparable_count


def prototype_match_score_v1(
    *,
    structured_score: float | None,
    vector_score_normalized: float,
) -> float:
    if structured_score is None:
        return round(vector_score_normalized, 6)
    return round(0.75 * structured_score + 0.25 * vector_score_normalized, 6)


def normalize_vector_score(vector_score: float) -> float:
    if not math.isfinite(vector_score):
        raise ValueError("vector_score must be finite")
    return round((max(-1.0, min(1.0, float(vector_score))) + 1.0) / 2.0, 6)


def _missing(query_value: str, candidate_value: str) -> FieldComparison | None:
    if not normalize_text(query_value):
        return _comparison(
            query_value,
            candidate_value,
            "missing_query",
            "The order query does not provide this field.",
        )
    if not normalize_text(candidate_value):
        return _comparison(
            query_value,
            candidate_value,
            "missing_candidate",
            "The material candidate does not provide this field.",
        )
    return None


def _comparison(
    query_value: str,
    candidate_value: str,
    status: FieldStatus,
    reason: str,
) -> FieldComparison:
    return FieldComparison(
        query_value=str(query_value or ""),
        candidate_value=str(candidate_value or ""),
        status=status,
        score=STATUS_SCORES[status],
        reason=reason,
    )


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", normalize_text(value).casefold()).replace("×", "*").replace(
        "x", "*"
    )


def _style_features(value: str) -> set[str]:
    patterns = {
        "三飞边": r"三飞边",
        "被尾单飞边": r"被尾单飞边",
        "无飞边": r"无飞边",
        "口袋": r"口袋",
        "信封": r"信封",
        "有系带": r"有系带",
        "无系带": r"无系带",
        "拉链": r"拉链",
        "迎宾": r"迎宾",
    }
    return {label for label, pattern in patterns.items() if re.search(pattern, value)}
