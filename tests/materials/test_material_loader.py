from pathlib import Path

import pytest

from bedding_order_parser.materials.loader import MaterialLoadError, compute_sha256, load_material_csv
from bedding_order_parser.materials.models import EXPECTED_HEADERS


def write_csv(path: Path, rows: list[list[str]], *, headers=EXPECTED_HEADERS) -> None:
    lines = [",".join(headers), *(size_row(row) for row in rows)]
    path.write_text("\ufeff" + "\n".join(lines) + "\n", encoding="utf-8")


def size_row(row: list[str]) -> str:
    return ",".join(row)


def base_row(code: str = "F001") -> list[str]:
    return [
        code,
        "蒋梦杰样品被套",
        "240*260CM",
        "漂白色",
        "贡缎/C80S*C80S/200*100+100/缎纹",
        "",
        "无标",
        "交货尺寸",
        "贡缎 缎纹",
        "80S*80S",
        "T300",
        "C100",
    ]


def test_utf8_bom_csv_read_and_header_contract(tmp_path) -> None:
    source = tmp_path / "material_info.csv"
    write_csv(source, [base_row()])

    rows, audit = load_material_csv(source)

    assert audit.encoding == "utf-8-sig"
    assert audit.delimiter == ","
    assert audit.headers == list(EXPECTED_HEADERS)
    assert audit.row_count == 1
    assert rows[0].source_row == 2
    assert rows[0].material_code == "F001"
    assert rows[0].raw["物料名称"] == "蒋梦杰样品被套"


def test_header_contract_validation_rejects_missing_field(tmp_path) -> None:
    source = tmp_path / "material_info.csv"
    write_csv(source, [base_row()[:-1]], headers=EXPECTED_HEADERS[:-1])

    with pytest.raises(MaterialLoadError, match="headers"):
        load_material_csv(source)


def test_empty_material_code_rejected(tmp_path) -> None:
    source = tmp_path / "material_info.csv"
    write_csv(source, [base_row("")])

    with pytest.raises(MaterialLoadError, match="empty material codes"):
        load_material_csv(source)


def test_duplicate_material_code_rejected(tmp_path) -> None:
    source = tmp_path / "material_info.csv"
    write_csv(source, [base_row("F001"), base_row("F001")])

    with pytest.raises(MaterialLoadError, match="duplicate material codes"):
        load_material_csv(source)


def test_source_csv_sha_does_not_change_during_load(tmp_path) -> None:
    source = tmp_path / "material_info.csv"
    write_csv(source, [base_row()])
    before = compute_sha256(source)

    load_material_csv(source)

    assert compute_sha256(source) == before
