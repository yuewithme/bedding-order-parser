"""Pipeline for PI-to-final-JSON parsing with field diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bedding_order_parser.diagnostics.report_builder import build_parse_report
from bedding_order_parser.dictionaries.product_validation import (
    DEFAULT_RULES_PATH,
    DEFAULT_STYLES_PATH,
    build_failed_product_validation_report,
    build_product_validation_report,
    default_validation_path,
    write_product_validation_report,
)
from bedding_order_parser.excel.sheet_locator import locate_pi_sheet
from bedding_order_parser.excel.table_parser import parse_table
from bedding_order_parser.excel.workbook_reader import compute_sha256, load_pi_workbook
from bedding_order_parser.exceptions import InputFileError
from bedding_order_parser.extraction.item_extractor import build_final_results_with_diagnostics
from bedding_order_parser.extraction.metadata_extractor import extract_metadata
from bedding_order_parser.serialization.diagnostic_writer import (
    default_report_path,
    write_parse_outputs,
)


@dataclass(frozen=True)
class ParseSummary:
    record_count: int
    input_file_name: str
    input_path: Path
    output_path: Path
    report_path: Path
    warning_count: int
    input_sha256_before: str
    input_sha256_after: str
    validation_report_path: Path | None = None
    validation_status: str = ""


def parse_order(
    input_path: Path,
    output_path: Path,
    *,
    report_path: Path | None = None,
    overwrite: bool = False,
    dictionary_validate: bool = False,
    dictionary_rules_path: Path | None = None,
    dictionary_styles_path: Path | None = None,
    validation_path: Path | None = None,
) -> ParseSummary:
    report_path = report_path or default_report_path(output_path)
    loaded = load_pi_workbook(input_path)
    try:
        worksheet = locate_pi_sheet(loaded.workbook)
        table = parse_table(worksheet)
        metadata = extract_metadata(table, loaded.path)
        built_records = build_final_results_with_diagnostics(table, metadata, worksheet)
        records = [built.result for built in built_records]
        record_fields = [built.field_diagnostics for built in built_records]
        report = build_parse_report(
            input_file_name=loaded.path.name,
            input_sha256=loaded.sha256,
            sheet_name=table.sheet_title,
            result_path=output_path,
            report_path=report_path,
            records=records,
            record_fields=record_fields,
        )
    finally:
        loaded.workbook.close()

    after_hash = compute_sha256(loaded.path)
    if after_hash != loaded.sha256:
        raise InputFileError("Input file SHA-256 changed during parsing; aborting.")

    written_result, written_report = write_parse_outputs(
        records,
        report,
        output_path,
        report_path,
        overwrite=overwrite,
    )
    written_validation: Path | None = None
    validation_status = ""
    if dictionary_validate:
        validation_target = validation_path or default_validation_path(written_result)
        try:
            validation_report = build_product_validation_report(
                input_path=loaded.path,
                records=records,
                parse_report=report,
                rules_path=dictionary_rules_path or DEFAULT_RULES_PATH,
                styles_path=dictionary_styles_path or DEFAULT_STYLES_PATH,
            )
        except Exception as exc:
            # Validation is a sidecar executed after official outputs succeed.
            validation_report = build_failed_product_validation_report(
                input_path=loaded.path,
                parse_report=report,
                attempted_record_count=len(records),
                reason=str(exc),
            )
        validation_status = str(validation_report["status"])
        written_validation = write_product_validation_report(
            validation_report,
            validation_target,
            overwrite=overwrite,
        )

    return ParseSummary(
        record_count=len(records),
        input_file_name=loaded.path.name,
        input_path=loaded.path,
        output_path=written_result,
        report_path=written_report,
        warning_count=report.warning_count,
        input_sha256_before=loaded.sha256,
        input_sha256_after=after_hash,
        validation_report_path=written_validation,
        validation_status=validation_status,
    )
