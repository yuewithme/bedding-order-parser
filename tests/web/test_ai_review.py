from __future__ import annotations

import json

from bedding_order_parser.ai_full_order.contracts import AI_BUSINESS_FIELD_NAMES
from bedding_order_parser.web.ai_review import (
    ai_review_summary,
    build_ai_review_view,
    unavailable_ai_review,
)


def _field(
    name: str,
    *,
    comparison: str = "agree",
    source: str = "ai",
    review: bool = False,
    severity: str = "none",
    technical: str = "bound",
) -> dict[str, object]:
    ai_value = "Synthetic AI value"
    python_value = ai_value
    formal = ai_value
    if comparison == "different":
        python_value = "Synthetic local value"
    elif comparison == "ai_only":
        python_value = ""
    elif comparison == "python_fill":
        ai_value = ""
        formal = python_value = "Synthetic local fill"
    elif comparison == "both_missing":
        ai_value = python_value = formal = ""
    return {
        "field_name": name,
        "formal_value": formal,
        "ai_display_value": ai_value,
        "ai_normalized_value": ai_value,
        "ai_evidence_ids": ["ev-safe"] if ai_value else [],
        "ai_supporting_quote": "Synthetic quote" if ai_value else "",
        "python_display_value": python_value,
        "python_normalized_value": python_value,
        "python_evidence_ids": ["ev-safe"] if python_value else [],
        "comparison_status": comparison,
        "status": "resolved",
        "selected_source": source,
        "review_required": review,
        "review_severity": severity,
        "reason_codes": ["safe_reason"],
        "technical_candidate_status": technical,
        "candidate_issue_code": "",
        "raw_response": "must never escape",
        "cache_identity": "must never escape",
    }


def _diagnostic() -> dict[str, object]:
    fields = {name: _field(name) for name in AI_BUSINESS_FIELD_NAMES}
    fields["客户"] = _field(
        "客户", comparison="different", review=True, severity="high"
    )
    fields["包装方式"] = _field(
        "包装方式",
        comparison="python_fill",
        source="python_fallback",
        review=True,
        severity="medium",
        technical="content_issue",
    )
    fields["颜色"] = _field(
        "颜色", comparison="different", review=True, severity="medium"
    )
    fields["物料名称"] = _field(
        "物料名称", comparison="ai_only", review=True, severity="medium"
    )
    fields["尺寸类型"] = _field(
        "尺寸类型",
        comparison="both_missing",
        source="none",
        review=True,
        severity="medium",
        technical="not_provided",
    )
    fields["面料"] = _field("面料", comparison="equivalent_after_normalization")
    return {
        "ai_enhanced": {
            "protocol": "v2",
            "technical_readiness": {"technical_ready": True},
            "field_decisions": [{"line_number": "6", "fields": fields}],
            "evidence_display": {
                "ev-safe": {
                    "sheet_id": "sheet-001",
                    "sheet_name": "Synthetic PI",
                    "cell_range": "B6:E6",
                    "source_row": 6,
                    "excerpt": "Synthetic bedding order excerpt",
                    "local_path": "C:/secret/order.xlsx",
                }
            },
            "provider_raw_response": "must never escape",
            "authorization": "must never escape",
        }
    }


def test_review_adapter_exposes_review_summary_and_safe_evidence_only() -> None:
    view = build_ai_review_view(_diagnostic())
    summary = ai_review_summary(view)

    assert view["available"] is True
    assert summary["technical_ready"] is True
    assert summary["review_required_count"] == 5
    assert summary["high_review_count"] == 1
    assert summary["has_unreviewed_differences"] is True
    assert summary["comparison_summary"]["different"] == 2
    assert summary["comparison_summary"]["ai_only"] == 1
    assert summary["comparison_summary"]["both_missing"] == 1
    assert summary["comparison_summary"]["equivalent_after_normalization"] == 1
    assert summary["python_fill_count"] == 1
    customer = next(item for item in view["items"] if item["field_name"] == "客户")
    assert customer["formal_value"] == "Synthetic AI value"
    assert customer["selected_source"] == "ai"
    assert customer["review_severity"] == "high"
    assert customer["ai_evidence"] == [
        {
            "sheet_name": "Synthetic PI",
            "sheet_id": "sheet-001",
            "cell_range": "B6:E6",
            "source_row": 6,
            "excerpt": "Synthetic bedding order excerpt",
        }
    ]
    serialized = json.dumps(view, ensure_ascii=False).lower()
    assert "ev-safe" not in serialized
    assert "raw_response" not in serialized
    assert "cache_identity" not in serialized
    assert "authorization" not in serialized
    assert "c:/secret" not in serialized


def test_review_adapter_rejects_unknown_enums_and_supports_historical_views() -> None:
    diagnostic = _diagnostic()
    diagnostic["ai_enhanced"]["field_decisions"][0]["fields"]["客户"][
        "comparison_status"
    ] = "model_invented_status"

    view = build_ai_review_view(diagnostic)
    names = {item["field_name"] for item in view["items"]}
    legacy = unavailable_ai_review(
        applicable=True,
        message="历史任务没有字段对照数据。",
        historical_attention_count=3,
    )

    assert "客户" not in names
    assert "model_invented_status" not in json.dumps(view, ensure_ascii=False)
    assert legacy["available"] is False
    assert legacy["summary"]["historical_attention_count"] == 3

    old_v2 = build_ai_review_view(
        {"ai_enhanced": {"protocol": "v2", "technical_readiness": {"technical_ready": True}}}
    )
    assert old_v2["available"] is False
    assert "对照" in old_v2["compatibility_message"]


def test_standard_review_view_is_explicitly_not_applicable() -> None:
    view = unavailable_ai_review(
        applicable=False,
        message="标准解析不展示 AI 整单字段对照。",
    )

    assert ai_review_summary(view) == {
        "applicable": False,
        "available": False,
        "compatibility_message": "标准解析不展示 AI 整单字段对照。",
        "technical_ready": False,
        "review_required_count": 0,
        "high_review_count": 0,
        "has_unreviewed_differences": False,
        "comparison_summary": {},
        "python_fill_count": 0,
        "ai_only_count": 0,
        "content_issue_count": 0,
        "historical_attention_count": 0,
    }
