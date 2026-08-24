"""Immutable local publication revisions for completed AI V2 results."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from bedding_order_parser.ai_full_order.contracts import AI_BUSINESS_FIELD_NAMES
from bedding_order_parser.ai_full_order.downstream import (
    BUSINESS_NAME,
    DictionaryValidator,
    MaterialMatcher,
    PublishedBundle,
    build_revised_v2_payloads,
    publish_immutable_revision_bundle,
    switch_bundle_current,
)
from bedding_order_parser.ai_full_order.normalization import (
    NORMALIZATION_VERSION,
    build_business_value_view,
    formal_value_for_field,
)
from bedding_order_parser.ai_full_order.preprocessing import preprocess_workbook
from bedding_order_parser.ai_full_order.resolution import (
    FieldDecision,
    ResolutionReason,
    ResolvedRecord,
)
from bedding_order_parser.dictionaries.product_validation import default_validation_path
from bedding_order_parser.materials.match_writer import CANDIDATES_NAME, SUMMARY_NAME
from bedding_order_parser.serialization.diagnostic_writer import default_report_path


REVISION_CONTRACT_VERSION = "1.0"
REVISION_DOWNSTREAM_VERSION = "1.0"
INITIAL_ENTRY_NAME = "INITIAL"
REVISION_DIRECTORY_NAME = "revisions"
REVISION_METADATA_DIRECTORY_NAME = "revision-metadata"
MAX_MANUAL_VALUE_CHARS = 2_000

REVISION_ARTIFACT_NAMES = (
    BUSINESS_NAME,
    default_report_path(BUSINESS_NAME).name,
    default_validation_path(BUSINESS_NAME).name,
    CANDIDATES_NAME,
    SUMMARY_NAME,
)


class RevisionAction(StrEnum):
    KEEP_AI = "keep_ai"
    USE_PYTHON = "use_python"
    MANUAL_OVERRIDE = "manual_override"


class ReviewStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    UNREVIEWED = "unreviewed"
    CONFIRMED_AI = "confirmed_ai"
    SELECTED_PYTHON = "selected_python"
    MANUAL_OVERRIDE = "manual_override"


class RevisionError(RuntimeError):
    pass


class RevisionNotSupported(RevisionError):
    pass


class RevisionConflict(RevisionError):
    pass


class RevisionValidationError(RevisionError):
    pass


@dataclass(frozen=True)
class RevisionRequest:
    expected_current_revision: str
    source_record_id: str
    field_name: str
    action: RevisionAction
    manual_value: str = ""


@dataclass(frozen=True)
class RevisionResult:
    revision_id: str
    revision_number: int
    parent_revision: str
    initial_revision: str
    bundle: PublishedBundle
    reused: bool


def initialize_revision_history(
    root: str | Path,
    extraction_bundle: PublishedBundle,
) -> RevisionResult:
    """Register the first successful extraction publication as immutable revision 0."""

    root = Path(root).expanduser().resolve()
    if set(extraction_bundle.paths) != set(REVISION_ARTIFACT_NAMES):
        raise RevisionValidationError("Initial AI bundle does not contain exactly five artifacts.")
    existing = revision_summary(root)
    if existing["supported"]:
        metadata = _read_metadata(root, existing["current_revision"])
        return RevisionResult(
            revision_id=existing["current_revision"],
            revision_number=int(metadata["revision_number"]),
            parent_revision=str(metadata["parent_revision"]),
            initial_revision=existing["initial_revision"],
            bundle=_published_bundle(root, existing["current_revision"], reused=True),
            reused=True,
        )

    payloads = {
        name: _read_json(extraction_bundle.paths[name])
        for name in REVISION_ARTIFACT_NAMES
    }
    diagnostic_name = default_report_path(BUSINESS_NAME).name
    diagnostic = _initial_revision_diagnostic(payloads[diagnostic_name])
    payloads[diagnostic_name] = diagnostic
    extraction_identity = _extraction_identity(diagnostic)
    revision_id = _stable_hash(
        {
            "revision_contract_version": REVISION_CONTRACT_VERSION,
            "kind": "initial",
            "extraction_identity": extraction_identity,
            "artifact_sha256": {
                name: _stable_hash(payload) for name, payload in payloads.items()
            },
        }
    )
    _set_revision_lineage(
        diagnostic,
        revision_id=revision_id,
        initial_revision=revision_id,
        parent_revision="",
        revision_number=0,
        action="initial_publication",
        source_record_id="",
        field_name="",
        previous_formal_value="",
        new_formal_value="",
        selected_source="",
        user_display_value="",
        user_normalized_value="",
        normalization_rule="",
    )
    bundle = publish_immutable_revision_bundle(root, revision_id, payloads)
    metadata = {
        "revision_contract_version": REVISION_CONTRACT_VERSION,
        "revision_id": revision_id,
        "revision_number": 0,
        "initial_revision": revision_id,
        "parent_revision": "",
        "extraction_identity": extraction_identity,
        "created_at": _now(),
        "action": "initial_publication",
        "operation_identity": "",
        "override": {},
        "artifact_sha256": dict(bundle.content_sha256),
    }
    _write_metadata(root, metadata)
    _atomic_text(root / INITIAL_ENTRY_NAME, revision_id + "\n")
    try:
        switch_bundle_current(root, revision_id)
    except Exception:
        (root / INITIAL_ENTRY_NAME).unlink(missing_ok=True)
        _discard_unpublished_revision(root, revision_id)
        raise
    return RevisionResult(revision_id, 0, "", revision_id, bundle, False)


def apply_revision(
    root: str | Path,
    input_path: str | Path,
    request: RevisionRequest,
    *,
    dictionary_validator: DictionaryValidator,
    material_matcher: MaterialMatcher,
) -> RevisionResult:
    """Apply one whitelisted field decision and atomically publish a new five-file revision."""

    root = Path(root).expanduser().resolve()
    summary = revision_summary(root)
    if not summary["supported"]:
        raise RevisionNotSupported("该历史任务不支持结果修订。")
    current_revision = str(summary["current_revision"])
    initial_revision = str(summary["initial_revision"])
    _validate_request(request)
    operation_identity = _operation_identity(
        initial_revision=initial_revision,
        parent_revision=request.expected_current_revision,
        request=request,
        dictionary_validator=dictionary_validator,
        material_matcher=material_matcher,
    )
    duplicate = _find_operation(root, operation_identity)
    if duplicate is not None and current_revision == duplicate["revision_id"]:
        revision_id = str(duplicate["revision_id"])
        return RevisionResult(
            revision_id,
            int(duplicate["revision_number"]),
            str(duplicate["parent_revision"]),
            initial_revision,
            _published_bundle(root, revision_id, reused=True),
            True,
        )
    if request.expected_current_revision != current_revision:
        raise RevisionConflict("结果版本已更新，请刷新页面后再提交。")

    parent_metadata = _read_metadata(root, current_revision)
    payloads = _load_revision_payloads(root, current_revision)
    diagnostic_name = default_report_path(BUSINESS_NAME).name
    diagnostic = payloads[diagnostic_name]
    extraction_identity = _extraction_identity(diagnostic)
    if extraction_identity != parent_metadata.get("extraction_identity"):
        raise RevisionValidationError("Revision extraction identity is inconsistent.")

    changed = _apply_field_action(diagnostic, request)
    revision_number = int(parent_metadata["revision_number"]) + 1
    revision_id = _stable_hash(
        {
            "revision_contract_version": REVISION_CONTRACT_VERSION,
            "downstream_version": REVISION_DOWNSTREAM_VERSION,
            "normalization_version": NORMALIZATION_VERSION,
            "extraction_identity": extraction_identity,
            "parent_revision": current_revision,
            "operation_identity": operation_identity,
        }
    )
    _set_revision_lineage(
        diagnostic,
        revision_id=revision_id,
        initial_revision=initial_revision,
        parent_revision=current_revision,
        revision_number=revision_number,
        action=request.action.value,
        source_record_id=request.source_record_id,
        field_name=request.field_name,
        previous_formal_value=changed["previous_formal_value"],
        new_formal_value=changed["new_formal_value"],
        selected_source=changed["selected_source"],
        user_display_value=changed["user_display_value"],
        user_normalized_value=changed["user_normalized_value"],
        normalization_rule=changed["normalization_rule"],
    )
    records = _canonical_records(diagnostic)
    preprocessed = preprocess_workbook(input_path)
    if preprocessed.source_file_sha256 != _source_sha256(diagnostic):
        raise RevisionValidationError("Revision source workbook identity does not match.")
    evidence = {
        item.evidence_id: item.to_dict() for item in preprocessed.evidence_catalog
    }
    payloads = build_revised_v2_payloads(
        records,
        diagnostic=diagnostic,
        dictionary_evidence=evidence,
        dictionary_validator=dictionary_validator,
        material_matcher=material_matcher,
    )
    bundle = publish_immutable_revision_bundle(root, revision_id, payloads)
    metadata = {
        "revision_contract_version": REVISION_CONTRACT_VERSION,
        "revision_id": revision_id,
        "revision_number": revision_number,
        "initial_revision": initial_revision,
        "parent_revision": current_revision,
        "extraction_identity": extraction_identity,
        "created_at": _now(),
        "action": request.action.value,
        "operation_identity": operation_identity,
        "override": {
            "source_record_id": request.source_record_id,
            "field_name": request.field_name,
            "previous_formal_value": changed["previous_formal_value"],
            "new_formal_value": changed["new_formal_value"],
            "selected_source": changed["selected_source"],
            "user_display_value": changed["user_display_value"],
            "user_normalized_value": changed["user_normalized_value"],
            "normalization_rule": changed["normalization_rule"],
        },
        "artifact_sha256": dict(bundle.content_sha256),
    }
    _write_metadata(root, metadata)
    try:
        switch_bundle_current(root, revision_id)
    except Exception:
        _discard_unpublished_revision(root, revision_id)
        raise
    return RevisionResult(
        revision_id,
        revision_number,
        current_revision,
        initial_revision,
        bundle,
        False,
    )


def revision_summary(root: str | Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    initial = _read_pointer(root / INITIAL_ENTRY_NAME)
    current = _read_pointer(root / "CURRENT")
    if not initial or not current:
        return {
            "supported": False,
            "initial_revision": "",
            "current_revision": "",
            "revision_number": 0,
            "revision_count": 0,
        }
    try:
        current_metadata = _read_metadata(root, current)
        initial_metadata = _read_metadata(root, initial)
        _validate_revision_bundle(root, current, current_metadata)
        _validate_revision_bundle(root, initial, initial_metadata)
        history = _history(root, initial)
    except RevisionError:
        raise
    except Exception as exc:
        raise RevisionValidationError("Revision history is invalid.") from exc
    return {
        "supported": True,
        "initial_revision": initial,
        "current_revision": current,
        "revision_number": int(current_metadata["revision_number"]),
        "revision_count": len(history),
    }


def resolve_current_bundle(root: str | Path) -> tuple[Path, str, bool]:
    """Resolve revision-aware CURRENT, falling back to the legacy extraction bundle."""

    root = Path(root).expanduser().resolve()
    current = _read_pointer(root / "CURRENT")
    if not current:
        raise RevisionValidationError("AI result CURRENT entry is unavailable.")
    revision = root / REVISION_DIRECTORY_NAME / current
    if revision.is_dir():
        metadata = _read_metadata(root, current)
        _validate_revision_bundle(root, current, metadata)
        return revision, current, True
    legacy = root / "bundles" / current
    if legacy.is_dir():
        return legacy, current, False
    raise RevisionValidationError("AI result CURRENT entry does not identify a bundle.")


def _initial_revision_diagnostic(value: Any) -> dict[str, Any]:
    diagnostic = _deep_mapping(value, "Initial diagnostic is invalid.")
    envelope = _v2_envelope(diagnostic)
    rows = envelope.get("field_decisions")
    if not isinstance(rows, list) or not rows:
        raise RevisionNotSupported("该历史任务没有可修订的 V2 字段决策。")
    for row in rows:
        if not isinstance(row, dict) or not str(row.get("record_local_id", "")):
            raise RevisionNotSupported("该历史任务缺少 Revision 所需的本地记录身份。")
        fields = row.get("fields")
        if not isinstance(fields, dict) or tuple(fields) != AI_BUSINESS_FIELD_NAMES:
            raise RevisionNotSupported("该历史任务没有完整的 17 字段决策。")
        for field in fields.values():
            if not isinstance(field, dict):
                raise RevisionNotSupported("该历史任务字段决策无法安全读取。")
            original_review = field.get("review_required") is True
            field["original_review_required"] = original_review
            field["review_status"] = (
                ReviewStatus.UNREVIEWED.value
                if original_review
                else ReviewStatus.NOT_REQUIRED.value
            )
            field["current_formal_value"] = str(field.get("formal_value", ""))
            field["current_selected_source"] = str(field.get("selected_source", ""))
            field["user_revision"] = {}
    return diagnostic


def _apply_field_action(
    diagnostic: dict[str, Any], request: RevisionRequest
) -> dict[str, str]:
    envelope = _v2_envelope(diagnostic)
    rows = envelope.get("field_decisions")
    row = next(
        (
            item
            for item in rows
            if isinstance(item, dict)
            and item.get("source_record_id") == request.source_record_id
        ),
        None,
    )
    if row is None:
        raise RevisionValidationError("未找到可修订的订单记录。")
    fields = row.get("fields")
    field = fields.get(request.field_name) if isinstance(fields, dict) else None
    if not isinstance(field, dict):
        raise RevisionValidationError("未找到可修订的业务字段。")

    previous = str(field.get("formal_value", ""))
    display = ""
    normalized = ""
    rule = ""
    if request.action is RevisionAction.KEEP_AI:
        if (
            field.get("technical_candidate_status") != "bound"
            or not str(field.get("ai_display_value", ""))
        ):
            raise RevisionValidationError("该字段的 AI 候选不能作为正式值。")
        display = str(field["ai_display_value"])
        view = build_business_value_view(request.field_name, display)
        normalized = view.normalized_value
        rule = view.normalization_rule
        formal = formal_value_for_field(request.field_name, view)
        source = "ai"
        review_status = ReviewStatus.CONFIRMED_AI.value
    elif request.action is RevisionAction.USE_PYTHON:
        display = str(field.get("python_display_value", ""))
        if not display:
            raise RevisionValidationError("该字段没有可采用的本地规则值。")
        view = build_business_value_view(request.field_name, display)
        normalized = view.normalized_value
        rule = view.normalization_rule
        formal = formal_value_for_field(request.field_name, view)
        source = "user_selected_python"
        review_status = ReviewStatus.SELECTED_PYTHON.value
    else:
        display = request.manual_value
        view = build_business_value_view(request.field_name, display)
        normalized = view.normalized_value
        rule = view.normalization_rule
        formal = formal_value_for_field(request.field_name, view)
        source = "user_override"
        review_status = ReviewStatus.MANUAL_OVERRIDE.value

    field["formal_value"] = formal
    field["current_formal_value"] = formal
    field["current_selected_source"] = source
    field["selected_source"] = source
    field["review_required"] = False
    field["review_status"] = review_status
    field["user_revision"] = {
        "action": request.action.value,
        "previous_formal_value": previous,
        "new_formal_value": formal,
        "selected_source": source,
        "user_display_value": display if request.action is RevisionAction.MANUAL_OVERRIDE else "",
        "user_normalized_value": normalized if request.action is RevisionAction.MANUAL_OVERRIDE else "",
        "normalization_rule": rule if request.action is RevisionAction.MANUAL_OVERRIDE else "",
    }
    _recompute_review_summary(envelope)
    return {
        "previous_formal_value": previous,
        "new_formal_value": formal,
        "selected_source": source,
        "user_display_value": display if request.action is RevisionAction.MANUAL_OVERRIDE else "",
        "user_normalized_value": normalized if request.action is RevisionAction.MANUAL_OVERRIDE else "",
        "normalization_rule": rule if request.action is RevisionAction.MANUAL_OVERRIDE else "",
    }


def _canonical_records(diagnostic: Mapping[str, Any]) -> tuple[ResolvedRecord, ...]:
    envelope = _v2_envelope(diagnostic)
    rows = envelope.get("field_decisions")
    if not isinstance(rows, list) or not rows:
        raise RevisionValidationError("Revision field decisions are unavailable.")
    records: list[ResolvedRecord] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise RevisionValidationError("Revision record shape is invalid.")
        fields = row.get("fields")
        if not isinstance(fields, Mapping) or tuple(fields) != AI_BUSINESS_FIELD_NAMES:
            raise RevisionValidationError("Revision record does not contain exactly 17 fields.")
        decisions: dict[str, FieldDecision] = {}
        for name in AI_BUSINESS_FIELD_NAMES:
            field = fields[name]
            if not isinstance(field, Mapping) or not isinstance(field.get("formal_value"), str):
                raise RevisionValidationError("Revision formal value is invalid.")
            source = str(field.get("selected_source", ""))
            evidence_key = (
                "ai_evidence_ids"
                if source == "ai"
                else "python_evidence_ids"
                if source in {"python_fallback", "user_selected_python"}
                else ""
            )
            raw_evidence = field.get(evidence_key, []) if evidence_key else []
            evidence_ids = tuple(
                item for item in raw_evidence if isinstance(item, str)
            ) if isinstance(raw_evidence, list) else ()
            decisions[name] = FieldDecision(
                field_name=name,
                value=str(field["formal_value"]),
                selected_source=source,
                reason_code=ResolutionReason.DIRECT_EVIDENCE_SELECTED_AI,
                evidence_ids=evidence_ids,
            )
        records.append(
            ResolvedRecord(
                record_local_id=str(row.get("record_local_id", "")),
                source_record_id=str(row.get("source_record_id", "")),
                scope_id=str(row.get("scope_id", "")),
                line_number=str(row.get("line_number", "")),
                decisions=decisions,
            )
        )
    if any(
        not record.record_local_id
        or not record.source_record_id
        or not record.scope_id
        or not record.line_number
        for record in records
    ):
        raise RevisionValidationError("Revision record identity is incomplete.")
    return tuple(records)


def _set_revision_lineage(
    diagnostic: dict[str, Any],
    **lineage: Any,
) -> None:
    envelope = _v2_envelope(diagnostic)
    envelope["publication_revision"] = {
        "revision_contract_version": REVISION_CONTRACT_VERSION,
        **lineage,
    }


def _recompute_review_summary(envelope: dict[str, Any]) -> None:
    rows = envelope.get("field_decisions", [])
    fields = [
        field
        for row in rows
        if isinstance(row, Mapping)
        for field in (row.get("fields", {}) or {}).values()
        if isinstance(field, Mapping)
    ]
    pending = [field for field in fields if field.get("review_required") is True]
    summary = envelope.get("review_summary")
    if not isinstance(summary, dict):
        summary = {}
        envelope["review_summary"] = summary
    summary["review_required"] = bool(pending)
    summary["review_required_count"] = len(pending)
    summary["high_review_count"] = sum(
        field.get("review_severity") == "high" for field in pending
    )


def _validate_request(request: RevisionRequest) -> None:
    _require_identity(request.expected_current_revision)
    if not request.source_record_id or len(request.source_record_id) > 160:
        raise RevisionValidationError("订单记录身份无效。")
    if request.field_name not in AI_BUSINESS_FIELD_NAMES:
        raise RevisionValidationError("只能修订 17 个业务字段。")
    if request.action is RevisionAction.MANUAL_OVERRIDE:
        if not isinstance(request.manual_value, str) or len(request.manual_value) > MAX_MANUAL_VALUE_CHARS:
            raise RevisionValidationError("手工输入长度无效。")
        if any(ord(char) < 32 and char not in "\n\r\t" for char in request.manual_value):
            raise RevisionValidationError("手工输入包含不允许的控制字符。")
    elif request.manual_value:
        raise RevisionValidationError("当前修订操作不接受手工值。")


def _operation_identity(
    *,
    initial_revision: str,
    parent_revision: str,
    request: RevisionRequest,
    dictionary_validator: Any,
    material_matcher: Any,
) -> str:
    normalized_manual = ""
    if request.action is RevisionAction.MANUAL_OVERRIDE:
        normalized_manual = build_business_value_view(
            request.field_name, request.manual_value
        ).normalized_value
    return _stable_hash(
        {
            "revision_contract_version": REVISION_CONTRACT_VERSION,
            "downstream_version": REVISION_DOWNSTREAM_VERSION,
            "normalization_version": NORMALIZATION_VERSION,
            "initial_revision": initial_revision,
            "parent_revision": parent_revision,
            "source_record_id": request.source_record_id,
            "field_name": request.field_name,
            "action": request.action.value,
            "manual_value_sha256": _stable_hash(normalized_manual),
            "dictionary_validator": _dependency_identity(dictionary_validator),
            "material_matcher": _dependency_identity(material_matcher),
        }
    )


def _dependency_identity(value: Any) -> dict[str, str]:
    return {
        "implementation": f"{value.__class__.__module__}.{value.__class__.__qualname__}",
        "version": str(
            getattr(value, "version", "")
            or getattr(value, "contract_version", "")
            or REVISION_DOWNSTREAM_VERSION
        )[:120],
    }


def _find_operation(root: Path, operation_identity: str) -> dict[str, Any] | None:
    metadata_root = root / REVISION_METADATA_DIRECTORY_NAME
    if not metadata_root.is_dir():
        return None
    for path in metadata_root.glob("*.json"):
        metadata = _read_json(path)
        if metadata.get("operation_identity") == operation_identity:
            return metadata
    return None


def _history(root: Path, initial_revision: str) -> list[dict[str, Any]]:
    metadata_root = root / REVISION_METADATA_DIRECTORY_NAME
    history = [
        _read_json(path) for path in metadata_root.glob("*.json")
    ] if metadata_root.is_dir() else []
    history = [
        item for item in history if item.get("initial_revision") == initial_revision
    ]
    history.sort(key=lambda item: int(item.get("revision_number", -1)))
    if not history or history[0].get("revision_id") != initial_revision:
        raise RevisionValidationError("Initial revision history is missing.")
    expected_parent = ""
    for number, item in enumerate(history):
        if (
            item.get("revision_number") != number
            or item.get("parent_revision") != expected_parent
            or not _is_identity(str(item.get("revision_id", "")))
        ):
            raise RevisionValidationError("Revision history lineage is invalid.")
        expected_parent = str(item["revision_id"])
    return history


def _validate_revision_bundle(
    root: Path, revision_id: str, metadata: Mapping[str, Any]
) -> None:
    if metadata.get("revision_id") != revision_id:
        raise RevisionValidationError("Revision metadata identity mismatch.")
    bundle = root / REVISION_DIRECTORY_NAME / revision_id
    if not bundle.is_dir():
        raise RevisionValidationError("Revision bundle is missing.")
    json_names = {path.name for path in bundle.glob("*.json")}
    if json_names != set(REVISION_ARTIFACT_NAMES):
        raise RevisionValidationError("Revision bundle must contain exactly five JSON artifacts.")
    expected = metadata.get("artifact_sha256")
    if not isinstance(expected, Mapping):
        raise RevisionValidationError("Revision artifact hashes are missing.")
    actual = {name: _stable_hash(_read_json(bundle / name)) for name in REVISION_ARTIFACT_NAMES}
    if dict(expected) != actual:
        raise RevisionValidationError("Revision artifact hash validation failed.")


def _load_revision_payloads(root: Path, revision_id: str) -> dict[str, Any]:
    metadata = _read_metadata(root, revision_id)
    _validate_revision_bundle(root, revision_id, metadata)
    bundle = root / REVISION_DIRECTORY_NAME / revision_id
    return {name: _read_json(bundle / name) for name in REVISION_ARTIFACT_NAMES}


def _published_bundle(root: Path, revision_id: str, *, reused: bool) -> PublishedBundle:
    payloads = _load_revision_payloads(root, revision_id)
    bundle = root / REVISION_DIRECTORY_NAME / revision_id
    return PublishedBundle(
        revision_id,
        bundle,
        {name: bundle / name for name in REVISION_ARTIFACT_NAMES},
        {name: _stable_hash(payload) for name, payload in payloads.items()},
        reused,
    )


def _write_metadata(root: Path, metadata: Mapping[str, Any]) -> None:
    revision_id = str(metadata.get("revision_id", ""))
    _require_identity(revision_id)
    path = root / REVISION_METADATA_DIRECTORY_NAME / f"{revision_id}.json"
    if path.is_file():
        if _read_json(path) != dict(metadata):
            raise RevisionConflict("Immutable revision metadata already exists with different content.")
        return
    _atomic_text(
        path,
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
    )


def _discard_unpublished_revision(root: Path, revision_id: str) -> None:
    (root / REVISION_METADATA_DIRECTORY_NAME / f"{revision_id}.json").unlink(
        missing_ok=True
    )
    shutil.rmtree(root / REVISION_DIRECTORY_NAME / revision_id, ignore_errors=True)


def _read_metadata(root: Path, revision_id: str) -> dict[str, Any]:
    _require_identity(revision_id)
    path = root / REVISION_METADATA_DIRECTORY_NAME / f"{revision_id}.json"
    if not path.is_file():
        raise RevisionValidationError("Revision metadata is missing.")
    metadata = _read_json(path)
    if not isinstance(metadata, dict):
        raise RevisionValidationError("Revision metadata is invalid.")
    return metadata


def _extraction_identity(diagnostic: Mapping[str, Any]) -> str:
    envelope = _v2_envelope(diagnostic)
    identity = envelope.get("result_identity")
    cache_key = identity.get("cache_key") if isinstance(identity, Mapping) else ""
    cache_key = str(cache_key or envelope.get("cache_key", ""))
    _require_identity(cache_key)
    return cache_key


def _source_sha256(diagnostic: Mapping[str, Any]) -> str:
    value = diagnostic.get("input")
    sha = str(value.get("sha256", "")) if isinstance(value, Mapping) else ""
    _require_identity(sha)
    return sha


def _v2_envelope(diagnostic: Mapping[str, Any]) -> dict[str, Any]:
    envelope = diagnostic.get("ai_enhanced")
    if not isinstance(envelope, dict) or envelope.get("protocol") != "v2":
        raise RevisionNotSupported("该历史任务不是可修订的 AI Contract V2 结果。")
    return envelope


def _deep_mapping(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RevisionValidationError(message)
    return json.loads(json.dumps(value, ensure_ascii=False))


def _read_pointer(path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return value if _is_identity(value) else ""


def _require_identity(value: str) -> None:
    if not _is_identity(value):
        raise RevisionValidationError("Revision identity is invalid.")


def _is_identity(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RevisionValidationError("Revision file cannot be read safely.") from exc


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.{uuid.uuid4().hex}.", suffix=".tmp"
    )
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(4):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep(0.005 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def _now() -> str:
    return datetime.now(UTC).isoformat()
