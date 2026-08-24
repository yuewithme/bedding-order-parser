"""Strict, dependency-free contracts for offline whole-order AI extraction."""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Any, Mapping


SCHEMA_VERSION = "1.0"
V2_SCHEMA_VERSION = "2.0"
V2_CONTRACT_VERSION = "2.0"
NORMALIZATION_RULES_VERSION = "1.0"


class ParseMode(StrEnum):
    STANDARD = "standard"
    AI_ENHANCED = "ai_enhanced"


AI_BUSINESS_FIELD_NAMES: tuple[str, ...] = (
    "客户",
    "币种",
    "业务员",
    "表头备注",
    "物料名称",
    "规格",
    "颜色",
    "面料",
    "面料-涤棉成分",
    "款式",
    "加标方式",
    "尺寸类型",
    "数量",
    "行备注",
    "计划发货日期",
    "包装方式",
    "是否绣花",
)
FIELD_EXTRACTION_STATUSES = (
    "extracted",
    "normalized",
    "source_not_provided",
    "ambiguous",
    "invalid",
)
RECORD_EXTRACTION_STATUSES = ("complete", "partial", "unresolved", "invalid")
FORBIDDEN_MODEL_FIELD_NAMES = frozenset({"行号", "物料编码", "相似分数"})
V2_CANDIDATE_INTERPRETATIONS = ("direct", "semantic", "source_summary")

_SAFE_CONTRACT_STAGES = frozenset(
    {
        "",
        "request_validation",
        "output_schema",
        "identity_validation",
        "evidence_validation",
        "forbidden_fields",
        "provider_metadata",
        "response_parsing",
        "v2_output_schema",
        "v2_request_validation",
        "v2_hard_contract",
        "provenance_binding",
        "v1_compatibility",
    }
)
_SAFE_CONTRACT_CATEGORIES = frozenset(
    {
        "",
        "missing_required_fields",
        "extra_fields",
        "type_mismatch",
        "enum_or_constant_mismatch",
        "length_or_range_mismatch",
        "source_file_sha256_mismatch",
        "record_count_mismatch",
        "record_identity_mismatch",
        "scope_mismatch",
        "evidence_id_missing",
        "evidence_cross_scope",
        "evidence_untraceable",
        "field_evidence_requirements",
        "provider_metadata_or_usage",
        "response_parse",
        "duplicate_field_name",
        "duplicate_evidence_reference",
        "target_identity_invalid",
        "evidence_not_in_target",
        "v1_compatibility",
    }
)
_SAFE_JSON_TYPES = frozenset(
    {"", "null", "boolean", "object", "array", "string", "integer", "number", "other"}
)


