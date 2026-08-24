"""Local provenance binding for the sparse V2 whole-order candidate contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Sequence

from bedding_order_parser.ai_full_order.contracts import (
    FullOrderContractError,
    normalize_evidence_text,
    validate_full_order_output,
    validate_full_order_v2_output,
)
from bedding_order_parser.ai_full_order.preprocessing import EvidenceItem, LocalRecord


V2_PROVENANCE_BINDING_VERSION = "2.0"


class CandidateValidationStatus(StrEnum):
    BOUND = "bound"
    ISSUE = "candidate_issue"


class CandidateIssueCode(StrEnum):
    DIRECT_CANDIDATE_UNTRACEABLE = "direct_candidate_untraceable"
    SUPPORTING_QUOTE_REQUIRED = "supporting_quote_required"
    SUPPORTING_QUOTE_UNTRACEABLE = "supporting_quote_untraceable"


@dataclass(frozen=True)
class EvidenceSnapshot:
    evidence_id: str
    scope_id: str
    sheet_id: str
    sheet_name: str
    cell_range: str
    original_text: str
    normalized_text: str

    def to_dict(self) -> dict[str, str]:
        return {
            "evidence_id": self.evidence_id,
            "scope_id": self.scope_id,
            "sheet_id": self.sheet_id,
            "sheet_name": self.sheet_name,
            "cell_range": self.cell_range,
            "original_text": self.original_text,
            "normalized_text": self.normalized_text,
        }


@dataclass(frozen=True)
class LocalQuoteSpan:
    """A zero-based, end-exclusive span in an evidence snapshot's normalized text."""

    evidence_id: str
    start: int
    end: int
    matched_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "start": self.start,
            "end": self.end,
            "matched_text": self.matched_text,
        }


@dataclass(frozen=True)
class BoundCandidate:
    target_record_local_id: str
    target_source_record_id: str
    target_scope_id: str
    target_sheet_id: str
    target_source_row: int
    field_name: str
    candidate_value: str
    interpretation: str
    supporting_quote: str
    evidence_references: tuple[str, ...]
    evidence_snapshots: tuple[EvidenceSnapshot, ...]
    quote_span: LocalQuoteSpan | None
    validation_status: CandidateValidationStatus
    issue_code: CandidateIssueCode | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_record_local_id": self.target_record_local_id,
            "target_source_record_id": self.target_source_record_id,
            "target_scope_id": self.target_scope_id,
            "target_sheet_id": self.target_sheet_id,
            "target_source_row": self.target_source_row,
            "field_name": self.field_name,
            "candidate_value": self.candidate_value,
            "interpretation": self.interpretation,
            "supporting_quote": self.supporting_quote,
            "evidence_references": list(self.evidence_references),
            "evidence_snapshots": [item.to_dict() for item in self.evidence_snapshots],
            "quote_span": self.quote_span.to_dict() if self.quote_span else None,
            "validation_status": self.validation_status.value,
            "issue_code": self.issue_code.value if self.issue_code else "",
        }


def bind_v2_candidates(
    output: Any,
    *,
    target: LocalRecord,
    evidence_catalog: Sequence[EvidenceItem | Mapping[str, Any]],
) -> tuple[BoundCandidate, ...]:
    """Bind a verified V2 candidate list to one locally-created extraction unit.

    This function performs no field decision.  It raises only for hard envelope
    and provenance violations; ordinary quote/value failures remain structured
    candidate issues for the future field-policy layer.
    """

    validated = validate_full_order_v2_output(output)
    target_evidence_ids = _validate_target(target, evidence_catalog)
    catalog = _catalog_by_id(evidence_catalog)
    bound: list[BoundCandidate] = []
    for candidate in validated["candidates"]:
        references = tuple(candidate["evidence_references"])
        snapshots = tuple(
            _bind_evidence_reference(
                evidence_id,
                target=target,
                target_evidence_ids=target_evidence_ids,
                catalog=catalog,
            )
            for evidence_id in references
        )
        quote_text = (
            candidate["candidate_value"]
            if candidate["interpretation"] == "direct"
            else candidate["supporting_quote"]
        )
        issue = _candidate_issue(candidate, snapshots, quote_text)
        span = None if issue else _locate_normalized_quote(quote_text, snapshots)
        bound.append(
            BoundCandidate(
                target_record_local_id=target.record_local_id,
                target_source_record_id=target.source_record_id,
                target_scope_id=target.scope_id,
                target_sheet_id=target.sheet_id,
                target_source_row=target.source_row,
                field_name=candidate["field_name"],
                candidate_value=candidate["candidate_value"],
                interpretation=candidate["interpretation"],
                supporting_quote=candidate["supporting_quote"],
                evidence_references=references,
                evidence_snapshots=snapshots,
                quote_span=span,
                validation_status=(
                    CandidateValidationStatus.ISSUE if issue else CandidateValidationStatus.BOUND
                ),
                issue_code=issue,
            )
        )
    return tuple(bound)


