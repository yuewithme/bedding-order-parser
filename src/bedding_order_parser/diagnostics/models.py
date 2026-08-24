"""Models for field-level parsing diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


EXTRACTED = "extracted"
NORMALIZED = "normalized"
DERIVED = "derived"
DEFAULTED = "defaulted"
SOURCE_NOT_PROVIDED = "source_not_provided"
UNRECOGNIZED = "unrecognized"
AMBIGUOUS = "ambiguous"
NOT_IMPLEMENTED = "not_implemented"

FIELD_STATUSES: tuple[str, ...] = (
    EXTRACTED,
    NORMALIZED,
    DERIVED,
    DEFAULTED,
    SOURCE_NOT_PROVIDED,
    UNRECOGNIZED,
    AMBIGUOUS,
    NOT_IMPLEMENTED,
)

STATUS_DEFINITIONS: dict[str, str] = {
    EXTRACTED: "从源Excel找到明确值，仅做无害清理。",
    NORMALIZED: "源Excel有明确证据，按业务规则标准化后输出。",
    DERIVED: "由其他已确定字段生成。",
    DEFAULTED: "源文件未明确提供，使用已批准的固定业务默认值。",
    SOURCE_NOT_PROVIDED: "已检查相关区域，源Excel未提供足够信息。",
    UNRECOGNIZED: "源Excel存在相关内容，但当前规则无法稳定转换。",
    AMBIGUOUS: "存在冲突或不完整候选，无法安全确定唯一值。",
    NOT_IMPLEMENTED: "该字段属于后续阶段，本阶段尚未实现。",
}


@dataclass(frozen=True)
class SourceEvidence:
    sheet: str = ""
    cells: tuple[str, ...] = ()
    region: str = ""
    label: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "sheet": self.sheet,
            "cells": list(self.cells),
            "region": self.region,
            "label": self.label,
        }


@dataclass(frozen=True)
class FieldDiagnostic:
    value: str | float
    status: str
    source: SourceEvidence = field(default_factory=SourceEvidence)
    rule: str = ""
    message: str = ""

    def __post_init__(self) -> None:
        if self.status not in FIELD_STATUSES:
            raise ValueError(f"Unsupported field diagnostic status: {self.status}")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "status": self.status,
            "source": self.source.to_json_dict(),
            "rule": self.rule,
            "message": self.message,
        }


@dataclass(frozen=True)
class RecordDiagnostic:
    line_number: str
    fields: dict[str, FieldDiagnostic]
    warnings: tuple[str, ...] = ()

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "行号": self.line_number,
            "fields": {name: diagnostic.to_json_dict() for name, diagnostic in self.fields.items()},
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ParseReport:
    input_file_name: str
    input_sha256: str
    sheet_name: str
    result_json: str
    parse_report_json: str
    records: tuple[RecordDiagnostic, ...] = ()
    file_warnings: tuple[str, ...] = ()
    report_version: str = "1.0"

    @property
    def warning_count(self) -> int:
        return len(self.file_warnings) + sum(len(record.warnings) for record in self.records)

    def field_status_counts(self) -> dict[str, int]:
        counts = {status: 0 for status in FIELD_STATUSES}
        for record in self.records:
            for diagnostic in record.fields.values():
                counts[diagnostic.status] += 1
        return counts

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "report_version": self.report_version,
            "input": {
                "file_name": self.input_file_name,
                "sha256": self.input_sha256,
                "sheet_name": self.sheet_name,
            },
            "outputs": {
                "result_json": self.result_json,
                "parse_report_json": self.parse_report_json,
            },
            "status_definitions": dict(STATUS_DEFINITIONS),
            "summary": {
                "record_count": len(self.records),
                "warning_count": self.warning_count,
                "field_status_counts": self.field_status_counts(),
            },
            "records": [record.to_json_dict() for record in self.records],
            "file_warnings": list(self.file_warnings),
        }
