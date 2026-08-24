"""Locate the PI worksheet inside a workbook."""

from __future__ import annotations

from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet


def _normalize_sheet_name(name: str) -> str:
    return "".join(ch for ch in name.casefold() if ch.isalnum())


def locate_pi_sheet(workbook: Workbook) -> Worksheet:
    sheets = list(workbook.worksheets)
    exact = {sheet.title.casefold(): sheet for sheet in sheets}
    if "pi-update" in exact:
        return exact["pi-update"]
    if "pi" in exact:
        return exact["pi"]

    for sheet in sheets:
        normalized = _normalize_sheet_name(sheet.title)
        if "piupdate" in normalized or normalized == "pi" or "pi" in normalized:
            return sheet

    return sheets[0]
