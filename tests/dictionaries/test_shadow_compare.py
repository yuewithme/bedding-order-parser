import hashlib
import json

import pytest
from openpyxl import Workbook

from bedding_order_parser.dictionaries.models import (
    DictionaryBundle,
    DictionarySource,
    FabricRow,
    RuleRow,
    StyleRow,
)
from bedding_order_parser.dictionaries.shadow_matcher import (
    _Evidence,
    _evidence_for_field,
    compare_shadow_field,
)
from bedding_order_parser.dictionaries.shadow_models import (
    SHADOW_FIELDS,
    SHADOW_STATUSES,
    ShadowFieldComparison,
    ShadowFileReport,
    ShadowRecord,
    ShadowReport,
)
from bedding_order_parser.dictionaries.shadow_writer import write_shadow_report
from bedding_order_parser.exceptions import OutputFileError


@pytest.fixture()
def bundle() -> DictionaryBundle:
    return DictionaryBundle(
        sources=[
            DictionarySource(
                file_name="PI单提取规则.xlsx",
                sha256="rules",
                sheet_name="被套 提取规则",
            ),
            DictionarySource(
                file_name="款式表_structured.xlsx",
                sha256="styles",
                sheet_name="Sheet1",
            ),
        ],
        rules=[
            RuleRow(
                source_row=2,
                source_cells={"字段名": "A2"},
                field_name="产品名称",
                rule_description="duvet cover",
                standard_value="被套",
                notes="",
                raw_values={"字段名": "产品名称", "关键描述": "duvet cover"},
            )
        ],
        fabrics=[
            FabricRow(
                source_row=2,
                fabric_family="贡缎",
                fabric_standard="贡缎/JC60S*JC40S/173*120/缎纹",
                color_standard="漂白",
                composition_raw="100%棉",
                density="T300",
                raw_values={},
            ),
            FabricRow(
                source_row=3,
                fabric_family="贡缎",
                fabric_standard="贡缎/JC40S*JC40S/200*100/缎纹",
                color_standard="漂白",
                composition_raw="100%棉",
                density="T300",
                raw_values={},
            ),
        ],
        styles=[
            StyleRow(
                source_row=2,
                standard_name="无飞边口袋无系带式",
                flange="无飞边",
                tie="无系带",
                zipper="无拉链",
                has_pocket="是",
                is_welcome_style="否",
                other_structure="口袋",
                dimensions="",
                raw_values={},
            ),
            StyleRow(
                source_row=3,
                standard_name="无飞边口袋无系带带手洞式",
                flange="无飞边",
                tie="无系带",
                zipper="无拉链",
                has_pocket="是",
                is_welcome_style="是",
                other_structure="口袋 手洞",
                dimensions="",
                raw_values={},
            ),
            StyleRow(
                source_row=4,
                standard_name="无飞边口袋无系带手洞备选式",
                flange="无飞边",
                tie="无系带",
                zipper="无拉链",
                has_pocket="是",
                is_welcome_style="是",
                other_structure="口袋 手洞",
                dimensions="",
                raw_values={},
            ),
        ],
        summary={"rule_rows": 1, "fabric_rows": 2, "style_rows": 3},
    )


def ev(source, python_value, status="normalized", cells=None) -> _Evidence:
    return _Evidence(
        source_text=source,
        source_cells=["A1"] if cells is None else cells,
        python_value=python_value,
        python_status=status,
    )


def with_rows(
    bundle: DictionaryBundle,
    *,
    fabrics: list[FabricRow] | None = None,
    styles: list[StyleRow] | None = None,
) -> DictionaryBundle:
    return DictionaryBundle(
        sources=bundle.sources,
        rules=bundle.rules,
        fabrics=bundle.fabrics if fabrics is None else fabrics,
        styles=bundle.styles if styles is None else styles,
        summary=bundle.summary,
    )


def fabric_row(
    source_row: int,
    family: str,
    standard: str,
    composition: str,
    density: str,
    color: str = "漂白",
) -> FabricRow:
    return FabricRow(
        source_row=source_row,
        fabric_family=family,
        fabric_standard=standard,
        color_standard=color,
        composition_raw=composition,
        density=density,
        raw_values={},
    )


