from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

from bedding_order_parser.diagnostics.models import NORMALIZED, SOURCE_NOT_PROVIDED
from bedding_order_parser.excel.table_parser import parse_table
from bedding_order_parser.extraction.metadata_extractor import extract_metadata


def _metadata_from_rows(rows: list[list[object]], tmp_path: Path, file_name: str = "sample.xlsx"):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "PI"
    for row in rows:
        worksheet.append(row)
    table = parse_table(worksheet)
    return extract_metadata(table, tmp_path / file_name)


def _base_table_rows() -> list[list[object]]:
    return [
        ["No.", "Item", "Size W*L", "Specification", "QTY"],
        ["1", "Duvet Cover", "200*240cm", "100% cotton white", "12"],
    ]


def test_customer_extracts_invoice_to_adjacent_cell(tmp_path: Path) -> None:
    metadata = _metadata_from_rows(
        [
            ["Invoice To:", "Blooming Nakanishi & Company"],
            *_base_table_rows(),
        ],
        tmp_path,
    )

    assert metadata.customer == "Blooming Nakanishi & Company"


def test_customer_extracts_standalone_to_label(tmp_path: Path) -> None:
    metadata = _metadata_from_rows(
        [
            ["To :", "OC International Furniture"],
            *_base_table_rows(),
        ],
        tmp_path,
    )

    assert metadata.customer == "OC International Furniture"


def test_customer_ignores_to_inside_regular_sentence(tmp_path: Path) -> None:
    metadata = _metadata_from_rows(
        [
            ["Please ship to the address below", "Wrong Customer"],
            *_base_table_rows(),
        ],
        tmp_path,
    )

    assert metadata.customer == ""


def test_customer_ignores_signature_label_words_after_real_buyer(tmp_path: Path) -> None:
    metadata = _metadata_from_rows(
        [
            ["Buyer: HAI HA HANDICRAFT CO., LTD", "", "", "", "Seller: Canasin"],
            *_base_table_rows(),
            ["SELLER Canasin", "", "", "", "BUYER", "BUYER"],
        ],
        tmp_path,
    )

    assert metadata.customer == "HAI HA HANDICRAFT CO., LTD"


def test_currency_extracts_cny_from_number_format(tmp_path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["Buyer:", "Hotel"])
    worksheet.append(["No.", "Item", "Size", "Specification", "QTY", "Unit Price", "Amount"])
    worksheet.append(["1", "Duvet Cover", "200*240cm", "white", "12", 10, 120])
    worksheet["F3"].number_format = '"￥"#,##0.00'
    worksheet["G3"].number_format = '"￥"#,##0.00'

    table = parse_table(worksheet)
    metadata = extract_metadata(table, tmp_path / "sample.xlsx")

    assert metadata.currency == "人民币"


def test_currency_scans_late_footer_for_usd(tmp_path: Path) -> None:
    metadata = _metadata_from_rows(
        [
            ["Buyer:", "Hotel"],
            *_base_table_rows(),
            [""] * 5,
            [""] * 5,
            [""] * 5,
            [""] * 5,
            [""] * 5,
            [""] * 5,
            [""] * 5,
            [""] * 5,
            [""] * 5,
            [""] * 5,
            ["Payment Currency: USD"],
        ],
        tmp_path,
    )

    assert metadata.currency == "美元"


def test_currency_conflicting_codes_returns_empty(tmp_path: Path) -> None:
    metadata = _metadata_from_rows(
        [
            ["Currency: USD"],
            ["Payment Currency: CNY"],
            *_base_table_rows(),
        ],
        tmp_path,
    )

    assert metadata.currency == ""


def test_currency_ignores_cny_holiday_without_settlement_evidence(tmp_path: Path) -> None:
    metadata = _metadata_from_rows(
        [
            ["Production schedule excludes CNY holiday"],
            *_base_table_rows(),
        ],
        tmp_path,
    )

    assert metadata.currency == ""
    assert metadata.field_diagnostics["币种"].status == SOURCE_NOT_PROVIDED


def test_payment_currency_usd_remains_normalized(tmp_path: Path) -> None:
    metadata = _metadata_from_rows(
        [
            ["Payment Currency: USD"],
            *_base_table_rows(),
        ],
        tmp_path,
    )

    assert metadata.currency == "美元"
    assert metadata.field_diagnostics["币种"].status == NORMALIZED


def test_salesperson_extracts_business_contact_label(tmp_path: Path) -> None:
    metadata = _metadata_from_rows(
        [
            ["Jiangsu Canasin Weaving Co., Ltd."],
            ["Contact Person:", "Ms Sunny"],
            *_base_table_rows(),
        ],
        tmp_path,
    )

    assert metadata.salesperson == "Ms Sunny"


def test_salesperson_extracts_person_from_canasin_block(tmp_path: Path) -> None:
    metadata = _metadata_from_rows(
        [
            ["", "", "Jiangsu Canasin Weaving Co., Ltd."],
            ["", "", "", "", "Ms Sunny"],
            *_base_table_rows(),
        ],
        tmp_path,
    )

    assert metadata.salesperson == "Ms Sunny"


def test_salesperson_does_not_use_customer_contact(tmp_path: Path) -> None:
    metadata = _metadata_from_rows(
        [
            ["Invoice To:", "Buyer Hotel"],
            ["Contact Person:", "Buyer Alice"],
            *_base_table_rows(),
        ],
        tmp_path,
    )

    assert metadata.salesperson == ""


def test_salesperson_prefers_right_side_business_contact_over_customer_contact(tmp_path: Path) -> None:
    metadata = _metadata_from_rows(
        [
            ["Canasin International Textile (Jiangsu) Co., Ltd."],
            ["To : Buyer Hotel", "", "", "Contact Person: Seller Name"],
            ["Contact Person: Buyer Alice"],
            *_base_table_rows(),
        ],
        tmp_path,
    )

    assert metadata.salesperson == "Seller Name"


def test_plain_date_and_filename_do_not_set_planned_ship_date(tmp_path: Path) -> None:
    metadata = _metadata_from_rows(
        [
            ["Date:", datetime(2025, 12, 31)],
            *_base_table_rows(),
        ],
        tmp_path,
        file_name="20251231 sample.xlsx",
    )

    assert metadata.planned_ship_date == ""
    assert metadata.header_note == ""


def test_shipping_date_extracts_iso_date_without_time(tmp_path: Path) -> None:
    metadata = _metadata_from_rows(
        [
            ["Shipping Date:", datetime(2025, 8, 9, 15, 30)],
            *_base_table_rows(),
        ],
        tmp_path,
    )

    assert metadata.planned_ship_date == "2025-08-09"
    assert "00:00:00" not in metadata.planned_ship_date
