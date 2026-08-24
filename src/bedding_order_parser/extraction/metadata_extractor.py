"""Extract order-level metadata and its field diagnostics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from openpyxl.utils import get_column_letter

from bedding_order_parser.diagnostics.models import (
    AMBIGUOUS,
    DEFAULTED,
    NORMALIZED,
    SOURCE_NOT_PROVIDED,
    FieldDiagnostic,
    SourceEvidence,
)
from bedding_order_parser.excel.table_parser import ParsedTable
from bedding_order_parser.extraction.party_extractor import extract_parties
from bedding_order_parser.normalization.field_normalizer import DEFAULT_PACKAGING, normalize_optional_text


@dataclass(frozen=True)
class OrderMetadata:
    customer: str
    currency: str
    salesperson: str
    header_note: str
    planned_ship_date: str
    packaging: str
    field_diagnostics: dict[str, FieldDiagnostic]


def extract_metadata(table: ParsedTable, input_path: Path) -> OrderMetadata:
    del input_path
    parties = extract_parties(table)
    currency = _extract_currency_diagnostic(table)
    planned_ship_date = _extract_planned_ship_date_diagnostic(table)
    header_note = FieldDiagnostic(
        value="",
        status=SOURCE_NOT_PROVIDED,
        source=SourceEvidence(sheet=table.sheet_title, region="header"),
        rule="metadata.header_note",
        message="未发现明确表头备注",
    )
    packaging = FieldDiagnostic(
        value=DEFAULT_PACKAGING,
        status=DEFAULTED,
        source=SourceEvidence(sheet=table.sheet_title, region="default"),
        rule="packaging.default",
        message="源文件未明确包装方式，使用已批准默认包装",
    )
    diagnostics = {
        "客户": parties.customer,
        "币种": currency,
        "业务员": parties.salesperson,
        "表头备注": header_note,
        "计划发货日期": planned_ship_date,
        "包装方式": packaging,
    }
    return OrderMetadata(
        customer=str(parties.customer.value),
        currency=str(currency.value),
        salesperson=str(parties.salesperson.value),
        header_note=str(header_note.value),
        planned_ship_date=str(planned_ship_date.value),
        packaging=str(packaging.value),
        field_diagnostics=diagnostics,
    )


def _extract_currency(
    headers: list[str],
    rows: list[list[str]],
    number_formats: list[list[str]],
) -> str:
    table = ParsedTable(
        sheet_title="",
        rows=rows,
        number_formats=number_formats,
        header_index=0,
        headers=headers,
        data_rows=[],
        pre_header_rows=[],
        post_table_rows=[],
    )
    return str(_extract_currency_diagnostic(table).value)


def _extract_currency_diagnostic(table: ParsedTable) -> FieldDiagnostic:
    explicit: dict[str, list[str]] = {}
    symbols: dict[str, list[str]] = {}
    qualified_formats: dict[str, list[tuple[str, int]]] = {}
    for row_index, row in enumerate(table.rows):
        for column_index, text in enumerate(row):
            if not text:
                continue
            coordinate = _coordinate(row_index, column_index)
            upper = _remove_non_currency_cny_phrases(text.upper())
            for code in CURRENCY_CODE_NAMES:
                if re.search(rf"(?<![A-Z0-9]){re.escape(code)}(?![A-Z0-9])", upper):
                    explicit.setdefault(code, []).append(coordinate)
            if "US$" in upper:
                explicit.setdefault("USD", []).append(coordinate)
            if "CN¥" in upper or "CN￥" in upper:
                explicit.setdefault("CNY", []).append(coordinate)
            if "JP¥" in upper or "JP￥" in upper:
                explicit.setdefault("JPY", []).append(coordinate)
            _collect_currency_symbols(text, coordinate, symbols)

    for row_index, row_formats in enumerate(table.number_formats):
        if row_index >= len(table.rows) or not any(table.rows[row_index]):
            continue
        for column_index, number_format in enumerate(row_formats):
            if number_format:
                _collect_number_format_currency(
                    number_format,
                    _coordinate(row_index, column_index),
                    column_index,
                    qualified_formats,
                    symbols,
                )

    for code, evidence in qualified_formats.items():
        if len({column for _coordinate_value, column in evidence}) <= 3:
            explicit.setdefault(code, []).extend(
                coordinate for coordinate, _column in evidence
            )

    if len(explicit) == 1:
        code = next(iter(explicit))
        return _currency_result(table, code, explicit[code], "currency.explicit")
    if len(explicit) > 1:
        return FieldDiagnostic(
            value="",
            status=AMBIGUOUS,
            source=SourceEvidence(
                sheet=table.sheet_title,
                cells=_flatten_evidence(explicit),
                region="currency",
                label="currency code",
            ),
            rule="currency.conflict",
            message="发现多个结算币种候选，需要人工复核",
        )
    if len(symbols) == 1:
        code = next(iter(symbols))
        return _currency_result(table, code, symbols[code], "currency.symbol")
    if len(symbols) > 1:
        return FieldDiagnostic(
            value="",
            status=AMBIGUOUS,
            source=SourceEvidence(
                sheet=table.sheet_title,
                cells=_flatten_evidence(symbols),
                region="currency",
                label="currency symbol",
            ),
            rule="currency.conflict",
            message="发现多个结算币种符号，需要人工复核",
        )
    return FieldDiagnostic(
        value="",
        status=SOURCE_NOT_PROVIDED,
        source=SourceEvidence(sheet=table.sheet_title, region="currency"),
        rule="currency.explicit",
        message="未发现明确结算币种",
    )


def _currency_result(
    table: ParsedTable,
    code: str,
    cells: list[str],
    rule: str,
) -> FieldDiagnostic:
    return FieldDiagnostic(
        value=CURRENCY_CODE_NAMES[code],
        status=NORMALIZED,
        source=SourceEvidence(
            sheet=table.sheet_title,
            cells=tuple(dict.fromkeys(cells)),
            region="currency",
            label=code,
        ),
        rule=rule,
        message=f"{code}已标准化为{CURRENCY_CODE_NAMES[code]}",
    )


def _remove_non_currency_cny_phrases(text: str) -> str:
    return re.sub(
        r"\bCNY\s+(?:HOLIDAY|HOLIDAYS|PUBLIC\s+HOLIDAY|NEW\s+YEAR)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )


def _collect_currency_symbols(
    text: str,
    coordinate: str,
    candidates: dict[str, list[str]],
) -> None:
    if "$" in text:
        candidates.setdefault("USD", []).append(coordinate)
    if "€" in text:
        candidates.setdefault("EUR", []).append(coordinate)
    if "£" in text:
        candidates.setdefault("GBP", []).append(coordinate)
    if "¥" in text or "￥" in text:
        candidates.setdefault("CNY", []).append(coordinate)
    if "円" in text:
        candidates.setdefault("JPY", []).append(coordinate)


def _collect_number_format_currency(
    number_format: str,
    coordinate: str,
    column_index: int,
    qualified: dict[str, list[tuple[str, int]]],
    symbols: dict[str, list[str]],
) -> None:
    upper = number_format.upper()
    if "US$" in upper:
        qualified.setdefault("USD", []).append((coordinate, column_index))
        return
    if "CN¥" in upper or "CN￥" in upper:
        qualified.setdefault("CNY", []).append((coordinate, column_index))
        return
    if "JP¥" in upper or "JP￥" in upper:
        qualified.setdefault("JPY", []).append((coordinate, column_index))
        return
    _collect_currency_symbols(number_format, coordinate, symbols)


def _extract_planned_ship_date_diagnostic(table: ParsedTable) -> FieldDiagnostic:
    for row_index, row in enumerate(table.rows):
        for column_index, cell in enumerate(row):
            matched = _match_label(cell, SHIPPING_DATE_LABELS)
            if not matched:
                continue
            label, inline_value = matched
            values: list[tuple[str, str]] = []
            if inline_value:
                values.append((inline_value, _coordinate(row_index, column_index)))
            for next_column in range(column_index + 1, min(len(row), column_index + 5)):
                value = normalize_optional_text(row[next_column])
                if value:
                    values.append((value, _coordinate(row_index, next_column)))
            for raw_value, coordinate in values:
                parsed = _parse_date(raw_value)
                if parsed:
                    return FieldDiagnostic(
                        value=parsed,
                        status=NORMALIZED,
                        source=SourceEvidence(
                            sheet=table.sheet_title,
                            cells=tuple(
                                dict.fromkeys(
                                    (
                                        _coordinate(row_index, column_index),
                                        coordinate,
                                    )
                                )
                            ),
                            region="header",
                            label=label,
                        ),
                        rule="shipping_date.iso",
                        message="计划发货日期已标准化为YYYY-MM-DD",
                    )
    return FieldDiagnostic(
        value="",
        status=SOURCE_NOT_PROVIDED,
        source=SourceEvidence(sheet=table.sheet_title, region="header"),
        rule="shipping_date.explicit",
        message="未发现明确计划发货日期",
    )


def _match_label(cell: str, labels: tuple[str, ...]) -> tuple[str, str] | None:
    text = cell.strip()
    if not text:
        return None
    for label in labels:
        label_pattern = r"\s+".join(re.escape(part) for part in label.split())
        match = re.match(
            rf"^{label_pattern}\s*(?:[:：]\s*(.*)|$)",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            return label, (match.group(1) or "").strip()
    return None


def _parse_date(value: str) -> str:
    text = normalize_optional_text(value)
    if not text:
        return ""
    match = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}"
    match = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b", text)
    if match:
        first, second, year = (int(part) for part in match.groups())
        month, day = (first, second) if first <= 12 else (second, first)
        return f"{year:04d}-{month:02d}-{day:02d}"
    return ""


def _coordinate(row_index: int, column_index: int) -> str:
    return f"{get_column_letter(column_index + 1)}{row_index + 1}"


def _flatten_evidence(candidates: dict[str, list[str]]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            coordinate
            for coordinates in candidates.values()
            for coordinate in coordinates
        )
    )


SHIPPING_DATE_LABELS: tuple[str, ...] = (
    "planned shipping date",
    "plan shipping date",
    "shipping date",
    "shipment date",
    "delivery date",
    "requested delivery date",
    "etd",
    "ex-factory date",
    "ex factory date",
    "计划发货日期",
    "交货日期",
)

CURRENCY_CODE_NAMES: dict[str, str] = {
    "USD": "美元",
    "CNY": "人民币",
    "RMB": "人民币",
    "EUR": "欧元",
    "GBP": "英镑",
    "JPY": "日元",
    "AED": "阿联酋迪拉姆",
    "SAR": "沙特里亚尔",
}