class FullOrderContractError(ValueError):
    """Raised when a full-order request or model result breaks its contract."""

    def __init__(self, message: str, *, diagnostic: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.diagnostic = safe_contract_diagnostic(diagnostic)


def safe_contract_diagnostic(value: Any) -> dict[str, Any]:
    """Return only fixed-contract diagnostic facts; never return model keys or values."""
    if isinstance(value, FullOrderContractError):
        value = value.diagnostic
    if not isinstance(value, Mapping):
        return {}
    stage = str(value.get("stage", ""))
    category = str(value.get("category", ""))
    if not stage and not category:
        return {}
    if stage not in _SAFE_CONTRACT_STAGES or category not in _SAFE_CONTRACT_CATEGORIES:
        return {}
    result: dict[str, Any] = {"stage": stage, "category": category}
    path = _safe_contract_path(value.get("path"))
    if path:
        result["path"] = path
    for name in ("expected_type", "actual_type"):
        item = str(value.get(name, ""))
        if item and item in _SAFE_JSON_TYPES:
            result[name] = item
    for name in ("missing_fixed_fields", "forbidden_fields"):
        fields = _safe_fixed_fields(value.get(name))
        if fields:
            result[name] = fields
    extra_count = value.get("extra_field_count", 0)
    if isinstance(extra_count, int) and not isinstance(extra_count, bool) and extra_count > 0:
        result["extra_field_count"] = extra_count
    return result


def _safe_contract_path(value: Any) -> str:
    path = re.sub(r"\[\d+\]", "[]", str(value or ""))
    if path == "$":
        return path

    root_fields = {
        "schema_version", "parse_mode", "source_file_sha256", "request_chunk_id",
        "structure_status", "blocks", "records", "record_count", "evidence_catalog",
        "provider", "model", "request_id", "warnings", "usage", "latency_ms",
        "attempt_count", "candidates",
        "extraction_unit_id", "target",
    }
    if path in {f"$.{field}" for field in root_fields}:
        return path

    if path in {"$.usage", "$.usage.input_tokens", "$.usage.output_tokens", "$.usage.total_tokens"}:
        return path

    target_fields = {
        "record_local_id", "source_record_id", "scope_id", "sheet_id", "source_row",
        "evidence_ids",
    }
    if path == "$.target" or path in {f"$.target.{field}" for field in target_fields}:
        return path

    block_fields = {
        "block_id", "scope_id", "sheet_id", "sheet_name", "cell_range",
        "header_evidence_ids", "record_local_ids",
    }
    if path == "$.blocks[]" or path in {f"$.blocks[].{field}" for field in block_fields}:
        return path

    evidence_fields = {
        "evidence_id", "scope_id", "sheet_id", "sheet_name", "cell_range",
        "original_text", "normalized_text",
    }
    if path == "$.evidence_catalog[]" or path in {
        f"$.evidence_catalog[].{field}" for field in evidence_fields
    }:
        return path

    record_fields = {
        "record_local_id", "source_record_id", "scope_id", "fields",
        "extraction_status", "warnings", "unresolved_fields",
    }
    if path == "$.records[]" or path in {f"$.records[].{field}" for field in record_fields}:
        return path
    allowed_field_names = set(AI_BUSINESS_FIELD_NAMES) | set(FORBIDDEN_MODEL_FIELD_NAMES)
    for field_name in allowed_field_names:
        base = f"$.records[].fields.{field_name}"
        if path == base or path in {
            f"{base}.value", f"{base}.original_value", f"{base}.evidence_references",
            f"{base}.extraction_status", f"{base}.reason",
        }:
            return path

    candidate_fields = {
        "field_name", "candidate_value", "evidence_references", "interpretation",
        "supporting_quote",
    }
    if path == "$.candidates[]" or path in {
        f"$.candidates[].{field}" for field in candidate_fields
    }:
        return path
    return ""


def _safe_schema_field_names() -> frozenset[str]:
    return frozenset(
        {
            "schema_version", "parse_mode", "source_file_sha256", "request_chunk_id",
            "structure_status", "blocks", "records", "record_count", "evidence_catalog",
            "block_id", "scope_id", "sheet_id", "sheet_name", "cell_range",
            "header_evidence_ids", "record_local_ids", "record_local_id", "source_record_id",
            "source_row", "evidence_ids", "evidence_id", "original_text", "normalized_text",
            "provider", "model", "request_id", "warnings", "usage", "input_tokens",
            "output_tokens", "total_tokens", "latency_ms", "attempt_count", "fields",
            "extraction_status", "unresolved_fields", "value", "original_value",
            "evidence_references", "reason", "candidates", "field_name", "candidate_value",
            "interpretation", "supporting_quote", *AI_BUSINESS_FIELD_NAMES,
            "extraction_unit_id", "target",
            *FORBIDDEN_MODEL_FIELD_NAMES,
        }
    )


def _safe_fixed_fields(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return []
    allowed = _safe_schema_field_names()
    return sorted({str(item) for item in value if str(item) in allowed})


def _contract_error(message: str, **diagnostic: Any) -> FullOrderContractError:
    return FullOrderContractError(message, diagnostic=diagnostic)


def parse_mode_from_value(value: str) -> ParseMode:
    try:
        return ParseMode(value)
    except ValueError as exc:
        raise FullOrderContractError(f"Unsupported parse_mode: {value}") from exc


def normalize_evidence_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def build_source_record_id(
    *,
    source_file_sha256: str,
    sheet_id: str,
    scope_id: str,
    source_row: int,
    evidence_ids: list[str],
) -> str:
    canonical = "\n".join(
        [source_file_sha256, sheet_id, scope_id, str(source_row), *sorted(evidence_ids)]
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


STRING_ARRAY_SCHEMA: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
EVIDENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "evidence_id": {"type": "string", "minLength": 1},
        "scope_id": {"type": "string", "minLength": 1},
        "sheet_id": {"type": "string", "minLength": 1},
        "sheet_name": {"type": "string", "minLength": 1},
        "cell_range": {"type": "string", "minLength": 1},
        "original_text": {"type": "string", "minLength": 1},
        "normalized_text": {"type": "string", "minLength": 1},
    },
    "required": [
        "evidence_id",
        "scope_id",
        "sheet_id",
        "sheet_name",
        "cell_range",
        "original_text",
        "normalized_text",
    ],
}
REQUEST_RECORD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "record_local_id": {"type": "string", "minLength": 1},
        "source_record_id": {"type": "string", "minLength": 1},
        "scope_id": {"type": "string", "minLength": 1},
        "sheet_id": {"type": "string", "minLength": 1},
        "source_row": {"type": "integer", "minimum": 1},
        "evidence_ids": STRING_ARRAY_SCHEMA,
    },
    "required": [
        "record_local_id",
        "source_record_id",
        "scope_id",
        "sheet_id",
        "source_row",
        "evidence_ids",
    ],
}
BLOCK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "block_id": {"type": "string", "minLength": 1},
        "scope_id": {"type": "string", "minLength": 1},
        "sheet_id": {"type": "string", "minLength": 1},
        "sheet_name": {"type": "string", "minLength": 1},
        "cell_range": {"type": "string", "minLength": 1},
        "header_evidence_ids": STRING_ARRAY_SCHEMA,
        "record_local_ids": STRING_ARRAY_SCHEMA,
    },
    "required": [
        "block_id",
        "scope_id",
        "sheet_id",
        "sheet_name",
        "cell_range",
        "header_evidence_ids",
        "record_local_ids",
    ],
}
FULL_ORDER_REQUEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "string", "const": SCHEMA_VERSION},
        "parse_mode": {"type": "string", "const": ParseMode.AI_ENHANCED.value},
        "source_file_sha256": {"type": "string", "minLength": 1},
        "request_chunk_id": {"type": "string", "minLength": 1},
        "structure_status": {"type": "string", "enum": ["locally_resolved", "ambiguous"]},
        "blocks": {"type": "array", "items": BLOCK_SCHEMA},
        "records": {"type": "array", "items": REQUEST_RECORD_SCHEMA},
        "record_count": {"type": "integer", "minimum": 0},
        "evidence_catalog": {"type": "array", "items": EVIDENCE_SCHEMA},
    },
    "required": [
        "schema_version",
        "parse_mode",
        "source_file_sha256",
        "request_chunk_id",
        "structure_status",
        "blocks",
        "records",
        "record_count",
        "evidence_catalog",
    ],
}
FIELD_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "value": {"type": "string"},
        "original_value": {"type": "string"},
        "evidence_references": STRING_ARRAY_SCHEMA,
        "extraction_status": {"type": "string", "enum": list(FIELD_EXTRACTION_STATUSES)},
        "reason": {"type": "string"},
    },
    "required": ["value", "original_value", "evidence_references", "extraction_status", "reason"],
}
FIELDS_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {name: FIELD_OUTPUT_SCHEMA for name in AI_BUSINESS_FIELD_NAMES},
    "required": list(AI_BUSINESS_FIELD_NAMES),
}
OUTPUT_RECORD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "record_local_id": {"type": "string", "minLength": 1},
        "source_record_id": {"type": "string", "minLength": 1},
        "scope_id": {"type": "string", "minLength": 1},
        "fields": FIELDS_OUTPUT_SCHEMA,
        "extraction_status": {"type": "string", "enum": list(RECORD_EXTRACTION_STATUSES)},
        "warnings": STRING_ARRAY_SCHEMA,
        "unresolved_fields": {"type": "array", "items": {"type": "string", "enum": list(AI_BUSINESS_FIELD_NAMES)}},
    },
    "required": [
        "record_local_id",
        "source_record_id",
        "scope_id",
        "fields",
        "extraction_status",
        "warnings",
        "unresolved_fields",
    ],
}
FULL_ORDER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "string", "const": SCHEMA_VERSION},
        "parse_mode": {"type": "string", "const": ParseMode.AI_ENHANCED.value},
        "source_file_sha256": {"type": "string", "minLength": 1},
        "provider": {"type": "string", "minLength": 1},
        "model": {"type": "string", "minLength": 1},
        "request_id": {"type": "string", "minLength": 1},
        "records": {"type": "array", "items": OUTPUT_RECORD_SCHEMA},
        "record_count": {"type": "integer", "minimum": 0},
        "warnings": STRING_ARRAY_SCHEMA,
        "usage": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "input_tokens": {"type": "integer", "minimum": 0},
                "output_tokens": {"type": "integer", "minimum": 0},
                "total_tokens": {"type": "integer", "minimum": 0},
            },
            "required": ["input_tokens", "output_tokens", "total_tokens"],
        },
        "latency_ms": {"type": "integer", "minimum": 0},
        "attempt_count": {"type": "integer", "minimum": 0},
    },
    "required": [
        "schema_version",
        "parse_mode",
        "source_file_sha256",
        "provider",
        "model",
        "request_id",
        "records",
        "record_count",
        "warnings",
        "usage",
        "latency_ms",
        "attempt_count",
    ],
}

