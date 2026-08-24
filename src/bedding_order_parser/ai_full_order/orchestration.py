"""Offline chunk orchestration for AI-enhanced whole-order parsing."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from openpyxl.utils.cell import coordinate_to_tuple, range_boundaries

from bedding_order_parser.ai_full_order.contracts import (
    AI_BUSINESS_FIELD_NAMES,
    FullOrderContractError,
    ParseMode,
    SCHEMA_VERSION,
    V2_SCHEMA_VERSION,
    normalize_evidence_text,
    validate_full_order_output,
    validate_full_order_request,
    validate_full_order_v2_request,
)
from bedding_order_parser.ai_full_order.field_policy import (
    V2CanonicalRecord,
    V2FieldPolicyError,
    resolve_v2_record,
)
from bedding_order_parser.ai_full_order.preprocessing import (
    EvidenceItem,
    LocalRecord,
    PreprocessedWorkbook,
)
from bedding_order_parser.ai_full_order.provenance import (
    CandidateValidationStatus,
    bind_v2_candidates,
)
from bedding_order_parser.ai_full_order.resolution import (
    FieldResolutionError,
    PythonShadowRecord,
    ResolvedRecord,
    resolve_records,
)
from bedding_order_parser.ai_full_order.structure_manifest import (
    build_structure_manifest,
)
from bedding_order_parser.ai_full_order.structure_resolution import (
    apply_structure_decision,
)


class ChunkStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    VALIDATED = "validated"


class BatchStatus(StrEnum):
    READY = "ready_for_downstream"
    ISOLATED = "isolated"


@dataclass(frozen=True)
class ChunkManifestItem:
    source_file_sha256: str
    scope_id: str
    chunk_id: str
    block_id: str
    record_identities: tuple[str, ...]
    evidence_range: str
    order: int
    status: ChunkStatus = ChunkStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file_sha256": self.source_file_sha256,
            "scope": self.scope_id,
            "chunk_id": self.chunk_id,
            "block_id": self.block_id,
            "record_identities": list(self.record_identities),
            "evidence_range": self.evidence_range,
            "order": self.order,
            "status": self.status.value,
        }


@dataclass(frozen=True)
class ChunkOutcome:
    manifest: ChunkManifestItem
    status: ChunkStatus
    resolved_records: tuple[ResolvedRecord, ...] = ()
    error_code: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class BatchAggregate:
    status: BatchStatus
    reasons: tuple[str, ...]
    records: tuple[ResolvedRecord, ...]

    @property
    def ready_for_downstream(self) -> bool:
        return self.status is BatchStatus.READY


@dataclass(frozen=True)
class OrchestrationResult:
    manifest: tuple[ChunkManifestItem, ...]
    chunk_outcomes: tuple[ChunkOutcome, ...]
    batch: BatchAggregate
    structure_recognition_calls: int
    extraction_calls: int
    network_calls: int


class V2ExtractionUnitStatus(StrEnum):
    PENDING = "pending"
    VALIDATED = "validated"
    FAILED = "failed"


@dataclass(frozen=True)
class V2ExtractionUnit:
    source_file_sha256: str
    chunk_id: str
    extraction_unit_id: str
    target: LocalRecord
    evidence_catalog: tuple[EvidenceItem, ...]
    order: int


@dataclass(frozen=True)
class V2ExtractionUnitOutcome:
    unit: V2ExtractionUnit
    status: V2ExtractionUnitStatus
    record: V2CanonicalRecord | None = None
    error_code: str = ""


@dataclass(frozen=True)
class V2BatchAggregate:
    status: BatchStatus
    reasons: tuple[str, ...]
    records: tuple[V2CanonicalRecord, ...]
    review_required_count: int = 0
    high_review_count: int = 0
    comparison_summary: Mapping[str, int] = field(default_factory=dict)

    @property
    def technical_ready(self) -> bool:
        return self.status is BatchStatus.READY and not self.reasons

    @property
    def review_required(self) -> bool:
        return self.review_required_count > 0

    @property
    def ready_for_downstream(self) -> bool:
        """Compatibility alias; review never changes technical readiness."""

        return self.technical_ready


@dataclass(frozen=True)
class V2OrchestrationResult:
    extraction_units: tuple[V2ExtractionUnit, ...]
    outcomes: tuple[V2ExtractionUnitOutcome, ...]
    batch: V2BatchAggregate
    structure_recognition_calls: int
    extraction_calls: int
    network_calls: int


_V2_CONTEXT_LABELS = (
    "buyer",
    "customer",
    "client",
    "sold to",
    "contact person",
    "salesperson",
    "sales person",
    "currency",
    "unit price",
    "delivery date",
    "shipping date",
    "ship date",
    "客户",
    "买方",
    "业务员",
    "币种",
    "交货日期",
    "发货日期",
)
_V2_CONTEXT_VALUE_FOLLOWS = ("buyer", "customer", "client", "sold to", "客户", "买方")
_V2_CONTEXT_SENSITIVE_LABELS = (
    "bank",
    "account",
    "iban",
    "swift",
    "payment",
    "银行",
    "账号",
    "付款",
)
V2_CONTEXT_SELECTION_VERSION = "2.0"


def build_chunk_manifest(preprocessed: PreprocessedWorkbook) -> tuple[ChunkManifestItem, ...]:
    records_by_id = {record.record_local_id: record for record in preprocessed.records}
    items: list[ChunkManifestItem] = []
    for order, block in enumerate(preprocessed.blocks, start=1):
        record_identities = tuple(
            records_by_id[record_id].source_record_id for record_id in block.record_local_ids
        )
        canonical = "\n".join(
            [
                preprocessed.source_file_sha256,
                block.scope_id,
                block.block_id,
                block.cell_range,
                *block.record_local_ids,
                *record_identities,
                *block.header_evidence_ids,
            ]
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        items.append(
            ChunkManifestItem(
                source_file_sha256=preprocessed.source_file_sha256,
                scope_id=block.scope_id,
                chunk_id=f"chunk:{digest}",
                block_id=block.block_id,
                record_identities=record_identities,
                evidence_range=block.cell_range,
                order=order,
            )
        )
    return tuple(items)


def build_v2_extraction_units(
    preprocessed: PreprocessedWorkbook,
) -> tuple[V2ExtractionUnit, ...]:
    """Build stable single-record V2 units with explicit same-scope context evidence."""

    manifest = build_chunk_manifest(preprocessed)
    block_by_id = {block.block_id: block for block in preprocessed.blocks}
    record_by_id = {record.record_local_id: record for record in preprocessed.records}
    sheet_by_id = {sheet.sheet_id: sheet for sheet in preprocessed.sheets}
    base_evidence = {item.evidence_id: item for item in preprocessed.evidence_catalog}
    units: list[V2ExtractionUnit] = []
    order = 0
    for chunk in manifest:
        block = block_by_id[chunk.block_id]
        sheet = sheet_by_id[block.sheet_id]
        _min_column, min_row, _max_column, _max_row = range_boundaries(block.cell_range)
        context_rows = _v2_context_rows(sheet.cells, min_row)
        for record_id in block.record_local_ids:
            order += 1
            record = record_by_id[record_id]
            catalog = {
                evidence_id: base_evidence[evidence_id]
                for evidence_id in record.evidence_ids
            }
            for cell in sheet.cells:
                row, _column = coordinate_to_tuple(cell.reference)
                if row not in context_rows or cell.merged_anchor:
                    continue
                original = cell.display_text or cell.formula_text
                if not original:
                    continue
                evidence_id = f"{record.scope_id}:{cell.cell_id}"
                catalog[evidence_id] = EvidenceItem(
                    evidence_id=evidence_id,
                    scope_id=record.scope_id,
                    sheet_id=record.sheet_id,
                    sheet_name=sheet.sheet_name,
                    cell_range=cell.reference,
                    original_text=original,
                    normalized_text=normalize_evidence_text(original),
                )
            target = replace(record, evidence_ids=tuple(catalog))
            canonical = "\n".join(
                [
                    preprocessed.source_file_sha256,
                    chunk.chunk_id,
                    target.record_local_id,
                    target.source_record_id,
                    target.scope_id,
                    target.sheet_id,
                    str(target.source_row),
                    *sorted(target.evidence_ids),
                ]
            )
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
            units.append(
                V2ExtractionUnit(
                    source_file_sha256=preprocessed.source_file_sha256,
                    chunk_id=chunk.chunk_id,
                    extraction_unit_id=f"v2-unit:{digest}",
                    target=target,
                    evidence_catalog=tuple(catalog.values()),
                    order=order,
                )
            )
    return tuple(units)


def _v2_context_rows(cells: Sequence[Any], block_min_row: int) -> frozenset[int]:
    row_text: dict[int, list[str]] = {}
    for cell in cells:
        row, _column = coordinate_to_tuple(cell.reference)
        if row >= block_min_row or cell.merged_anchor:
            continue
        text = normalize_evidence_text(cell.display_text or cell.formula_text)
        if text:
            row_text.setdefault(row, []).append(text)

    selected: set[int] = set()
    for row, values in row_text.items():
        combined = " ".join(values).casefold()
        if not any(label in combined for label in _V2_CONTEXT_LABELS):
            continue
        selected.add(row)
        if any(label in combined for label in _V2_CONTEXT_VALUE_FOLLOWS):
            next_row = row + 1
            next_text = " ".join(row_text.get(next_row, ())).casefold()
            if (
                next_row < block_min_row
                and next_row in row_text
                and not any(label in next_text for label in _V2_CONTEXT_SENSITIVE_LABELS)
            ):
                selected.add(next_row)
    return frozenset(selected)


def build_v2_extraction_request(unit: V2ExtractionUnit) -> dict[str, Any]:
    request = {
        "schema_version": V2_SCHEMA_VERSION,
        "parse_mode": ParseMode.AI_ENHANCED.value,
        "source_file_sha256": unit.source_file_sha256,
        "request_chunk_id": unit.chunk_id,
        "extraction_unit_id": unit.extraction_unit_id,
        "target": unit.target.to_request_dict(),
        "evidence_catalog": [item.to_dict() for item in unit.evidence_catalog],
    }
    return validate_full_order_v2_request(request)


def run_v2_offline_orchestration(
    preprocessed: PreprocessedWorkbook,
    provider: Any,
    python_shadow: Sequence[PythonShadowRecord],
    *,
    unit_order: Sequence[str] | None = None,
) -> V2OrchestrationResult:
    """Run V2 candidates through binding, field policy, and an in-memory ready gate."""

    if preprocessed.structure_status == "ambiguous":
        structure_manifest = _structure_manifest(
            preprocessed, build_chunk_manifest(preprocessed)
        )
        application = apply_structure_decision(
            preprocessed,
            structure_manifest,
            provider.resolve_structure(structure_manifest),
        )
        if not application.resolved:
            return V2OrchestrationResult(
                extraction_units=(),
                outcomes=(),
                batch=V2BatchAggregate(
                    status=BatchStatus.ISOLATED,
                    reasons=("structure_unresolved",),
                    records=(),
                ),
                structure_recognition_calls=int(
                    getattr(provider, "structure_call_count", 0)
                ),
                extraction_calls=int(getattr(provider, "extraction_call_count", 0)),
                network_calls=int(getattr(provider, "network_call_count", 0)),
            )
        preprocessed = application.preprocessed

    units = build_v2_extraction_units(preprocessed)

    shadow_by_id = {record.record_local_id: record for record in python_shadow}
    expected_ids = {unit.target.record_local_id for unit in units}
    if set(shadow_by_id) != expected_ids:
        raise V2FieldPolicyError("Python shadow identities do not match V2 extraction units.")

    unit_by_id = {unit.extraction_unit_id: unit for unit in units}
    run_units = list(units)
    if unit_order is not None:
        if set(unit_order) != set(unit_by_id) or len(unit_order) != len(unit_by_id):
            raise V2FieldPolicyError("V2 unit order does not match the extraction manifest.")
        run_units = [unit_by_id[unit_id] for unit_id in unit_order]

    outcomes: list[V2ExtractionUnitOutcome] = []
    for unit in run_units:
        try:
            request = build_v2_extraction_request(unit)
            output = provider.extract_v2(request)
            bound = bind_v2_candidates(
                output,
                target=unit.target,
                evidence_catalog=unit.evidence_catalog,
            )
            record = resolve_v2_record(
                unit.target,
                bound,
                shadow_by_id[unit.target.record_local_id],
            )
            validate_v2_accepted_ai_provenance(record)
            outcomes.append(
                V2ExtractionUnitOutcome(
                    unit=unit,
                    status=V2ExtractionUnitStatus.VALIDATED,
                    record=record,
                )
            )
        except Exception:
            outcomes.append(
                V2ExtractionUnitOutcome(
                    unit=unit,
                    status=V2ExtractionUnitStatus.FAILED,
                    error_code="v2_hard_contract_or_resolution_failure",
                )
            )

    batch = aggregate_v2_batch(units, outcomes)
    return V2OrchestrationResult(
        extraction_units=units,
        outcomes=tuple(outcomes),
        batch=batch,
        structure_recognition_calls=int(getattr(provider, "structure_call_count", 0)),
        extraction_calls=int(getattr(provider, "extraction_call_count", 0)),
        network_calls=int(getattr(provider, "network_call_count", 0)),
    )


def aggregate_v2_batch(
    units: Sequence[V2ExtractionUnit],
    outcomes: Sequence[V2ExtractionUnitOutcome],
) -> V2BatchAggregate:
    reasons: list[str] = []
    expected_unit_ids = {unit.extraction_unit_id for unit in units}
    outcome_unit_ids = [outcome.unit.extraction_unit_id for outcome in outcomes]
    if len(outcome_unit_ids) != len(set(outcome_unit_ids)):
        reasons.append("duplicate_extraction_unit_outcome")
    if not set(outcome_unit_ids) <= expected_unit_ids:
        reasons.append("unexpected_extraction_unit_outcome")
    validated = [
        outcome
        for outcome in outcomes
        if outcome.status is V2ExtractionUnitStatus.VALIDATED and outcome.record is not None
    ]
    if {outcome.unit.extraction_unit_id for outcome in validated} != expected_unit_ids:
        reasons.append("missing_extraction_units")
    if any(outcome.status is V2ExtractionUnitStatus.FAILED for outcome in outcomes):
        reasons.append("hard_contract_or_resolution_failure")

    ordered = sorted(validated, key=lambda outcome: outcome.unit.order)
    records = tuple(outcome.record for outcome in ordered if outcome.record is not None)
    if len(records) != len(units):
        reasons.append("record_count_mismatch")
    identities = [record.source_record_id for record in records]
    if len(identities) != len(set(identities)):
        reasons.append("duplicate_record_identity")
    expected_scopes = {unit.target.source_record_id: unit.target.scope_id for unit in units}
    if any(expected_scopes.get(record.source_record_id) != record.scope_id for record in records):
        reasons.append("scope_crossing")
    expected_targets = {
        unit.target.source_record_id: (
            unit.target.record_local_id,
            unit.target.scope_id,
        )
        for unit in units
    }
    if any(
        expected_targets.get(record.source_record_id)
        != (record.record_local_id, record.scope_id)
        or not isinstance(record.line_number, str)
        or not record.line_number
        for record in records
    ):
        reasons.append("record_identity_mismatch")
    if any(not record.technical_ready for record in records):
        reasons.append("canonical_field_mismatch")
    try:
        for record in records:
            validate_v2_accepted_ai_provenance(record)
    except V2FieldPolicyError:
        reasons.append("accepted_ai_provenance_invalid")

    unique_reasons = tuple(dict.fromkeys(reasons))
    decisions = [decision for record in records for decision in record.decisions.values()]
    comparison_summary = Counter(
        decision.comparison_status.value for decision in decisions
    )
    return V2BatchAggregate(
        status=BatchStatus.READY if not unique_reasons else BatchStatus.ISOLATED,
        reasons=unique_reasons,
        records=records,
        review_required_count=sum(decision.review_required for decision in decisions),
        high_review_count=sum(
            decision.review_required and decision.review_severity.value == "high"
            for decision in decisions
        ),
        comparison_summary=dict(sorted(comparison_summary.items())),
    )


def validate_v2_accepted_ai_provenance(record: V2CanonicalRecord) -> None:
    for decision in record.decisions.values():
        if decision.selected_source not in {"ai", "both"}:
            continue
        candidate = decision.ai_candidate
        if (
            candidate is None
            or candidate.validation_status is not CandidateValidationStatus.BOUND
            or candidate.quote_span is None
        ):
            raise V2FieldPolicyError("Accepted AI candidate lacks valid local provenance.")


def run_offline_orchestration(
    preprocessed: PreprocessedWorkbook,
    provider: Any,
    python_shadow: Sequence[PythonShadowRecord],
    *,
    chunk_order: Sequence[str] | None = None,
) -> OrchestrationResult:
    manifest = build_chunk_manifest(preprocessed)
    if preprocessed.structure_status == "ambiguous":
        provider.resolve_structure(_structure_manifest(preprocessed, manifest))

    manifest_by_id = {item.chunk_id: item for item in manifest}
    run_items = list(manifest)
    if chunk_order is not None:
        run_items = [manifest_by_id[chunk_id] for chunk_id in chunk_order]

    outcomes: list[ChunkOutcome] = []
    for item in run_items:
        request = build_chunk_request(preprocessed, item)
        try:
            validate_full_order_request(request)
            output = provider.extract(request)
            validate_full_order_output(output, request=request)
            shadows = _shadow_for_request(python_shadow, request)
            resolved = resolve_records(output, request=request, python_shadow=shadows)
            outcomes.append(
                ChunkOutcome(
                    manifest=replace(item, status=ChunkStatus.VALIDATED),
                    status=ChunkStatus.VALIDATED,
                    resolved_records=tuple(resolved),
                )
            )
        except Exception as exc:
            outcomes.append(
                ChunkOutcome(
                    manifest=replace(item, status=ChunkStatus.FAILED),
                    status=ChunkStatus.FAILED,
                    error_code="schema_or_evidence_failure",
                    error_message=str(exc),
                )
            )

    batch = aggregate_batch(manifest, outcomes)
    return OrchestrationResult(
        manifest=manifest,
        chunk_outcomes=tuple(outcomes),
        batch=batch,
        structure_recognition_calls=int(getattr(provider, "structure_call_count", 0)),
        extraction_calls=int(getattr(provider, "extraction_call_count", 0)),
        network_calls=int(getattr(provider, "network_call_count", 0)),
    )


def build_chunk_request(
    preprocessed: PreprocessedWorkbook,
    manifest_item: ChunkManifestItem,
) -> dict[str, Any]:
    block_by_id = {block.block_id: block for block in preprocessed.blocks}
    block = block_by_id[manifest_item.block_id]
    record_ids = set(block.record_local_ids)
    records = [record for record in preprocessed.records if record.record_local_id in record_ids]
    evidence_ids = set(block.header_evidence_ids)
    for record in records:
        evidence_ids.update(record.evidence_ids)
    evidence_catalog = [
        item for item in preprocessed.evidence_catalog if item.evidence_id in evidence_ids
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "parse_mode": ParseMode.AI_ENHANCED.value,
        "source_file_sha256": preprocessed.source_file_sha256,
        "request_chunk_id": manifest_item.chunk_id,
        "structure_status": preprocessed.structure_status,
        "blocks": [block.to_request_dict()],
        "records": [record.to_request_dict() for record in records],
        "record_count": len(records),
        "evidence_catalog": [item.to_dict() for item in evidence_catalog],
    }


def formal_line_number_from_request(
    record: Mapping[str, Any],
    evidence_catalog: Sequence[Mapping[str, Any]],
) -> str:
    """Return the standard-mode formal line number from the numbered item cell."""
    source_row = int(record["source_row"])
    expected_cell = f"A{source_row}"
    record_evidence = set(record["evidence_ids"])
    matches = [
        item for item in evidence_catalog
        if item["evidence_id"] in record_evidence and item["cell_range"] == expected_cell
    ]
    if len(matches) != 1:
        raise FieldResolutionError(
            f"Cannot prove standard line-number evidence for row {source_row}."
        )
    value = normalize_evidence_text(str(matches[0]["original_text"]))
    if not value:
        raise FieldResolutionError("Formal line number evidence is empty.")
    return value


def aggregate_batch(
    manifest: Sequence[ChunkManifestItem],
    outcomes: Sequence[ChunkOutcome],
) -> BatchAggregate:
    reasons: list[str] = []
    expected_chunk_ids = {item.chunk_id for item in manifest}
    validated_outcomes = [
        outcome for outcome in outcomes if outcome.status is ChunkStatus.VALIDATED
    ]
    completed_chunk_ids = {outcome.manifest.chunk_id for outcome in validated_outcomes}
    if completed_chunk_ids != expected_chunk_ids:
        reasons.append("missing_chunks")
    if any(outcome.status is ChunkStatus.FAILED for outcome in outcomes):
        reasons.append("schema_or_evidence_failure")

    order_by_chunk = {item.chunk_id: item.order for item in manifest}
    ordered_outcomes = sorted(
        validated_outcomes,
        key=lambda outcome: order_by_chunk.get(outcome.manifest.chunk_id, 10**9),
    )
    records = tuple(
        record for outcome in ordered_outcomes for record in outcome.resolved_records
    )

    expected_record_count = sum(len(item.record_identities) for item in manifest)
    if len(records) != expected_record_count:
        reasons.append("record_count_mismatch")

    identities = [record.source_record_id for record in records]
    if len(identities) != len(set(identities)):
        reasons.append("duplicate_record_identity")

    known_scopes = {item.scope_id for item in manifest}
    if any(record.scope_id not in known_scopes for record in records):
        reasons.append("scope_crossing")

    if any(decision.blocking for record in records for decision in record.decisions.values()):
        reasons.append("unresolved_high_risk_conflict")

    unique_reasons = tuple(dict.fromkeys(reasons))
    return BatchAggregate(
        status=BatchStatus.READY if not unique_reasons else BatchStatus.ISOLATED,
        reasons=unique_reasons,
        records=records,
    )


def _structure_manifest(
    preprocessed: PreprocessedWorkbook,
    manifest: Sequence[ChunkManifestItem],
) -> dict[str, Any]:
    return build_structure_manifest(preprocessed, manifest)


def _shadow_for_request(
    shadow_records: Sequence[PythonShadowRecord],
    request: Mapping[str, Any],
) -> tuple[PythonShadowRecord, ...]:
    expected_ids = {record["record_local_id"] for record in request["records"]}
    selected = [
        record for record in shadow_records if record.record_local_id in expected_ids
    ]
    if {record.record_local_id for record in selected} != expected_ids:
        raise FieldResolutionError("Python shadow records do not match the chunk request.")
    return tuple(selected)
