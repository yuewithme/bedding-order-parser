"""Models for dictionary shadow comparison reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


SHADOW_FIELDS = (
    "币种",
    "物料名称",
    "规格",
    "颜色",
    "面料",
    "面料-涤棉成分",
    "款式",
    "尺寸类型",
    "行备注",
    "是否绣花",
)

ShadowStatus = Literal[
    "exact_match",
    "equivalent_match",
    "dictionary_more_specific",
    "partial_match",
    "ambiguous",
    "conflict",
    "dictionary_no_match",
    "source_not_provided",
]

SHADOW_STATUSES: tuple[ShadowStatus, ...] = (
    "exact_match",
    "equivalent_match",
    "dictionary_more_specific",
    "partial_match",
    "ambiguous",
    "conflict",
    "dictionary_no_match",
    "source_not_provided",
)


@dataclass(frozen=True)
class ShadowFieldComparison:
    """One field-level dictionary candidate compared against official Python output."""

    field_name: str
    source_text: str
    source_cells: list[str]
    python_value: str
    python_status: str
    dictionary_candidates: list[str]
    matched_rules: list[str]
    comparison_status: ShadowStatus
    detailed_candidates: list[str] = field(default_factory=list)
    matched_components: list[str] = field(default_factory=list)
    missing_components: list[str] = field(default_factory=list)
    conflicting_components: list[str] = field(default_factory=list)
    reason: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "source_text": self.source_text,
            "source_cells": self.source_cells,
            "python_value": self.python_value,
            "python_status": self.python_status,
            "dictionary_candidates": self.dictionary_candidates,
            "detailed_candidates": self.detailed_candidates,
            "matched_rules": self.matched_rules,
            "comparison_status": self.comparison_status,
            "matched_components": self.matched_components,
            "missing_components": self.missing_components,
            "conflicting_components": self.conflicting_components,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ShadowRecord:
    """All shadow comparisons for one official output record."""

    line_number: str
    fields: dict[str, ShadowFieldComparison]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "line_number": self.line_number,
            "fields": {
                field_name: comparison.to_json_dict()
                for field_name, comparison in self.fields.items()
            },
        }


@dataclass(frozen=True)
class ShadowFileReport:
    """Shadow comparison result for one source PI workbook."""

    source_file: str
    source_sha256: str
    result_json: str
    result_json_sha256: str
    parse_report_json: str
    parse_report_sha256: str
    records: list[ShadowRecord]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "source_sha256": self.source_sha256,
            "result_json": self.result_json,
            "result_json_sha256": self.result_json_sha256,
            "parse_report_json": self.parse_report_json,
            "parse_report_sha256": self.parse_report_sha256,
            "records": [record.to_json_dict() for record in self.records],
        }


@dataclass(frozen=True)
class ShadowReport:
    """Top-level dictionary shadow comparison report."""

    summary: dict[str, Any]
    files: list[ShadowFileReport]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "files": [file_report.to_json_dict() for file_report in self.files],
        }
