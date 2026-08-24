from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

from bedding_order_parser.web.services import ARTIFACT_ROLES


WEB_ROOT = Path(__file__).resolve().parents[2] / "src" / "bedding_order_parser" / "web"


def _assets() -> tuple[str, str, str]:
    return (
        (WEB_ROOT / "templates" / "index.html").read_text(encoding="utf-8"),
        (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8"),
        (WEB_ROOT / "static" / "styles.css").read_text(encoding="utf-8"),
    )


def test_help_navigation_and_three_sections_are_present() -> None:
    page, script, _styles = _assets()

    assert 'data-route="help"' in page
    assert 'if (parts[0] === "help") return renderHelp();' in script
    assert "function renderHelp()" in script
    for heading in ("英文术语注释", "软件使用方法", "软件处理流程"):
        assert heading in script
    for target in ("help-terms", "help-usage", "help-flow"):
        assert f'data-help-target="{target}"' in script
        assert f'aria-controls="{target}"' in script
    assert 'href="#help-' not in script


def test_help_terms_use_existing_roles_and_safe_user_visible_keys() -> None:
    _page, script, _styles = _assets()

    for role in ARTIFACT_ROLES:
        assert role in script
    for key in (
        "material_code",
        "similarity_score",
        "source_cells",
        "validation_only",
        "candidates",
        "accuracy_statement",
        "awaiting_user_decision",
    ):
        assert key in script
    assert "不代表绝对准确率或正确概率" in script
    assert "Authorization" not in script
    assert "API Key" not in script


def test_help_includes_both_modes_and_user_workflows() -> None:
    _page, script, _styles = _assets()

    for text in (
        "上传 Excel",
        "阅读并确认提示",
        "查看任务进度",
        "查看五类结果",
        "预览或下载文件",
        "标准解析当前支持完整结果 ZIP",
        "Excel 导出以界面可用状态为准",
        "使用历史记录",
        "使用本地 Python 规则提取订单字段",
        "使用 AI 理解订单内容",
        "该功能仍在持续优化",
        "物料 TopK 候选匹配",
        "本地验证和对照",
    ):
        assert text in script


def test_help_route_is_render_only_and_has_narrow_layout_rules() -> None:
    _page, script, styles = _assets()
    help_function = script.split("function renderHelp()", 1)[1].split("function renderUpload()", 1)[0]

    assert "api(" not in help_function
    assert "help-entry-grid" in styles
    assert ".help-term-row { grid-template-columns: 1fr; gap: 3px; }" in styles
    assert ".help-entry-grid," in styles


def test_help_entry_clicks_scroll_without_changing_the_help_route() -> None:
    _page, script, _styles = _assets()
    start = script.index("function scrollToHelpSection(")
    end = script.index("function renderHelp()", start)
    navigation_source = script[start:end]
    node_program = f"""
      const assert = require("node:assert/strict");
      const calls = [];
      const targets = new Map(["help-terms", "help-usage", "help-flow"].map((id) => [id, {{
        scrollIntoView(options) {{ calls.push([id, options]); }},
      }}]));
      const entries = ["help-terms", "help-usage", "help-flow", "missing-target"].map((target) => ({{
        dataset: {{ helpTarget: target }},
        handlers: {{}},
        addEventListener(name, handler) {{ this.handlers[name] = handler; }},
      }}));
      let apiCalls = 0;
      let jobCreations = 0;
      global.api = () => {{ apiCalls += 1; }};
      global.createJob = () => {{ jobCreations += 1; }};
      global.window = {{ location: {{ hash: "#help" }} }};
      global.document = {{
        getElementById(id) {{ return targets.get(id) || null; }},
        querySelectorAll(selector) {{
          assert.equal(selector, ".help-entry-link[data-help-target]");
          return entries;
        }},
      }};
      {navigation_source}
      bindHelpEntryNavigation(document);
      for (const entry of entries.slice(0, 3)) {{
        assert.equal(typeof entry.handlers.click, "function");
        entry.handlers.click({{ currentTarget: entry }});
        entry.handlers.click({{ currentTarget: entry, keyboard: true }});
      }}
      entries[3].handlers.click({{ currentTarget: entries[3] }});
      assert.deepEqual(calls, [
        ["help-terms", {{ behavior: "smooth", block: "start" }}],
        ["help-terms", {{ behavior: "smooth", block: "start" }}],
        ["help-usage", {{ behavior: "smooth", block: "start" }}],
        ["help-usage", {{ behavior: "smooth", block: "start" }}],
        ["help-flow", {{ behavior: "smooth", block: "start" }}],
        ["help-flow", {{ behavior: "smooth", block: "start" }}],
      ]);
      assert.equal(window.location.hash, "#help");
      assert.equal(apiCalls, 0);
      assert.equal(jobCreations, 0);
    """

    result = subprocess.run(
        ["node", "-e", textwrap.dedent(node_program)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
