"""Read-only simulation of dictionary integration decisions."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from bedding_order_parser.dictionaries.shadow_models import (
    SHADOW_FIELDS,
    SHADOW_STATUSES,
)
from bedding_order_parser.exceptions import BeddingOrderParserError, OutputFileError


IntegrationAction = Literal[
    "keep_python",
    "keep_default",
    "propose_fill",
    "propose_replace_default",
    "propose_enrich",
    "manual_review",
    "not_applicable",
]

INTEGRATION_ACTIONS: tuple[IntegrationAction, ...] = (
    "keep_python",
    "keep_default",
    "propose_fill",
    "propose_replace_default",
    "propose_enrich",
    "manual_review",
    "not_applicable",
)

RiskLevel = Literal["low_risk", "medium_risk", "high_risk", "not_ready"]

_SAFE_MATCH_STATUSES = {
    "exact_match",
    "equivalent_match",
    "dictionary_more_specific",
}
_NO_OVERRIDE_STATUSES = {
    "partial_match",
    "dictionary_no_match",
    "source_not_provided",
}
_MANUAL_REVIEW_STATUSES = {"ambiguous", "conflict"}
_EMPTY_PYTHON_STATUSES = {"unrecognized", "source_not_provided"}
_PROPOSED_ACTIONS = {
    "propose_fill",
    "propose_replace_default",
    "propose_enrich",
}


def _nonempty_text(value: Any) -> str:
    return str(value or "").strip()


def _unique_candidates(comparison: Mapping[str, Any]) -> list[str]:
    return list(
        dict.fromkeys(
            candidate
            for raw_candidate in comparison.get("dictionary_candidates", [])
            if (candidate := _nonempty_text(raw_candidate))
        )
    )


def _has_explicit_source_evidence(comparison: Mapping[str, Any]) -> bool:
    source_cells = [
        _nonempty_text(cell) for cell in comparison.get("source_cells", [])
    ]
    return bool(_nonempty_text(comparison.get("source_text"))) and any(source_cells)


def _supports_enrichment(comparison: Mapping[str, Any]) -> bool:
    """Accept source-projected components, never detailed dictionary-row extras."""
    return (
        _has_explicit_source_evidence(comparison)
        and bool(comparison.get("matched_components"))
        and not comparison.get("missing_components")
        and not comparison.get("conflicting_components")
    )


def decide_integration_action(
    comparison: Mapping[str, Any],
) -> tuple[IntegrationAction, str, str]:
    """Return the simulated action, selected candidate, and audit reason."""
    status = _nonempty_text(comparison.get("comparison_status"))
    if status not in SHADOW_STATUSES:
        raise BeddingOrderParserError(f"Unsupported shadow status: {status!r}")

    python_value = _nonempty_text(comparison.get("python_value"))
    python_status = _nonempty_text(comparison.get("python_status"))
    candidates = _unique_candidates(comparison)
    unique_candidate = candidates[0] if len(candidates) == 1 else ""
    has_source = _has_explicit_source_evidence(comparison)
    python_is_empty = not python_value or python_status in _EMPTY_PYTHON_STATUSES

    if status in _MANUAL_REVIEW_STATUSES:
        return (
            "manual_review",
            unique_candidate,
            f"{status} cannot safely change the official Python result.",
        )

    if status in _NO_OVERRIDE_STATUSES:
        if python_status == "defaulted":
            return (
                "keep_default",
                "",
                f"{status} provides no safe basis to replace the Python default.",
            )
        return (
            "keep_python",
            "",
            f"{status} cannot safely override the official Python result.",
        )

    if status not in _SAFE_MATCH_STATUSES:
        raise BeddingOrderParserError(f"Unhandled shadow status: {status!r}")

    if python_status == "defaulted":
        if unique_candidate and has_source:
            return (
                "propose_replace_default",
                unique_candidate,
                "Explicit PI evidence and one source-derived candidate can replace "
                "the Python default.",
            )
        return (
            "keep_default",
            "",
            "The Python default remains because explicit PI evidence or a unique "
            "candidate is missing.",
        )

    if python_is_empty:
        if unique_candidate and has_source:
            return (
                "propose_fill",
                unique_candidate,
                "The official value is empty or unrecognized, and explicit PI "
                "evidence yields one candidate.",
            )
        return (
            "keep_python",
            "",
            "The empty or unrecognized official value has no safe source-backed "
            "unique candidate.",
        )

    if status in {"exact_match", "equivalent_match"}:
        return (
            "keep_python",
            unique_candidate,
            "The dictionary validates a nonempty official Python value.",
        )

    if unique_candidate and _supports_enrichment(comparison):
        return (
            "propose_enrich",
            unique_candidate,
            "The unique source-projected candidate adds explicitly evidenced "
            "components without changing confirmed components.",
        )

    return (
        "keep_python",
        "",
        "Dictionary-only detail or incomplete source evidence cannot enrich the "
        "official Python value.",
    )


def _empty_counter(keys: tuple[str, ...]) -> dict[str, int]:
    return {key: 0 for key in keys}


def _risk_level(
    field_name: str,
    *,
    status_counts: Mapping[str, int],
) -> tuple[RiskLevel, str]:
    total = sum(status_counts.values())
    verified = (
        status_counts["exact_match"] + status_counts["equivalent_match"]
    )
    verified_ratio = verified / total if total else 0.0
    manual = status_counts["ambiguous"] + status_counts["conflict"]
    partial = status_counts["partial_match"]
    no_match = status_counts["dictionary_no_match"]
    source_missing = status_counts["source_not_provided"]

    if verified_ratio < 0.60 or (
        source_missing >= 25 and verified < 20
    ):
        return (
            "not_ready",
            f"Only {verified}/{total} observations are dictionary-verified; "
            f"partial={partial}, no_match={no_match}, "
            f"source_not_provided={source_missing}.",
        )

    if verified_ratio < 0.80 or no_match >= 10:
        if field_name == "币种" and manual == 0:
            return (
                "medium_risk",
                f"Verified {verified}/{total}; {no_match} no-match and "
                f"{source_missing} source-missing cases require Python fallback.",
            )
        return (
            "high_risk",
            f"Verified {verified}/{total}; manual_review={manual}, "
            f"no_match={no_match}, source_not_provided={source_missing}.",
        )

    if (
        verified_ratio >= 0.90
        and manual == 0
        and partial == 0
        and no_match <= 3
        and source_missing == 0
    ):
        return (
            "low_risk",
            f"Verified {verified}/{total} with no ambiguity, partial match, or "
            "missing source evidence.",
        )

    return (
        "medium_risk",
        f"Verified {verified}/{total}; manual_review={manual}, partial={partial}, "
        f"no_match={no_match}, source_not_provided={source_missing}.",
    )


def _validate_shadow_report(
    shadow_report: Mapping[str, Any],
) -> tuple[list[Mapping[str, Any]], int]:
    files = shadow_report.get("files")
    if not isinstance(files, list) or not files:
        raise BeddingOrderParserError("Shadow report must contain a nonempty files list.")

    records: list[Mapping[str, Any]] = []
    seen_files: set[str] = set()
    for file_report in files:
        if not isinstance(file_report, Mapping):
            raise BeddingOrderParserError("Shadow file entries must be JSON objects.")
        source_file = _nonempty_text(file_report.get("source_file"))
        if not source_file or source_file in seen_files:
            raise BeddingOrderParserError(
                f"Missing or duplicate shadow source file: {source_file!r}"
            )
        seen_files.add(source_file)

        file_records = file_report.get("records")
        if not isinstance(file_records, list):
            raise BeddingOrderParserError(
                f"Shadow file has no records list: {source_file}"
            )
        for record in file_records:
            if not isinstance(record, Mapping):
                raise BeddingOrderParserError(
                    f"Shadow record must be an object: {source_file}"
                )
            fields = record.get("fields")
            if not isinstance(fields, Mapping):
                raise BeddingOrderParserError(
                    f"Shadow record has no fields object: {source_file}"
                )
            actual_fields = tuple(fields.keys())
            if set(actual_fields) != set(SHADOW_FIELDS):
                missing = sorted(set(SHADOW_FIELDS) - set(actual_fields))
                extra = sorted(set(actual_fields) - set(SHADOW_FIELDS))
                raise BeddingOrderParserError(
                    f"Shadow field contract mismatch in {source_file} line "
                    f"{record.get('line_number')}: missing={missing}, extra={extra}"
                )
            records.append(
                {
                    "source_file": source_file,
                    "source_sha256": file_report.get("source_sha256", ""),
                    "result_json": file_report.get("result_json", ""),
                    "result_json_sha256": file_report.get(
                        "result_json_sha256", ""
                    ),
                    "parse_report_json": file_report.get(
                        "parse_report_json", ""
                    ),
                    "parse_report_sha256": file_report.get(
                        "parse_report_sha256", ""
                    ),
                    "line_number": _nonempty_text(record.get("line_number")),
                    "fields": fields,
                }
            )

    summary = shadow_report.get("summary", {})
    expected_files = summary.get("file_count")
    expected_records = summary.get("record_count")
    expected_fields = summary.get("field_count")
    evaluated = len(records) * len(SHADOW_FIELDS)
    if expected_files is not None and expected_files != len(files):
        raise BeddingOrderParserError("Shadow file count does not match its summary.")
    if expected_records is not None and expected_records != len(records):
        raise BeddingOrderParserError("Shadow record count does not match its summary.")
    if expected_fields is not None and expected_fields != evaluated:
        raise BeddingOrderParserError("Shadow field count does not match its summary.")
    return records, len(files)


def _decision_entry(
    *,
    record: Mapping[str, Any],
    field_name: str,
    comparison: Mapping[str, Any],
    action: IntegrationAction,
    selected_candidate: str,
    reason: str,
    risk_level: RiskLevel,
) -> dict[str, Any]:
    return {
        "source_file": record["source_file"],
        "line_number": record["line_number"],
        "field": field_name,
        "python_value": comparison.get("python_value", ""),
        "python_status": comparison.get("python_status", ""),
        "dictionary_candidate": selected_candidate,
        "dictionary_candidates": _unique_candidates(comparison),
        "shadow_status": comparison.get("comparison_status", ""),
        "proposed_action": action,
        "source_cells": comparison.get("source_cells", []),
        "source_text": comparison.get("source_text", ""),
        "reason": reason,
        "risk_level": risk_level,
    }


def build_integration_preview(
    shadow_report: Mapping[str, Any],
    *,
    shadow_report_sha256: str = "",
) -> dict[str, Any]:
    """Evaluate every shadow-covered field without changing official outputs."""
    records, file_count = _validate_shadow_report(shadow_report)
    field_status_counts = {
        field_name: Counter({status: 0 for status in SHADOW_STATUSES})
        for field_name in SHADOW_FIELDS
    }
    decisions: list[
        tuple[
            Mapping[str, Any],
            str,
            Mapping[str, Any],
            IntegrationAction,
            str,
            str,
        ]
    ] = []

    for record in records:
        fields = record["fields"]
        for field_name in SHADOW_FIELDS:
            comparison = fields[field_name]
            status = _nonempty_text(comparison.get("comparison_status"))
            if status not in SHADOW_STATUSES:
                raise BeddingOrderParserError(
                    f"Unsupported status in {record['source_file']} line "
                    f"{record['line_number']} field {field_name}: {status!r}"
                )
            field_status_counts[field_name][status] += 1
            action, candidate, reason = decide_integration_action(comparison)
            decisions.append(
                (
                    record,
                    field_name,
                    comparison,
                    action,
                    candidate,
                    reason,
                )
            )

    field_risks: dict[str, RiskLevel] = {}
    risk_reasons: dict[str, str] = {}
    for field_name in SHADOW_FIELDS:
        risk, reason = _risk_level(
            field_name,
            status_counts=field_status_counts[field_name],
        )
        field_risks[field_name] = risk
        risk_reasons[field_name] = reason

    action_counts = Counter({action: 0 for action in INTEGRATION_ACTIONS})
    field_action_counts = {
        field_name: Counter({action: 0 for action in INTEGRATION_ACTIONS})
        for field_name in SHADOW_FIELDS
    }
    proposed_changes: list[dict[str, Any]] = []
    manual_reviews: list[dict[str, Any]] = []

    for record, field_name, comparison, action, candidate, reason in decisions:
        action_counts[action] += 1
        field_action_counts[field_name][action] += 1
        if action in _PROPOSED_ACTIONS or action == "manual_review":
            entry = _decision_entry(
                record=record,
                field_name=field_name,
                comparison=comparison,
                action=action,
                selected_candidate=candidate,
                reason=reason,
                risk_level=field_risks[field_name],
            )
            if action in _PROPOSED_ACTIONS:
                proposed_changes.append(entry)
            else:
                manual_reviews.append(entry)

    field_assessments: dict[str, dict[str, Any]] = {}
    for field_name in SHADOW_FIELDS:
        statuses = dict(field_status_counts[field_name])
        verified = statuses["exact_match"] + statuses["equivalent_match"]
        unique_candidates = sum(
            len(_unique_candidates(comparison)) == 1
            for _, decision_field, comparison, _, _, _ in decisions
            if decision_field == field_name
        )
        explicit_source = sum(
            _has_explicit_source_evidence(comparison)
            for _, decision_field, comparison, _, _, _ in decisions
            if decision_field == field_name
        )
        total = sum(statuses.values())
        field_assessments[field_name] = {
            "observation_count": total,
            "status_counts": statuses,
            "action_counts": dict(field_action_counts[field_name]),
            "verified_count": verified,
            "verified_rate": round(verified / total, 6) if total else 0.0,
            "unique_candidate_count": unique_candidates,
            "explicit_source_evidence_count": explicit_source,
            "risk_level": field_risks[field_name],
            "risk_reason": risk_reasons[field_name],
        }

    provenance = [
        {
            "source_file": file_report.get("source_file", ""),
            "source_sha256": file_report.get("source_sha256", ""),
            "result_json": file_report.get("result_json", ""),
            "result_json_sha256": file_report.get("result_json_sha256", ""),
            "parse_report_json": file_report.get("parse_report_json", ""),
            "parse_report_sha256": file_report.get(
                "parse_report_sha256", ""
            ),
        }
        for file_report in shadow_report["files"]
    ]
    evaluated_count = len(decisions)
    proposed_count = sum(action_counts[action] for action in _PROPOSED_ACTIONS)

    return {
        "summary": {
            "file_count": file_count,
            "record_count": len(records),
            "evaluated_field_count": evaluated_count,
            "action_counts": dict(action_counts),
            "field_risk_levels": field_risks,
            "proposed_change_count": proposed_count,
            "manual_review_count": action_counts["manual_review"],
            "shadow_report_sha256": shadow_report_sha256,
        },
        "proposed_changes": proposed_changes,
        "manual_reviews": manual_reviews,
        "field_assessments": field_assessments,
        "provenance": provenance,
    }


def load_and_build_integration_preview(shadow_report_path: Path) -> dict[str, Any]:
    """Load one existing shadow report and build a read-only impact preview."""
    resolved = shadow_report_path.expanduser().resolve()
    try:
        raw = resolved.read_bytes()
        shadow_report = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BeddingOrderParserError(
            f"Failed to read dictionary shadow report: {resolved}"
        ) from exc
    if not isinstance(shadow_report, Mapping):
        raise BeddingOrderParserError("Dictionary shadow report must be a JSON object.")
    return build_integration_preview(
        shadow_report,
        shadow_report_sha256=hashlib.sha256(raw).hexdigest(),
    )


def write_integration_preview(
    preview: Mapping[str, Any],
    output_path: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write the local preview atomically without touching official results."""
    resolved = output_path.expanduser().resolve()
    if resolved.exists() and not overwrite:
        raise OutputFileError(f"Output file already exists: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)

    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=resolved.parent,
            delete=False,
            suffix=".tmp",
        ) as temp_file:
            temp_name = temp_file.name
            json.dump(preview, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
        os.replace(temp_name, resolved)
    except Exception as exc:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
        raise OutputFileError(
            f"Failed to write dictionary integration preview: {resolved}"
        ) from exc
    return resolved