def style_row(
    source_row: int,
    standard: str,
    *,
    flange: str,
    pocket: str,
    welcome: str,
    other: str = "",
) -> StyleRow:
    return StyleRow(
        source_row=source_row,
        standard_name=standard,
        flange=flange,
        tie="无系带",
        zipper="无拉链",
        has_pocket=pocket,
        is_welcome_style=welcome,
        other_structure=other,
        dimensions="",
        raw_values={},
    )


def test_shadow_fields_are_the_gate_3a_c_contract() -> None:
    assert SHADOW_FIELDS == (
        "币种",
        "物料名称",
        "规格",
        "颜色",
        "面料",
        "面料-涤棉成分",
        "款式",
        "尺寸类型",
        "行备注",
        "是否绣花",
    )


def test_shadow_statuses_are_closed_set() -> None:
    assert SHADOW_STATUSES == (
        "exact_match",
        "equivalent_match",
        "dictionary_more_specific",
        "partial_match",
        "ambiguous",
        "conflict",
        "dictionary_no_match",
        "source_not_provided",
    )


def test_source_cell_value_can_conflict_with_python_color(bundle) -> None:
    comparison = compare_shadow_field(bundle, "颜色", ev("Grey duvet cover", "漂白色"))

    assert comparison.comparison_status == "conflict"
    assert comparison.dictionary_candidates == ["灰色"]
    assert comparison.conflicting_components == ["颜色"]


def test_100_percent_cotton_is_equivalent_to_100c(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "面料-涤棉成分",
        ev("100% cotton sateen", "100C"),
    )

    assert comparison.comparison_status == "equivalent_match"
    assert comparison.dictionary_candidates == ["100C"]


def test_c80_t20_conflicts_with_c50_t50(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "面料-涤棉成分",
        ev("C80/T20", "C50/T50"),
    )

    assert comparison.comparison_status == "conflict"
    assert comparison.conflicting_components == ["composition"]


def test_usd_maps_to_official_chinese_currency(bundle) -> None:
    comparison = compare_shadow_field(bundle, "币种", ev("Amount USD 12.00", "美元"))

    assert comparison.comparison_status == "exact_match"
    assert comparison.dictionary_candidates == ["美元"]


def test_size_uses_source_order_labels_and_unit_conversion(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "规格",
        ev("W180cm x L270cm overlap 10mm", "270*180+1cm"),
    )

    assert comparison.comparison_status == "exact_match"
    assert comparison.dictionary_candidates == ["270*180+1cm"]


def test_reversed_size_numbers_are_equivalent_for_duvet_raw_width_length(bundle) -> None:
    comparison = compare_shadow_field(bundle, "规格", ev("180*270cm", "270*180"))

    assert comparison.comparison_status == "equivalent_match"
    assert comparison.dictionary_candidates == ["270*180"]


def test_size_with_structural_flap_is_equivalent(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "规格",
        ev("340*260 bottom opening one side on opening 15cm flap", "260*340+15cm"),
    )

    assert comparison.comparison_status == "equivalent_match"
    assert comparison.dictionary_candidates == ["260*340+15cm"]


def test_size_can_supplement_flap_from_same_item_row(bundle) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "PI"
    sheet["C2"] = "340*260"
    sheet["D2"] = "bottom opening one side on opening 15cm flap"
    parse_record = {
        "fields": {
            "规格": {"status": "normalized", "source": {"sheet": "PI", "cells": ["C2"]}},
            "款式": {"source": {"sheet": "PI", "cells": ["D2"]}},
        }
    }
    official_record = {"规格": "260*340+15cm"}

    evidence = _evidence_for_field(workbook, parse_record, official_record, "规格")
    comparison = compare_shadow_field(bundle, "规格", evidence)
    workbook.close()

    assert evidence.source_cells == ["C2", "D2"]
    assert comparison.comparison_status == "equivalent_match"
    assert comparison.dictionary_candidates == ["260*340+15cm"]


def test_hand_hole_size_does_not_become_structural_extension(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "规格",
        ev("155x250 bag with 20cm hand holes", "250*155cm"),
    )

    assert comparison.comparison_status == "equivalent_match"
    assert comparison.dictionary_candidates == ["250*155"]


def test_location_count_does_not_become_structural_extension(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "规格",
        ev("180*270 IC Chip: 1 location", "270*180cm"),
    )

    assert comparison.comparison_status == "equivalent_match"
    assert comparison.dictionary_candidates == ["270*180"]


