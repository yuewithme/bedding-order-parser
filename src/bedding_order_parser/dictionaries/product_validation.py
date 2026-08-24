"""Validation-only core-field reporting for parsed duvet-cover orders."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from bedding_order_parser.diagnostics.models import ParseReport
from bedding_order_parser.dictionaries.loader import load_dictionary_bundle
from bedding_order_parser.dictionaries.models import DictionaryBundle
from bedding_order_parser.dictionaries.shadow_matcher import (
    _evidence_for_field,
    compare_shadow_field,
)
from bedding_order_parser.dictionaries.shadow_models import ShadowFieldComparison
from bedding_order_parser.extraction.metadata_extractor import CURRENCY_CODE_NAMES
from bedding_order_parser.excel.workbook_reader import compute_sha256, load_pi_workbook
from bedding_order_parser.exceptions import BeddingOrderParserError, InputFileError
from bedding_order_parser.models.final_result import FinalResult
from bedding_order_parser.serialization.diagnostic_writer import (
    _reserve_temporary_path,
    _write_temporary_json,
)


VALIDATION_VERSION = "1.0"
VALIDATION_MODE = "validation_only"
VALIDATION_FIELDS = ("物料名称", "币种", "规格", "颜色")
VALIDATION_STATUSES = (
    "exact_match",
    "equivalent_match",
    "partial_match",
    "ambiguous",
    "dictionary_no_match",
    "source_not_provided",
    "conflict",
)
VALIDATION_ACTIONS = ("keep_python", "manual_review")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RULES_PATH = PROJECT_ROOT / "data" / "reference" / "PI单提取规则.xlsx"
DEFAULT_STYLES_PATH = PROJECT_ROOT / "data" / "reference" / "款式表_structured.xlsx"


class ProductValidationError(BeddingOrderParserError):
    """Raised when a core-field validation report cannot be built."""


def default_validation_path(result_path: str | Path) -> Path:
    path = Path(result_path)
    return path.with_name(f"{path.stem}_dictionary_validation.json")


def build_product_validation_report(
    *,
    input_path: Path,
    records: Sequence[FinalResult],
    parse_report: ParseReport,
    rules_path: Path = DEFAULT_RULES_PATH,
    styles_path: Path = DEFAULT_STYLES_PATH,
) -> dict[str, Any]:
    """Build independent core-field checks from source cells and approved rules."""
    bundle = load_dictionary_bundle(rules_path, styles_path)
    loaded = load_pi_workbook(input_path)
    try:
        report_records = [record.to_json_dict() for record in parse_report.records]
        official_records = [record.to_json_dict() for record in records]
        if len(report_records) != len(official_records):
            raise ProductValidationError(
                "Official result and parse report record counts do not match."
            )

        validations = [
            _validate_record(
                bundle=bundle,
                workbook=loaded.workbook,
                source_file=loaded.path.name,
                parse_record=parse_record,
                official_record=official_record,
            )
            for parse_record, official_record in zip(
                report_records,
                official_records,
                strict=True,
            )
        ]
    finally:
        loaded.workbook.close()

    after_hash = compute_sha256(loaded.path)
    if after_hash != loaded.sha256:
        raise InputFileError(
            "Input file SHA-256 changed during dictionary validation; "
            "official outputs remain unchanged."
        )

    return {
        "validation_version": VALIDATION_VERSION,
        "mode": VALIDATION_MODE,
        "status": "completed",
        "input": {
            "file_name": loaded.path.name,
            "sheet_name": parse_report.sheet_name,
        },
        "dictionary": {
            "sources": [source.to_json_dict() for source in bundle.sources],
        },
        "summary": {
            "record_count": len(validations),
            "field_count": len(validations) * len(VALIDATION_FIELDS),
            "fields": _field_summary(validations),
        },
        "records": validations,
        "failure_reason": "",
    }


def build_failed_product_validation_report(
    *,
    input_path: Path,
    parse_report: ParseReport,
    attempted_record_count: int,
    reason: str,
) -> dict[str, Any]:
    """Represent a validation-side failure without changing official outputs."""
    return {
        "validation_version": VALIDATION_VERSION,
        "mode": VALIDATION_MODE,
        "status": "failed",
        "input": {
            "file_name": Path(input_path).name,
            "sheet_name": parse_report.sheet_name,
        },
        "dictionary": {"sources": []},
        "summary": {
            "record_count": 0,
            "attempted_record_count": attempted_record_count,
            "field_count": 0,
            "fields": {
                field: _empty_field_counts()
                for field in VALIDATION_FIELDS
            },
            **{status: 0 for status in VALIDATION_STATUSES},
        },
        "records": [],
        "failure_reason": str(reason),
    }


def write_product_validation_report(
    report: Mapping[str, Any],
    output_path: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Atomically write one UTF-8 validation report beside official outputs."""
    resolved = output_path.expanduser().resolve()
    if resolved.exists() and not overwrite:
        raise ProductValidationError(
            f"Dictionary validation report already exists: {resolved}"
        )
    resolved.parent.mkdir(parents=True, exist_ok=True)

    temporary = _write_temporary_json(resolved, report)
    backup: Path | None = None
    installed = False
    try:
        if overwrite and resolved.exists():
            backup = _reserve_temporary_path(resolved, ".bak")
            os.replace(resolved, backup)
        os.replace(temporary, resolved)
        installed = True
    except Exception as exc:
        if installed:
            resolved.unlink(missing_ok=True)
        if backup and backup.exists():
            os.replace(backup, resolved)
        temporary.unlink(missing_ok=True)
        raise ProductValidationError(
            f"Failed to write dictionary validation report: {resolved}"
        ) from exc

    if backup:
        backup.unlink(missing_ok=True)
    return resolved


