from __future__ import annotations

from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2] / "src" / "bedding_order_parser" / "web"


def test_dual_mode_upload_and_preflight_are_explicit() -> None:
    script = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert 'selectedParseMode: "standard"' in script
    assert 'value="standard"' in script
    assert 'value="ai_enhanced"' in script
    assert 'api("/api/ai-enhanced/preflight")' in script
    assert "await loadAIEnhancedPreflight();" in script
    assert 'form.append("parse_mode", mode);' in script
    assert "allow_ai" not in script
    assert "aiAllowed" not in script


def test_ai_confirmation_and_decision_actions_remain_user_confirmed() -> None:
    script = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert "confirmAIEnhanced" in script
    assert "aiFullConsent" in script
    assert "不发送 Excel 二进制" in script
    assert "当前无法可靠估算" in script
    assert "if (!confirmed)" in script
    assert "reprocess-standard" in script
    assert "createReprocessOperationId" in script
    assert "X-Idempotency-Key" in script
    assert "回退为标准解析" not in script
    assert "retry" in script and "keep-failed" in script
    assert "state.submitting" in script
    assert "state.actionSubmitting" in script


def test_ai_result_roles_history_and_sidecar_boundary_are_visible() -> None:
    script = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "static" / "styles.css").read_text(encoding="utf-8")

    for role in (
        "official_result",
        "parse_diagnostics",
        "dictionary_validation",
        "material_candidates",
        "material_summary",
    ):
        assert role in script
    assert "ai_full_order.json" not in script
    assert "modeFilter" in script
    assert "标准解析（历史任务）" in script
    assert "AI增强整单解析不会自动触发单记录AI复核。" in script
    for selector in (
        ".parse-mode-picker",
        ".mode-choice",
        ".ai-confirm-overlay",
        ".ai-job-details",
        ".decision-panel",
        ".mode-chip",
        ".artifact-grid-five",
    ):
        assert selector in styles