def test_row_quantity_after_bottom_opening_does_not_become_extension(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "规格",
        ev("270 x 240 cm | no flap, bottom opening | 100", "240*270cm"),
    )

    assert comparison.comparison_status == "equivalent_match"
    assert comparison.dictionary_candidates == ["240*270"]


def test_thread_count_does_not_become_size_or_extension(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "规格",
        ev("180*270cm 300TC sateen", "270*180cm"),
    )

    assert comparison.comparison_status == "equivalent_match"
    assert comparison.dictionary_candidates == ["270*180"]


def test_size_mm_converts_to_cm(bundle) -> None:
    comparison = compare_shadow_field(bundle, "规格", ev("2800*2600 mm", "260*280cm"))

    assert comparison.comparison_status == "equivalent_match"
    assert comparison.dictionary_candidates == ["260*280"]


def test_size_inches_convert_to_cm(bundle) -> None:
    comparison = compare_shadow_field(bundle, "规格", ev('60x90"', "228.6*152.4cm"))

    assert comparison.comparison_status == "equivalent_match"
    assert comparison.dictionary_candidates == ["228.6*152.4"]


def test_truly_different_size_remains_conflict(bundle) -> None:
    comparison = compare_shadow_field(bundle, "规格", ev("180*270cm", "260*180cm"))

    assert comparison.comparison_status == "conflict"
    assert comparison.conflicting_components == ["dimensions"]


def test_ambiguous_structural_extension_is_partial_not_conflict(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "规格",
        ev(
            "270x240cm bottom opening, one side on opening 15cm Flap "
            "with 5cm hem, the other side no flap",
            "240*270+5cm",
        ),
    )

    assert comparison.comparison_status == "partial_match"
    assert comparison.missing_components == ["structural_extension_cm_ambiguous"]


def test_fabric_partial_match_when_official_is_less_specific(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "面料",
        ev("sateen T300 100% cotton", "贡缎/T300"),
    )

    assert comparison.comparison_status == "equivalent_match"
    assert comparison.dictionary_candidates == ["贡缎/T300/100C"]
    assert len(comparison.detailed_candidates) == 2


def test_fabric_dictionary_no_match_when_no_row_matches(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "面料",
        ev("percale T180 C50/T50", "平布/T180/C50/T50"),
    )

    assert comparison.comparison_status == "dictionary_no_match"
    assert comparison.dictionary_candidates == ["平布/T180/C50/T50"]


def test_sateen_stripe_prefers_stripe_category(bundle) -> None:
    calibrated = with_rows(
        bundle,
        fabrics=[
            fabric_row(
                10,
                "缎纹小提花",
                "0.4CM缎条/(C60/T40)40S*(C60/T40)40S/140*110/缎纹小提花",
                "60%棉40%涤",
                "T250",
            ),
            fabric_row(
                11,
                "贡缎 / 缎纹",
                "贡缎/C40S*(C60/T40)40S/140*110/缎纹",
                "60%棉40%涤",
                "T250",
            ),
        ],
    )

    comparison = compare_shadow_field(
        calibrated,
        "面料",
        ev("60% cotton 40% polyester, 4mm sateen stripe, white T250", "缎条/T250/C60/T40"),
    )

    assert comparison.comparison_status == "equivalent_match"
    assert comparison.dictionary_candidates == ["缎条/T250/C60/T40"]
    assert comparison.detailed_candidates[0].startswith("0.4CM缎条/")


def test_plain_sateen_maps_to_sateen_projection(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "面料",
        ev("100% cotton T300 sateen weave white", "贡缎/T300/100C"),
    )

    assert comparison.comparison_status == "equivalent_match"
    assert comparison.dictionary_candidates == ["贡缎/T300/100C"]


def test_distinct_fabric_projections_remain_ambiguous(bundle) -> None:
    calibrated = with_rows(
        bundle,
        fabrics=[
            fabric_row(10, "贡缎 / 缎纹", "贡缎/JC60S*C40S/173*120/缎纹", "100%棉", "T300"),
            fabric_row(
                11,
                "贡缎 / 缎纹",
                "贡缎/JC60S*(C80/T20)40S/173*120/缎纹",
                "80%棉20%涤",
                "T300",
            ),
        ],
    )

    comparison = compare_shadow_field(
        calibrated,
        "面料",
        ev("T300 sateen weave", "贡缎/T300"),
    )

    assert comparison.comparison_status == "ambiguous"
    assert comparison.dictionary_candidates == [
        "贡缎/T300/100C",
        "贡缎/T300/C80/T20",
    ]