def adapt_verified_v1_record_to_v2_candidates(
    output: Any,
    *,
    request: Mapping[str, Any],
    target: LocalRecord,
    evidence_catalog: Sequence[EvidenceItem | Mapping[str, Any]],
) -> tuple[BoundCandidate, ...]:
    """Map a strictly verified V1 record into the V2 local binding representation."""

    validated = validate_full_order_output(output, request=request)
    output_record = next(
        (item for item in validated["records"] if item["record_local_id"] == target.record_local_id),
        None,
    )
    if output_record is None or output_record["scope_id"] != target.scope_id:
        raise _compatibility_error()

    candidates: list[dict[str, Any]] = []
    for field_name, field in output_record["fields"].items():
        if field["extraction_status"] in {"extracted", "normalized"}:
            candidates.append(
                {
                    "field_name": field_name,
                    "candidate_value": field["value"],
                    "evidence_references": list(field["evidence_references"]),
                    "interpretation": "direct",
                    "supporting_quote": "",
                }
            )
    return bind_v2_candidates(
        {"candidates": candidates}, target=target, evidence_catalog=evidence_catalog
    )


def _validate_target(
    target: LocalRecord, evidence_catalog: Sequence[EvidenceItem | Mapping[str, Any]]
) -> frozenset[str]:
    if not (
        target.record_local_id
        and target.source_record_id
        and target.scope_id
        and target.sheet_id
        and target.source_row >= 1
        and target.evidence_ids
        and len(target.evidence_ids) == len(set(target.evidence_ids))
    ):
        raise _target_error()
    catalog = _catalog_by_id(evidence_catalog)
    for evidence_id in target.evidence_ids:
        item = catalog.get(evidence_id)
        if item is None or item.scope_id != target.scope_id or item.sheet_id != target.sheet_id:
            raise _target_error()
    return frozenset(target.evidence_ids)


def _catalog_by_id(
    evidence_catalog: Sequence[EvidenceItem | Mapping[str, Any]],
) -> dict[str, EvidenceSnapshot]:
    catalog: dict[str, EvidenceSnapshot] = {}
    for item in evidence_catalog:
        snapshot = _snapshot(item)
        if not snapshot.evidence_id or snapshot.evidence_id in catalog:
            raise _target_error()
        catalog[snapshot.evidence_id] = snapshot
    return catalog


def _snapshot(item: EvidenceItem | Mapping[str, Any]) -> EvidenceSnapshot:
    if isinstance(item, EvidenceItem):
        return EvidenceSnapshot(**item.to_dict())
    try:
        return EvidenceSnapshot(
            evidence_id=str(item["evidence_id"]),
            scope_id=str(item["scope_id"]),
            sheet_id=str(item["sheet_id"]),
            sheet_name=str(item["sheet_name"]),
            cell_range=str(item["cell_range"]),
            original_text=str(item["original_text"]),
            normalized_text=str(item["normalized_text"]),
        )
    except (KeyError, TypeError) as exc:
        raise _target_error() from exc


def _bind_evidence_reference(
    evidence_id: str,
    *,
    target: LocalRecord,
    target_evidence_ids: frozenset[str],
    catalog: Mapping[str, EvidenceSnapshot],
) -> EvidenceSnapshot:
    snapshot = catalog.get(evidence_id)
    if snapshot is None:
        raise FullOrderContractError(
            "V2 candidate references an unknown evidence ID.",
            diagnostic={
                "stage": "provenance_binding",
                "category": "evidence_id_missing",
                "path": "$.candidates[].evidence_references",
            },
        )
    if snapshot.scope_id != target.scope_id:
        raise FullOrderContractError(
            "V2 candidate references evidence outside its target scope.",
            diagnostic={
                "stage": "provenance_binding",
                "category": "evidence_cross_scope",
                "path": "$.candidates[].evidence_references",
            },
        )
    if evidence_id not in target_evidence_ids:
        raise FullOrderContractError(
            "V2 candidate references evidence outside its target extraction unit.",
            diagnostic={
                "stage": "provenance_binding",
                "category": "evidence_not_in_target",
                "path": "$.candidates[].evidence_references",
            },
        )
    return snapshot


def _candidate_issue(
    candidate: Mapping[str, str], snapshots: Sequence[EvidenceSnapshot], quote_text: str
) -> CandidateIssueCode | None:
    if candidate["interpretation"] == "direct":
        return (
            None
            if _locate_normalized_quote(quote_text, snapshots)
            else CandidateIssueCode.DIRECT_CANDIDATE_UNTRACEABLE
        )
    if not quote_text:
        return CandidateIssueCode.SUPPORTING_QUOTE_REQUIRED
    return (
        None
        if _locate_normalized_quote(quote_text, snapshots)
        else CandidateIssueCode.SUPPORTING_QUOTE_UNTRACEABLE
    )


def _locate_normalized_quote(
    quote_text: str, snapshots: Sequence[EvidenceSnapshot]
) -> LocalQuoteSpan | None:
    normalized_quote = normalize_evidence_text(quote_text)
    if not normalized_quote:
        return None
    for snapshot in snapshots:
        start = snapshot.normalized_text.find(normalized_quote)
        if start >= 0:
            return LocalQuoteSpan(
                evidence_id=snapshot.evidence_id,
                start=start,
                end=start + len(normalized_quote),
                matched_text=normalized_quote,
            )
    return None


def _target_error() -> FullOrderContractError:
    return FullOrderContractError(
        "The local V2 target identity is invalid.",
        diagnostic={
            "stage": "provenance_binding",
            "category": "target_identity_invalid",
            "path": "$.records[].record_local_id",
        },
    )


def _compatibility_error() -> FullOrderContractError:
    return FullOrderContractError(
        "The verified V1 record cannot be mapped to the requested local target.",
        diagnostic={"stage": "v1_compatibility", "category": "v1_compatibility"},
    )
