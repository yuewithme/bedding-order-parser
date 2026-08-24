from bedding_order_parser.materials.document_builder import attach_embedding_text
from bedding_order_parser.materials.models import RawMaterialRow
from bedding_order_parser.materials.normalizer import normalize_material, normalize_spec


def raw_row(**overrides: str) -> RawMaterialRow:
    raw = {
        "物料名称": "蒋梦杰样品被套",
        "规格": "240*260CM",
        "颜色": "漂白色",
        "面料": "贡缎/C80S*C80S/200*100+100/缎纹",
        "款式": "",
        "加标方式": "无标",
        "尺寸类型": "交货尺寸",
        "面料-品类": "贡缎 缎纹",
        "面料-纱支": "80S*80S",
        "面料-密度": "T300",
        "面料-涤棉成分": "C100",
    }
    raw.update(overrides)
    return RawMaterialRow(source_row=2, material_code="F001", raw=raw)


def test_one_csv_row_becomes_one_material_object_and_raw_is_preserved() -> None:
    record = normalize_material(raw_row())

    assert record.source_row == 2
    assert record.material_code == "F001"
    assert record.raw["物料名称"] == "蒋梦杰样品被套"
    assert record.raw["规格"] == "240*260CM"
    assert record.normalized["product_category"] == "被套"
    assert record.normalized["spec"] == "240*260cm"


def test_customer_or_person_prefix_does_not_enter_product_category() -> None:
    record = normalize_material(raw_row(**{"物料名称": "Bridgeway Company Limited 样品被套"}))

    assert record.normalized["product_category"] == "被套"


def test_deterministic_spec_normalization() -> None:
    assert normalize_spec("240 × 260 CM") == "240*260cm"
    assert normalize_spec("2400mm x 2600mm + 50mm") == "240*260cm+5cm"
    assert normalize_spec('94.49"x102.36"') == "240*260cm"


def test_standardized_fields_do_not_overwrite_raw_fields() -> None:
    record = normalize_material(raw_row(**{"颜色": "plain white", "面料-涤棉成分": "100%C"}))

    assert record.raw["颜色"] == "plain white"
    assert record.normalized["color"] == "漂白色"
    assert record.raw["面料-涤棉成分"] == "100%C"
    assert record.normalized["composition"] == "C100"


def test_embedding_text_skips_empty_fields_and_material_code() -> None:
    record = attach_embedding_text(normalize_material(raw_row(**{"款式": ""})))

    assert "款式:" not in record.embedding_text
    assert "F001" not in record.embedding_text
    assert "source_row" not in record.embedding_text
    assert record.embedding_text.startswith("品类:被套；规格:240*260cm；颜色:漂白色")