def _validate_record(
    *,
    bundle: DictionaryBundle,
    workbook,
    source_file: str,
    parse_record: dict[str, Any],
    official_record: dict[str, Any],
) -> dict[str, Any]:
    fields = parse_record.get("fields", {})
    sheet_name = ""
    validations: dict[str, Any] = {}
    for field_name in VALIDATION_FIELDS:
        diagnostic = fields.get(field_name, {})
        source = diagnostic.get("source", {}) if isinstance(diagnostic, dict) else {}
        sheet_name = sheet_name or str(source.get("sheet") or workbook.sheetnames[0])
        validations[field_name] = _validate_field(
            bundle=bundle,
            workbook=workbook,
            parse_record=parse_record,
            official_record=official_record,
            field_name=field_name,
        )
    return {
        "行号": str(official_record.get("行号", "")),
        "source_file": source_file,
        "sheet": sheet_name,
        "fields": validations,
    }


def _validate_field(
    *,
    bundle: DictionaryBundle,
    workbook,
    parse_record: dict[str, Any],
    official_record: dict[str, Any],
    field_name: str,
) -> dict[str, Any]:
    evidence = _evidence_for_field(
        workbook,
        parse_record,
        official_record,
        field_name,
    )
    comparison_evidence = _comparison_evidence(field_name, evidence)
    comparison = compare_shadow_field(bundle, field_name, comparison_evidence)
    comparison = _apply_validation_overrides(field_name, comparison, evidence)
    status = comparison.comparison_status
    if status not in VALIDATION_STATUSES:
        raise ProductValidationError(
            f"Unsupported {field_name} validation status: {status}"
        )
    action = _action_for_status(status)

    candidates = list(dict.fromkeys(comparison.dictionary_candidates))
    result = {
        "source_cells": evidence.source_cells,
        "source_text": evidence.source_text,
        "python_value": comparison.python_value,
        "dictionary_candidates": candidates,
        "validation_status": status,
        "action": action,
        "reason": comparison.reason,
    }
    if field_name == "物料名称":
        unsupported_candidates = [
            candidate for candidate in candidates if candidate != "被套"
        ]
        if unsupported_candidates:
            raise ProductValidationError(
                "Product validation is restricted to the 被套 category."
            )
        result["detected_category"] = candidates[0] if len(candidates) == 1 else ""
    return result


def _comparison_evidence(field_name: str, evidence):
    if field_name == "物料名称":
        return replace(
            evidence,
            source_text=re.sub(
                r"\bdubet(\s*cover)\b",
                r"duvet\1",
                evidence.source_text,
                flags=re.IGNORECASE,
            ),
        )
    if field_name == "颜色":
        return replace(
            evidence,
            source_text=_remove_craft_color_evidence(evidence.source_text),
        )
    return evidence


def _apply_validation_overrides(
    field_name: str,
    comparison: ShadowFieldComparison,
    original_evidence,
) -> ShadowFieldComparison:
    if field_name == "币种" and comparison.comparison_status == "dictionary_no_match":
        candidates = _approved_currency_candidates(original_evidence.source_text)
        if candidates:
            comparison = _currency_comparison_from_candidates(
                field_name,
                original_evidence,
                candidates,
            )
    if field_name == "颜色":
        candidates = _specific_color_candidates(original_evidence.source_text)
        if candidates:
            comparison = _color_comparison_from_candidates(
                field_name,
                original_evidence,
                candidates,
            )
    if (
        field_name == "币种"
        and comparison.comparison_status == "exact_match"
        and comparison.python_value
        and comparison.python_value.casefold() not in original_evidence.source_text.casefold()
    ):
        return replace(
            comparison,
            comparison_status="equivalent_match",
            reason="Source currency code or symbol is equivalent to the official Chinese currency.",
        )
    return comparison

