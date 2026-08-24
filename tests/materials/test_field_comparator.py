from __future__ import annotations

import pytest

from bedding_order_parser.materials.candidate_filter import (
    MaterialCandidate,
    OrderQuery,
)
from bedding_order_parser.materials.field_comparator import (
    compare_candidate,
    compare_composition,
    compare_density,
    compare_fabric,
    compare_spec,
)


def query(**overrides: str) -> OrderQuery:
    values = {
        "source_file": "sample.xlsx",
        "sheet": "PI",
        "line_number": "1",
        "result_json": "sample_gate2d.json",
        "parse_report_json": "sample_gate2d_parse_report.json",
        "product_category": "被套",
        "spec": "260*240cm",
        "color": "漂白色",
        "fabric": "贡缎/T300/100C",
        "fabric_category": "贡缎",
        "density": "T300",
        "composition": "C100",
        "style": "无飞边",
        "label_method": "客标",
        "size_type": "交货尺寸",
        "line_note": "",
        "embedding_text": "query",
    }
    values.update(overrides)
    return OrderQuery(**values)


def candidate(**overrides: object) -> MaterialCandidate:
    values: dict[str, object] = {
        "material_code": "MAT-001",
        "source_row": 2,
        "product_category": "被套",
        "spec": "240*260cm",
        "color": "漂白色",
        "fabric": "贡缎",
        "fabric_category": "贡缎",
        "density": "T300",
        "composition": "C100",
        "style": "无飞边",
        "label_method": "客标",
        "size_type": "交货尺寸",
        "embedding_text": "candidate",
    }
    values.update(overrides)
    return MaterialCandidate(**values)


def test_candidate_missing_field_is_not_hard_conflict() -> None:
    result = compare_candidate(
        query(),
        candidate(composition=""),
        vector_score=0.4,
    )

    assert result.fields["composition"].status == "missing_candidate"
    assert "composition" not in result.hard_conflict_fields


def test_explicit_base_dimension_difference_is_hard_conflict() -> None:
    result = compare_spec("260*240cm", "260*250cm")

    assert result.status == "hard_conflict"


def test_missing_structural_extension_is_partial_match() -> None:
    result = compare_spec("260*240+15cm", "240*260cm")

    assert result.status == "partial_match"


def test_hand_hole_dimension_is_not_structural_extension() -> None:
    result = compare_spec("260*240cm hand hole 20cm", "240*260+20cm")

    assert result.status == "partial_match"


def test_composition_and_density_explicit_differences_are_hard_conflicts() -> None:
    assert compare_composition("100C", "C80/T20").status == "hard_conflict"
    assert compare_density("T300", "T400").status == "hard_conflict"


def test_approved_fabric_hierarchy_aliases_are_equivalent() -> None:
    assert compare_fabric("sateen", "贡缎").status == "equivalent_match"


def test_process_color_in_line_note_does_not_override_main_color() -> None:
    result = compare_candidate(
        query(line_note="blue ID thread"),
        candidate(color="漂白色"),
        vector_score=0.5,
    )

    assert result.fields["color"].status == "exact_match"


def test_missing_fields_are_excluded_and_available_weights_renormalized() -> None:
    result = compare_candidate(
        query(
            composition="",
            fabric="",
            fabric_category="",
            density="",
            style="",
            label_method="",
            size_type="",
        ),
        candidate(),
        vector_score=0.2,
    )

    assert result.comparable_field_count == 2
    assert result.structured_score == pytest.approx(0.964286)


def test_vector_score_is_preserved_and_prototype_score_is_reproducible() -> None:
    result = compare_candidate(query(), candidate(), vector_score=0.4)

    assert result.vector_score == 0.4
    assert result.vector_score_normalized == 0.7
    assert result.prototype_match_score == pytest.approx(
        round(0.75 * result.structured_score + 0.25 * 0.7, 6)
    )