# V2 is deliberately a separate sparse candidate contract.  It does not share
# V1's record echo, provider metadata, or all-fields-required output shape.
V2_CANDIDATE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "field_name": {"type": "string", "enum": list(AI_BUSINESS_FIELD_NAMES)},
        "candidate_value": {"type": "string", "minLength": 1},
        "evidence_references": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
        "interpretation": {"type": "string", "enum": list(V2_CANDIDATE_INTERPRETATIONS)},
        "supporting_quote": {"type": "string"},
    },
    "required": [
        "field_name",
        "candidate_value",
        "evidence_references",
        "interpretation",
        "supporting_quote",
    ],
}
V2_TARGET_RECORD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "record_local_id": {"type": "string", "minLength": 1},
        "source_record_id": {"type": "string", "minLength": 1},
        "scope_id": {"type": "string", "minLength": 1},
        "sheet_id": {"type": "string", "minLength": 1},
        "source_row": {"type": "integer", "minimum": 1},
        "evidence_ids": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
    },
    "required": [
        "record_local_id",
        "source_record_id",
        "scope_id",
        "sheet_id",
        "source_row",
        "evidence_ids",
    ],
}
FULL_ORDER_V2_REQUEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "string", "const": V2_SCHEMA_VERSION},
        "parse_mode": {"type": "string", "const": ParseMode.AI_ENHANCED.value},
        "source_file_sha256": {"type": "string", "minLength": 1},
        "request_chunk_id": {"type": "string", "minLength": 1},
        "extraction_unit_id": {"type": "string", "minLength": 1},
        "target": V2_TARGET_RECORD_SCHEMA,
        "evidence_catalog": {
            "type": "array",
            "minItems": 1,
            "items": EVIDENCE_SCHEMA,
        },
    },
    "required": [
        "schema_version",
        "parse_mode",
        "source_file_sha256",
        "request_chunk_id",
        "extraction_unit_id",
        "target",
        "evidence_catalog",
    ],
}
FULL_ORDER_V2_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "candidates": {"type": "array", "items": V2_CANDIDATE_OUTPUT_SCHEMA},
    },
    "required": ["candidates"],
}


