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


def test_progress_presentation_renders_the_persisted_ai_stage_and_five_step_states() -> None:
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

const runtime = new Function(
  "aiStageLabels", "escapeHtml", "icon",
  `${extractFunction("stageRows")}\n${extractFunction("progressPresentation")}; return {stageRows, progressPresentation};`
)(
  extractConst("aiStageLabels"),
  (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;"),
  () => "<check>",
);

const names = ["文件读取", "订单字段提取", "字典校验", "物料匹配", "结果生成"];
function stages(active, complete = false) {
  return names.map((name, index) => ({name, status: complete || index < active ? "completed" : index === active ? "processing" : "waiting"}));
}
const cases = [
  ["structure_resolution", 12, "正在确认表格结构", 0],
  ["ai_extraction", 42, "正在提取订单候选字段", 1],
  ["dictionary_validation", 82, "正在验证业务字段", 2],
  ["material_matching", 88, "正在匹配参考物料", 3],
  ["publication", 94, "正在生成结果", 4],
  ["completed", 100, "解析完成", 4, true],
];
for (const [stage, progress, label, active, complete] of cases) {
  const job = {
    parse_mode: "ai_enhanced",
    progress,
    current_stage: label,
    ai_execution: {stage},
    stages: stages(active, complete),
  };
  const view = runtime.progressPresentation(job);
  if (view.currentStage !== label || view.progress !== progress) throw new Error(`left presentation mismatch: ${stage}`);
  const statuses = view.stages.map((item) => item.status);
  if (statuses[active] !== "processing" && !complete) throw new Error(`active five-step mismatch: ${stage}`);
  if (!complete && statuses.slice(active + 1).some((value) => value !== "waiting")) throw new Error(`future stage mismatch: ${stage}`);
  if (!complete && statuses.slice(0, active).some((value) => value !== "completed")) throw new Error(`prior stage mismatch: ${stage}`);
  if (complete && statuses.some((value) => value !== "completed")) throw new Error("completed stages mismatch");
  const html = runtime.stageRows(view.stages);
  if (!complete && !html.includes('stage-row processing')) throw new Error(`processing row missing: ${stage}`);
  if (!complete && !html.includes("进行中")) throw new Error(`processing label missing: ${stage}`);
}
const legacy = runtime.progressPresentation({parse_mode: "ai_enhanced", progress: 12, current_stage: "structure_resolution", ai_execution: {stage: "structure_resolution"}, stages: stages(0)});
if (legacy.currentStage !== "正在确认表格结构") throw new Error("legacy stage fallback failed");
const standard = runtime.progressPresentation({parse_mode: "standard", progress: 70, current_stage: "正在物料匹配", stages: stages(3)});
if (standard.currentStage !== "正在物料匹配") throw new Error("standard presentation changed");
process.stdout.write(JSON.stringify({cases: cases.length, standard: standard.currentStage, legacy: legacy.currentStage}));
"""
    result = subprocess.run(
        ["node", "-e", script, str(APP_JS)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert json.loads(result.stdout) == {
        "cases": 6,
        "standard": "正在物料匹配",
        "legacy": "正在确认表格结构",
    }
