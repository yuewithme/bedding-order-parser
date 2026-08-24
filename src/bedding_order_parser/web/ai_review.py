"""Safe, user-facing review views derived from published V2 diagnostics."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from bedding_order_parser.ai_full_order.contracts import AI_BUSINESS_FIELD_NAMES


COMPARISON_STATUSES = frozenset(
    {
        "agree",
        "equivalent_after_normalization",
        "different",
        "ai_only",
        "python_fill",
        "both_missing",
    }
)
SELECTED_SOURCES = frozenset(
    {"ai", "python_fallback", "none", "user_selected_python", "user_override"}
)
REVIEW_SEVERITIES = frozenset({"none", "medium", "high"})
TECHNICAL_CANDIDATE_STATUSES = frozenset({"not_provided", "bound", "content_issue"})
REVIEW_STATUSES = frozenset(
    {"not_required", "unreviewed", "confirmed_ai", "selected_python", "manual_override"}
)
MAX_VALUE_CHARS = 2_000
MAX_EVIDENCE_ITEMS = 12
MAX_EXCERPT_CHARS = 180


def unavailable_ai_review(
    *,
    applicable: bool,
    message: str,
    historical_attention_count: int = 0,
) -> dict[str, Any]:
    return {
        "applicable": applicable,
        "available": False,
        "compatibility_message": message,
        "summary": {
            "technical_ready": False,
            "review_required_count": 0,
            "high_review_count": 0,
            "has_unreviewed_differences": False,
            "comparison_summary": {},
            "python_fill_count": 0,
            "ai_only_count": 0,
            "content_issue_count": 0,
            "historical_attention_count": max(0, int(historical_attention_count)),
        },
        "items": [],
        "revision": {
            "supported": False,
            "initial_revision": "",
            "current_revision": "",
            "revision_number": 0,
        },
    }


def build_ai_review_view(diagnostic: Any) -> dict[str, Any]:
    """Convert published diagnostics into a strict UI/API whitelist."""

    if not isinstance(diagnostic, Mapping):
        return unavailable_ai_review(
            applicable=True,
            message="该任务的解析诊断无法读取，暂时不能展示字段对照。",
        )
    envelope = diagnostic.get("ai_enhanced")
    if not isinstance(envelope, Mapping) or envelope.get("protocol") != "v2":
        return unavailable_ai_review(
            applicable=True,
            message="该历史任务没有可用的 AI 与本地规则对照数据。",
        )
    rows = envelope.get("field_decisions")
    if not isinstance(rows, list):
        return unavailable_ai_review(
            applicable=True,
            message="该历史 V2 任务生成于对照功能上线之前，无法还原字段差异。",
        )
    evidence_catalog = envelope.get("evidence_display")
    if not isinstance(evidence_catalog, Mapping):
        evidence_catalog = {}
    raw_revision = envelope.get("publication_revision")
    revision = _safe_revision(raw_revision)

    items: list[dict[str, Any]] = []
    for record_index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            continue
        fields = row.get("fields")
        if not isinstance(fields, Mapping):
            continue
        line_number = _text(row.get("line_number"), 80)
        for field_name in AI_BUSINESS_FIELD_NAMES:
            raw = fields.get(field_name)
            item = _safe_field_item(
                raw,
                field_name=field_name,
                record_index=record_index,
                line_number=line_number,
                source_record_id=_text(row.get("source_record_id"), 160),
                evidence_catalog=evidence_catalog,
                revision_supported=revision["supported"],
            )
            if item is not None:
                items.append(item)

    if not items:
        return unavailable_ai_review(
            applicable=True,
            message="该历史 V2 任务没有完整的字段对照数据，结果文件仍可正常查看。",
        )

    items.sort(
        key=lambda item: (
            not item["review_required"],
            item["review_severity"] != "high",
            item["record_index"],
            AI_BUSINESS_FIELD_NAMES.index(item["field_name"]),
        )
    )
    comparisons = Counter(item["comparison_status"] for item in items)
    review_count = sum(item["review_required"] for item in items)
    high_count = sum(
        item["review_required"] and item["review_severity"] == "high"
        for item in items
    )
    technical = envelope.get("technical_readiness")
    technical_ready = isinstance(technical, Mapping) and technical.get("technical_ready") is True
    return {
        "applicable": True,
        "available": True,
        "compatibility_message": "",
        "summary": {
            "technical_ready": technical_ready,
            "review_required_count": review_count,
            "high_review_count": high_count,
            "has_unreviewed_differences": review_count > 0,
            "comparison_summary": dict(sorted(comparisons.items())),
            "python_fill_count": sum(
                item["selected_source"] == "python_fallback" for item in items
            ),
            "ai_only_count": comparisons["ai_only"],
            "content_issue_count": sum(item["content_issue"] for item in items),
            "historical_attention_count": 0,
        },
        "items": items,
        "revision": revision,
    }


def ai_review_summary(view: Mapping[str, Any]) -> dict[str, Any]:
    summary = view.get("summary")
    safe_summary = dict(summary) if isinstance(summary, Mapping) else {}
    return {
        "applicable": view.get("applicable") is True,
        "available": view.get("available") is True,
        "compatibility_message": _text(view.get("compatibility_message"), 240),
        "technical_ready": safe_summary.get("technical_ready") is True,
        "review_required_count": _count(safe_summary.get("review_required_count")),
        "high_review_count": _count(safe_summary.get("high_review_count")),
        "has_unreviewed_differences": (
            safe_summary.get("has_unreviewed_differences") is True
        ),
        "comparison_summary": _safe_comparison_counts(
            safe_summary.get("comparison_summary")
        ),
        "python_fill_count": _count(safe_summary.get("python_fill_count")),
        "ai_only_count": _count(safe_summary.get("ai_only_count")),
        "content_issue_count": _count(safe_summary.get("content_issue_count")),
        "historical_attention_count": _count(
            safe_summary.get("historical_attention_count")
        ),
    }


def _safe_field_item(
    value: Any,
    *,
    field_name: str,
    record_index: int,
    line_number: str,
    source_record_id: str,
    evidence_catalog: Mapping[str, Any],
    revision_supported: bool,
) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    comparison_status = _enum(value.get("comparison_status"), COMPARISON_STATUSES)
    selected_source = _enum(value.get("selected_source"), SELECTED_SOURCES)
    review_severity = _enum(value.get("review_severity"), REVIEW_SEVERITIES)
    technical_status = _enum(
        value.get("technical_candidate_status"), TECHNICAL_CANDIDATE_STATUSES
    )
    if not all((comparison_status, selected_source, review_severity, technical_status)):
        return None
    review_status = _enum(value.get("review_status"), REVIEW_STATUSES)
    if not review_status:
        review_status = (
            "unreviewed" if value.get("review_required") is True else "not_required"
        )
    ai_value = _text(value.get("ai_display_value"), MAX_VALUE_CHARS)
    python_value = _text(value.get("python_display_value"), MAX_VALUE_CHARS)
    actions = {
        "keep_ai": (
            revision_supported and technical_status == "bound" and bool(ai_value)
        ),
        "use_python": revision_supported and bool(python_value),
        "manual_override": revision_supported,
    }
    return {
        "record_index": record_index,
        "source_record_id": source_record_id,
        "line_number": line_number,
        "field_name": field_name,
        "formal_value": _text(value.get("formal_value"), MAX_VALUE_CHARS),
        "ai_display_value": ai_value,
        "ai_normalized_value": _text(
            value.get("ai_normalized_value"), MAX_VALUE_CHARS
        ),
        "python_display_value": python_value,
        "python_normalized_value": _text(
            value.get("python_normalized_value"), MAX_VALUE_CHARS
        ),
        "comparison_status": comparison_status,
        "selected_source": selected_source,
        "review_required": value.get("review_required") is True,
        "review_severity": review_severity,
        "content_issue": technical_status == "content_issue",
        "original_review_required": (
            value.get("original_review_required") is True
            or value.get("review_required") is True
        ),
        "review_status": review_status,
        "available_actions": actions,
        "user_revision": _safe_user_revision(value.get("user_revision")),
        "ai_supporting_quote": _text(
            value.get("ai_supporting_quote"), MAX_EXCERPT_CHARS
        ),
        "ai_evidence": _safe_evidence_views(
            value.get("ai_evidence_ids"), evidence_catalog
        ),
        "python_evidence": _safe_evidence_views(
            value.get("python_evidence_ids"), evidence_catalog
        ),
    }


def _safe_revision(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "supported": False,
            "initial_revision": "",
            "current_revision": "",
            "revision_number": 0,
        }
    revision_id = _identity(value.get("revision_id"))
    initial = _identity(value.get("initial_revision"))
    number = value.get("revision_number")
    if not revision_id or not initial or not isinstance(number, int) or number < 0:
        return {
            "supported": False,
            "initial_revision": "",
            "current_revision": "",
            "revision_number": 0,
        }
    return {
        "supported": True,
        "initial_revision": initial,
        "current_revision": revision_id,
        "revision_number": number,
    }


def _safe_user_revision(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    action = str(value.get("action", ""))
    if action not in {"keep_ai", "use_python", "manual_override"}:
        return {}
    return {
        "action": action,
        "selected_source": str(value.get("selected_source", ""))[:40],
        "user_display_value": _text(value.get("user_display_value"), MAX_VALUE_CHARS),
        "user_normalized_value": _text(
            value.get("user_normalized_value"), MAX_VALUE_CHARS
        ),
        "normalization_rule": str(value.get("normalization_rule", ""))[:80],
    }


def _identity(value: Any) -> str:
    text = value if isinstance(value, str) else ""
    return text if len(text) == 64 and all(char in "0123456789abcdef" for char in text) else ""


def _safe_evidence_views(value: Any, catalog: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_id in value[:MAX_EVIDENCE_ITEMS]:
        evidence_id = raw_id if isinstance(raw_id, str) else ""
        if not evidence_id or evidence_id in seen:
            continue
        seen.add(evidence_id)
        raw = catalog.get(evidence_id)
        if not isinstance(raw, Mapping):
            continue
        source_row = raw.get("source_row")
        result.append(
            {
                "sheet_name": _text(raw.get("sheet_name"), 120),
                "sheet_id": _text(raw.get("sheet_id"), 80),
                "cell_range": _text(raw.get("cell_range"), 80),
                "source_row": (
                    source_row
                    if isinstance(source_row, int) and not isinstance(source_row, bool)
                    else 0
                ),
                "excerpt": _text(raw.get("excerpt"), MAX_EXCERPT_CHARS),
            }
        )
    return result


def _safe_comparison_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {
        status: _count(value.get(status))
        for status in sorted(COMPARISON_STATUSES)
        if _count(value.get(status))
    }


def _enum(value: Any, allowed: frozenset[str]) -> str:
    text = value if isinstance(value, str) else ""
    return text if text in allowed else ""


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value[:limit]
