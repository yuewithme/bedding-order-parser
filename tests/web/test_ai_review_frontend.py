from __future__ import annotations

import json
import subprocess
from pathlib import Path


APP_JS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "bedding_order_parser"
    / "web"
    / "static"
    / "app.js"
)


def test_ai_review_renderer_and_interactions_execute_with_fake_dom() -> None:
    script = r"""
const fs = require("fs");
const source = fs.readFileSync(process.argv[1], "utf8");

function extractFunction(name) {
  const marker = `function ${name}(`;
  const start = source.indexOf(marker);
  if (start < 0) throw new Error(`missing ${name}`);
  const brace = source.indexOf("{", start);
  let depth = 0;
  for (let index = brace; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  throw new Error(`unterminated ${name}`);
}

function extractConst(name) {
  const marker = `const ${name} = `;
  const start = source.indexOf(marker);
  if (start < 0) throw new Error(`missing ${name}`);
  const valueStart = start + marker.length;
  const terminator = source.slice(valueStart).match(/;\r?\n/);
  if (!terminator) throw new Error(`unterminated ${name}`);
  const end = valueStart + terminator.index;
  return new Function(`return (${source.slice(valueStart, end)});`)();
}

const functions = [
  "reviewValue", "reviewEvidence", "reviewStatusText", "renderAIReviewItem",
  "renderAIReviewSection", "applyAIReviewFilter", "bindKeyboardActivation",
  "bindAIReviewInteractions",
].map(extractFunction).join("\n");
const runtime = new Function(
  "aiComparisonCopy", "aiSelectedSourceCopy", "aiReviewStatusCopy", "escapeHtml",
  `${functions}; return {renderAIReviewSection, applyAIReviewFilter, bindAIReviewInteractions};`
)(
  extractConst("aiComparisonCopy"),
  extractConst("aiSelectedSourceCopy"),
  extractConst("aiReviewStatusCopy"),
  (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;"),
);

class FakeElement {
  constructor(dataset = {}) {
    this.dataset = dataset;
    this.attributes = {};
    this.hidden = false;
    this.textContent = "";
    this.listeners = {};
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || null; }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  click() { this.listeners.click(); }
  press(key) { this.listeners.keydown({key, preventDefault() {}}); }
}

const filters = ["review", "high", "python_fill", "all"].map((value) => new FakeElement({reviewFilter: value}));
const items = [
  new FakeElement({reviewRequired: "true", reviewSeverity: "high", selectedSource: "ai"}),
  new FakeElement({reviewRequired: "true", reviewSeverity: "medium", selectedSource: "python_fallback"}),
  new FakeElement({reviewRequired: "false", reviewSeverity: "none", selectedSource: "ai"}),
];
const toggle = new FakeElement({reviewTarget: "detail-1"});
toggle.setAttribute("aria-expanded", "false");
const panel = new FakeElement();
panel.hidden = true;
const empty = new FakeElement();
const section = new FakeElement({defaultReviewFilter: "review"});
section.querySelectorAll = (selector) => selector === "[data-review-filter]" ? filters : selector === ".review-item" ? items : selector === ".review-detail-toggle" ? [toggle] : [];
section.querySelector = (selector) => selector === ".review-empty" ? empty : selector === '[data-review-panel="detail-1"]' ? panel : null;
const root = {querySelector: (selector) => selector === "[data-ai-review]" ? section : null};
const initialHash = "#job/synthetic/result";
let hash = initialHash;
let apiCalls = 0;
let jobCreates = 0;

runtime.bindAIReviewInteractions(root);
if (items.map((item) => item.hidden).join(",") !== "false,false,true") throw new Error("default review filter failed");
filters[1].click();
if (items.map((item) => item.hidden).join(",") !== "false,true,true") throw new Error("high filter failed");
filters[2].click();
if (items.map((item) => item.hidden).join(",") !== "true,false,true") throw new Error("python fill filter failed");
filters[3].click();
if (items.some((item) => item.hidden)) throw new Error("all filter failed");
filters[1].press("Enter");
if (items.map((item) => item.hidden).join(",") !== "false,true,true") throw new Error("keyboard high filter failed");
filters[3].press(" ");
if (items.some((item) => item.hidden)) throw new Error("keyboard all filter failed");
toggle.click();
if (panel.hidden || toggle.getAttribute("aria-expanded") !== "true") throw new Error("detail expansion failed");
toggle.press(" ");
if (!panel.hidden || toggle.getAttribute("aria-expanded") !== "false") throw new Error("keyboard detail toggle failed");
if (hash !== initialHash || apiCalls !== 0 || jobCreates !== 0) throw new Error("review interaction changed route or called backend");

const review = {
  applicable: true,
  available: true,
  summary: {review_required_count: 2, high_review_count: 1, python_fill_count: 1},
  items: [{
    record_index: 1, line_number: "6", field_name: "客户", formal_value: "AI Hotel",
    ai_display_value: "AI Hotel", ai_normalized_value: "AI Hotel",
    python_display_value: "Local Hotel", comparison_status: "different",
    selected_source: "ai", review_required: true, review_severity: "high",
    content_issue: false, ai_supporting_quote: "AI Hotel",
    ai_evidence: [{sheet_name: "PI", cell_range: "B6", excerpt: "AI Hotel"}],
    python_evidence: [{sheet_name: "PI", cell_range: "A6:E6", excerpt: "Local Hotel"}],
  }],
};
const html = runtime.renderAIReviewSection(review);
for (const expected of ["AI 与本地规则对照", "正式结果已经生成", "高风险 · 建议重点核对", "当前采用：AI", "AI 来源", "本地规则来源", "PI · B6"]) {
  if (!html.includes(expected)) throw new Error(`missing rendered copy: ${expected}`);
}
if (!html.includes('<button data-review-filter="review"') || !html.includes('type="button"')) throw new Error("filters are not semantic buttons");
for (const [status, expected] of Object.entries({
  agree: "AI 与本地规则一致",
  equivalent_after_normalization: "表达形式不同，含义一致",
  different: "AI 与本地规则不一致，建议核对原订单",
  ai_only: "仅 AI 识别到此字段",
  python_fill: "AI 未识别，本字段由本地规则补全",
  both_missing: "AI 与本地规则均未识别到此字段",
})) {
  const item = {...review.items[0], comparison_status: status, content_issue: false};
  if (!runtime.renderAIReviewSection({...review, items: [item]}).includes(expected)) throw new Error(`missing status copy: ${status}`);
}
const contentIssue = {...review.items[0], content_issue: true};
if (!runtime.renderAIReviewSection({...review, items: [contentIssue]}).includes("证据不足，未作为正式值")) throw new Error("missing content issue copy");
if (runtime.renderAIReviewSection({applicable: false}) !== "") throw new Error("standard result must not render AI review");
process.stdout.write(JSON.stringify({filters: 4, items: 3, route: hash, apiCalls, jobCreates}));
"""
    result = subprocess.run(
        ["node", "-e", script, str(APP_JS)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert json.loads(result.stdout) == {
        "filters": 4,
        "items": 3,
        "route": "#job/synthetic/result",
        "apiCalls": 0,
        "jobCreates": 0,
    }


def test_revision_action_executes_api_refresh_and_keyboard_path_with_fake_dom() -> None:
    script = r"""
const fs = require("fs");
const source = fs.readFileSync(process.argv[1], "utf8");
function extractFunction(name) {
  const start = source.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`missing ${name}`);
  const brace = source.indexOf("{", start);
  let depth = 0;
  for (let index = brace; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  throw new Error(`unterminated ${name}`);
}

class FakeElement {
  constructor(dataset = {}) {
    this.dataset = dataset;
    this.attributes = {};
    this.hidden = false;
    this.disabled = false;
    this.value = "";
    this.listeners = {};
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || null; }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  click() { this.lastPromise = this.listeners.click?.(); return this.lastPromise; }
  press(key) { this.listeners.keydown?.({key, preventDefault() {}}); return this.lastPromise; }
  focus() { this.focused = true; }
}

const functions = ["applyAIReviewFilter", "bindKeyboardActivation", "bindAIReviewInteractions"].map(extractFunction).join("\n");
const state = {actionSubmitting: false};
const apiCalls = [];
const renders = [];
const toasts = [];
const api = async (path, options) => { apiCalls.push({path, body: JSON.parse(options.body)}); return {revision: {reused: false}}; };
const renderResult = async (jobId) => { renders.push(jobId); };
const showToast = (message) => { toasts.push(message); };
const runtime = new Function("state", "api", "renderResult", "showToast", `${functions}; return {bindAIReviewInteractions};`)(state, api, renderResult, showToast);

const filter = new FakeElement({reviewFilter: "review"});
const itemElement = new FakeElement({reviewRequired: "true", reviewSeverity: "high", selectedSource: "ai"});
const usePython = new FakeElement({revisionAction: "use_python", reviewIndex: "0"});
const manualSave = new FakeElement({revisionAction: "manual_override", reviewIndex: "0"});
const manualToggle = new FakeElement({reviewEditor: "editor-0"});
manualToggle.setAttribute("aria-expanded", "false");
const input = new FakeElement();
input.value = "Manual Hotel";
const editor = new FakeElement();
editor.hidden = true;
editor.querySelector = (selector) => selector === "input" ? input : null;
const empty = new FakeElement();
const section = new FakeElement({defaultReviewFilter: "review"});
section.querySelectorAll = (selector) => ({
  "[data-review-filter]": [filter],
  ".review-item": [itemElement],
  ".review-detail-toggle": [],
  ".revision-edit-toggle": [manualToggle],
  ".revision-action": [usePython, manualSave],
}[selector] || []);
section.querySelector = (selector) => {
  if (selector === ".review-empty") return empty;
  if (selector === '[data-review-editor-panel="editor-0"]') return editor;
  if (selector === '[data-review-manual-input="0"]') return input;
  return null;
};
const root = {querySelector: (selector) => selector === "[data-ai-review]" ? section : null};
const review = {
  revision: {current_revision: "a".repeat(64)},
  items: [{source_record_id: "record-1", field_name: "客户"}],
};
const job = {id: "job-1"};

(async () => {
  runtime.bindAIReviewInteractions(root, review, job);
  manualToggle.press(" ");
  if (editor.hidden || !input.focused) throw new Error("manual editor keyboard toggle failed");
  await usePython.press("Enter");
  if (apiCalls.length !== 1 || renders.join(",") !== "job-1") throw new Error("revision action did not refresh result");
  const submitted = apiCalls[0];
  if (submitted.path !== "/api/jobs/job-1/ai-review/revisions") throw new Error("wrong revision endpoint");
  if (submitted.body.action !== "use_python" || submitted.body.field_name !== "客户" || submitted.body.source_record_id !== "record-1") throw new Error("wrong revision whitelist body");
  if (submitted.body.expected_current_revision !== "a".repeat(64) || submitted.body.manual_value !== "") throw new Error("wrong optimistic concurrency body");
  if (!toasts[0]?.includes("修改已保存")) throw new Error("missing saved confirmation");

  state.actionSubmitting = false;
  usePython.disabled = false;
  manualSave.disabled = false;
  await manualSave.click();
  if (apiCalls[1].body.action !== "manual_override" || apiCalls[1].body.manual_value !== "Manual Hotel") throw new Error("manual override body failed");
  process.stdout.write(JSON.stringify({apiCalls: apiCalls.length, renders: renders.length, keyboard: true, manual: true}));
})().catch((error) => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        ["node", "-e", script, str(APP_JS)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert json.loads(result.stdout) == {
        "apiCalls": 2,
        "renders": 2,
        "keyboard": True,
        "manual": True,
    }