def validate_full_order_v2_request(value: Any) -> dict[str, Any]:
    """Validate one locally-bound V2 extraction unit and its exact evidence set."""

    _validate_schema(value, FULL_ORDER_V2_REQUEST_SCHEMA, stage="v2_request_validation")
    assert isinstance(value, dict)
    target = value["target"]
    target_ids = list(target["evidence_ids"])
    catalog_ids = [item["evidence_id"] for item in value["evidence_catalog"]]
    if len(target_ids) != len(set(target_ids)) or len(catalog_ids) != len(set(catalog_ids)):
        raise _contract_error(
            "Duplicate V2 request evidence IDs are not allowed.",
            stage="v2_request_validation",
            category="duplicate_evidence_reference",
            path="$.target.evidence_ids",
        )
    if set(target_ids) != set(catalog_ids):
        missing = set(target_ids) - set(catalog_ids)
        raise _contract_error(
            "V2 request evidence catalog does not exactly match the local target.",
            stage="v2_request_validation",
            category="evidence_id_missing" if missing else "evidence_not_in_target",
            path="$.target.evidence_ids",
        )
    for item in value["evidence_catalog"]:
        if item["scope_id"] != target["scope_id"]:
            raise _contract_error(
                "V2 request evidence crosses the target scope.",
                stage="v2_request_validation",
                category="evidence_cross_scope",
                path="$.evidence_catalog[].scope_id",
            )
        if item["sheet_id"] != target["sheet_id"]:
            raise _contract_error(
                "V2 request evidence sheet does not match the local target.",
                stage="v2_request_validation",
                category="target_identity_invalid",
                path="$.evidence_catalog[].sheet_id",
            )
    return value


