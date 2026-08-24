"""Read-only adapter from the deterministic standard parser to AI V2 shadow records."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Sequence

from bedding_order_parser.ai_full_order.orchestration import formal_line_number_from_request
from bedding_order_parser.ai_full_order.preprocessing import (
    EvidenceItem,
    LocalRecord,
    PreprocessedWorkbook,
)
from bedding_order_parser.ai_full_order.resolution import (
    PythonFieldCandidate,
    PythonShadowRecord,
    adapt_python_shadow_records,
)
from bedding_order_parser.excel.table_parser import parse_table
from bedding_order_parser.excel.workbook_reader import compute_sha256, load_pi_workbook
from bedding_order_parser.extraction.item_extractor import BuiltResult, build_final_results_with_diagnostics
from bedding_order_parser.extraction.metadata_extractor import extract_metadata


V2_PYTHON_SHADOW_ADAPTER_VERSION = "2.0"


class PythonShadowAdapterError(ValueError):
    """Raised when standard-parser facts cannot be bound to local V2 identities."""


def build_deterministic_python_shadow(
    input_path: str | Path,
    preprocessed: PreprocessedWorkbook,
    *,
    target_records: Sequence[LocalRecord] | None = None,
    evidence_catalog: Sequence[EvidenceItem] | None = None,
) -> tuple[PythonShadowRecord, ...]:
    """Run standard deterministic extraction in memory and bind only proven candidates."""

    working = preprocessed
    if target_records is not None or evidence_catalog is not None:
        if target_records is None or evidence_catalog is None:
            raise PythonShadowAdapterError(
                "V2 shadow context requires both target records and evidence catalog."
            )
        working = replace(
            preprocessed,
            records=tuple(target_records),
            evidence_catalog=tuple(evidence_catalog),
        )

    loaded = load_pi_workbook(Path(input_path))
    if loaded.sha256 != preprocessed.source_file_sha256:
        loaded.workbook.close()
        raise PythonShadowAdapterError("Python shadow input SHA does not match preprocessing.")
    try:
        built_by_source: dict[tuple[str, int], BuiltResult] = {}
        sheet_id_by_name = {
            sheet.sheet_name: sheet.sheet_id for sheet in preprocessed.sheets if sheet.included
        }
        record_sheet_ids = {record.sheet_id for record in preprocessed.records}
        for worksheet in loaded.workbook.worksheets:
            sheet_id = sheet_id_by_name.get(worksheet.title)
            if sheet_id is None or sheet_id not in record_sheet_ids:
                continue
            table = parse_table(worksheet)
            metadata = extract_metadata(table, loaded.path)
            for built in build_final_results_with_diagnostics(table, metadata, worksheet):
                key = (sheet_id, built.item.excel_row_number)
                if key in built_by_source:
                    raise PythonShadowAdapterError("Duplicate standard-parser source row.")
                built_by_source[key] = built

        request = working.to_request_dict()
        formal_records: list[dict[str, str]] = []
        diagnostics: list[dict[str, object]] = []
        for local_record in working.records:
            line_number = formal_line_number_from_request(
                local_record.to_request_dict(), request["evidence_catalog"]
            )
            built = built_by_source.get((local_record.sheet_id, local_record.source_row))
            if built is None:
                formal_records.append({"行号": line_number})
                diagnostics.append({})
                continue
            if str(built.result.values["行号"]) != line_number:
                raise PythonShadowAdapterError(
                    "Standard-parser line number does not match local evidence."
                )
            formal_records.append(
                {name: str(value) for name, value in built.result.values.items()}
            )
            diagnostics.append(
                {
                    name: diagnostic.to_json_dict()
                    for name, diagnostic in built.field_diagnostics.items()
                }
            )
    finally:
        loaded.workbook.close()

    if compute_sha256(loaded.path) != loaded.sha256:
        raise PythonShadowAdapterError("Python shadow parsing changed the input workbook.")

    adapted = adapt_python_shadow_records(working, formal_records, diagnostics)
    return _discard_unproven_candidates(adapted, working)


def _discard_unproven_candidates(
    records: tuple[PythonShadowRecord, ...],
    preprocessed: PreprocessedWorkbook,
) -> tuple[PythonShadowRecord, ...]:
    local_by_id = {record.record_local_id: record for record in preprocessed.records}
    evidence_by_id = {item.evidence_id: item for item in preprocessed.evidence_catalog}
    sanitized: list[PythonShadowRecord] = []
    for shadow in records:
        local = local_by_id[shadow.record_local_id]
        allowed = set(local.evidence_ids)
        fields: dict[str, PythonFieldCandidate] = {}
        for name, candidate in shadow.fields.items():
            proven = bool(candidate.evidence_ids) and all(
                evidence_id in allowed
                and evidence_id in evidence_by_id
                and evidence_by_id[evidence_id].scope_id == local.scope_id
                for evidence_id in candidate.evidence_ids
            )
            fields[name] = candidate if not candidate.value or proven else PythonFieldCandidate()
        sanitized.append(replace(shadow, fields=fields))
    return tuple(sanitized)
