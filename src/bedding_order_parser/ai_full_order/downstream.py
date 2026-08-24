"""Offline downstream adapters and atomic five-artifact publication for AI batches."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from bedding_order_parser.ai_full_order.orchestration import (
    BatchStatus,
    ChunkStatus,
    V2ExtractionUnitStatus,
    validate_v2_accepted_ai_provenance,
)
from bedding_order_parser.ai_full_order.field_policy import V2FieldPolicyError
from bedding_order_parser.ai_full_order.reliability import ReliableRunResult, RunDisposition
from bedding_order_parser.ai_full_order.reliability_v2 import (
    V2ReliableRunResult,
    V2RunDisposition,
    V2UnitRunState,
)
from bedding_order_parser.ai_full_order.resolution import FieldDecision, ResolvedRecord
from bedding_order_parser.diagnostics.models import DERIVED, EXTRACTED, FieldDiagnostic, ParseReport, RecordDiagnostic, SourceEvidence
from bedding_order_parser.dictionaries.product_validation import default_validation_path
from bedding_order_parser.materials.hybrid_matcher import build_order_query
from bedding_order_parser.materials.match_writer import CANDIDATES_NAME, SUMMARY_NAME
from bedding_order_parser.models.final_result import FINAL_FIELD_NAMES, FinalResult, STRING_FIELD_NAMES
from bedding_order_parser.serialization.diagnostic_writer import default_report_path


BUSINESS_NAME = "ai_full_order.json"
CURRENT_ENTRY_NAME = "CURRENT"


class DownstreamError(RuntimeError):
    pass


class PublicationError(DownstreamError):
    pass


@dataclass(frozen=True)
class MaterialSelection:
    source_record_id: str
    material_code: str = ""
    similarity_score: float = 0.0


@dataclass(frozen=True)
class MaterialMatchOutput:
    selections: Mapping[str, MaterialSelection]
    candidates_payload: Mapping[str, Any]
    summary_payload: Mapping[str, Any]


class DictionaryValidator(Protocol):
    def validate(self, records: Sequence[ResolvedRecord], evidence: Mapping[str, Mapping[str, str]]) -> Mapping[str, Any]: ...


class MaterialMatcher(Protocol):
    def match(self, records: Sequence[FinalResult], resolved: Sequence[ResolvedRecord]) -> MaterialMatchOutput: ...


@dataclass(frozen=True)
class PublishedBundle:
    cache_key: str
    bundle_dir: Path
    paths: Mapping[str, Path]
    content_sha256: Mapping[str, str]
    reused: bool


def publish_ready_batch(
    execution: ReliableRunResult,
    *,
    preprocessed,
    dictionary_validator: DictionaryValidator,
    material_matcher: MaterialMatcher,
    publish_root: str | Path,
) -> PublishedBundle:
    """Run validation then matching, and expose exactly one verified five-file bundle."""
    _require_ready(execution)
    resolved = tuple(execution.batch.records)
    evidence = {item.evidence_id: item.to_dict() for item in preprocessed.evidence_catalog}
    dictionary_payload = dict(dictionary_validator.validate(resolved, evidence))
    _validate_dictionary_payload(dictionary_payload, len(resolved))

    provisional = tuple(_provisional_result(record) for record in resolved)
    # Reuses the existing material-query normalizer without loading BGE-M3/FAISS.
    _build_queries(provisional, resolved)
    match = material_matcher.match(provisional, resolved)
    _validate_match_output(match, resolved)
    final_records = tuple(_assemble_final(record, match.selections[record.source_record_id]) for record in resolved)
    diagnostic = _diagnostic_payload(execution, preprocessed, final_records, resolved)
    payloads = _bundle_payloads(final_records, diagnostic, dictionary_payload, match)
    _validate_bundle_payloads(payloads)
    return _publish_bundle(Path(publish_root), execution.cache_key, payloads)


def publish_ready_v2_batch(
    execution: V2ReliableRunResult,
    *,
    preprocessed,
    dictionary_validator: DictionaryValidator,
    material_matcher: MaterialMatcher,
    publish_root: str | Path,
) -> PublishedBundle:
    """Adapt a fully revalidated V2 batch to the unchanged five-artifact boundary."""

    _require_v2_ready(execution)
    v2_records = tuple(execution.batch.records)
    resolved = adapt_v2_records_for_downstream(v2_records)
    evidence_items = {
        item.evidence_id: item
        for unit in execution.extraction_units
        for item in unit.evidence_catalog
    }
    dictionary_evidence = {
        evidence_id: item.to_dict() for evidence_id, item in evidence_items.items()
    }
    dictionary_payload = dict(dictionary_validator.validate(resolved, dictionary_evidence))
    _validate_dictionary_payload(dictionary_payload, len(resolved))

    provisional = tuple(_provisional_result(record) for record in resolved)
    _build_queries(provisional, resolved)
    match = material_matcher.match(provisional, resolved)
    _validate_match_output(match, resolved)
    final_records = tuple(
        _assemble_final(record, match.selections[record.source_record_id])
        for record in resolved
    )
    diagnostic = _v2_diagnostic_payload(
        execution,
        preprocessed,
        final_records,
        v2_records,
        evidence_items,
    )
    payloads = _bundle_payloads(final_records, diagnostic, dictionary_payload, match)
    _validate_bundle_payloads(payloads)
    return _publish_bundle(Path(publish_root), execution.cache_key, payloads)


def build_revised_v2_payloads(
    records: Sequence[ResolvedRecord],
    *,
    diagnostic: Mapping[str, Any],
    dictionary_evidence: Mapping[str, Mapping[str, Any]],
    dictionary_validator: DictionaryValidator,
    material_matcher: MaterialMatcher,
) -> dict[str, Any]:
    """Rebuild all five payloads from trusted revised canonical records locally."""

    if not records:
        raise DownstreamError("A revision requires at least one canonical record.")
    identities = [record.source_record_id for record in records]
    if len(identities) != len(set(identities)):
        raise DownstreamError("Revision record identities are not unique.")
    if any(
        tuple(record.decisions) != tuple(
            name for name in FINAL_FIELD_NAMES if name not in {"行号", "物料编码", "相似分数"}
        )
        for record in records
    ):
        raise DownstreamError("Revision canonical records must contain exactly 17 business fields.")

    dictionary_payload = dict(
        dictionary_validator.validate(records, dictionary_evidence)
    )
    _validate_dictionary_payload(dictionary_payload, len(records))
    provisional = tuple(_provisional_result(record) for record in records)
    _build_queries(provisional, records)
    match = material_matcher.match(provisional, records)
    _validate_match_output(match, records)
    final_records = tuple(
        _assemble_final(record, match.selections[record.source_record_id])
        for record in records
    )
    revised_diagnostic = _diagnostic_with_revised_values(diagnostic, final_records)
    payloads = _bundle_payloads(
        final_records, revised_diagnostic, dictionary_payload, match
    )
    _validate_bundle_payloads(payloads)
    return payloads


def publish_immutable_revision_bundle(
    root: str | Path,
    revision_id: str,
    payloads: Mapping[str, Any],
    *,
    switch_current: bool = False,
    replace_retries: int = 3,
) -> PublishedBundle:
    """Publish a five-artifact revision without coupling it to extraction cache."""

    _validate_bundle_payloads(payloads)
    return _publish_bundle(
        Path(root),
        revision_id,
        payloads,
        replace_retries=replace_retries,
        bundle_dir_name="revisions",
        switch_current=switch_current,
    )


def switch_bundle_current(
    root: str | Path, identity: str, *, replace_retries: int = 3
) -> None:
    """Atomically expose an already validated immutable bundle identity."""

    if len(identity) != 64 or any(char not in "0123456789abcdef" for char in identity):
        raise PublicationError("Published bundle identity is invalid.")
    _atomic_text(Path(root).expanduser().resolve() / CURRENT_ENTRY_NAME, identity + "\n", replace_retries)


def adapt_v2_records_for_downstream(records) -> tuple[ResolvedRecord, ...]:
    """Remove V2-only policy detail while preserving the existing downstream port."""

    adapted: list[ResolvedRecord] = []
    for record in records:
        decisions = {
            name: FieldDecision(
                field_name=name,
                value=decision.value,
                selected_source=decision.selected_source,
                reason_code=decision.reason_code,
                evidence_ids=decision.evidence_ids,
                blocking=False,
            )
            for name, decision in record.decisions.items()
        }
        adapted.append(
            ResolvedRecord(
                record_local_id=record.record_local_id,
                source_record_id=record.source_record_id,
                scope_id=record.scope_id,
                line_number=record.line_number,
                decisions=decisions,
            )
        )
    return tuple(adapted)


def _require_ready(execution: ReliableRunResult) -> None:
    if execution.disposition not in {RunDisposition.EXECUTED, RunDisposition.CACHED}:
        raise DownstreamError("B2B execution is not validated for downstream work.")
    if execution.batch.status is not BatchStatus.READY or not execution.batch.ready_for_downstream:
        raise DownstreamError("B2A batch is not ready_for_downstream.")
    if len(execution.outcomes) != len(execution.manifest):
        raise DownstreamError("Expected chunks are incomplete.")
    if any(outcome.status is not ChunkStatus.VALIDATED for outcome in execution.outcomes):
        raise DownstreamError("A chunk is not validated.")
    identities = [record.source_record_id for record in execution.batch.records]
    if len(identities) != len(set(identities)):
        raise DownstreamError("Resolved record identities are not unique.")
    if any(decision.blocking for record in execution.batch.records for decision in record.decisions.values()):
        raise DownstreamError("Unresolved high-risk field conflict.")


def _require_v2_ready(execution: V2ReliableRunResult) -> None:
    if execution.disposition not in {V2RunDisposition.EXECUTED, V2RunDisposition.CACHED}:
        raise DownstreamError("V2 reliability execution is not validated for downstream work.")
    if execution.batch.status is not BatchStatus.READY or not execution.batch.technical_ready:
        raise DownstreamError("V2 batch is not technically ready for downstream work.")
    if execution.batch.reasons:
        raise DownstreamError("V2 batch contains technical failure reasons.")
    if len(execution.outcomes) != len(execution.extraction_units):
        raise DownstreamError("Expected V2 extraction units are incomplete.")
    if any(outcome.status is not V2ExtractionUnitStatus.VALIDATED for outcome in execution.outcomes):
        raise DownstreamError("A V2 extraction unit is not validated.")
    identities = [record.source_record_id for record in execution.batch.records]
    if len(identities) != len(set(identities)):
        raise DownstreamError("V2 canonical record identities are not unique.")
    expected = {
        unit.target.source_record_id: (unit.target.record_local_id, unit.target.scope_id)
        for unit in execution.extraction_units
    }
    if any(
        expected.get(record.source_record_id)
        != (record.record_local_id, record.scope_id)
        or not record.technical_ready
        for record in execution.batch.records
    ):
        raise DownstreamError("V2 canonical record identity or shape is invalid.")
    try:
        for record in execution.batch.records:
            validate_v2_accepted_ai_provenance(record)
    except V2FieldPolicyError as exc:
        raise DownstreamError("V2 accepted AI provenance is invalid.") from exc


def _provisional_result(record: ResolvedRecord) -> FinalResult:
    values: dict[str, str | float] = {field: "" for field in STRING_FIELD_NAMES}
    values.update(record.business_fields())
    values["物料编码"] = ""
    values["相似分数"] = 0.0
    return FinalResult.from_mapping(values)


def _build_queries(records: Sequence[FinalResult], resolved: Sequence[ResolvedRecord]) -> tuple[Any, ...]:
    return tuple(
        build_order_query(
            record.to_json_dict(), source_file="ai_enhanced", sheet=item.scope_id,
            result_json=BUSINESS_NAME, parse_report_json=default_report_path(BUSINESS_NAME).name,
        )
        for record, item in zip(records, resolved, strict=True)
    )


def _assemble_final(record: ResolvedRecord, selection: MaterialSelection) -> FinalResult:
    if selection.source_record_id != record.source_record_id:
        raise DownstreamError("Material selection identity does not match resolved record.")
    if not isinstance(selection.material_code, str):
        raise DownstreamError("Material code must come from the matcher as a string.")
    if isinstance(selection.similarity_score, bool) or not isinstance(selection.similarity_score, float):
        raise DownstreamError("Similarity score must come from the matcher as a float.")
    values: dict[str, str | float] = {field: "" for field in STRING_FIELD_NAMES}
    values.update(record.business_fields())
    values["物料编码"] = selection.material_code
    values["相似分数"] = selection.similarity_score
    final = FinalResult.from_mapping(values)
    _validate_final_record(final.to_json_dict())
    return final


def _diagnostic_payload(execution: ReliableRunResult, preprocessed, records: Sequence[FinalResult], resolved: Sequence[ResolvedRecord]) -> dict[str, Any]:
    evidence = {item.evidence_id: item for item in preprocessed.evidence_catalog}
    diagnostic_records: list[RecordDiagnostic] = []
    decision_rows: list[dict[str, Any]] = []
    for result, record in zip(records, resolved, strict=True):
        fields: dict[str, FieldDiagnostic] = {}
        decisions: dict[str, Any] = {}
        for name in FINAL_FIELD_NAMES:
            if name in {"物料编码", "相似分数"}:
                fields[name] = FieldDiagnostic(result.values[name], DERIVED, rule="material_matching")
                continue
            if name == "行号":
                fields[name] = FieldDiagnostic(
                    result.values[name],
                    DERIVED,
                    rule="local_standard_line_number",
                )
                continue
            decision = record.decisions[name]
            source = _source_from_evidence(decision.evidence_ids, evidence)
            fields[name] = FieldDiagnostic(
                result.values[name], EXTRACTED if decision.evidence_ids else DERIVED,
                source=source, rule=f"field_resolution.{decision.reason_code}", message=decision.message,
            )
            decisions[name] = {"reason_code": decision.reason_code.value, "selected_source": decision.selected_source, "evidence_ids": list(decision.evidence_ids)}
        diagnostic_records.append(RecordDiagnostic(str(result.values["行号"]), fields))
        decision_rows.append({"source_record_id": record.source_record_id, "scope_id": record.scope_id, "fields": decisions})
    report = ParseReport(
        input_file_name="ai_enhanced", input_sha256=preprocessed.source_file_sha256, sheet_name="multiple",
        result_json=BUSINESS_NAME, parse_report_json=default_report_path(BUSINESS_NAME).name,
        records=tuple(diagnostic_records),
    ).to_json_dict()
    report["ai_enhanced"] = {
        "parse_mode": "ai_enhanced", "cache_key": execution.cache_key,
        "chunk_ids": [item.chunk_id for item in execution.manifest], "field_decisions": decision_rows,
    }
    return report


def _v2_diagnostic_payload(
    execution: V2ReliableRunResult,
    preprocessed,
    records: Sequence[FinalResult],
    canonical_records,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    diagnostic_records: list[RecordDiagnostic] = []
    decision_rows: list[dict[str, Any]] = []
    content_issue_fields = 0
    for result, record in zip(records, canonical_records, strict=True):
        fields: dict[str, FieldDiagnostic] = {}
        decisions: dict[str, Any] = {}
        for name in FINAL_FIELD_NAMES:
            if name in {"物料编码", "相似分数"}:
                fields[name] = FieldDiagnostic(
                    result.values[name], DERIVED, rule="material_matching"
                )
                continue
            if name == "行号":
                fields[name] = FieldDiagnostic(
                    result.values[name], DERIVED, rule="local_standard_line_number"
                )
                continue
            decision = record.decisions[name]
            fields[name] = FieldDiagnostic(
                result.values[name],
                EXTRACTED if decision.evidence_ids else DERIVED,
                source=_source_from_evidence(decision.evidence_ids, evidence),
                rule=f"v2_field_policy.{decision.reason_code.value}",
            )
            if decision.technical_candidate_status.value == "content_issue":
                content_issue_fields += 1
            decisions[name] = {
                "field_name": name,
                "formal_value": decision.value,
                "ai_display_value": decision.ai_display_value,
                "ai_normalized_value": decision.ai_normalized_value,
                "ai_evidence_ids": list(decision.ai_evidence_ids),
                "python_display_value": decision.python_display_value,
                "python_normalized_value": decision.python_normalized_value,
                "python_evidence_ids": list(decision.python_evidence_ids),
                "comparison_status": decision.comparison_status.value,
                "status": decision.status.value,
                "selected_source": decision.selected_source,
                "review_required": decision.review_required,
                "review_severity": decision.review_severity.value,
                "reason_codes": [reason.value for reason in decision.reason_codes],
                "technical_candidate_status": decision.technical_candidate_status.value,
                "candidate_issue_code": decision.candidate_issue_code,
                "ai_supporting_quote": _short_evidence_text(
                    (
                        decision.ai_candidate.supporting_quote
                        if decision.ai_candidate is not None
                        else ""
                    )
                ),
            }
        diagnostic_records.append(RecordDiagnostic(str(result.values["行号"]), fields))
        decision_rows.append(
            {
                "record_local_id": record.record_local_id,
                "source_record_id": record.source_record_id,
                "scope_id": record.scope_id,
                "line_number": record.line_number,
                "fields": decisions,
            }
        )
    report = ParseReport(
        input_file_name="ai_enhanced",
        input_sha256=preprocessed.source_file_sha256,
        sheet_name="multiple",
        result_json=BUSINESS_NAME,
        parse_report_json=default_report_path(BUSINESS_NAME).name,
        records=tuple(diagnostic_records),
    ).to_json_dict()
    referenced_evidence_ids = {
        evidence_id
        for record in canonical_records
        for decision in record.decisions.values()
        for evidence_id in (*decision.ai_evidence_ids, *decision.python_evidence_ids)
    }
    report["ai_enhanced"] = {
        "parse_mode": "ai_enhanced",
        "protocol": "v2",
        "cache_key": execution.cache_key,
        "result_identity": {
            "cache_key": execution.cache_key,
            "source_file_sha256": preprocessed.source_file_sha256,
        },
        "contract_versions": {
            "contract_version": execution.cache_identity.contract_version,
            "schema_version": execution.cache_identity.schema_version,
            "prompt_version": execution.cache_identity.prompt_version,
            "preprocessor_version": execution.cache_identity.preprocessor_version,
            "context_selection_version": execution.cache_identity.context_selection_version,
            "evidence_normalization_version": (
                execution.cache_identity.evidence_normalization_version
            ),
            "normalization_version": execution.cache_identity.normalization_version,
            "comparison_version": execution.cache_identity.comparison_version,
            "python_shadow_adapter_version": (
                execution.cache_identity.python_shadow_adapter_version
            ),
            "field_policy_version": execution.cache_identity.field_policy_version,
            "provenance_binding_version": (
                execution.cache_identity.provenance_binding_version
            ),
        },
        "technical_readiness": {
            "technical_ready": execution.batch.technical_ready,
            "failure_reasons": list(execution.batch.reasons),
        },
        "review_summary": {
            "review_required": execution.batch.review_required,
            "review_required_count": execution.batch.review_required_count,
            "high_review_count": execution.batch.high_review_count,
            "comparison_status_counts": dict(execution.batch.comparison_summary),
            "content_issue_field_count": content_issue_fields,
        },
        "evidence_display": _evidence_display_index(
            referenced_evidence_ids, evidence
        ),
        "extraction_unit_ids": [
            unit.extraction_unit_id for unit in execution.extraction_units
        ],
        "unit_states": [
            (
                V2UnitRunState.VALIDATED_WITH_CONTENT_ISSUE.value
                if any(
                    decision.technical_candidate_status.value == "content_issue"
                    for decision in outcome.record.decisions.values()
                )
                else V2UnitRunState.VALIDATED.value
            )
            for outcome in execution.outcomes
            if outcome.record is not None
        ],
        "provider_telemetry": [dict(item) for item in execution.provider_telemetry],
        "field_decisions": decision_rows,
    }
    return report


def _evidence_display_index(
    evidence_ids: set[str], catalog: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    display: dict[str, dict[str, Any]] = {}
    for evidence_id in sorted(evidence_ids):
        item = catalog.get(evidence_id)
        if item is None:
            continue
        cell_range = str(item.cell_range)[:80]
        row_match = re.search(r"\d+", cell_range)
        display[evidence_id] = {
            "sheet_id": str(item.sheet_id)[:80],
            "sheet_name": str(item.sheet_name)[:120],
            "cell_range": cell_range,
            "source_row": int(row_match.group()) if row_match else 0,
            "excerpt": _short_evidence_text(item.original_text),
        }
    return display


def _short_evidence_text(value: str, limit: int = 180) -> str:
    compact = " ".join(str(value).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _source_from_evidence(ids: Sequence[str], catalog: Mapping[str, Any]) -> SourceEvidence:
    item = next((catalog[item_id] for item_id in ids if item_id in catalog), None)
    if item is None:
        return SourceEvidence(region="field_resolution")
    return SourceEvidence(sheet=item.sheet_name, cells=(item.cell_range,), region="field_resolution")


def _bundle_payloads(records: Sequence[FinalResult], diagnostic: Mapping[str, Any], dictionary: Mapping[str, Any], match: MaterialMatchOutput) -> dict[str, Any]:
    business = [record.to_json_dict() for record in records]
    return {
        BUSINESS_NAME: business,
        default_report_path(BUSINESS_NAME).name: dict(diagnostic),
        default_validation_path(BUSINESS_NAME).name: dict(dictionary),
        CANDIDATES_NAME: dict(match.candidates_payload),
        SUMMARY_NAME: dict(match.summary_payload),
    }


def _diagnostic_with_revised_values(
    diagnostic: Mapping[str, Any], records: Sequence[FinalResult]
) -> dict[str, Any]:
    revised = json.loads(json.dumps(diagnostic, ensure_ascii=False))
    rows = revised.get("records")
    if not isinstance(rows, list) or len(rows) != len(records):
        raise DownstreamError("Revision diagnostic record count mismatch.")
    for row, result in zip(rows, records, strict=True):
        fields = row.get("fields") if isinstance(row, dict) else None
        if not isinstance(fields, dict):
            raise DownstreamError("Revision diagnostic fields are invalid.")
        values = result.to_json_dict()
        for field_name in FINAL_FIELD_NAMES:
            item = fields.get(field_name)
            if not isinstance(item, dict):
                raise DownstreamError("Revision diagnostic field shape is invalid.")
            item["value"] = values[field_name]
            if field_name not in {"行号", "物料编码", "相似分数"}:
                item["rule"] = "user_revision.current_formal_value"
    return revised


def _validate_match_output(match: MaterialMatchOutput, resolved: Sequence[ResolvedRecord]) -> None:
    expected = {record.source_record_id for record in resolved}
    if set(match.selections) != expected:
        raise DownstreamError("Matcher selections do not exactly match resolved identities.")
    if not isinstance(match.candidates_payload.get("records"), list):
        raise DownstreamError("Material candidates payload must contain records.")
    if "accuracy_statement" not in match.summary_payload:
        raise DownstreamError("Material summary must preserve its non-accuracy statement.")


def _validate_dictionary_payload(payload: Mapping[str, Any], count: int) -> None:
    if payload.get("mode") != "validation_only" or not isinstance(payload.get("records"), list):
        raise DownstreamError("Dictionary validator must return validation-only records.")
    if len(payload["records"]) != count:
        raise DownstreamError("Dictionary validation record count mismatch.")


def _validate_final_record(value: Mapping[str, Any]) -> None:
    if tuple(value) != FINAL_FIELD_NAMES:
        raise DownstreamError("Formal result field order is invalid.")
    if any(value[field] is None or not isinstance(value[field], str) for field in STRING_FIELD_NAMES):
        raise DownstreamError("Formal string fields must be non-null strings.")
    if isinstance(value["相似分数"], bool) or not isinstance(value["相似分数"], float):
        raise DownstreamError("Formal similarity score must be a float.")


def _validate_bundle_payloads(payloads: Mapping[str, Any]) -> None:
    expected = {BUSINESS_NAME, default_report_path(BUSINESS_NAME).name, default_validation_path(BUSINESS_NAME).name, CANDIDATES_NAME, SUMMARY_NAME}
    if set(payloads) != expected:
        raise PublicationError("Exactly five core JSON artifacts are required.")
    business = payloads[BUSINESS_NAME]
    if not isinstance(business, list):
        raise PublicationError("Business artifact must be a JSON list.")
    for record in business:
        _validate_final_record(record)
        forbidden = {"parse_mode", "model", "token", "cache", "evidence", "decision"}
        if forbidden & set(record):
            raise PublicationError("Business JSON contains internal AI metadata.")
    if "ai_enhanced" not in payloads[default_report_path(BUSINESS_NAME).name]:
        raise PublicationError("AI metadata belongs only in diagnostics.")


def _publish_bundle(
    root: Path,
    cache_key: str,
    payloads: Mapping[str, Any],
    *,
    replace_retries: int = 3,
    bundle_dir_name: str = "bundles",
    switch_current: bool = True,
) -> PublishedBundle:
    root = root.expanduser().resolve()
    bundles = root / bundle_dir_name
    target = bundles / cache_key
    expected_hashes = {name: _sha_json(payload) for name, payload in payloads.items()}
    if target.exists():
        found = _bundle_hashes(target, payloads)
        if found != expected_hashes:
            raise PublicationError("Existing bundle belongs to a different result identity.")
        if switch_current:
            _atomic_text(root / CURRENT_ENTRY_NAME, cache_key + "\n", replace_retries)
        return PublishedBundle(cache_key, target, {name: target / name for name in payloads}, found, True)
    bundles.mkdir(parents=True, exist_ok=True)
    staging = bundles / f".{cache_key}.{uuid.uuid4().hex}.staging"
    staging.mkdir()
    try:
        for name, payload in payloads.items():
            _write_json(staging / name, payload, replace_retries)
        if _bundle_hashes(staging, payloads) != expected_hashes:
            raise PublicationError("Staging bundle validation failed.")
        _replace_with_retry(staging, target, replace_retries)
        _fsync_directory(bundles)
        if switch_current:
            _atomic_text(root / CURRENT_ENTRY_NAME, cache_key + "\n", replace_retries)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        current = root / CURRENT_ENTRY_NAME
        if (
            not target.exists()
            and current.is_file()
            and current.read_text(encoding="utf-8").strip() == cache_key
        ):
            current.unlink(missing_ok=True)
        raise
    return PublishedBundle(cache_key, target, {name: target / name for name in payloads}, expected_hashes, False)


def _write_json(path: Path, payload: Any, retries: int) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    _atomic_text(path, text, retries)


def _atomic_text(path: Path, text: str, retries: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(temporary, path, retries)
    finally:
        temporary.unlink(missing_ok=True)


def _replace_with_retry(source: Path, target: Path, retries: int) -> None:
    for attempt in range(retries + 1):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == retries:
                raise
            time.sleep(0.005 * (attempt + 1))


def _bundle_hashes(directory: Path, payloads: Mapping[str, Any]) -> dict[str, str]:
    actual: dict[str, str] = {}
    for name in payloads:
        path = directory / name
        if not path.is_file():
            raise PublicationError(f"Missing published artifact: {name}")
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if _sha_json(parsed) != _sha_json(payloads[name]):
            raise PublicationError(f"Published artifact contract mismatch: {name}")
        actual[name] = _sha_json(parsed)
    return actual


def _sha_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
