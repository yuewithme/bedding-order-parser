"""Python shadow adaptation and field-level decisions for whole-order AI."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from bedding_order_parser.ai_full_order.contracts import (
    AI_BUSINESS_FIELD_NAMES,
    FullOrderContractError,
    normalize_evidence_text,
    validate_full_order_output,
)
from bedding_order_parser.ai_full_order.preprocessing import PreprocessedWorkbook
from bedding_order_parser.diagnostics.models import EXTRACTED, NORMALIZED


HIGH_RISK_FIELDS = frozenset({"客户", "币种", "业务员", "数量", "计划发货日期"})
FREE_TEXT_FIELDS = frozenset({"表头备注", "行备注"})
DIRECT_STATUSES = frozenset({EXTRACTED, NORMALIZED, "extracted", "normalized"})


class ResolutionReason(StrEnum):
    AI_PYTHON_AGREE = "ai_python_agree"
    AI_FILLS_PYTHON_BLANK = "ai_fills_python_blank"
    PYTHON_RETAINED_AI_OMITTED = "python_retained_ai_omitted"
    DIRECT_EVIDENCE_SELECTED_AI = "direct_evidence_selected_ai"
    DIRECT_EVIDENCE_SELECTED_PYTHON = "direct_evidence_selected_python"
    UNRESOLVED_DIRECT_EVIDENCE_CONFLICT = "unresolved_direct_evidence_conflict"
    NO_DIRECT_EVIDENCE_CONFLICT = "no_direct_evidence_conflict"
    BOTH_MISSING = "both_missing"
    AI_REJECTED_BUSINESS_CONSTRAINT = "ai_rejected_business_constraint"
    AI_CONTRACT_FAILURE = "ai_contract_failure"


class FieldResolutionError(ValueError):
    """Raised when Python shadow and AI output cannot be merged safely."""


@dataclass(frozen=True)
class PythonFieldCandidate:
    value: str = ""
    evidence_ids: tuple[str, ...] = ()
    status: str = "source_not_provided"
    source: str = "python"

    @property
    def has_value(self) -> bool:
        return bool(self.value)

    @property
    def has_direct_evidence(self) -> bool:
        return bool(self.value and self.evidence_ids and self.status in DIRECT_STATUSES)


@dataclass(frozen=True)
class PythonShadowRecord:
    record_local_id: str
    source_record_id: str
    scope_id: str
    line_number: str
    fields: dict[str, PythonFieldCandidate]


@dataclass(frozen=True)
class FieldDecision:
    field_name: str
    value: str
    selected_source: str
    reason_code: ResolutionReason
    ai_value: str = ""
    python_value: str = ""
    evidence_ids: tuple[str, ...] = ()
    blocking: bool = False
    message: str = ""


@dataclass(frozen=True)
class ResolvedRecord:
    record_local_id: str
    source_record_id: str
    scope_id: str
    line_number: str
    decisions: dict[str, FieldDecision]

    def business_fields(self) -> dict[str, str]:
        return {
            "行号": self.line_number,
            **{name: self.decisions[name].value for name in AI_BUSINESS_FIELD_NAMES},
        }


def adapt_python_shadow_records(
    preprocessed: PreprocessedWorkbook,
    formal_records: Sequence[Mapping[str, Any]],
    diagnostics: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[PythonShadowRecord, ...]:
    if len(formal_records) != len(preprocessed.records):
        raise FieldResolutionError("Python shadow record count does not match preprocessing.")
    if diagnostics is not None and len(diagnostics) != len(formal_records):
        raise FieldResolutionError("Python shadow diagnostics count does not match records.")

    evidence_by_scope_cell = {
        (item.scope_id, item.cell_range): item.evidence_id
        for item in preprocessed.evidence_catalog
    }
    shadow: list[PythonShadowRecord] = []
    for index, (local_record, formal) in enumerate(
        zip(preprocessed.records, formal_records, strict=True)
    ):
        line_number = str(formal.get("行号", ""))
        fields: dict[str, PythonFieldCandidate] = {}
        diagnostic_fields = diagnostics[index] if diagnostics is not None else {}
        for field_name in AI_BUSINESS_FIELD_NAMES:
            diagnostic = diagnostic_fields.get(field_name, {})
            status = str(diagnostic.get("status", "source_not_provided"))
            evidence_ids = _evidence_ids_from_diagnostic(
                local_record.scope_id,
                diagnostic,
                evidence_by_scope_cell,
            )
            fields[field_name] = PythonFieldCandidate(
                value=str(formal.get(field_name, "")),
                evidence_ids=evidence_ids,
                status=status,
            )
        shadow.append(
            PythonShadowRecord(
                record_local_id=local_record.record_local_id,
                source_record_id=local_record.source_record_id,
                scope_id=local_record.scope_id,
                line_number=line_number,
                fields=fields,
            )
        )
    return tuple(shadow)


def resolve_records(
    ai_output: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    python_shadow: Sequence[PythonShadowRecord],
) -> tuple[ResolvedRecord, ...]:
    try:
        validate_full_order_output(dict(ai_output), request=request)
    except FullOrderContractError as exc:
        raise FieldResolutionError(str(exc)) from exc

    request_records = {record["record_local_id"]: record for record in request["records"]}
    shadow_by_id = {record.record_local_id: record for record in python_shadow}
    if set(shadow_by_id) != set(request_records):
        raise FieldResolutionError("Python shadow identities do not match AI request.")

    resolved: list[ResolvedRecord] = []
    for output_record in ai_output["records"]:
        record_id = output_record["record_local_id"]
        requested = request_records[record_id]
        shadow = shadow_by_id[record_id]
        if shadow.source_record_id != requested["source_record_id"]:
            raise FieldResolutionError("Python shadow source_record_id mismatch.")
        if shadow.scope_id != requested["scope_id"]:
            raise FieldResolutionError("Python shadow scope mismatch.")

        decisions: dict[str, FieldDecision] = {}
        for field_name in AI_BUSINESS_FIELD_NAMES:
            decisions[field_name] = resolve_field(
                field_name,
                output_record["fields"][field_name],
                shadow.fields[field_name],
            )
        resolved.append(
            ResolvedRecord(
                record_local_id=record_id,
                source_record_id=shadow.source_record_id,
                scope_id=shadow.scope_id,
                line_number=shadow.line_number,
                decisions=decisions,
            )
        )
    return tuple(resolved)


def resolve_field(
    field_name: str,
    ai_field: Mapping[str, Any],
    python_field: PythonFieldCandidate,
) -> FieldDecision:
    ai_value = str(ai_field["value"])
    python_value = python_field.value
    ai_evidence = tuple(str(item) for item in ai_field["evidence_references"])
    ai_status = str(ai_field["extraction_status"])
    ai_has_value = bool(ai_value)
    ai_direct = ai_has_value and bool(ai_evidence) and ai_status in {"extracted", "normalized"}
    py_has_value = bool(python_value)
    py_direct = python_field.has_direct_evidence

    constraint_error = _ai_business_constraint_error(field_name, ai_value, ai_status)
    if constraint_error:
        if py_has_value:
            return FieldDecision(
                field_name,
                python_value,
                "python",
                ResolutionReason.AI_REJECTED_BUSINESS_CONSTRAINT,
                ai_value=ai_value,
                python_value=python_value,
                evidence_ids=python_field.evidence_ids,
                message=constraint_error,
            )
        return FieldDecision(
            field_name,
            "",
            "none",
            ResolutionReason.AI_REJECTED_BUSINESS_CONSTRAINT,
            ai_value=ai_value,
            python_value=python_value,
            blocking=field_name in HIGH_RISK_FIELDS,
            message=constraint_error,
        )

    if ai_status in {"ambiguous", "invalid"}:
        if py_has_value:
            return FieldDecision(
                field_name,
                python_value,
                "python",
                ResolutionReason.AI_CONTRACT_FAILURE,
                ai_value=ai_value,
                python_value=python_value,
                evidence_ids=python_field.evidence_ids,
            )
        return FieldDecision(
            field_name,
            "",
            "none",
            ResolutionReason.AI_CONTRACT_FAILURE,
            ai_value=ai_value,
            python_value=python_value,
            blocking=field_name in HIGH_RISK_FIELDS,
        )

    if ai_has_value and py_has_value and _same_value(ai_value, python_value):
        return FieldDecision(
            field_name,
            python_value,
            "both",
            ResolutionReason.AI_PYTHON_AGREE,
            ai_value=ai_value,
            python_value=python_value,
            evidence_ids=tuple(dict.fromkeys([*ai_evidence, *python_field.evidence_ids])),
        )
    if ai_has_value and not py_has_value:
        return FieldDecision(
            field_name,
            ai_value,
            "ai",
            ResolutionReason.AI_FILLS_PYTHON_BLANK,
            ai_value=ai_value,
            python_value=python_value,
            evidence_ids=ai_evidence,
        )
    if py_has_value and not ai_has_value:
        return FieldDecision(
            field_name,
            python_value,
            "python",
            ResolutionReason.PYTHON_RETAINED_AI_OMITTED,
            ai_value=ai_value,
            python_value=python_value,
            evidence_ids=python_field.evidence_ids,
        )
    if ai_direct and not py_direct:
        return FieldDecision(
            field_name,
            ai_value,
            "ai",
            ResolutionReason.DIRECT_EVIDENCE_SELECTED_AI,
            ai_value=ai_value,
            python_value=python_value,
            evidence_ids=ai_evidence,
        )
    if py_direct and not ai_direct:
        return FieldDecision(
            field_name,
            python_value,
            "python",
            ResolutionReason.DIRECT_EVIDENCE_SELECTED_PYTHON,
            ai_value=ai_value,
            python_value=python_value,
            evidence_ids=python_field.evidence_ids,
        )
    if ai_direct and py_direct:
        return FieldDecision(
            field_name,
            "",
            "none",
            ResolutionReason.UNRESOLVED_DIRECT_EVIDENCE_CONFLICT,
            ai_value=ai_value,
            python_value=python_value,
            evidence_ids=tuple(dict.fromkeys([*ai_evidence, *python_field.evidence_ids])),
            blocking=field_name in HIGH_RISK_FIELDS,
        )
    if not ai_has_value and not py_has_value:
        return FieldDecision(
            field_name,
            "",
            "none",
            ResolutionReason.BOTH_MISSING,
            ai_value=ai_value,
            python_value=python_value,
        )
    return FieldDecision(
        field_name,
        "",
        "none",
        ResolutionReason.NO_DIRECT_EVIDENCE_CONFLICT,
        ai_value=ai_value,
        python_value=python_value,
        blocking=False,
    )


def _evidence_ids_from_diagnostic(
    scope_id: str,
    diagnostic: Mapping[str, Any],
    evidence_by_scope_cell: Mapping[tuple[str, str], str],
) -> tuple[str, ...]:
    source = diagnostic.get("source", {})
    if not isinstance(source, Mapping):
        return ()
    cells = source.get("cells", ())
    if not isinstance(cells, Sequence) or isinstance(cells, str):
        return ()
    ids = [
        evidence_by_scope_cell[(scope_id, str(cell))]
        for cell in cells
        if (scope_id, str(cell)) in evidence_by_scope_cell
    ]
    return tuple(dict.fromkeys(ids))


def _ai_business_constraint_error(
    field_name: str,
    ai_value: str,
    ai_status: str,
) -> str:
    if not ai_value or ai_status not in {"extracted", "normalized"}:
        return ""
    if field_name == "数量" and re.fullmatch(r"\d+(?:\.\d+)?", ai_value) is None:
        return "数量必须是可无损追溯的数字字符串。"
    if field_name == "计划发货日期" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", ai_value) is None:
        return "计划发货日期必须是 YYYY-MM-DD。"
    if field_name in FREE_TEXT_FIELDS:
        original = str(ai_value)
        if normalize_evidence_text(ai_value) != normalize_evidence_text(original):
            return "备注字段不得由 AI 扩写。"
    return ""


def _same_value(left: str, right: str) -> bool:
    return normalize_evidence_text(left) == normalize_evidence_text(right)
