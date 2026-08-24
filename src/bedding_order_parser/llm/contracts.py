"""Versioned vendor-neutral request and advisory response contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bedding_order_parser.llm.advisory_schema import (
    SCHEMA_VERSION,
    validate_final_advisory,
)


ENHANCEMENT_REASONS = frozenset(
    {
        "user_requested",
        "ambiguous_tie",
        "insufficient_evidence",
        "no_candidate",
        "parse_uncertainty",
        "dictionary_conflict",
    }
)


@dataclass(frozen=True)
class LLMEnhancementRequest:
    """Evidence package for exactly one source record."""

    source_record_id: str
    source_file: str
    sheet_name: str
    source_row: str
    raw_evidence: dict[str, Any]
    parsed_record: dict[str, Any]
    parse_diagnostics: dict[str, Any]
    dictionary_validation: dict[str, Any]
    top_candidates: list[dict[str, Any]]
    enhancement_reason: str
    schema_version: str = SCHEMA_VERSION
    job_id: str = ""

    def __post_init__(self) -> None:
        if not self.source_record_id.strip():
            raise ValueError("source_record_id is required.")
        if self.enhancement_reason not in ENHANCEMENT_REASONS:
            raise ValueError(
                f"Unsupported enhancement_reason: {self.enhancement_reason}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "source_record_id": self.source_record_id,
            "source_file": self.source_file,
            "sheet_name": self.sheet_name,
            "source_row": self.source_row,
            "raw_evidence": self.raw_evidence,
            "parsed_record": self.parsed_record,
            "parse_diagnostics": self.parse_diagnostics,
            "dictionary_validation": self.dictionary_validation,
            "top_candidates": self.top_candidates,
            "enhancement_reason": self.enhancement_reason,
        }


@dataclass(frozen=True)
class SuggestedField:
    field_name: str
    original_value: str
    suggested_value: str
    reason: str
    evidence_references: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "original_value": self.original_value,
            "suggested_value": self.suggested_value,
            "reason": self.reason,
            "evidence_references": list(self.evidence_references),
        }


@dataclass(frozen=True)
class MaterialAssessment:
    status: str
    suggested_material_code: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "status": self.status,
            "suggested_material_code": self.suggested_material_code,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class LLMConnectivityResult:
    """Metadata-only result for one minimal provider connectivity call."""

    provider: str
    model: str
    request_id: str
    status: str
    finish_status: str
    text: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    latency_ms: int = 0
    attempt_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "request_id": self.request_id,
            "status": self.status,
            "finish_status": self.finish_status,
            "text": self.text,
            "usage": self.usage.to_dict(),
            "latency_ms": self.latency_ms,
            "attempt_count": self.attempt_count,
        }


@dataclass(frozen=True)
class LLMEnhancementResponse:
    """Strict sidecar suggestion; it can never confirm or overwrite results."""

    provider: str
    model: str
    request_id: str
    source_record_id: str
    status: str
    finish_status: str
    action: str
    confidence: float
    suggested_fields: tuple[SuggestedField, ...] = ()
    material_assessment: MaterialAssessment = field(
        default_factory=lambda: MaterialAssessment(
            status="insufficient_evidence",
            suggested_material_code="",
            reason="No provider evidence is available.",
        )
    )
    reasoning_summary: str = ""
    warnings: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()
    usage: LLMUsage = field(default_factory=LLMUsage)
    latency_ms: int = 0
    attempt_count: int = 0
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "model": self.model,
            "request_id": self.request_id,
            "source_record_id": self.source_record_id,
            "status": self.status,
            "finish_status": self.finish_status,
            "action": self.action,
            "confidence": self.confidence,
            "suggested_fields": [
                item.to_dict() for item in self.suggested_fields
            ],
            "material_assessment": self.material_assessment.to_dict(),
            "reasoning_summary": self.reasoning_summary,
            "warnings": list(self.warnings),
            "evidence_references": list(self.evidence_references),
            "usage": self.usage.to_dict(),
            "latency_ms": self.latency_ms,
            "attempt_count": self.attempt_count,
            "advisory_only": True,
        }
        validate_final_advisory(payload)
        return payload
