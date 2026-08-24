"""Narrow read-only geometry adapter over the deterministic standard parser."""

from __future__ import annotations

from dataclasses import dataclass

from openpyxl.worksheet.worksheet import Worksheet

from bedding_order_parser.excel.table_parser import (
    _is_numbered_item_row,
    _row_header_score,
    parse_table,
)
from bedding_order_parser.exceptions import WorkbookStructureError
from bedding_order_parser.extraction.item_extractor import extract_raw_items


STANDARD_GEOMETRY_ADAPTER_VERSION = "1.0"


@dataclass(frozen=True)
class StandardSheetGeometry:
    """Only source coordinates and table boundaries proven by standard parsing."""

    stable: bool
    header_rows: tuple[int, ...] = ()
    record_rows: tuple[int, ...] = ()
    parsed_record_count: int = 0
    post_table_start_row: int = 0
    auxiliary_numbered_rows: tuple[int, ...] = ()
    has_explicit_secondary_table: bool = False
    reason_code: str = ""


def derive_standard_sheet_geometry(worksheet: Worksheet) -> StandardSheetGeometry:
    """Return standard-parser geometry without exposing or reusing business values."""

    try:
        table = parse_table(worksheet)
    except WorkbookStructureError:
        return StandardSheetGeometry(stable=False, reason_code="standard_table_unresolved")

    record_rows = tuple(
        dict.fromkeys(item.excel_row_number for item in extract_raw_items(table, worksheet))
    )
    first_data_row = min(
        (row.excel_row_number for row in table.data_rows),
        default=table.header_index + 2,
    )
    header_rows = tuple(range(table.header_index + 1, first_data_row))
    post_table_start_row = len(table.rows) - len(table.post_table_rows) + 1
    auxiliary_rows = tuple(
        post_table_start_row + offset
        for offset, row in enumerate(table.post_table_rows)
        if _is_numbered_item_row(row)
    )
    explicit_secondary = _has_explicit_secondary_table(table.post_table_rows)
    if not record_rows:
        return StandardSheetGeometry(
            stable=False,
            header_rows=header_rows,
            parsed_record_count=len(table.data_rows),
            post_table_start_row=post_table_start_row,
            auxiliary_numbered_rows=auxiliary_rows,
            has_explicit_secondary_table=explicit_secondary,
            reason_code="standard_records_unresolved",
        )
    if explicit_secondary:
        return StandardSheetGeometry(
            stable=False,
            header_rows=header_rows,
            record_rows=record_rows,
            parsed_record_count=len(table.data_rows),
            post_table_start_row=post_table_start_row,
            auxiliary_numbered_rows=auxiliary_rows,
            has_explicit_secondary_table=True,
            reason_code="possible_secondary_order_table",
        )
    return StandardSheetGeometry(
        stable=True,
        header_rows=header_rows,
        record_rows=record_rows,
        parsed_record_count=len(table.data_rows),
        post_table_start_row=post_table_start_row,
        auxiliary_numbered_rows=auxiliary_rows,
        reason_code="standard_geometry_aligned",
    )


def _has_explicit_secondary_table(rows: list[list[str]]) -> bool:
    """Use the standard parser's own predicates to detect another explicit table."""

    for index, row in enumerate(rows):
        if _row_header_score(row) < 3:
            continue
        if any(_is_numbered_item_row(candidate) for candidate in rows[index + 1 :]):
            return True
    return False
