"""Strict local validation and application of controlled layout decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from bedding_order_parser.ai_full_order.preprocessing import (
    LocalStructureCandidate,
    PreprocessedWorkbook,
    SheetStructureState,
    layout_candidate_id,
)
from bedding_order_parser.ai_full_order.structure_manifest import (
    LAYOUT_CONTRACT_VERSION,
    STRUCTURE_CONTEXT_VERSION,
    validate_structure_manifest,
)


LAYOUT_DECISION_REASONS = (
    "selected_local_order_candidate",
    "auxiliary_non_order_content",
    "insufficient_structure",
    "conflicting_candidates",
    "no_applicable_candidate",
)
LAYOUT_ROLES = ("order", "auxiliary", "unresolved")
LAYOUT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "layout_contract_version": {
            "type": "string",
            "enum": [LAYOUT_CONTRACT_VERSION],
        },
        "status": {"type": "string", "enum": ["resolved", "ambiguous"]},
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "sheet_id": {"type": "string"},
                    "role": {"type": "string", "enum": list(LAYOUT_ROLES)},
                    "candidate_id": {"type": "string"},
                    "reason": {
                        "type": "string",
                        "enum": list(LAYOUT_DECISION_REASONS),
                    },
                },
                "required": ["sheet_id", "role", "candidate_id", "reason"],
            },
        },
    },
    "required": ["layout_contract_version", "status", "decisions"],
}


class StructureDecisionValidationError(ValueError):
    """A provider layout decision cannot be bound to local structure facts."""


@dataclass(frozen=True)
class StructureApplicationResult:
    preprocessed: PreprocessedWorkbook
    resolved: bool
    summary: Mapping[str, Any]


def validate_layout_output_shape(value: Any) -> dict[str, Any]:
    """Validate the provider-owned portion before local candidate binding."""

    if not isinstance(value, Mapping):
        raise StructureDecisionValidationError("Layout output must be an object.")
    expected = {"layout_contract_version", "status", "decisions"}
    if set(value) != expected:
        raise StructureDecisionValidationError("Layout output fields are invalid.")
    if value.get("layout_contract_version") != LAYOUT_CONTRACT_VERSION:
        raise StructureDecisionValidationError("Layout contract version is invalid.")
    status = value.get("status")
    decisions = value.get("decisions")
    if status not in {"resolved", "ambiguous"} or not isinstance(decisions, list):
        raise StructureDecisionValidationError("Layout status or decisions are invalid.")
    validated: list[dict[str, str]] = []
    for decision in decisions:
        if not isinstance(decision, Mapping) or set(decision) != {
            "sheet_id",
            "role",
            "candidate_id",
            "reason",
        }:
            raise StructureDecisionValidationError("Layout decision fields are invalid.")
        item = {name: str(decision[name]) for name in decision}
        if not item["sheet_id"] or item["role"] not in LAYOUT_ROLES:
            raise StructureDecisionValidationError("Layout decision identity is invalid.")
        if item["reason"] not in LAYOUT_DECISION_REASONS:
            raise StructureDecisionValidationError("Layout decision reason is invalid.")
        validated.append(item)
    return {
        "layout_contract_version": LAYOUT_CONTRACT_VERSION,
        "status": str(status),
        "decisions": validated,
    }


def apply_structure_decision(
    preprocessed: PreprocessedWorkbook,
    manifest: Mapping[str, Any],
    output: Any,
) -> StructureApplicationResult:
    """Bind provider choices to local candidates and build a safe workbook view."""

    manifest = validate_structure_manifest(manifest)
    decision = validate_layout_output_shape(output)
    if manifest["source_file_sha256"] != preprocessed.source_file_sha256:
        raise StructureDecisionValidationError("Structure source identity mismatch.")
    unresolved_context = {
        item["sheet_id"]: item for item in manifest["unresolved_sheets"]
    }
    decisions = decision["decisions"]
    decision_ids = [item["sheet_id"] for item in decisions]
    if len(decision_ids) != len(set(decision_ids)) or set(decision_ids) != set(
        unresolved_context
    ):
        raise StructureDecisionValidationError("Layout decisions must cover each unresolved sheet once.")

    candidates = {item.candidate_id: item for item in preprocessed.layout_candidates}
    selected_order: list[LocalStructureCandidate] = []
    bound: list[dict[str, str]] = []
    for item in decisions:
        sheet_id = item["sheet_id"]
        context = unresolved_context[sheet_id]
        advertised = {
            option["candidate_id"]: option for option in context["candidate_options"]
        }
        role = item["role"]
        candidate_id = item["candidate_id"]
        reason = item["reason"]
        if role == "unresolved":
            if candidate_id or reason not in {
                "insufficient_structure",
                "conflicting_candidates",
                "no_applicable_candidate",
            }:
                raise StructureDecisionValidationError("Unresolved layout decision is invalid.")
        else:
            expected_reason = (
                "selected_local_order_candidate"
                if role == "order"
                else "auxiliary_non_order_content"
            )
            option = advertised.get(candidate_id)
            candidate = candidates.get(candidate_id)
            if (
                reason != expected_reason
                or option is None
                or candidate is None
                or option.get("role") != role
                or candidate.role != role
                or candidate.sheet_id != sheet_id
            ):
                raise StructureDecisionValidationError("Layout candidate binding is invalid.")
            expected_candidate_id = layout_candidate_id(
                source_file_sha256=preprocessed.source_file_sha256,
                sheet_id=candidate.sheet_id,
                role=candidate.role,
                block_ids=candidate.block_ids,
                record_local_ids=candidate.record_local_ids,
                cell_ranges=candidate.cell_ranges,
            )
            if candidate.candidate_id != expected_candidate_id:
                raise StructureDecisionValidationError("Local layout candidate identity is invalid.")
            if role == "auxiliary" and (
                candidate.block_ids or candidate.record_local_ids
            ):
                raise StructureDecisionValidationError("Auxiliary candidate is not locally eligible.")
            if role == "order":
                selected_order.append(candidate)
        bound.append(
            {
                "sheet_id": sheet_id,
                "role": role,
                "candidate_id": candidate_id,
                "reason": reason,
            }
        )

    has_unresolved = any(item["role"] == "unresolved" for item in bound)
    expected_status = "ambiguous" if has_unresolved else "resolved"
    if decision["status"] != expected_status:
        raise StructureDecisionValidationError("Layout status does not match sheet decisions.")
    summary = {
        "structure_context_version": STRUCTURE_CONTEXT_VERSION,
        "layout_contract_version": LAYOUT_CONTRACT_VERSION,
        "context_sha256": manifest["context_sha256"],
        "status": decision["status"],
        "validation_status": "unresolved" if has_unresolved else "applied",
        "decisions": bound,
    }
    if has_unresolved:
        return StructureApplicationResult(preprocessed, False, summary)

    confirmed_block_ids = {
        block_id
        for state in preprocessed.sheet_states
        if state.local_status == "confirmed_order"
        for block_id in state.known_block_ids
    }
    confirmed_block_ids.update(
        block_id for candidate in selected_order for block_id in candidate.block_ids
    )
    blocks = tuple(
        block for block in preprocessed.blocks if block.block_id in confirmed_block_ids
    )
    record_ids = {
        record_id for block in blocks for record_id in block.record_local_ids
    }
    records = tuple(
        record for record in preprocessed.records if record.record_local_id in record_ids
    )
    evidence_ids = {
        evidence_id
        for block in blocks
        for evidence_id in block.header_evidence_ids
    }
    evidence_ids.update(
        evidence_id for record in records for evidence_id in record.evidence_ids
    )
    evidence = tuple(
        item for item in preprocessed.evidence_catalog if item.evidence_id in evidence_ids
    )
    if not blocks or not records or not evidence:
        raise StructureDecisionValidationError("Applied layout cannot form extraction units.")

    roles_by_sheet = {item["sheet_id"]: item["role"] for item in bound}
    states: list[SheetStructureState] = []
    for state in preprocessed.sheet_states:
        role = roles_by_sheet.get(state.sheet_id)
        if role is None:
            states.append(state)
            continue
        chosen_blocks = tuple(
            block.block_id for block in blocks if block.sheet_id == state.sheet_id
        )
        chosen_records = tuple(
            record.record_local_id for record in records if record.sheet_id == state.sheet_id
        )
        states.append(
            replace(
                state,
                local_status=(
                    "ai_selected_local_order_candidate"
                    if role == "order"
                    else "ai_confirmed_auxiliary"
                ),
                known_block_ids=chosen_blocks,
                known_record_local_ids=chosen_records,
                resolution_required=False,
            )
        )
    applied = replace(
        preprocessed,
        blocks=blocks,
        records=records,
        evidence_catalog=evidence,
        structure_status="locally_resolved",
        structure_resolution_requested=True,
        sheet_states=tuple(states),
    )
    return StructureApplicationResult(applied, True, summary)


def replayable_layout_output(
    summary: Any,
    manifest: Mapping[str, Any],
    *,
    operation_identity_sha256: str,
) -> dict[str, Any] | None:
    """Return a locally revalidated resolved decision for an exact context only."""

    if not isinstance(summary, Mapping):
        return None
    if (
        summary.get("structure_context_version") != STRUCTURE_CONTEXT_VERSION
        or summary.get("layout_contract_version") != LAYOUT_CONTRACT_VERSION
        or summary.get("context_sha256") != manifest.get("context_sha256")
        or summary.get("operation_identity_sha256") != operation_identity_sha256
        or summary.get("status") != "resolved"
        or summary.get("validation_status") != "applied"
    ):
        return None
    return validate_layout_output_shape(
        {
            "layout_contract_version": summary["layout_contract_version"],
            "status": summary["status"],
            "decisions": summary.get("decisions"),
        }
    )