def test_explicit_fabric_composition_conflict_remains_conflict(bundle) -> None:
    calibrated = with_rows(
        bundle,
        fabrics=[
            fabric_row(
                10,
                "贡缎 / 缎纹",
                "贡缎/JC60S*(C80/T20)40S/173*120/缎纹",
                "80%棉20%涤",
                "T300",
            )
        ],
    )

    comparison = compare_shadow_field(
        calibrated,
        "面料",
        ev("C80/T20 T300 sateen", "贡缎/T300/C50/T50"),
    )

    assert comparison.comparison_status == "conflict"
    assert comparison.conflicting_components == ["composition"]


def test_missing_source_yarn_does_not_remove_valid_fabric_rows(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "面料",
        ev("100% cotton T300 sateen white", "贡缎/T300/100C"),
    )

    assert comparison.comparison_status == "equivalent_match"
    assert len(comparison.detailed_candidates) == 2


def test_density_composition_and_yarn_filter_together(bundle) -> None:
    calibrated = with_rows(
        bundle,
        fabrics=[
            fabric_row(10, "贡缎 / 缎纹", "贡缎/JC80S*JC60S/200*184/缎纹", "100%棉", "T400"),
            fabric_row(11, "贡缎 / 缎纹", "贡缎/JC60S*JC80S/200*184/缎纹", "100%棉", "T400"),
        ],
    )

    comparison = compare_shadow_field(
        calibrated,
        "面料",
        ev("100% cotton, TC: 400, 80S*60S sateen white", "贡缎/T400/100C"),
    )

    assert comparison.comparison_status == "equivalent_match"
    assert comparison.detailed_candidates == ["贡缎/JC80S*JC60S/200*184/缎纹"]


def test_style_complete_dictionary_match(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "款式",
        ev("no flange pocket no tie", "无飞边口袋无系带式"),
    )

    assert comparison.comparison_status == "equivalent_match"
    assert comparison.dictionary_candidates == ["无飞边口袋无系带式"]


def test_style_ambiguous_when_multiple_rows_match(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "款式",
        ev("no flange pocket no tie hand hole", "无飞边口袋无系带式"),
    )

    assert comparison.comparison_status == "ambiguous"
    assert len(comparison.dictionary_candidates) == 2


def test_no_falnge_is_controlled_alias_for_no_flange(bundle) -> None:
    calibrated = with_rows(
        bundle,
        styles=[
            style_row(
                10,
                "无飞边口袋无系带迎宾式",
                flange="无飞边",
                pocket="有口袋",
                welcome="迎宾式",
            )
        ],
    )

    comparison = compare_shadow_field(
        calibrated,
        "款式",
        ev("Bag style with hand holes, no falnge", "无飞边口袋无系带迎宾式"),
    )

    assert comparison.comparison_status == "equivalent_match"
    assert comparison.dictionary_candidates == ["无飞边口袋无系带迎宾式"]


def test_no_flange_does_not_match_positive_flange_style(bundle) -> None:
    calibrated = with_rows(
        bundle,
        styles=[
            style_row(
                10,
                "无飞边口袋无系带迎宾式",
                flange="无飞边",
                pocket="有口袋",
                welcome="迎宾式",
            ),
            style_row(
                11,
                "被尾单飞边双层口叠边口袋无系带迎宾式",
                flange="有飞边",
                pocket="有口袋",
                welcome="迎宾式",
                other="双层口",
            ),
        ],
    )

    comparison = compare_shadow_field(
        calibrated,
        "款式",
        ev("Bag style with hand holes, no flange", "无飞边口袋无系带迎宾式"),
    )

    assert comparison.dictionary_candidates == ["无飞边口袋无系带迎宾式"]


def test_bag_style_and_hand_holes_form_welcome_pocket_style(bundle) -> None:
    calibrated = with_rows(
        bundle,
        styles=[
            style_row(
                10,
                "无飞边口袋无系带迎宾式",
                flange="无飞边",
                pocket="有口袋",
                welcome="迎宾式",
            )
        ],
    )

    comparison = compare_shadow_field(
        calibrated,
        "款式",
        ev("Bag model, 2 hands holes, without inner flap", "无飞边口袋无系带迎宾式"),
    )

    assert comparison.comparison_status == "equivalent_match"


