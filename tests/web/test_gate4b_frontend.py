from __future__ import annotations

from pathlib import Path
import re


WEB_ROOT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "bedding_order_parser"
    / "web"
)


def _css_block(css: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\n\}}", css, re.S)
    assert match is not None
    return match.group("body")


def _compact_css(block: str) -> str:
    return re.sub(r"\s+", " ", block)


def test_five_existing_pages_remain_present() -> None:
    script = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    for function in (
        "renderUpload",
        "renderProgress",
        "renderResult",
        "renderMatch",
        "renderHistory",
    ):
        assert f"function {function}" in script or f"async function {function}" in script


def test_ai_is_manual_confirmed_and_never_automatic() -> None:
    script = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert 'api("/api/capabilities")' in script
    assert "state.capabilities.llm?.configured" in script
    assert "允许手动生成 AI 建议" not in script
    assert "allow_ai" not in script
    assert "aiAllowed" not in script
    assert "window.confirm" not in script
    assert "confirmAIReview" in script
    assert "本次仅复核当前订单记录。" in script
    assert "可能产生少量Token费用。" in script
    assert "取消" in script
    assert "确认生成" in script
    assert "/ai-enhance" in script
    assert "不会修改正式订单数据" in script


def test_ai_advisory_states_and_cached_result_remain_visible() -> None:
    script = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    for state in (
        "not_requested",
        "running",
        "completed",
        "failed",
        "cached",
    ):
        assert state in script
    assert "正在生成AI复核建议" in script
    assert "已读取缓存" in script
    assert "suggested_fields" in script
    assert "total_tokens" in script
    assert "历史英文建议" in script
    assert "重新生成中文建议" in script
    assert "regenerate_chinese" in script


def test_reference_match_score_disclaimer_is_exact() -> None:
    script = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert (
        "参考匹配分数未经业务真值标定，不代表准确率或正确概率；"
        "请结合可比较字段、缺失和冲突判断。"
    ) in script


def test_frontend_does_not_claim_business_truth() -> None:
    script = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    for forbidden in (
        "正确编码",
        "已确认正确",
        "自动落码成功",
        "100%正确",
        "精确匹配",
    ):
        assert forbidden not in script
    assert "推荐物料编码" in script
    assert "参考匹配分数" in script
    assert "正确概率" in script


def test_ai_fixed_labels_are_localized_and_evidence_is_collapsed() -> None:
    script = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "static" / "styles.css").read_text(encoding="utf-8")

    for label in (
        "AI复核结论",
        "置信度",
        "建议修改字段",
        "物料评估",
        "主要依据",
        "风险提示",
        "证据来源",
        "Token用量",
        "响应耗时",
        "尝试次数",
        "仅供参考",
    ):
        assert label in script
    for internal, localized in (
        ("insufficient_evidence", "证据不足"),
        ("suggested", "提供候选物料建议"),
        ("no_suggestion", "暂不确认物料编码"),
        ("suggest_change", "建议修改"),
        ("no_change", "无需修改"),
        ("needs_manual_review", "建议人工核查"),
        ("ambiguous", "存在歧义"),
    ):
        assert internal in script
        assert localized in script
    assert '<details class="ai-evidence-details">' in script
    assert "<summary>查看详细证据</summary>" in script
    assert '<details class="ai-evidence-details" open>' not in script
    assert ".ai-confirm-overlay" in styles


def test_all_twenty_business_fields_have_explicit_chinese_labels() -> None:
    script = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")
    fields = (
        "客户",
        "币种",
        "业务员",
        "表头备注",
        "行号",
        "物料编码",
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
        "相似分数",
    )

    for field in fields:
        assert f'"{field}": "{field}"' in script

    for alias in (
        "salesperson",
        "header_note",
        "line_number",
        "quantity",
        "planned_ship_date",
        "similarity_score",
    ):
        assert f"{alias}:" in script


def _standalone_css_block(css: str, selector: str) -> str:
    matches = re.findall(rf"(?:^|\n){re.escape(selector)}\s*\{{(?P<body>.*?)\n\}}", css, re.S)
    assert matches
    return matches[-1]


def test_desktop_shell_fills_webview_window() -> None:
    styles = (WEB_ROOT / "static" / "styles.css").read_text(encoding="utf-8")
    app_shell = _compact_css(_css_block(styles, ".app-shell"))
    workspace = _compact_css(_css_block(styles, ".workspace"))
    body = _compact_css(_standalone_css_block(styles, "body"))

    assert "width: 100%;" in app_shell
    assert "height: 100vh;" in app_shell
    assert "margin: 0;" in app_shell
    assert "border-radius: 0;" in app_shell
    assert "box-shadow: none;" in app_shell
    assert "max-width" not in app_shell
    assert "auto" not in app_shell

    assert "overflow: hidden;" in body
    assert "overflow-y: auto;" in workspace
    assert "overflow-x: hidden;" in workspace

    assert ".app-shell { width: calc(100% - 24px)" not in styles
    assert ".app-shell { width: 100%; min-height: 100vh; margin: 0;" not in styles


def test_page_internal_spacing_remains_intentional() -> None:
    styles = (WEB_ROOT / "static" / "styles.css").read_text(encoding="utf-8")
    assert "width: min(920px, calc(100% - 72px));" in styles
    assert "padding: 42px 0 48px;" in styles