def validate_full_order_v2_output(value: Any) -> dict[str, Any]:
    """Validate only V2's model-owned sparse candidate envelope.

    Target identity and evidence provenance are intentionally bound later by
    ``provenance.bind_v2_candidates`` from the local extraction unit.
    """

    _validate_schema(value, FULL_ORDER_V2_OUTPUT_SCHEMA, stage="v2_output_schema")
    assert isinstance(value, dict)
    candidates = value["candidates"]
    _assert_v2_unique(
        [candidate["field_name"] for candidate in candidates],
        "field_name",
        path="$.candidates[].field_name",
        category="duplicate_field_name",
    )
    for candidate in candidates:
        _assert_v2_unique(
            list(candidate["evidence_references"]),
            "evidence_references",
            path="$.candidates[].evidence_references",
            category="duplicate_evidence_reference",
        )
    return value


def validate_full_order_request(value: Any) -> dict[str, Any]:
    _validate_schema(value, FULL_ORDER_REQUEST_SCHEMA, stage="request_validation")
    assert isinstance(value, dict)
    if value["record_count"] != len(value["records"]):
        raise _contract_error(
            "$.record_count must equal $.records length.",
            stage="request_validation", category="record_count_mismatch", path="$.record_count",
        )
    _assert_unique(
        [record["record_local_id"] for record in value["records"]],
        "record_local_id", stage="request_validation",
    )
    _assert_unique(
        [record["source_record_id"] for record in value["records"]],
        "source_record_id", stage="request_validation",
    )
    evidence_values = [item["evidence_id"] for item in value["evidence_catalog"]]
    _assert_unique(evidence_values, "evidence_id", stage="request_validation")
    evidence_ids = set(evidence_values)
    for record in value["records"]:
        for evidence_id in record["evidence_ids"]:
            if evidence_id not in evidence_ids:
                raise _contract_error(
                    "Unknown request evidence_id.",
                    stage="request_validation", category="evidence_id_missing", path="$.records[].evidence_ids",
                )
    return value