def test_no_flap_is_not_treated_as_positive_flap(bundle) -> None:
    calibrated = with_rows(
        bundle,
        styles=[
            style_row(
                10,
                "无飞边平口信封迎宾式",
                flange="无飞边",
                pocket="无口袋",
                welcome="迎宾式",
            )
        ],
    )

    no_flap = compare_shadow_field(
        calibrated,
        "款式",
        ev("bottom opening, no flap, hand holes", "无飞边平口信封迎宾式"),
    )
    with_flap = compare_shadow_field(
        calibrated,
        "款式",
        ev("bottom opening, one side 15cm flap, hand holes", "无飞边平口信封迎宾式"),
    )

    assert no_flap.comparison_status == "dictionary_no_match"
    assert with_flap.comparison_status == "equivalent_match"


def test_envelope_style_is_component_matched(bundle) -> None:
    calibrated = with_rows(
        bundle,
        styles=[
            style_row(
                10,
                "无飞边平口信封式",
                flange="无飞边",
                pocket="无口袋",
                welcome="非迎宾",
            )
        ],
    )

    comparison = compare_shadow_field(
        calibrated,
        "款式",
        ev("Envelope style with flap 50cm", "无飞边平口信封式"),
    )

    assert comparison.comparison_status == "equivalent_match"


def test_insufficient_style_source_does_not_force_match(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "款式",
        ev("250TC cotton with 5cm hem at 3 sides", ""),
    )

    assert comparison.comparison_status == "source_not_provided"
    assert comparison.dictionary_candidates == []


def test_source_missing_status_is_reported_and_python_status_retained(bundle) -> None:
    comparison = compare_shadow_field(
        bundle,
        "是否绣花",
        ev("", "N", status="defaulted", cells=[]),
    )

    assert comparison.comparison_status == "source_not_provided"
    assert comparison.python_status == "defaulted"
    assert comparison.source_cells == []


def test_dictionary_no_match_for_unrecognized_color(bundle) -> None:
    comparison = compare_shadow_field(bundle, "颜色", ev("chartreuse", "漂白色"))

    assert comparison.comparison_status == "dictionary_no_match"
    assert comparison.dictionary_candidates == []


def test_shadow_writer_keeps_chinese_unescaped(tmp_path) -> None:
    output = tmp_path / "shadow.json"
    report = ShadowReport(
        summary={"file_count": 1, "record_count": 1},
        files=[
            ShadowFileReport(
                source_file="来源.xlsx",
                source_sha256="a",
                result_json="正式.json",
                result_json_sha256="b",
                parse_report_json="报告.json",
                parse_report_sha256="c",
                records=[
                    ShadowRecord(
                        line_number="1",
                        fields={
                            "颜色": ShadowFieldComparison(
                                field_name="颜色",
                                source_text="white",
                                source_cells=["A1"],
                                python_value="漂白色",
                                python_status="normalized",
                                dictionary_candidates=["漂白色"],
                                matched_rules=["color.white"],
                                comparison_status="exact_match",
                            )
                        },
                    )
                ],
            )
        ],
    )

    write_shadow_report(report, output)

    text = output.read_text(encoding="utf-8")
    assert "漂白色" in text
    assert "\\u6f02" not in text


def test_shadow_writer_refuses_overwrite(tmp_path) -> None:
    output = tmp_path / "shadow.json"
    output.write_text("old", encoding="utf-8")

    with pytest.raises(OutputFileError, match="already exists"):
        write_shadow_report(ShadowReport(summary={}, files=[]), output)


def test_shadow_compare_does_not_modify_official_json(tmp_path, bundle) -> None:
    official = tmp_path / "official.json"
    official.write_text(json.dumps([{"行号": "1", "颜色": "漂白色"}], ensure_ascii=False), encoding="utf-8")
    before = hashlib.sha256(official.read_bytes()).hexdigest()

    compare_shadow_field(bundle, "颜色", ev("white", "漂白色"))

    after = hashlib.sha256(official.read_bytes()).hexdigest()
    assert after == before