def _currency_comparison_from_candidates(
    field_name: str,
    evidence,
    candidates: list[str],
) -> ShadowFieldComparison:
    unique_candidates = list(dict.fromkeys(candidate for candidate in candidates if candidate))
    python_value = str(evidence.python_value)
    if len(unique_candidates) == 1:
        candidate = unique_candidates[0]
        status = "exact_match" if candidate == python_value else "conflict"
        if candidate and candidate != python_value and _same_text(candidate, python_value):
            status = "equivalent_match"
        return ShadowFieldComparison(
            field_name=field_name,
            source_text=evidence.source_text,
            source_cells=evidence.source_cells,
            python_value=python_value,
            python_status=evidence.python_status,
            dictionary_candidates=unique_candidates,
            matched_rules=["currency.approved_metadata_rules"],
            comparison_status=status,
            matched_components=[field_name] if status != "conflict" else [],
            conflicting_components=[field_name] if status == "conflict" else [],
            reason=(
                "Approved project currency code maps to official output."
                if status != "conflict"
                else "Approved project currency code conflicts with official output."
            ),
        )
    status = "equivalent_match" if python_value in unique_candidates else "conflict"
    return ShadowFieldComparison(
        field_name=field_name,
        source_text=evidence.source_text,
        source_cells=evidence.source_cells,
        python_value=python_value,
        python_status=evidence.python_status,
        dictionary_candidates=unique_candidates,
        matched_rules=["currency.approved_metadata_rules"],
        comparison_status=status,
        matched_components=[field_name] if status != "conflict" else [],
        conflicting_components=[field_name] if status == "conflict" else [],
        reason=(
            "Official output is compatible with one approved currency candidate."
            if status != "conflict"
            else "Multiple approved source currencies do not include the official output."
        ),
    )


def _approved_currency_candidates(text: str) -> list[str]:
    normalized = text.casefold()
    candidates = []
    for code, standard in CURRENCY_CODE_NAMES.items():
        if re.search(rf"\b{re.escape(code.casefold())}\b", normalized):
            candidates.append(standard)
    return list(dict.fromkeys(candidates))


def _specific_color_candidates(text: str) -> list[str]:
    normalized = text.casefold()
    candidates = []
    if re.search(r"\blight\s+gr[ae]y\b|浅灰", normalized):
        candidates.append("浅灰色")
    if re.search(r"\bdark\s+gr[ae]y\b|深灰", normalized):
        candidates.append("深灰色")
    return list(dict.fromkeys(candidates))


def _color_comparison_from_candidates(
    field_name: str,
    evidence,
    candidates: list[str],
) -> ShadowFieldComparison:
    unique_candidates = list(dict.fromkeys(candidate for candidate in candidates if candidate))
    python_value = str(evidence.python_value)
    if len(unique_candidates) > 1:
        status = "ambiguous"
    else:
        candidate = unique_candidates[0]
        status = "equivalent_match" if _same_text(candidate, python_value) else "conflict"
    return ShadowFieldComparison(
        field_name=field_name,
        source_text=evidence.source_text,
        source_cells=evidence.source_cells,
        python_value=python_value,
        python_status=evidence.python_status,
        dictionary_candidates=unique_candidates,
        matched_rules=["color.specific_shade_validation"],
        comparison_status=status,
        matched_components=[field_name] if status == "equivalent_match" else [],
        conflicting_components=[field_name] if status == "conflict" else [],
        reason=(
            "Source color shade is equivalent to the official color."
            if status == "equivalent_match"
            else "Specific source color shade conflicts with official output."
        ),
    )

def _remove_craft_color_evidence(text: str) -> str:
    color_words = (
        r"blue|green|red|yellow|black|white|grey|gray|beige|"
        r"蓝色?|绿色?|红色?|黄色?|黑色?|白色?|灰色?|米色?"
    )
    craft_terms = (
        r"id(?:entification)?\s*(?:thread|line)s?|"
        r"(?:thread|line|stitch(?:ing)?|label)\s*(?:color|colour)?|"
        r"color\s*(?:line|lines|coding)|colored\s*stitching|"
        r"色线|识别线|标签色|线色"
    )
    patterns = [
        rf"(?:size\s+)?colored\s+stitching[^|;]*?(?:{color_words})",
        rf"(?:size\s+)?color\s+coding[^|;]*?(?:{color_words})",
        rf"\b(?:{color_words})\s+(?:{craft_terms})\b",
        rf"\b(?:{craft_terms})\s*[:=\-]?\s*(?:{color_words})\b",
        rf"(?:{color_words})\s*(?:色线|识别线|标签色|线色)",
        rf"(?:色线|识别线|标签色|线色)\s*[:：]?\s*(?:{color_words})",
    ]
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, " craft_color ", cleaned, flags=re.IGNORECASE)
    return cleaned

def _same_text(left: str, right: str) -> bool:
    return " ".join(left.casefold().split()) == " ".join(right.casefold().split())


def _action_for_status(status: str) -> str:
    action = "manual_review" if status in {"ambiguous", "conflict"} else "keep_python"
    if action not in VALIDATION_ACTIONS:
        raise ProductValidationError(f"Unsupported validation action: {action}")
    return action


def _field_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    summary = {field: _empty_field_counts() for field in VALIDATION_FIELDS}
    for record in records:
        fields = record.get("fields", {})
        for field_name in VALIDATION_FIELDS:
            validation = fields.get(field_name, {})
            status = str(validation.get("validation_status", ""))
            action = str(validation.get("action", ""))
            if status in VALIDATION_STATUSES:
                summary[field_name][status] += 1
            if action in VALIDATION_ACTIONS:
                summary[field_name][action] += 1
    return summary


def _empty_field_counts() -> dict[str, int]:
    return {
        **{status: 0 for status in VALIDATION_STATUSES},
        **{action: 0 for action in VALIDATION_ACTIONS},
    }