def validate_full_order_output(value: Any, *, request: Mapping[str, Any]) -> dict[str, Any]:
    validated_request = validate_full_order_request(dict(request))
    _validate_schema(value, FULL_ORDER_OUTPUT_SCHEMA, stage="output_schema")
    assert isinstance(value, dict)
    if value["source_file_sha256"] != validated_request["source_file_sha256"]:
        raise _contract_error(
            "$.source_file_sha256 does not match the request.",
            stage="identity_validation", category="source_file_sha256_mismatch", path="$.source_file_sha256",
        )
    if value["record_count"] != len(value["records"]):
        raise _contract_error(
            "$.record_count must equal $.records length.",
            stage="identity_validation", category="record_count_mismatch", path="$.record_count",
        )

    expected_records = {record["record_local_id"]: record for record in validated_request["records"]}
    actual_ids = [record["record_local_id"] for record in value["records"]]
    _assert_unique(actual_ids, "output record_local_id", stage="identity_validation")
    if set(actual_ids) != set(expected_records):
        raise _contract_error(
            "Output records do not exactly match requested records.",
            stage="identity_validation", category="record_identity_mismatch", path="$.records[].record_local_id",
        )

    evidence = {item["evidence_id"]: item for item in validated_request["evidence_catalog"]}
    for output_record in value["records"]:
        expected = expected_records[output_record["record_local_id"]]
        if output_record["source_record_id"] != expected["source_record_id"]:
            raise _contract_error(
                "$.records[].source_record_id does not match the request.",
                stage="identity_validation", category="record_identity_mismatch", path="$.records[].source_record_id",
            )
        if output_record["scope_id"] != expected["scope_id"]:
            raise _contract_error(
                "$.records[].scope_id does not match the request.",
                stage="identity_validation", category="scope_mismatch", path="$.records[].scope_id",
            )
        _validate_record_evidence(output_record, evidence)
    return value


def _validate_record_evidence(record: Mapping[str, Any], evidence: Mapping[str, Mapping[str, Any]]) -> None:
    scope_id = str(record["scope_id"])
    for field_name in AI_BUSINESS_FIELD_NAMES:
        field = record["fields"][field_name]
        references = list(field["evidence_references"])
        status = field["extraction_status"]
        value = field["value"]
        original = field["original_value"]
        if status in {"extracted", "normalized"}:
            if not value or not original or not references:
                raise _contract_error(
                    f"{field_name} requires value, original_value and evidence.",
                    stage="evidence_validation", category="field_evidence_requirements",
                    path=f"$.records[].fields.{field_name}",
                )
        if status == "source_not_provided" and (value or original or references):
                raise _contract_error(
                    f"{field_name} source_not_provided must be empty.",
                    stage="evidence_validation", category="field_evidence_requirements",
                    path=f"$.records[].fields.{field_name}",
                )
        if status in {"ambiguous", "invalid"} and value:
                raise _contract_error(
                    f"{field_name} {status} must not publish a value.",
                    stage="evidence_validation", category="field_evidence_requirements",
                    path=f"$.records[].fields.{field_name}",
                )
        referenced_items: list[Mapping[str, Any]] = []
        for evidence_id in references:
            item = evidence.get(evidence_id)
            if item is None:
                raise _contract_error(
                    f"{field_name} references a missing evidence cell.",
                    stage="evidence_validation", category="evidence_id_missing",
                    path=f"$.records[].fields.{field_name}.evidence_references",
                )
            if item["scope_id"] != scope_id:
                raise _contract_error(
                    f"{field_name} references evidence outside its scope.",
                    stage="evidence_validation", category="evidence_cross_scope",
                    path=f"$.records[].fields.{field_name}.evidence_references",
                )
            referenced_items.append(item)
        if original:
            originals = {normalize_evidence_text(str(item["original_text"])) for item in referenced_items}
            if normalize_evidence_text(original) not in originals:
                raise _contract_error(
                    f"{field_name} original_value is not traceable to evidence.",
                    stage="evidence_validation", category="evidence_untraceable",
                    path=f"$.records[].fields.{field_name}.original_value",
                )
        if value and normalize_evidence_text(value) != normalize_evidence_text(original):
            raise _contract_error(
                f"{field_name} value is not traceable through the approved normalizer.",
                stage="evidence_validation", category="evidence_untraceable",
                path=f"$.records[].fields.{field_name}.value",
            )


