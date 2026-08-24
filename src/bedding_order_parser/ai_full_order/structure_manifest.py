"""Versioned, bounded structure context for controlled layout decisions."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from openpyxl.utils.cell import coordinate_to_tuple, range_boundaries

from bedding_order_parser.ai_full_order.contracts import build_source_record_id
from bedding_order_parser.ai_full_order.preprocessing import (
    PREPROCESSOR_VERSION,
    LocalStructureCandidate,
    PreprocessedWorkbook,
    layout_candidate_id,
)


STRUCTURE_MANIFEST_VERSION = "2.0"
STRUCTURE_CONTEXT_VERSION = "2.0"
LAYOUT_CONTRACT_VERSION = "2.0"
LAYOUT_PROMPT_VERSION = "2.0"
MAX_STRUCTURE_EXCERPTS = 32
MAX_STRUCTURE_EXCERPT_CHARS = 80
MAX_STRUCTURE_EXCERPT_ROWS = 8
MAX_STRUCTURE_EXCERPTS_PER_ROW = 4
MAX_STRUCTURE_ROW_PATTERNS = 48
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SENSITIVE_STRUCTURE_LABELS = (
    "bank",
    "account",
    "iban",
    "swift",
    "payment",
    "银行",
    "账号",
    "付款",
)


class StructureManifestAdapterError(ValueError):
    """Local structure facts cannot be represented by the layout contract."""


def build_structure_manifest(
    preprocessed: PreprocessedWorkbook,
    chunks: Sequence[Any],
) -> dict[str, Any]:
    """Build known and unresolved sheet context without exposing system identities."""

    if not _SHA256.fullmatch(preprocessed.source_file_sha256):
        raise StructureManifestAdapterError("Invalid local source identity.")
    if not preprocessed.sheet_states:
        raise StructureManifestAdapterError("Per-sheet structure state is missing.")

    sheets = {sheet.sheet_id: sheet for sheet in preprocessed.sheets}
    states = {state.sheet_id: state for state in preprocessed.sheet_states}
    if set(states) != set(sheets) or len(states) != len(preprocessed.sheet_states):
        raise StructureManifestAdapterError("Per-sheet structure identity is invalid.")
    blocks = {block.block_id: block for block in preprocessed.blocks}
    records = {record.record_local_id: record for record in preprocessed.records}
    evidence = {item.evidence_id: item for item in preprocessed.evidence_catalog}
    candidates = {item.candidate_id: item for item in preprocessed.layout_candidates}
    if len(candidates) != len(preprocessed.layout_candidates):
        raise StructureManifestAdapterError("Local layout candidate identity is duplicated.")

    validated_chunks: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        payload = chunk.to_dict()
        block_id = str(payload.get("block_id", ""))
        validated_chunks[block_id] = _validate_chunk(
            payload,
            preprocessed=preprocessed,
            blocks=blocks,
            records=records,
            evidence=evidence,
        )

    known_chunks: list[dict[str, Any]] = []
    unresolved_sheets: list[dict[str, Any]] = []
    known_sheet_ids: set[str] = set()
    for state in preprocessed.sheet_states:
        sheet = sheets[state.sheet_id]
        if not sheet.included or state.local_status == "ignored_by_local_contract":
            continue
        if state.local_status == "confirmed_order":
            if not state.known_block_ids:
                raise StructureManifestAdapterError("Confirmed sheet has no known block.")
            for block_id in state.known_block_ids:
                chunk = validated_chunks.get(block_id)
                block = blocks.get(block_id)
                if chunk is None or block is None or block.sheet_id != state.sheet_id:
                    raise StructureManifestAdapterError("Known chunk ownership is invalid.")
                known_chunks.append(chunk)
                known_sheet_ids.add(state.sheet_id)
            continue
        if not state.resolution_required:
            raise StructureManifestAdapterError("Included sheet state is not actionable.")
        unresolved_sheets.append(
            _unresolved_sheet_context(
                preprocessed,
                sheet_id=state.sheet_id,
                candidates=candidates,
                blocks=blocks,
                records=records,
            )
        )

    if not known_chunks and not unresolved_sheets:
        raise StructureManifestAdapterError("No included sheet can form structure context.")
    unresolved_ids = {item["sheet_id"] for item in unresolved_sheets}
    if known_sheet_ids & unresolved_ids:
        raise StructureManifestAdapterError("A sheet cannot be both known and unresolved.")

    provider_payload = {
        "structure_context_version": STRUCTURE_CONTEXT_VERSION,
        "layout_contract_version": LAYOUT_CONTRACT_VERSION,
        "known_chunks": sorted(known_chunks, key=lambda item: item["order"]),
        "unresolved_sheets": unresolved_sheets,
    }
    context_sha256 = hashlib.sha256(
        _canonical(
            {
                "source_file_sha256": preprocessed.source_file_sha256,
                "preprocessor_version": PREPROCESSOR_VERSION,
                **provider_payload,
            }
        ).encode("utf-8")
    ).hexdigest()
    manifest = {
        "manifest_version": STRUCTURE_MANIFEST_VERSION,
        "source_file_sha256": preprocessed.source_file_sha256,
        "context_sha256": context_sha256,
        **provider_payload,
    }
    validate_structure_manifest(manifest)
    return manifest


def validate_structure_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "manifest_version",
        "source_file_sha256",
        "context_sha256",
        "structure_context_version",
        "layout_contract_version",
        "known_chunks",
        "unresolved_sheets",
    }
    if set(manifest) != expected:
        raise StructureManifestAdapterError("Structure manifest fields are invalid.")
    if manifest.get("manifest_version") != STRUCTURE_MANIFEST_VERSION:
        raise StructureManifestAdapterError("Structure manifest version is invalid.")
    if manifest.get("structure_context_version") != STRUCTURE_CONTEXT_VERSION:
        raise StructureManifestAdapterError("Structure context version is invalid.")
    if manifest.get("layout_contract_version") != LAYOUT_CONTRACT_VERSION:
        raise StructureManifestAdapterError("Layout contract version is invalid.")
    if not _SHA256.fullmatch(str(manifest.get("source_file_sha256", ""))):
        raise StructureManifestAdapterError("Structure source identity is invalid.")
    if not _SHA256.fullmatch(str(manifest.get("context_sha256", ""))):
        raise StructureManifestAdapterError("Structure context identity is invalid.")
    known = manifest.get("known_chunks")
    unresolved = manifest.get("unresolved_sheets")
    if not isinstance(known, list) or not isinstance(unresolved, list):
        raise StructureManifestAdapterError("Structure context collections are invalid.")
    known_ids = [str(item.get("sheet_id", "")) for item in known if isinstance(item, Mapping)]
    unresolved_ids = [
        str(item.get("sheet_id", "")) for item in unresolved if isinstance(item, Mapping)
    ]
    if (
        len(known_ids) != len(known)
        or len(unresolved_ids) != len(unresolved)
        or len(unresolved_ids) != len(set(unresolved_ids))
        or set(known_ids) & set(unresolved_ids)
    ):
        raise StructureManifestAdapterError("Structure sheet identities are invalid.")
    expected_context_sha256 = hashlib.sha256(
        _canonical(
            {
                "source_file_sha256": manifest["source_file_sha256"],
                "preprocessor_version": PREPROCESSOR_VERSION,
                "structure_context_version": manifest["structure_context_version"],
                "layout_contract_version": manifest["layout_contract_version"],
                "known_chunks": known,
                "unresolved_sheets": unresolved,
            }
        ).encode("utf-8")
    ).hexdigest()
    if manifest["context_sha256"] != expected_context_sha256:
        raise StructureManifestAdapterError("Structure context hash mismatch.")
    return dict(manifest)


def provider_structure_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_structure_manifest(manifest)
    return {
        "structure_context_version": validated["structure_context_version"],
        "layout_contract_version": validated["layout_contract_version"],
        "known_chunks": validated["known_chunks"],
        "unresolved_sheets": validated["unresolved_sheets"],
    }


def _validate_chunk(
    payload: Mapping[str, Any],
    *,
    preprocessed: PreprocessedWorkbook,
    blocks: Mapping[str, Any],
    records: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    chunk_id = str(payload.get("chunk_id", ""))
    scope_id = str(payload.get("scope", ""))
    block_id = str(payload.get("block_id", ""))
    if not chunk_id or not scope_id or not block_id:
        raise StructureManifestAdapterError("Invalid local chunk identity.")
    if payload.get("source_file_sha256") != preprocessed.source_file_sha256:
        raise StructureManifestAdapterError("Chunk source identity mismatch.")
    block = blocks.get(block_id)
    if block is None or block.scope_id != scope_id:
        raise StructureManifestAdapterError("Chunk block identity mismatch.")
    local_ids = tuple(block.record_local_ids)
    if not local_ids or any(record_id not in records for record_id in local_ids):
        raise StructureManifestAdapterError("Chunk record identity is unknown.")
    for record_id in local_ids:
        record = records[record_id]
        expected_identity = build_source_record_id(
            source_file_sha256=preprocessed.source_file_sha256,
            sheet_id=record.sheet_id,
            scope_id=record.scope_id,
            source_row=record.source_row,
            evidence_ids=record.evidence_ids,
        )
        if record.source_record_id != expected_identity:
            raise StructureManifestAdapterError("Chunk record identity mismatch.")
        if record.sheet_id != block.sheet_id or record.scope_id != block.scope_id:
            raise StructureManifestAdapterError("Chunk record ownership mismatch.")
    evidence_ids = tuple(
        dict.fromkeys(
            [
                *block.header_evidence_ids,
                *(
                    evidence_id
                    for record_id in local_ids
                    for evidence_id in records[record_id].evidence_ids
                ),
            ]
        )
    )
    if any(
        evidence_id not in evidence or evidence[evidence_id].scope_id != scope_id
        for evidence_id in evidence_ids
    ):
        raise StructureManifestAdapterError("Chunk evidence identity mismatch.")
    return {
        "sheet_id": block.sheet_id,
        "chunk_id": chunk_id,
        "block_id": block_id,
        "scope_id": scope_id,
        "evidence_range": block.cell_range,
        "record_count": len(local_ids),
        "order": int(payload.get("order", 0)),
        "status": str(payload.get("status", "")),
    }


def _unresolved_sheet_context(
    preprocessed: PreprocessedWorkbook,
    *,
    sheet_id: str,
    candidates: Mapping[str, LocalStructureCandidate],
    blocks: Mapping[str, Any],
    records: Mapping[str, Any],
) -> dict[str, Any]:
    sheet = next(item for item in preprocessed.sheets if item.sheet_id == sheet_id)
    state = next(item for item in preprocessed.sheet_states if item.sheet_id == sheet_id)
    options: list[dict[str, Any]] = []
    for candidate_id in state.candidate_ids:
        candidate = candidates.get(candidate_id)
        if candidate is None or candidate.sheet_id != sheet_id:
            raise StructureManifestAdapterError("Layout candidate ownership is invalid.")
        _validate_candidate(preprocessed, candidate, blocks=blocks, records=records)
        options.append(
            {
                "candidate_id": candidate.candidate_id,
                "role": candidate.role,
                "cell_ranges": list(candidate.cell_ranges),
                "block_count": len(candidate.block_ids),
                "record_count": len(candidate.record_local_ids),
            }
        )
    row_patterns = _row_patterns(sheet.cells)
    excerpts = _bounded_excerpts(sheet.cells)
    min_col, min_row, max_col, max_row = range_boundaries(sheet.used_range)
    return {
        "sheet_id": sheet_id,
        "used_range": sheet.used_range,
        "local_status": state.local_status,
        "standard_geometry_status": state.standard_geometry_status,
        "heuristic_status": state.heuristic_status,
        "structural_summary": {
            "row_count": max_row - min_row + 1,
            "column_count": max_col - min_col + 1,
            "nonempty_cell_count": len(
                [cell for cell in sheet.cells if not cell.merged_anchor]
            ),
            "merged_anchor_count": len(
                {cell.merged_anchor for cell in sheet.cells if cell.merged_anchor}
            ),
            "candidate_count": len(options),
        },
        "candidate_options": options,
        "row_patterns": row_patterns,
        "excerpts": excerpts,
    }


def _validate_candidate(
    preprocessed: PreprocessedWorkbook,
    candidate: LocalStructureCandidate,
    *,
    blocks: Mapping[str, Any],
    records: Mapping[str, Any],
) -> None:
    expected_id = layout_candidate_id(
        source_file_sha256=preprocessed.source_file_sha256,
        sheet_id=candidate.sheet_id,
        role=candidate.role,
        block_ids=candidate.block_ids,
        record_local_ids=candidate.record_local_ids,
        cell_ranges=candidate.cell_ranges,
    )
    if candidate.candidate_id != expected_id:
        raise StructureManifestAdapterError("Local layout candidate identity mismatch.")
    if candidate.role == "auxiliary":
        if candidate.block_ids or candidate.record_local_ids:
            raise StructureManifestAdapterError("Auxiliary candidate contains order identities.")
        return
    if candidate.role != "order" or not candidate.block_ids or not candidate.record_local_ids:
        raise StructureManifestAdapterError("Order candidate shape is invalid.")
    candidate_blocks = [blocks.get(block_id) for block_id in candidate.block_ids]
    if any(block is None or block.sheet_id != candidate.sheet_id for block in candidate_blocks):
        raise StructureManifestAdapterError("Order candidate block ownership is invalid.")
    expected_records = tuple(
        record_id for block in candidate_blocks for record_id in block.record_local_ids
    )
    if expected_records != candidate.record_local_ids or any(
        record_id not in records or records[record_id].sheet_id != candidate.sheet_id
        for record_id in candidate.record_local_ids
    ):
        raise StructureManifestAdapterError("Order candidate record ownership is invalid.")


def _row_patterns(cells: Sequence[Any]) -> list[dict[str, int | str]]:
    rows: dict[int, list[Any]] = defaultdict(list)
    for cell in cells:
        if not cell.merged_anchor:
            row, _column = coordinate_to_tuple(cell.reference)
            rows[row].append(cell)
    patterns: list[dict[str, int | str]] = []
    for row in sorted(rows)[:MAX_STRUCTURE_ROW_PATTERNS]:
        values = [str(cell.display_text or "").strip() for cell in rows[row]]
        patterns.append(
            {
                "row_id": f"row:{row}",
                "nonempty_count": len([value for value in values if value]),
                "numeric_count": len(
                    [value for value in values if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value)]
                ),
                "text_count": len(
                    [value for value in values if value and not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value)]
                ),
            }
        )
    return patterns


def _bounded_excerpts(cells: Sequence[Any]) -> list[dict[str, str]]:
    rows: dict[int, list[Any]] = defaultdict(list)
    for cell in cells:
        if cell.merged_anchor:
            continue
        row, _column = coordinate_to_tuple(cell.reference)
        rows[row].append(cell)
    selected_rows: list[int] = []
    for row in sorted(rows):
        values = [str(cell.display_text or "").strip() for cell in rows[row]]
        combined = " ".join(values).casefold()
        if any(label in combined for label in _SENSITIVE_STRUCTURE_LABELS):
            continue
        selected_rows.append(row)
        if len(selected_rows) >= MAX_STRUCTURE_EXCERPT_ROWS:
            break
    excerpts: list[dict[str, str]] = []
    for row in selected_rows:
        for cell in sorted(rows[row], key=lambda item: coordinate_to_tuple(item.reference)[1])[
            :MAX_STRUCTURE_EXCERPTS_PER_ROW
        ]:
            text = str(cell.display_text or "").strip()
            if not text:
                continue
            bounded = text[:MAX_STRUCTURE_EXCERPT_CHARS]
            digest = hashlib.sha256(
                f"{cell.sheet_id}\n{cell.reference}\n{bounded}".encode("utf-8")
            ).hexdigest()[:16]
            excerpts.append(
                {
                    "excerpt_id": f"layout-excerpt:{digest}",
                    "cell_range": cell.reference,
                    "text": bounded,
                }
            )
            if len(excerpts) >= MAX_STRUCTURE_EXCERPTS:
                return excerpts
    return excerpts


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
