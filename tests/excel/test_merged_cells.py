from openpyxl import Workbook

from bedding_order_parser.excel.merged_cells import (
    build_merged_cell_value_map,
    value_with_merged_fallback,
)


def test_merged_cell_values_are_mapped_to_all_cells() -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet["A1"] = "BUYER:"
    worksheet.merge_cells("A1:B1")

    merged_values = build_merged_cell_value_map(worksheet)

    assert value_with_merged_fallback(worksheet, 1, 2, merged_values) == "BUYER:"