def _assert_unique(values: list[str], name: str, *, stage: str) -> None:
    if len(values) != len(set(values)):
        raise _contract_error(
            f"Duplicate {name} values are not allowed.",
            stage=stage, category="record_identity_mismatch", path="$.records[].record_local_id",
        )


def _assert_v2_unique(values: list[str], name: str, *, path: str, category: str) -> None:
    if len(values) != len(set(values)):
        raise _contract_error(
            f"Duplicate V2 {name} values are not allowed.",
            stage="v2_hard_contract", category=category, path=path,
        )


def _validate_schema(value: Any, schema: Mapping[str, Any], path: str = "$", *, stage: str) -> None:
    if "const" in schema and value != schema["const"]:
        raise _contract_error(
            f"{path} must equal the schema constant.",
            stage=stage, category="enum_or_constant_mismatch", path=path,
        )
    if "enum" in schema and value not in schema["enum"]:
        raise _contract_error(
            f"{path} contains an unsupported value.",
            stage=stage, category="enum_or_constant_mismatch", path=path,
        )
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            raise _contract_error(f"{path} must be an object.", stage=stage, category="type_mismatch", path=path, expected_type="object", actual_type=_json_type(value))
        properties = schema.get("properties", {})
        missing = [name for name in schema.get("required", []) if name not in value]
        if missing:
            raise _contract_error(f"{path} is missing required fields.", stage=stage, category="missing_required_fields", path=path, missing_fixed_fields=missing)
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                forbidden = sorted(set(extras) & FORBIDDEN_MODEL_FIELD_NAMES)
                raise _contract_error(f"{path} contains extra fields.", stage="forbidden_fields" if forbidden else stage, category="extra_fields", path=path, extra_field_count=len(extras), forbidden_fields=forbidden)
        for name, item in value.items():
            if name in properties:
                _validate_schema(item, properties[name], f"{path}.{name}", stage=stage)
        return
    if expected == "array":
        if not isinstance(value, list):
            raise _contract_error(f"{path} must be an array.", stage=stage, category="type_mismatch", path=path, expected_type="array", actual_type=_json_type(value))
        if len(value) < int(schema.get("minItems", 0)):
            raise _contract_error(
                f"{path} has too few items.",
                stage=stage, category="length_or_range_mismatch", path=path,
            )
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _validate_schema(item, item_schema, f"{path}[{index}]", stage=stage)
        return
    if expected == "string":
        if not isinstance(value, str):
            raise _contract_error(f"{path} must be a string, not null or another type.", stage=stage, category="type_mismatch", path=path, expected_type="string", actual_type=_json_type(value))
        if len(value) < int(schema.get("minLength", 0)):
            raise _contract_error(f"{path} is too short.", stage=stage, category="length_or_range_mismatch", path=path)
        return
    if expected == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise _contract_error(f"{path} must be an integer.", stage=stage, category="type_mismatch", path=path, expected_type="integer", actual_type=_json_type(value))
    elif expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _contract_error(f"{path} must be a number.", stage=stage, category="type_mismatch", path=path, expected_type="number", actual_type=_json_type(value))
    if expected in {"integer", "number"}:
        if "minimum" in schema and value < schema["minimum"]:
            raise _contract_error(f"{path} is below the minimum.", stage=stage, category="length_or_range_mismatch", path=path)
        if "maximum" in schema and value > schema["maximum"]:
            raise _contract_error(f"{path} is above the maximum.", stage=stage, category="length_or_range_mismatch", path=path)


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "other"
