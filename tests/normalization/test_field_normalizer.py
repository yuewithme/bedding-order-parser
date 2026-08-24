from bedding_order_parser.normalization.field_normalizer import (
    normalize_component,
    normalize_fabric,
    normalize_size,
    normalize_size_type,
    normalize_yes_no_embroidery,
)


def test_component_normalization_rules() -> None:
    assert normalize_component("100% cotton") == "100C"
    assert normalize_component("100% coton") == "100C"
    assert normalize_component("80/20 cotton/poly") == "C80/T20"
    assert normalize_component("50/50 cotton/poly") == "C50/T50"


def test_size_normalization_swaps_width_and_length_and_adds_flap() -> None:
    assert normalize_size("205x273cm", "with Flap: 50cm") == "273*205+50cm"
    assert (
        normalize_size("340*260", "one side on opening 15cm flap, 20cm hand holds")
        == "260*340+15cm"
    )


def test_size_normalization_converts_mm_to_cm() -> None:
    assert normalize_size("2800*2600 mm", "") == "260*280cm"


def test_size_normalization_keeps_needed_decimal_after_mm_conversion() -> None:
    assert normalize_size("2585*2550mm", "") == "255*258.5cm"


def test_size_normalization_does_not_reconvert_cm_or_guess_abnormal_specs() -> None:
    assert normalize_size("205x273cm", "with Flap: 50cm") == "273*205+50cm"
    assert normalize_size("26W x 245L cm", "") == "245*26cm"


def test_size_normalization_uses_width_length_labels_in_either_order() -> None:
    assert normalize_size("245L x 26W cm", "") == "245*26cm"


def test_size_normalization_converts_extra_flap_units() -> None:
    assert normalize_size("2800*2600mm", "flap 200mm") == "260*280+20cm"


def test_size_type_normalization() -> None:
    assert normalize_size_type("Delivery size") == "交货尺寸"
    assert normalize_size_type("afterwash") == "洗涤尺寸"
    assert normalize_size_type("") == "洗涤尺寸"


def test_embroidery_normalization() -> None:
    assert normalize_yes_no_embroidery("with white embroidery") == "Y"
    assert normalize_yes_no_embroidery("plain white") == "N"


def test_annupuri_fabric_typo_and_thread_count_are_normalized() -> None:
    text = "100% coton, 400 thread count, sateen fabric"

    assert normalize_fabric(text) == "贡缎/T400/100C"


def test_style_normalization_recognizes_bag_hand_holes_without_flange() -> None:
    from bedding_order_parser.normalization.field_normalizer import normalize_style

    assert normalize_style("Bag with Hand Holes, no flange") == "无飞边口袋无系带迎宾式"


def test_extra_size_does_not_come_from_location_counts_near_inner_flap() -> None:
    from bedding_order_parser.normalization.field_normalizer import normalize_row_note

    text = "IC Chip(1 location) Entrance side without inner flap, Bag model, 2 hands holes (20cm)"

    assert normalize_size("180*270cm", text) == "270*180cm"
    assert "重叠片1" not in normalize_row_note(text)


def test_size_type_prefers_delivery_size_even_when_remarks_are_combined() -> None:
    text = "300TC cotton after washed size in description Remarks: Delivery Size YELLOW MARK"

    assert normalize_size_type(text) == "交货尺寸"


def test_style_normalization_handles_gate2c_cover_styles() -> None:
    from bedding_order_parser.normalization.field_normalizer import normalize_style

    assert (
        normalize_style("bottom opening, one side on opening 15cm flap, no flange, 20cm hand holes")
        == "无飞边平口信封迎宾式"
    )
    assert normalize_style("Bag style with 5cm flange") == "被尾单飞边双层口叠边口袋无系带式"
    assert (
        normalize_style("Bag style with internal fold and hand holes")
        == "被尾单飞边双层口叠边口袋无系带迎宾式"
    )
    assert normalize_style("Open bag, 3 sides flange, hand holes") == "三飞边双层口叠边口袋无系带迎宾式"
    assert normalize_style("Bag with Hand Holes, no flange") == "无飞边口袋无系带迎宾式"
    assert normalize_style("Envelope style with 50cm flap") == "无飞边平口信封式"
