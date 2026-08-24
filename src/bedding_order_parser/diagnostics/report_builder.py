"""Build parse reports from final records and field diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from bedding_order_parser.diagnostics.models import (
    AMBIGUOUS,
    UNRECOGNIZED,
    FieldDiagnostic,
    ParseReport,
    RecordDiagnostic,
)
from bedding_order_parser.models.final_result import FINAL_FIELD_NAMES, FinalResult


def build_parse_report(
    *,
    input_file_name: str,
    input_sha256: str,
    sheet_name: str,
    result_path: Path,
    report_path: Path,
    records: Sequence[FinalResult],
    record_fields: Sequence[Mapping[str, FieldDiagnostic]],
    file_warnings: Sequence[str] = (),
) -> ParseReport:
    if len(records) != len(record_fields):
        raise ValueError("Result and diagnostic record counts do not match.")

    diagnostic_records: list[RecordDiagnostic] = []
    for result, supplied_fields in zip(records, record_fields, strict=True):
        if tuple(supplied_fields) != FINAL_FIELD_NAMES:
            raise ValueError("Diagnostic fields must follow the final 20-field contract.")

        ordered_fields: dict[str, FieldDiagnostic] = {}
        warnings: list[str] = []
        for field_name in FINAL_FIELD_NAMES:
            diagnostic = supplied_fields[field_name]
            if diagnostic.value != result.values[field_name]:
                raise ValueError(f"Diagnostic value does not match result field: {field_name}")
            ordered_fields[field_name] = diagnostic
            if diagnostic.status in {UNRECOGNIZED, AMBIGUOUS}:
                warnings.append(f"{field_name}：{diagnostic.message or '需要人工复核'}")

        diagnostic_records.append(
            RecordDiagnostic(
                line_number=str(result.values["行号"]),
                fields=ordered_fields,
                warnings=tuple(warnings),
            )
        )

    return ParseReport(
        input_file_name=input_file_name,
        input_sha256=input_sha256,
        sheet_name=sheet_name,
        result_json=str(result_path.expanduser().resolve()),
        parse_report_json=str(report_path.expanduser().resolve()),
        records=tuple(diagnostic_records),
        file_warnings=tuple(file_warnings),
    )
