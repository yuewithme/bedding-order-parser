"""Strict JSON Schemas and dependency-free validation for AI suggestions."""

from __future__ import annotations

from typing import Any, Mapping

from bedding_order_parser.llm.errors import SchemaValidationError


SCHEMA_VERSION = "1.0"
ADVISORY_ACTIONS = (
    "keep_python",
    "suggest_review",
    "insufficient_evidence",
)
MATERIAL_ASSESSMENT_STATUSES = (
    "no_suggestion",
    "suggested",
    "insufficient_evidence",
)

STRING_ARRAY_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {"type": "string"},
}

SUGGESTED_FIELD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "field_name": {"type": "string", "minLength": 1},
        "original_value": {"type": "string"},
        "suggested_value": {"type": "string"},
        "reason": {"type": "string", "minLength": 1},
        "evidence_references": STRING_ARRAY_SCHEMA,
    },
    "required": [
        "field_name",
        "original_value",
        "suggested_value",
        "reason",
        "evidence_references",
    ],
}

MATERIAL_ASSESSMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {
            "type": "string",
            "enum": list(MATERIAL_ASSESSMENT_STATUSES),
        },
        "suggested_material_code": {"type": "string"},
        "reason": {"type": "string", "minLength": 1},
    },
    "required": ["status", "suggested_material_code", "reason"],
}

MODEL_ADVISORY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "source_record_id": {"type": "string", "minLength": 1},
        "action": {"type": "string", "enum": list(ADVISORY_ACTIONS)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "suggested_fields": {
            "type": "array",
            "items": SUGGESTED_FIELD_SCHEMA,
        },
        "material_assessment": MATERIAL_ASSESSMENT_SCHEMA,
        "reasoning_summary": {"type": "string"},
        "warnings": STRING_ARRAY_SCHEMA,
        "evidence_references": STRING_ARRAY_SCHEMA,
    },
    "required": [
        "source_record_id",
        "action",
        "confidence",
        "suggested_fields",
        "material_assessment",
        "reasoning_summary",
        "warnings",
        "evidence_references",
    ],
}

FINAL_ADVISORY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "string", "const": SCHEMA_VERSION},
        "provider": {"type": "string", "minLength": 1},
        "model": {"type": "string"},
        "request_id": {"type": "string"},
        "source_record_id": {"type": "string", "minLength": 1},
        "status": {
            "type": "string",
            "enum": [
                "disabled",
                "not_configured",
                "succeeded",
                "failed",
            ],
        },
        "finish_status": {"type": "string"},
        "action": {"type": "string", "enum": list(ADVISORY_ACTIONS)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "suggested_fields": {
            "type": "array",
            "items": SUGGESTED_FIELD_SCHEMA,
        },
        "material_assessment": MATERIAL_ASSESSMENT_SCHEMA,
        "reasoning_summary": {"type": "string"},
        "warnings": STRING_ARRAY_SCHEMA,
        "evidence_references": STRING_ARRAY_SCHEMA,
        "usage": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "input_tokens": {"type": "integer", "minimum": 0},
                "output_tokens": {"type": "integer", "minimum": 0},
                "total_tokens": {"type": "integer", "minimum": 0},
            },
            "required": [
                "input_tokens",
                "output_tokens",
                "total_tokens",
            ],
        },
        "latency_ms": {"type": "integer", "minimum": 0},
        "attempt_count": {"type": "integer", "minimum": 0},
        "advisory_only": {"type": "boolean", "const": True},
    },
    "required": [
        "schema_version",
        "provider",
        "model",
        "request_id",
        "source_record_id",
        "status",
        "finish_status",
        "action",
        "confidence",
        "suggested_fields",
        "material_assessment",
        "reasoning_summary",
        "warnings",
        "evidence_references",
        "usage",
        "latency_ms",
        "attempt_count",
        "advisory_only",
    ],
}


def validate_model_advisory(
    value: Any, *, expected_source_record_id: str
) -> dict[str, Any]:
    validate_json_schema(value, MODEL_ADVISORY_SCHEMA)
    assert isinstance(value, dict)
    if value["source_record_id"] != expected_source_record_id:
        raise _schema_error(
            "$.source_record_id does not match the requested record.",
            "$.source_record_id",
            error_stage="source_record_id_mismatch",
            source_record_id_match=False,
        )
    material = value["material_assessment"]
    if (
        material["status"] != "suggested"
        and material["suggested_material_code"]
    ):
        raise _schema_error(
            "$.material_assessment.suggested_material_code must be empty "
            "unless status is suggested.",
            "$.material_assessment.suggested_material_code",
            error_stage="schema_validation",
        )
    return value


def validate_final_advisory(value: Any) -> None:
    validate_json_schema(value, FINAL_ADVISORY_SCHEMA)


def validate_json_schema(
    value: Any, schema: Mapping[str, Any], path: str = "$"
) -> None:
    if "const" in schema and value != schema["const"]:
        raise _schema_error(
            f"{path} must equal the schema constant.",
            path,
            error_stage="schema_validation",
        )
    if "enum" in schema and value not in schema["enum"]:
        raise _schema_error(
            f"{path} contains an unsupported value.",
            path,
            error_stage="schema_validation",
            invalid_enum_value=value,
        )

    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, dict):
            raise _type_error(path, "object", value)
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        missing = [name for name in required if name not in value]
        if missing:
            raise _schema_error(
                f"{path} is missing required fields: {', '.join(missing)}.",
                path,
                error_stage="schema_validation",
                missing_keys=missing,
            )
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                raise _schema_error(
                    f"{path} contains extra fields: {', '.join(extras)}.",
                    path,
                    error_stage="schema_validation",
                    extra_keys=extras,
                )
        for name, item in value.items():
            child_schema = properties.get(name)
            if child_schema is not None:
                validate_json_schema(item, child_schema, f"{path}.{name}")
        return

    if expected_type == "array":
        if not isinstance(value, list):
            raise _type_error(path, "array", value)
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                validate_json_schema(item, item_schema, f"{path}[{index}]")
        return

    if expected_type == "string":
        if not isinstance(value, str):
            raise _type_error(path, "string", value)
        if len(value) < int(schema.get("minLength", 0)):
            raise _schema_error(
                f"{path} is too short.",
                path,
                error_stage="schema_validation",
            )
        return

    if expected_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _type_error(path, "number", value)
        _validate_number_bounds(value, schema, path)
        return

    if expected_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise _type_error(path, "integer", value)
        _validate_number_bounds(value, schema, path)
        return

    if expected_type == "boolean" and not isinstance(value, bool):
        raise _type_error(path, "boolean", value)


def _validate_number_bounds(
    value: int | float, schema: Mapping[str, Any], path: str
) -> None:
    if "minimum" in schema and value < schema["minimum"]:
        raise _schema_error(
            f"{path} is below the minimum.",
            path,
            error_stage="schema_validation",
        )
    if "maximum" in schema and value > schema["maximum"]:
        raise _schema_error(
            f"{path} is above the maximum.",
            path,
            error_stage="schema_validation",
        )


def _type_error(path: str, expected_type: str, value: Any) -> SchemaValidationError:
    return _schema_error(
        f"{path} must be a {expected_type}.",
        path,
        error_stage="schema_validation",
        expected_type=expected_type,
        actual_type=_json_type(value),
    )


def _schema_error(
    message: str,
    path: str,
    **diagnostic: Any,
) -> SchemaValidationError:
    payload = {"schema_path": path, **diagnostic}
    return SchemaValidationError(message, path=path, diagnostic=payload)


def _json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
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
    return type(value).__name__
