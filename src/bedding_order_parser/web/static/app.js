"use strict";

const app = document.getElementById("app");
const previewModal = document.getElementById("previewModal");
const previewTitle = document.getElementById("previewTitle");
const previewContent = document.getElementById("previewContent");
const toast = document.getElementById("toast");
const AI_FULL_ORDER_UI_VERSION = "v2-ui-2026-08-05";
const state = {
  selectedFile: null,
  selectedParseMode: "standard",
  aiPreflight: {
    v2_backend_available: false,
    provider_ready: false,
    unavailable_reason_text: "正在检查AI整单解析服务。",
  },
  submitting: false,
  actionSubmitting: false,
  reprocessOperationIds: {},
  pollTimer: null,
  historyPage: 1,
  historyJobs: [],
  capabilities: {
    desktop: { mode: false },
    llm: { enabled: false, configured: false, provider: null, model: null },
  },
};

const artifactCopy = {
  official_result: ["正式业务结果", "固定20字段订单记录"],
  parse_diagnostics: ["解析诊断", "字段来源及处理过程"],
  dictionary_validation: ["字典验证", "一致、歧义及冲突信息"],
  material_candidates: ["物料候选", "参考物料候选与比较信息"],
  material_summary: ["物料匹配摘要", "相似分数是参考分数，不是准确率"],
};

const aiComparisonCopy = {
  agree: "AI 与本地规则一致",
  equivalent_after_normalization: "表达形式不同，含义一致",
  different: "AI 与本地规则不一致，建议核对原订单",
  ai_only: "仅 AI 识别到此字段",
  python_fill: "AI 未识别，本字段由本地规则补全",
  both_missing: "AI 与本地规则均未识别到此字段",
};

const aiSelectedSourceCopy = {
  ai: "AI",
  python_fallback: "本地规则补全",
  user_selected_python: "用户选择本地规则",
  user_override: "用户手工修订",
  none: "空值",
};

const aiReviewStatusCopy = {
  not_required: "无需处理",
  unreviewed: "待你确认",
  confirmed_ai: "已确认保留 AI",
  selected_python: "已改用本地规则",
  manual_override: "已手工修订",
};

const helpTermGroups = [
  {
    title: "正式业务结果",
    items: [
      ["official_result", "正式业务结果", "处理完成后可用于查看和导出的订单记录，共固定20个业务字段。"],
      ["material_code", "物料编码", "由物料匹配环节给出的参考编码，建议结合候选信息确认。"],
      ["similarity_score", "相似分数", "用于比较候选物料的参考分数，不代表绝对准确率或正确概率。"],
    ],
  },
  {
    title: "解析诊断",
    items: [
      ["parse_diagnostics", "解析诊断", "说明字段从哪里读取、是否存在缺失、歧义或需要关注的地方。"],
      ["field", "字段", "订单中的一个信息项目，例如颜色、规格或数量。"],
      ["source_cells", "来源单元格", "Excel 中支撑该字段的单元格位置，便于回看原表。"],
      ["status", "状态", "当前处理情况，例如已提取、存在歧义或需要人工查看。"],
    ],
  },
  {
    title: "字典验证",
    items: [
      ["dictionary_validation", "字典验证", "按已有字典规则检查字段格式和一致性，不会凭空补写订单内容。"],
      ["validation_only", "仅验证", "表示本步骤只做检查和提示，不替代原始订单信息。"],
      ["records", "记录", "本次任务中逐条处理的订单记录列表。"],
    ],
  },
  {
    title: "物料候选",
    items: [
      ["material_candidates", "物料候选", "按订单信息列出的可供人工比较的物料候选。"],
      ["candidates", "候选列表", "按参考程度排列的候选物料，不等于最终确认结果。"],
      ["record_count", "记录数量", "当前结果中包含的订单记录数，用于核对处理范围。"],
    ],
  },
  {
    title: "物料匹配摘要",
    items: [
      ["material_summary", "物料匹配摘要", "汇总候选匹配情况，帮助快速了解需要复核的订单。"],
      ["accuracy_statement", "分数说明", "提示相似分数只用于参考比较，不是准确率。"],
      ["no_candidate", "暂无候选", "当前没有足够信息给出参考候选，需要回看订单内容。"],
    ],
  },
  {
    title: "常见模式、状态和安全提示",
    items: [
      ["standard", "标准解析", "使用本地 Python 规则读取订单，是日常处理的默认方式。"],
      ["ai_enhanced", "AI增强整单解析", "由 AI 协助理解整份订单，处理时间和 Token 用量通常更多。"],
      ["completed", "已完成", "五类结果已完整生成，可以查看、下载或导出。"],
      ["awaiting_user_decision", "等待你的处理决定", "系统发现需要人工选择的情况，尚未发布不完整结果。"],
      ["interrupted", "已中断", "任务已安全停止，结果页会提示可继续处理的方式。"],
    ],
  },
];

const helpUsageSteps = [
  "上传 Excel：在订单解析页选择需要处理的订单文件。",
  "选择解析方式：可选标准解析或 AI增强整单解析。",
  "阅读并确认提示：AI增强整单解析会说明处理范围和注意事项。",
  "开始处理：确认后等待任务进入处理队列。",
  "查看任务进度：页面会显示当前处理阶段和完成情况。",
  "查看五类结果：正式业务结果、解析诊断、字典验证、物料候选和物料匹配摘要。",
  "预览或下载文件：可先预览 JSON 内容，再下载所需文件。",
  "下载结果：处理完成后可以预览和下载五类结果；标准解析当前支持完整结果 ZIP，Excel 导出以界面可用状态为准。",
  "使用历史记录：在历史记录中查看此前任务和已生成的完整结果。",
];

const aiStageLabels = {
  preprocessing: "正在读取订单",
  structure_resolution: "正在确认表格结构",
  python_shadow: "正在执行本地解析对照",
  ai_extraction: "正在提取订单候选字段",
  evidence_binding: "正在绑定来源证据",
  cache_revalidation: "正在复核本地缓存",
  publication: "正在发布完整结果",
  completed: "已完成",
  python_shadow_parse: "正在执行本地解析对照",
  local_structure_resolution: "正在分析表格结构",
  ai_layout_recognition: "正在识别订单区域",
  ai_block_extraction: "正在提取订单字段",
  evidence_validation: "正在验证来源证据",
  field_resolution: "正在处理字段差异",
  dictionary_validation: "正在验证业务字段",
  material_matching: "正在匹配参考物料",
  publishing: "正在生成结果",
  awaiting_user_decision: "等待你的处理决定",
};

const aiSafeErrorText = {
  AI_V2_STRUCTURE_UNRESOLVED: "订单结构暂时无法安全确认，请选择后续处理方式。",
  AI_V2_STRUCTURE_FAILED: "订单结构识别未能安全完成，请选择后续处理方式。",
  AI_V2_STRUCTURE_MANIFEST_INVALID: "本地订单结构清单未通过安全校验，请选择后续处理方式。",
  AI_V2_STRUCTURE_PROVIDER_FAILED: "订单结构识别服务未能安全完成，请选择后续处理方式。",
  AI_V2_CONTRACT_FAILED: "AI返回结果未通过本地安全校验，未发布正式结果。",
  AI_V2_HIGH_RISK_CONFLICT: "高风险字段存在冲突，未发布正式结果。",
  AI_V2_TRANSIENT_FAILURE: "AI服务暂时未完成，请选择是否重试。",
  AI_V2_CACHE_CORRUPT: "本地缓存状态无法安全复用，请选择是否重试。",
  AI_V2_IN_PROGRESS: "相同订单仍在处理中，请稍后查看。",
  AI_V2_INTERRUPTED: "任务已安全中断，可继续未验证部分。",
  AI_V2_PUBLICATION_FAILED: "结果发布未完成，未提供半套业务结果。",
  AI_NOT_READY: "AI整单解析服务当前未就绪。",
};

function icon(name, className = "") {
  return `<svg class="icon ${className}" aria-hidden="true"><use href="#icon-${name}"></use></svg>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function navigate(route) {
  window.location.hash = route;
}

function setActiveNav(route) {
  const history = route.startsWith("history");
  const help = route.startsWith("help");
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle(
      "active",
      history ? button.dataset.route === "history" : !help && button.dataset.route === "upload"
    );
  });
  document.querySelectorAll(".plain-nav[data-route]").forEach((button) => {
    button.classList.toggle("active", help && button.dataset.route === "help");
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const error = payload?.error;
    const message = typeof error === "object" ? error.message : error;
    throw new Error(message || "请求未完成，请稍后重试。");
  }
  return payload;
}

async function loadCapabilities() {
  try {
    state.capabilities = await api("/api/capabilities");
  } catch {
    state.capabilities = {
      desktop: { mode: false },
      llm: { enabled: false, configured: false, provider: null, model: null },
    };
  }
}

function desktopApi() {
  return window.pywebview?.api || null;
}

async function saveDesktopArtifact(jobId, kind) {
  const bridge = desktopApi();
  if (!bridge) return false;
  const result = await bridge.save_artifact(jobId, kind);
  if (result?.message) showToast(result.message);
  return true;
}

function bindDownloadLinks(root = document) {
  root.querySelectorAll(".artifact-download").forEach((link) => {
    link.addEventListener("click", async (event) => {
      if (!desktopApi()) return;
      event.preventDefault();
      try {
        await saveDesktopArtifact(link.dataset.job, link.dataset.kind);
      } catch {
        showToast("文件保存未完成，请重试。");
      }
    });
  });
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 2600);
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(date).replaceAll("/", "-");
}

function formatDuration(seconds) {
  return `${Number(seconds || 0).toFixed(1)} 秒`;
}

function stopPolling() {
  if (state.pollTimer) window.clearTimeout(state.pollTimer);
  state.pollTimer = null;
}

function renderHelpTermGroups() {
  return helpTermGroups.map((group) => `
    <article class="help-term-group">
      <h3>${escapeHtml(group.title)}</h3>
      <dl class="help-term-list">
        ${group.items.map(([term, name, description]) => `
          <div class="help-term-row">
            <dt><code>${escapeHtml(term)}</code></dt>
            <dd class="help-term-name">${escapeHtml(name)}</dd>
            <dd class="help-term-description">${escapeHtml(description)}</dd>
          </div>`).join("")}
      </dl>
    </article>`).join("");
}

function scrollToHelpSection(event) {
  const targetId = event.currentTarget.dataset.helpTarget;
  const target = document.getElementById(targetId);
  if (!target) return;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
}

function bindHelpEntryNavigation(root = document) {
  root.querySelectorAll(".help-entry-link[data-help-target]").forEach((button) => {
    button.addEventListener("click", scrollToHelpSection);
  });
}

function renderHelp() {
  stopPolling();
  setActiveNav("help");
  app.innerHTML = `
    <section class="page help-page">
      <header class="page-heading">
        <h1>帮助中心</h1>
        <p>按日常处理顺序，快速查看术语、使用方法和处理流程。</p>
      </header>

      <nav class="help-entry-grid" aria-label="帮助内容">
        <button type="button" class="help-entry-link" data-help-target="help-terms" aria-controls="help-terms"><strong>英文术语注释</strong><span>看懂结果和常见状态</span></button>
        <button type="button" class="help-entry-link" data-help-target="help-usage" aria-controls="help-usage"><strong>软件使用方法</strong><span>从上传到导出的日常步骤</span></button>
        <button type="button" class="help-entry-link" data-help-target="help-flow" aria-controls="help-flow"><strong>软件处理流程</strong><span>两种解析方式分别如何处理</span></button>
      </nav>

      <section class="help-section" id="help-terms" aria-labelledby="helpTermsTitle">
        <div class="help-section-heading">
          <p class="help-kicker">英文术语注释</p>
          <h2 id="helpTermsTitle">结果中常见的英文词</h2>
          <p>英文键名用于文件和结果识别；页面会优先显示中文说明。</p>
        </div>
        <div class="help-term-grid">${renderHelpTermGroups()}</div>
      </section>

      <section class="help-section" id="help-usage" aria-labelledby="helpUsageTitle">
        <div class="help-section-heading">
          <p class="help-kicker">软件使用方法</p>
          <h2 id="helpUsageTitle">从上传到查看结果</h2>
          <p>先按标准解析完成日常工作，遇到复杂订单时再选择 AI增强整单解析。</p>
        </div>
        <ol class="help-step-list">
          ${helpUsageSteps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}
        </ol>
        <div class="help-mode-grid">
          <article class="help-mode-card">
            <h3>标准解析</h3>
            <p>使用本地 Python 规则提取订单字段，完成字典验证和物料候选匹配。结果页可按需对单条订单使用 AI 复核。</p>
          </article>
          <article class="help-mode-card">
            <h3>AI增强整单解析</h3>
            <p>使用 AI 理解订单内容，通常需要更多处理时间和 Token。请在结果出来后检查重点字段；该功能仍在持续优化。</p>
          </article>
        </div>
      </section>

      <section class="help-section" id="help-flow" aria-labelledby="helpFlowTitle">
        <div class="help-section-heading">
          <p class="help-kicker">软件处理流程</p>
          <h2 id="helpFlowTitle">两种解析方式的处理步骤</h2>
          <p>无论选择哪种方式，结果都应结合订单原表和业务判断复核。</p>
        </div>
        <div class="help-flow-grid">
          <article class="help-flow-card">
            <h3>标准解析</h3>
            <p class="help-flow">读取 Excel <span>→</span> 识别表头和订单记录 <span>→</span> Python 提取字段 <span>→</span> 字典规则验证 <span>→</span> 物料 TopK 候选匹配 <span>→</span> 生成五类 JSON <span>→</span> 展示和导出结果</p>
          </article>
          <article class="help-flow-card">
            <h3>AI增强整单解析</h3>
            <p class="help-flow">读取 Excel <span>→</span> 本地识别订单结构 <span>→</span> AI 提取订单业务字段 <span>→</span> 本地验证和对照 <span>→</span> 字典验证与物料匹配 <span>→</span> 生成结果或显示需要处理的问题</p>
          </article>
        </div>
      </section>
    </section>`;
  bindHelpEntryNavigation(app);
}

function renderUpload() {
  stopPolling();
  setActiveNav("upload");
  const file = state.selectedFile;
  const aiAvailable = state.aiPreflight.v2_backend_available === true;
  const aiReady = state.aiPreflight.provider_ready === true;
  const mode = state.selectedParseMode;
  const canStart = Boolean(file) && (mode === "standard" || aiReady) && !state.submitting;
  const modeDescription = mode === "ai_enhanced"
    ? `<div class="mode-note ai-mode-note"><strong>AI整单解析</strong><ul><li>仅发送与订单解析有关的必要坐标化数据，不发送 Excel 二进制；可能产生Token费用。</li><li>处理时间通常更长，结果仍须经过本地证据、字段合同和业务校验。</li><li>AI不会生成或确认ERP物料编码；物料编码仍由本地物料匹配层产生。</li></ul></div>`
    : `<div class="mode-note"><strong>标准解析</strong><p>使用本地确定性规则解析，不会自动调用整单AI。完成后仍可对单条记录手动使用“AI复核建议”。</p></div>`;
  app.innerHTML = `
    <section class="page page-narrow">
      <header class="page-heading center">
        <h1>上传订单文件</h1>
        <p>支持上传 Excel 格式的 PI / 订单文件</p>
      </header>
      <div class="upload-zone" id="uploadZone">
        ${icon("upload", "upload-icon")}
        <p>将 Excel 文件拖到此处</p>
        <span class="or">或</span>
        <button class="button primary small" id="selectButton" type="button">选择文件</button>
        <input class="file-input" id="fileInput" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet">
      </div>
      ${file ? `
        <div class="selected-file">
          <span class="file-mark">X</span>
          <div class="file-copy"><strong>${escapeHtml(file.name)}</strong><small>${formatBytes(file.size)}</small></div>
          <button class="icon-button" id="removeFile" type="button" aria-label="移除文件">${icon("x")}</button>
        </div>` : ""}
      <fieldset class="parse-mode-picker" aria-describedby="parseModeHelp">
        <legend>解析方式</legend>
        <label class="mode-choice ${mode === "standard" ? "selected" : ""}"><input type="radio" name="parseMode" value="standard" ${mode === "standard" ? "checked" : ""}> <span><strong>标准解析</strong><small>本地确定性规则</small></span></label>
        <label class="mode-choice ${mode === "ai_enhanced" ? "selected" : ""} ${aiAvailable ? "" : "disabled"}"><input type="radio" name="parseMode" value="ai_enhanced" ${mode === "ai_enhanced" ? "checked" : ""} ${aiAvailable ? "" : "disabled"}> <span><strong>AI整单解析</strong><small>${aiReady ? "需确认数据发送与费用" : aiAvailable ? "当前配置未就绪" : "当前版本不可用"}</small></span></label>
      </fieldset>
      <div id="parseModeHelp">${modeDescription}${mode === "ai_enhanced" && !aiReady ? `<p class="mode-unavailable">${escapeHtml(state.aiPreflight.unavailable_reason_text || state.aiPreflight.reason || "AI整单解析服务当前未就绪，完成配置后即可提交。")}</p>` : ""}</div>
      <button class="button primary wide" id="startButton" type="button" ${canStart ? "" : "disabled"}>${state.submitting ? "正在提交..." : "开始解析"}</button>
    </section>`;

  const zone = document.getElementById("uploadZone");
  const input = document.getElementById("fileInput");
  const selectButton = document.getElementById("selectButton");
  const openPicker = () => input.click();
  selectButton.addEventListener("click", (event) => {
    event.stopPropagation();
    openPicker();
  });
  zone.addEventListener("click", openPicker);
  input.addEventListener("change", () => selectFile(input.files[0]));
  ["dragenter", "dragover"].forEach((name) => zone.addEventListener(name, (event) => {
    event.preventDefault();
    zone.classList.add("dragging");
  }));
  ["dragleave", "drop"].forEach((name) => zone.addEventListener(name, (event) => {
    event.preventDefault();
    zone.classList.remove("dragging");
  }));
  zone.addEventListener("drop", (event) => selectFile(event.dataTransfer.files[0]));
  document.getElementById("removeFile")?.addEventListener("click", () => {
    state.selectedFile = null;
    renderUpload();
  });
  document.querySelectorAll('input[name="parseMode"]').forEach((control) => {
    control.addEventListener("change", () => {
      const value = control.value;
      if (value === "standard" || (value === "ai_enhanced" && state.aiPreflight.v2_backend_available === true)) {
        state.selectedParseMode = value;
        renderUpload();
      }
    });
  });
  document.getElementById("startButton").addEventListener("click", startParsing);
}

function selectFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".xlsx")) {
    showToast("仅支持 .xlsx 格式的 Excel 文件。");
    return;
  }
  if (file.size > 25 * 1024 * 1024) {
    showToast("文件超过 25 MB，请确认后重新上传。");
    return;
  }
  state.selectedFile = file;
  renderUpload();
}

async function startParsing() {
  if (!state.selectedFile || state.submitting) return;
  const mode = state.selectedParseMode;
  if (mode !== "standard" && mode !== "ai_enhanced") return;
  if (mode === "ai_enhanced" && state.aiPreflight.provider_ready !== true) {
    showToast(state.aiPreflight.unavailable_reason_text || state.aiPreflight.reason || "AI整单解析服务当前未就绪。");
    return;
  }
  const button = document.getElementById("startButton");
  state.submitting = true;
  button.disabled = true;
  if (mode === "ai_enhanced") {
    const confirmed = await confirmAIEnhanced(state.selectedFile, state.aiPreflight);
    if (!confirmed) {
      state.submitting = false;
      renderUpload();
      return;
    }
  }
  button.textContent = "正在上传...";
  const form = new FormData();
  form.append("file", state.selectedFile);
  form.append("parse_mode", mode);
  try {
    const job = await api("/api/jobs", { method: "POST", body: form });
    state.selectedFile = null;
    state.selectedParseMode = "standard";
    state.submitting = false;
    navigate(`job/${job.id}/progress`);
  } catch (error) {
    state.submitting = false;
    button.disabled = false;
    button.textContent = "开始解析";
    showToast(error.message);
  }
}

function stageRows(stages) {
  const stateLabel = { completed: "已完成", processing: "进行中", waiting: "等待中" };
  return stages.map((stage) => `
    <div class="stage-row ${escapeHtml(stage.status)}">
      <span class="stage-dot">${stage.status === "completed" ? icon("check") : ""}</span>
      <span>${escapeHtml(stage.name)}</span>
      <span class="stage-state">${stateLabel[stage.status] || "等待中"}</span>
    </div>`).join("");
}

function progressPresentation(job) {
  const ai = job.ai_execution || {};
  const storedStage = String(job.current_stage || "");
  const aiStage = String(ai.stage || "");
  const currentStage = job.parse_mode === "ai_enhanced"
    ? (storedStage && storedStage !== aiStage ? storedStage : (aiStageLabels[aiStage] || storedStage || "正在准备"))
    : storedStage;
  return {
    progress: Number(job.progress || 0),
    currentStage,
    stages: Array.isArray(job.stages) ? job.stages : [],
  };
}

function remainingTime(progress) {
  const seconds = Math.max(1, Math.ceil((100 - progress) / 7));
  return `00:00:${String(seconds).padStart(2, "0")}`;
}

async function renderProgress(jobId) {
  const expectedHash = `#job/${jobId}/progress`;
  stopPolling();
  setActiveNav("upload");
  try {
    const job = await api(`/api/jobs/${jobId}`);
    if (window.location.hash !== expectedHash) return;
    if (job.status === "completed") {
      navigate(`job/${jobId}/result`);
      return;
    }
    if (job.status === "failed") {
      renderFailure(job);
      return;
    }
    if (job.status === "awaiting_user_decision") {
      renderAwaitingDecision(job);
      return;
    }
    const presentation = progressPresentation(job);
    const ai = job.parse_mode === "ai_enhanced" ? renderAIProgressDetails(job) : "";
    app.innerHTML = `
      <section class="page">
        <header class="page-heading">
          <h1>正在解析订单</h1>
          <p>请稍候，系统正在处理中...</p>
        </header>
        <div class="progress-layout">
          <div class="progress-visual">
            <div class="progress-ring" style="--progress:${presentation.progress}%">
              <div class="progress-number">${presentation.progress}%<small>处理中</small></div>
            </div>
            <p class="current-stage">${escapeHtml(presentation.currentStage)}</p>
          </div>
          <div class="stage-card">${stageRows(presentation.stages)}</div>
        </div>
        ${ai}
        <div class="time-remaining">${icon("info")}<span>预计剩余时间：　<strong>${remainingTime(presentation.progress)}</strong></span></div>
      </section>`;
    state.pollTimer = window.setTimeout(() => renderProgress(jobId), 650);
  } catch (error) {
    showToast(error.message);
    state.pollTimer = window.setTimeout(() => renderProgress(jobId), 1500);
  }
}

function renderFailure(job) {
  app.innerHTML = `
    <section class="page">
      <div class="error-state">
        <div>${icon("alert")}</div>
        <h2>解析未完成</h2>
        <p>${escapeHtml(job.error || "请检查文件后重新尝试。")}</p>
        <button class="button primary" id="retryUpload" type="button">返回重新上传</button>
      </div>
    </section>`;
  document.getElementById("retryUpload").addEventListener("click", () => navigate("upload"));
}

function artifactCard(job, role) {
  const [title, description] = artifactCopy[role];
  return `
    <article class="artifact-card">
      <h3>${title}</h3>
      <p>${role === "official_result" ? `${job.record_count} 条记录` : description}</p>
      <div class="artifact-actions">
        <button class="button small preview-button" data-kind="${role}" type="button">预览</button>
        <a class="button small artifact-download" data-job="${job.id}" data-kind="${role}" href="/api/jobs/${job.id}/artifacts/${role}/download">下载</a>
      </div>
    </article>`;
}

function reviewValue(value) {
  return value ? escapeHtml(value) : '<span class="review-missing">未识别</span>';
}

function reviewEvidence(label, entries, supportingQuote = "") {
  const safeEntries = Array.isArray(entries) ? entries : [];
  if (!safeEntries.length && !supportingQuote) {
    return `<div class="review-evidence"><strong>${label}</strong><span>暂无可展示的来源位置</span></div>`;
  }
  const locations = safeEntries.map((entry) => {
    const sheet = entry.sheet_name || entry.sheet_id || "工作表";
    const range = entry.cell_range || (entry.source_row ? `第 ${Number(entry.source_row)} 行` : "位置未记录");
    return `<li><span>${escapeHtml(sheet)} · ${escapeHtml(range)}</span>${entry.excerpt ? `<small>来源内容：${escapeHtml(entry.excerpt)}</small>` : ""}</li>`;
  }).join("");
  return `<div class="review-evidence"><strong>${label}</strong>${locations ? `<ul>${locations}</ul>` : ""}${supportingQuote ? `<p>AI 引用：${escapeHtml(supportingQuote)}</p>` : ""}</div>`;
}

function reviewStatusText(item) {
  if (item.content_issue) return "AI 给出了候选值，但证据不足，未作为正式值";
  return aiComparisonCopy[item.comparison_status] || "字段对照状态暂不可用";
}

function renderAIReviewItem(item, index) {
  const normalizedDiffers = item.ai_display_value && item.ai_normalized_value && item.ai_display_value !== item.ai_normalized_value;
  const isHigh = item.review_required && item.review_severity === "high";
  const panelId = `ai-review-detail-${index}`;
  const editorId = `ai-review-editor-${index}`;
  const actions = item.available_actions || {};
  const actionButtons = [
    actions.keep_ai ? `<button class="button small revision-action" data-revision-action="keep_ai" data-review-index="${index}" type="button">保留 AI</button>` : "",
    actions.use_python ? `<button class="button small revision-action" data-revision-action="use_python" data-review-index="${index}" type="button">使用本地规则</button>` : "",
    actions.manual_override ? `<button class="button small revision-edit-toggle" data-review-editor="${editorId}" type="button" aria-expanded="false">手动修改</button>` : "",
  ].join("");
  return `
    <article class="review-item ${isHigh ? "high-review" : ""}" data-review-required="${item.review_required}" data-review-severity="${escapeHtml(item.review_severity)}" data-selected-source="${escapeHtml(item.selected_source)}">
      <div class="review-item-heading">
        <div><span class="review-record">第 ${Number(item.record_index)} 条${item.line_number ? ` · 行号 ${escapeHtml(item.line_number)}` : ""}</span><h3>${escapeHtml(item.field_name)}</h3></div>
        <div class="review-badges">${isHigh ? '<span class="review-badge high">高风险 · 建议重点核对</span>' : ""}${item.review_required ? '<span class="review-badge">建议复核</span>' : ""}</div>
      </div>
      <p class="review-status">${escapeHtml(reviewStatusText(item))}</p>
      <p class="review-user-status">处理状态：${escapeHtml(aiReviewStatusCopy[item.review_status] || "待你确认")}</p>
      <dl class="review-values">
        <div><dt>当前正式结果</dt><dd>${reviewValue(item.formal_value)}<small>当前采用：${escapeHtml(aiSelectedSourceCopy[item.selected_source] || "未标记")}</small></dd></div>
        <div><dt>AI 提取</dt><dd>${reviewValue(item.ai_display_value)}${normalizedDiffers ? `<small>正式格式：${escapeHtml(item.ai_normalized_value)}</small>` : ""}</dd></div>
        <div><dt>本地规则</dt><dd>${reviewValue(item.python_display_value)}</dd></div>
      </dl>
      <button class="review-detail-toggle" data-review-target="${panelId}" type="button" aria-expanded="false">查看来源位置</button>
      <div class="review-detail" data-review-panel="${panelId}" hidden>
        ${reviewEvidence("AI 来源", item.ai_evidence, item.ai_supporting_quote)}
        ${reviewEvidence("本地规则来源", item.python_evidence)}
      </div>
      ${actionButtons ? `<div class="review-actions" data-review-actions>${actionButtons}</div>` : ""}
      ${actions.manual_override ? `<div class="review-manual-editor" data-review-editor-panel="${editorId}" hidden><label for="${editorId}-input">输入最终业务值</label><div><input id="${editorId}-input" data-review-manual-input="${index}" type="text" maxlength="2000" value="${escapeHtml(item.formal_value || "")}"><button class="button primary small revision-action" data-revision-action="manual_override" data-review-index="${index}" type="button">保存修改</button></div><small>保存后会重新执行本地字典验证和物料匹配，不会再次调用 AI。</small></div>` : ""}
    </article>`;
}

function renderAIReviewSection(review) {
  if (!review || review.applicable !== true) return "";
  if (review.available !== true) {
    return `<section class="section ai-review-section" data-ai-review><div class="section-heading-row"><div><h2 class="section-title">AI 与本地规则对照</h2><p>历史任务兼容视图</p></div></div><div class="review-compatibility">${escapeHtml(review.compatibility_message || "该任务没有可用的字段对照数据，五类结果仍可正常查看和下载。")}</div></section>`;
  }
  const summary = review.summary || {};
  const revision = review.revision || {};
  const items = Array.isArray(review.items) ? review.items : [];
  const reviewCount = Number(summary.review_required_count || 0);
  const defaultFilter = reviewCount > 0 ? "review" : "all";
  const intro = reviewCount > 0
    ? `正式结果已经生成，可以正常下载。其中有 ${reviewCount} 个字段建议人工核对，${Number(summary.high_review_count || 0)} 个属于高风险字段。`
    : "正式结果已经生成，AI 与本地规则未发现需要人工复核的差异。";
  return `
    <section class="section ai-review-section" data-ai-review data-default-review-filter="${defaultFilter}">
      <div class="section-heading-row"><div><h2 class="section-title">AI 与本地规则对照</h2><p>${escapeHtml(intro)}</p></div><span class="review-complete-mark">${revision.supported ? `当前结果：第 ${Number(revision.revision_number || 0) + 1} 版` : "解析已完成"}</span></div>
      <div class="review-summary-grid">
        <div><span>待复核字段</span><strong>${reviewCount}</strong></div>
        <div><span>高风险待复核</span><strong>${Number(summary.high_review_count || 0)}</strong></div>
        <div><span>本地规则补全</span><strong>${Number(summary.python_fill_count || 0)}</strong></div>
        <div><span>五类结果</span><strong>完整</strong></div>
      </div>
      <div class="review-filters" role="group" aria-label="字段对照筛选">
        <button data-review-filter="review" type="button" aria-pressed="${defaultFilter === "review"}">待复核</button>
        <button data-review-filter="high" type="button" aria-pressed="false">高风险</button>
        <button data-review-filter="python_fill" type="button" aria-pressed="false">本地补全</button>
        <button data-review-filter="all" type="button" aria-pressed="${defaultFilter === "all"}">全部</button>
      </div>
      <div class="review-list">${items.map((item, index) => renderAIReviewItem(item, index)).join("")}</div>
      <p class="review-empty" hidden>当前筛选条件下没有字段。</p>
    </section>`;
}

function applyAIReviewFilter(section, filter) {
  let visibleCount = 0;
  section.querySelectorAll("[data-review-filter]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.reviewFilter === filter));
  });
  section.querySelectorAll(".review-item").forEach((item) => {
    const visible = filter === "all"
      || (filter === "review" && item.dataset.reviewRequired === "true")
      || (filter === "high" && item.dataset.reviewRequired === "true" && item.dataset.reviewSeverity === "high")
      || (filter === "python_fill" && item.dataset.selectedSource === "python_fallback");
    item.hidden = !visible;
    if (visible) visibleCount += 1;
  });
  const empty = section.querySelector(".review-empty");
  if (empty) empty.hidden = visibleCount !== 0;
}

function bindKeyboardActivation(button) {
  button.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    button.click();
  });
}

function bindAIReviewInteractions(root) {
  const review = arguments.length > 1 ? arguments[1] : null;
  const job = arguments.length > 2 ? arguments[2] : null;
  const section = root.querySelector("[data-ai-review]");
  if (!section || !section.dataset.defaultReviewFilter) return;
  section.querySelectorAll("[data-review-filter]").forEach((button) => {
    button.addEventListener("click", () => applyAIReviewFilter(section, button.dataset.reviewFilter));
    bindKeyboardActivation(button);
  });
  section.querySelectorAll(".review-detail-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const panel = section.querySelector(`[data-review-panel="${button.dataset.reviewTarget}"]`);
      if (!panel) return;
      const expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!expanded));
      button.textContent = expanded ? "查看来源位置" : "收起来源位置";
      panel.hidden = expanded;
    });
    bindKeyboardActivation(button);
  });
  section.querySelectorAll(".revision-edit-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const editor = section.querySelector(`[data-review-editor-panel="${button.dataset.reviewEditor}"]`);
      if (!editor) return;
      const expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!expanded));
      button.textContent = expanded ? "手动修改" : "取消手动修改";
      editor.hidden = expanded;
      if (!expanded) editor.querySelector("input")?.focus();
    });
    bindKeyboardActivation(button);
  });
  section.querySelectorAll(".revision-action").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!review || !job || state.actionSubmitting) return;
      const item = review.items?.[Number(button.dataset.reviewIndex)];
      if (!item) return;
      const action = button.dataset.revisionAction;
      const input = section.querySelector(`[data-review-manual-input="${button.dataset.reviewIndex}"]`);
      const manualValue = action === "manual_override" ? String(input?.value ?? "") : "";
      state.actionSubmitting = true;
      section.querySelectorAll(".revision-action").forEach((control) => { control.disabled = true; });
      try {
        await api(`/api/jobs/${job.id}/ai-review/revisions`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            expected_current_revision: review.revision.current_revision,
            source_record_id: item.source_record_id,
            field_name: item.field_name,
            action,
            manual_value: manualValue,
          }),
        });
        showToast("修改已保存，当前结果已生成新版本。");
        await renderResult(job.id);
      } catch (error) {
        showToast(error.message);
      } finally {
        state.actionSubmitting = false;
      }
    });
    bindKeyboardActivation(button);
  });
  applyAIReviewFilter(section, section.dataset.defaultReviewFilter);
}

async function loadAIReview(job) {
  try {
    return await api(`/api/jobs/${job.id}/ai-review`);
  } catch (_error) {
    return {
      applicable: true,
      available: false,
      compatibility_message: "字段对照详情暂时无法读取，五类结果仍可正常查看和下载。",
      summary: job.ai_review_summary || {},
      items: [],
    };
  }
}

async function renderResult(jobId) {
  const expectedHash = `#job/${jobId}/result`;
  stopPolling();
  setActiveNav("upload");
  try {
    const job = await api(`/api/jobs/${jobId}`);
    if (window.location.hash !== expectedHash) return;
    if (job.status !== "completed") {
      navigate(`job/${jobId}/progress`);
      return;
    }
    if (!job.has_complete_five_results) {
      app.innerHTML = `<section class="page"><div class="error-state"><div>${icon("alert")}</div><h2>结果暂时无法打开</h2><p>五类结果文件不完整或无法通过安全校验，未提供下载。</p><button class="button primary" id="backProgress" type="button">返回任务状态</button></div></section>`;
      document.getElementById("backProgress").addEventListener("click", () => navigate(`job/${jobId}/progress`));
      return;
    }
    const roles = ["official_result", "parse_diagnostics", "dictionary_validation", "material_candidates", "material_summary"];
    const ai = job.ai_execution || {};
    const tokens = ai.token_summary || {};
    const isAIEnhanced = job.parse_mode === "ai_enhanced" && job.effective_parse_mode === "ai_enhanced";
    const review = isAIEnhanced ? await loadAIReview(job) : null;
    if (window.location.hash !== expectedHash) return;
    const reviewSummary = review?.summary || job.ai_review_summary || {};
    app.innerHTML = `
      <section class="page">
        <div class="completion-heading"><span class="success-badge">${icon("check")}</span><h1>${isAIEnhanced ? "AI整单解析完成" : "解析完成"}</h1></div>
        <div class="summary-strip">
          <span>文件名称：<strong title="${escapeHtml(job.file_name)}">${escapeHtml(job.file_name)}</strong></span>
          <span>订单记录：<strong>${job.record_count} 条</strong></span>
          <span>完成时间：<strong>${formatDuration(job.elapsed_seconds)}</strong></span>
          ${isAIEnhanced ? `<span>待复核字段：<strong>${Number(reviewSummary.review_required_count || 0)}</strong></span><span>高风险待复核：<strong>${Number(reviewSummary.high_review_count || 0)}</strong></span>` : ""}
        </div>
        ${modeMeta(job)}
        <div class="result-meta"><span>Provider：${escapeHtml(ai.provider || "本地标准解析")}</span><span>模型：${escapeHtml(ai.model || "-")}</span>${job.parse_mode === "ai_enhanced" ? `<span>内部合同：${escapeHtml(job.ai_contract_label || ai.contract_version || "未标记")}</span>` : ""}<span>Token：${Number(tokens.total_tokens || 0)}</span><span>逻辑调用：${Number(ai.logical_call_count || 0)}</span><span>五类结果：完整</span></div>
        ${isAIEnhanced ? renderAIReviewSection(review) : ""}
        <section class="section">
          <h2 class="section-title">解析结果文件</h2>
          <div class="artifact-grid artifact-grid-five">${roles.map((role) => artifactCard(job, role)).join("")}</div>
        </section>
        <section class="section">
          <h2 class="section-title">匹配结果概览</h2>
          <div class="metric-grid">
            <button class="metric-card green" data-match="high_match" type="button"><span class="label">推荐明确</span><strong>${job.summary.high_match}<span>条</span></strong>${icon("check", "metric-icon")}</button>
            <button class="metric-card amber" data-match="partial_match" type="button"><span class="label">建议人工查看</span><strong>${job.summary.partial_match}<span>条</span></strong>${icon("alert", "metric-icon")}</button>
            <button class="metric-card red" data-match="conflict" type="button"><span class="label">存在冲突</span><strong>${job.summary.conflict}<span>条</span></strong>${icon("alert", "metric-icon")}</button>
          </div>
        </section>
        <section class="section">
          <h2 class="section-title">导出结果</h2>
          <div class="export-actions">
            <button class="button primary" id="exportExcel" type="button">${icon("download")}导出 Excel</button>
            ${job.artifacts.zip ? `<a class="button artifact-download" data-job="${job.id}" data-kind="zip" href="/api/jobs/${job.id}/download-all">${icon("archive")}下载全部文件（ZIP）</a>` : ""}
          </div>
        </section>
      </section>`;
    document.querySelectorAll(".preview-button").forEach((button) => {
      button.addEventListener("click", () => openPreview(job, button.dataset.kind));
    });
    document.querySelectorAll(".metric-card").forEach((button) => {
      button.addEventListener("click", () => openFirstMatch(job.id, button.dataset.match));
    });
    bindAIReviewInteractions(app, review, job);
    bindDownloadLinks(app);
    document.getElementById("exportExcel").addEventListener("click", () => showToast("导出 Excel 将在下一阶段开放。"));
  } catch (error) {
    showToast(error.message);
  }
}

async function openPreview(job, kind) {
  try {
    const payload = await api(`/api/jobs/${job.id}/artifacts/${kind}/preview`);
    previewTitle.textContent = artifactCopy[kind][0];
    previewContent.textContent = JSON.stringify(payload, null, 2);
    previewModal.classList.remove("hidden");
  } catch (error) {
    showToast(error.message);
  }
}

async function openFirstMatch(jobId, statusKey) {
  try {
    const payload = await api(`/api/jobs/${jobId}/matches`);
    const record = payload.records.find((item) => item.summary_key === statusKey);
    if (!record) {
      showToast("该分类暂无记录。");
      return;
    }
    navigate(`job/${jobId}/match/${record.index}`);
  } catch (error) {
    showToast(error.message);
  }
}

function statusPill(status) {
  return `<span class="status-pill ${escapeHtml(status.key)}">${escapeHtml(status.label)}</span>`;
}

function modeMeta(job) {
  return `<div class="mode-meta"><span>原始模式：<strong>${escapeHtml(job.parse_mode_label || "标准解析")}</strong></span><span>当前有效模式：<strong>${escapeHtml(job.effective_parse_mode_label || "标准解析")}</strong></span>${job.fallback?.status === "confirmed" ? `<span class="fallback-mark">已回退：${escapeHtml(job.fallback.reason || "已确认回退")}</span>` : ""}</div>`;
}

function renderAIProgressDetails(job) {
  const ai = job.ai_execution || {};
  const tokens = ai.token_summary || {};
  const safeText = aiSafeErrorText[ai.safe_error_code] || "任务当前需要人工处理。";
  const review = job.ai_review_summary || {};
  const attentionCount = review.available ? Number(review.review_required_count || 0) : Number(ai.isolated_field_count || 0);
  const attentionLabel = review.available ? "待复核字段" : (job.status === "completed" && attentionCount ? "历史任务关注字段" : "待复核字段");
  const presentation = progressPresentation(job);
  return `<section class="ai-job-details"><h2 class="section-title">AI整单解析状态</h2>${modeMeta(job)}<dl class="job-detail-grid"><div><dt>当前阶段</dt><dd>${escapeHtml(presentation.currentStage || "正在准备")}</dd></div><div><dt>内部合同</dt><dd>${escapeHtml(job.ai_contract_label || ai.contract_version || "未标记")}</dd></div><div><dt>区块进度</dt><dd>${Number(ai.completed_chunks || 0)} / ${Number(ai.total_chunks || 0)}</dd></div><div><dt>逻辑AI调用</dt><dd>${Number(ai.logical_call_count || 0)}</dd></div><div><dt>HTTP尝试</dt><dd>${Number(ai.http_attempt_count || 0)}</dd></div><div><dt>Token汇总</dt><dd>${Number(tokens.total_tokens || 0)}</dd></div><div><dt>${attentionLabel}</dt><dd>${attentionCount}</dd></div><div><dt>Provider / 模型</dt><dd>${escapeHtml(ai.provider || "未配置")} / ${escapeHtml(ai.model || "未配置")}</dd></div><div><dt>五类结果</dt><dd>${job.has_complete_five_results ? "已完整生成" : "尚未生成完整结果"}</dd></div></dl>${ai.safe_error_code ? `<p class="safe-error"><strong>${escapeHtml(safeText)}</strong><small>安全代码：${escapeHtml(ai.safe_error_code)}</small></p>` : ""}</section>`;
}

function renderAwaitingDecision(job) {
  stopPolling();
  const ai = job.ai_execution || {};
  app.innerHTML = `
    <section class="page page-narrow">
      <header class="page-heading"><h1>等待你的处理决定</h1><p>AI整单解析尚未发布完整五类结果。</p></header>
      ${renderAIProgressDetails(job)}
      <div class="decision-panel"><h2>你可以选择</h2><p>${escapeHtml(job.error || "当前任务需要你确认下一步。")}</p><div class="decision-actions"><button class="button primary" data-ai-action="retry" type="button">重试未完成部分</button><button class="button secondary-button" data-ai-action="reprocess-standard" type="button">使用标准解析重新处理</button><button class="button danger-button" data-ai-action="keep-failed" type="button">保留失败并结束</button></div><p class="decision-note">将使用原始订单创建一个新的标准解析任务并立即开始。当前AI任务、失败原因和已记录的AI信息会保留；保留失败不会生成可下载的半套AI正式结果。</p></div>
    </section>`;
  document.querySelectorAll("[data-ai-action]").forEach((button) => {
    button.addEventListener("click", () => performAIJobAction(job, button.dataset.aiAction));
  });
}

async function performAIJobAction(job, action) {
  if (state.actionSubmitting) return;
  state.actionSubmitting = true;
  document.querySelectorAll("[data-ai-action]").forEach((button) => { button.disabled = true; });
  try {
    if (action === "reprocess-standard") {
      const operationId = state.reprocessOperationIds[job.id] || createReprocessOperationId();
      state.reprocessOperationIds[job.id] = operationId;
      const result = await api(`/api/jobs/${job.id}/reprocess-standard`, {
        method: "POST",
        headers: { "X-Idempotency-Key": operationId },
      });
      delete state.reprocessOperationIds[job.id];
      navigate(`job/${result.new_job_id}/progress`);
      return;
    }
    const updated = await api(`/api/jobs/${job.id}/ai-actions/${action}`, { method: "POST" });
    if (updated.status === "completed") navigate(`job/${job.id}/result`);
    else if (updated.status === "failed") renderFailure(updated);
    else renderProgress(job.id);
  } catch (error) {
    showToast(error.message);
    renderProgress(job.id);
  } finally {
    state.actionSubmitting = false;
  }
}

function createReprocessOperationId() {
  if (window.crypto?.randomUUID) return `reprocess-${window.crypto.randomUUID()}`;
  return `reprocess-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const AI_ACTION_LABELS = {
  keep_python: "保留标准解析结果",
  suggest_review: "建议人工核查",
  insufficient_evidence: "证据不足，建议人工核查",
  suggest_change: "建议修改",
  no_change: "无需修改",
  needs_manual_review: "建议人工核查",
  ambiguous: "存在歧义，建议人工核查",
};

const AI_MATERIAL_LABELS = {
  no_suggestion: "暂不确认物料编码",
  suggested: "提供候选物料建议",
  insufficient_evidence: "物料证据不足",
};

const AI_STATE_LABELS = {
  completed: "已生成",
  cached: "已读取缓存",
  running: "正在生成",
  failed: "生成失败",
};

const AI_FIELD_LABELS = {
  customer: "客户",
  currency: "币种",
  salesperson: "业务员",
  sales_person: "业务员",
  header_note: "表头备注",
  line_number: "行号",
  material_code: "物料编码",
  material_name: "物料名称",
  spec: "规格",
  color: "颜色",
  fabric: "面料",
  composition: "面料-涤棉成分",
  fabric_composition: "面料-涤棉成分",
  style: "款式",
  label_method: "加标方式",
  size_type: "尺寸类型",
  quantity: "数量",
  row_note: "行备注",
  planned_ship_date: "计划发货日期",
  packaging: "包装方式",
  embroidery: "是否绣花",
  similarity_score: "相似分数",
  prototype_match_score: "相似分数",
  density: "密度",
  "客户": "客户",
  "币种": "币种",
  "业务员": "业务员",
  "表头备注": "表头备注",
  "行号": "行号",
  "物料编码": "物料编码",
  "物料名称": "物料名称",
  "规格": "规格",
  "颜色": "颜色",
  "面料": "面料",
  "面料-涤棉成分": "面料-涤棉成分",
  "款式": "款式",
  "加标方式": "加标方式",
  "尺寸类型": "尺寸类型",
  "数量": "数量",
  "行备注": "行备注",
  "计划发货日期": "计划发货日期",
  "包装方式": "包装方式",
  "是否绣花": "是否绣花",
  "相似分数": "相似分数",
};

const AI_DIAGNOSTIC_LABELS = {
  parsed: "已从原始单据提取",
  exact_match: "完全一致",
  equivalent_match: "等价一致",
  matched: "一致",
  partial_match: "部分一致",
  conflict: "存在冲突",
  ambiguous: "存在歧义",
  insufficient_evidence: "证据不足",
  source_not_provided: "原始单据未提供",
  dictionary_no_match: "字典未匹配",
  not_comparable: "无法比较",
  missing: "缺失",
  defaulted: "使用默认值",
  no_match: "不一致",
  missing_query: "订单信息缺失",
  missing_candidate: "物料信息缺失",
  hard_conflict: "关键字段冲突",
};

function localLabel(labels, value, fallback = "未说明") {
  return labels[value] || fallback;
}

function fieldLabel(value) {
  if (AI_FIELD_LABELS[value]) return AI_FIELD_LABELS[value];
  if (/^[A-Za-z_]+$/.test(String(value || ""))) return "其他字段";
  return value || "未命名字段";
}

function diagnosticLabel(value) {
  return localLabel(AI_DIAGNOSTIC_LABELS, value, "未提供状态");
}

function formatReferenceScore(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(3) : "0.000";
}

function matchReviewHint(decision) {
  if (["unique_best_candidate", "ranked_candidates"].includes(decision)) {
    return "当前候选较明确，通常无需AI复核；仍可按需检查当前记录。";
  }
  if (decision === "no_candidate") {
    return "当前没有候选物料，可使用AI辅助检查已有证据。";
  }
  return "当前记录需要进一步判断，可使用AI辅助复核。";
}

function evidenceReferenceLabel(value) {
  const text = String(value || "");
  const mappings = [
    [/^raw_evidence\.(.+)$/i, (match) => `原始PI证据：${fieldLabel(match[1])}`],
    [/^parse_diagnostics\.(.+)$/i, (match) => `字段诊断：${fieldLabel(match[1])}`],
    [/^top_candidates\[(\d+)\]/i, (match) => `候选物料第${Number(match[1]) + 1}名`],
    [/^dictionary_validation/i, () => "字典独立验证结果"],
    [/^formal_record/i, () => "标准解析结果"],
  ];
  for (const [pattern, formatter] of mappings) {
    const match = text.match(pattern);
    if (match) return formatter(match);
  }
  return text || "任务已有证据";
}

function renderTechnicalDetails(advisory, result) {
  const details = advisory.technical_details || {};
  const source = details.source || {};
  const rawEvidence = Array.isArray(details.raw_evidence) ? details.raw_evidence : [];
  const diagnostics = Array.isArray(details.field_diagnostics) ? details.field_diagnostics : [];
  const candidates = Array.isArray(details.candidates) ? details.candidates : [];
  const evidenceReferences = Array.isArray(result.evidence_references) ? result.evidence_references : [];
  const usage = result.usage || {};
  const rawRows = rawEvidence.map((item) => `
    <tr>
      <td>${escapeHtml(fieldLabel(item.field))}</td>
      <td>${escapeHtml((item.source_cells || []).join("、") || "-")}</td>
      <td class="source-text">${escapeHtml(item.source_text || "-")}</td>
    </tr>`).join("");
  const diagnosticRows = diagnostics.map((item) => `
    <tr>
      <td>${escapeHtml(fieldLabel(item.field))}</td>
      <td>${escapeHtml(diagnosticLabel(item.status))}</td>
      <td>${escapeHtml((item.source_cells || []).join("、") || "-")}</td>
    </tr>`).join("");
  const candidateBlocks = candidates.map((candidate) => {
    const comparisonRows = (candidate.field_comparisons || []).map((comparison) => `
      <tr>
        <td>${escapeHtml(fieldLabel(comparison.field))}</td>
        <td>${escapeHtml(comparison.candidate_value || "-")}</td>
        <td>${escapeHtml(diagnosticLabel(comparison.status))}</td>
      </tr>`).join("");
    return `
      <div class="ai-candidate-evidence">
        <div class="ai-candidate-heading">
          <strong>候选${candidate.rank || "-" }：${escapeHtml(candidate.material_code || "-")}</strong>
          <span>参考分数 ${formatReferenceScore(candidate.reference_score)} · 可比较字段 ${Number(candidate.comparable_field_count || 0)} 个</span>
        </div>
        ${comparisonRows ? `<div class="table-scroll"><table class="data-table compact-table"><thead><tr><th>字段</th><th>候选值</th><th>比较结果</th></tr></thead><tbody>${comparisonRows}</tbody></table></div>` : `<p class="ai-muted">没有可展示的候选字段比较。</p>`}
      </div>`;
  }).join("");
  return `
    <details class="ai-evidence-details">
      <summary>查看详细证据</summary>
      <div class="ai-evidence-content">
        <div class="ai-source-line">
          <span><strong>PI文件：</strong>${escapeHtml(source.source_file || advisory.source_file || "-")}</span>
          <span><strong>工作表：</strong>${escapeHtml(source.sheet || advisory.sheet || "-")}</span>
          <span><strong>订单行：</strong>${escapeHtml(source.line_number || advisory.line_number || "-")}</span>
        </div>
        ${rawRows ? `<h4>原始PI证据</h4><div class="table-scroll"><table class="data-table compact-table"><thead><tr><th>字段</th><th>来源单元格</th><th>原始文本</th></tr></thead><tbody>${rawRows}</tbody></table></div>` : ""}
        ${diagnosticRows ? `<h4>字段诊断</h4><div class="table-scroll"><table class="data-table compact-table"><thead><tr><th>字段</th><th>诊断结果</th><th>来源单元格</th></tr></thead><tbody>${diagnosticRows}</tbody></table></div>` : ""}
        ${candidateBlocks ? `<h4>候选物料字段比较</h4>${candidateBlocks}` : ""}
        ${evidenceReferences.length ? `<div class="ai-list"><span>证据来源</span><ul>${evidenceReferences.map((item) => `<li>${escapeHtml(evidenceReferenceLabel(item))}</li>`).join("")}</ul></div>` : ""}
        <div class="ai-metadata">
          <span>模型：${escapeHtml(result.model || "-")}</span>
          <span>Token用量：${Number(usage.total_tokens || 0)}</span>
          <span>响应耗时：${Number(result.latency_ms || 0)} ms</span>
          <span>尝试次数：${Number(result.attempt_count || 0)}</span>
          <span>仅供参考：${result.advisory_only === true ? "是" : "否"}</span>
        </div>
      </div>
    </details>`;
}

function renderAIAdvisory(advisory) {
  const configured = Boolean(state.capabilities.llm?.configured);
  const stateKey = advisory?.state || "not_requested";
  if (advisory?.eligible === false) {
    return `<div class="ai-advisory-panel"><p class="ai-muted">AI增强整单解析不会自动触发单记录AI复核。</p></div>`;
  }
  const notice = `
    <p class="ai-cost-note">${icon("info")}<span>调用豆包可能产生少量Token费用。AI仅供参考，不会修改正式订单结果或自动写回。</span></p>`;
  const hint = `<p class="ai-review-hint">${escapeHtml(matchReviewHint(advisory?.decision_status))}</p>`;
  if (!configured) {
    return `<div class="ai-advisory-panel">${hint}${notice}<button class="button ai-analysis-button" type="button" disabled>豆包模型服务未配置</button></div>`;
  }
  if (stateKey === "running") {
    return `<div class="ai-advisory-panel">${notice}<div class="ai-running"><span class="ai-spinner" aria-hidden="true"></span><div><strong>正在生成AI复核建议</strong><small>正在调用豆包并校验中文结构化结果，请勿重复点击。</small></div></div></div>`;
  }
  if (stateKey === "failed") {
    return `<div class="ai-advisory-panel">${hint}${notice}<div class="ai-error"><strong>AI复核建议未生成</strong><span>${escapeHtml(advisory.error?.message || "请稍后手动重试。")}</span></div><button class="button ai-analysis-button" id="generateAIAdvisory" type="button">重新生成AI复核建议</button></div>`;
  }
  if (stateKey === "completed" || stateKey === "cached") {
    const result = advisory.result || {};
    const fields = Array.isArray(result.suggested_fields) ? result.suggested_fields : [];
    const warnings = Array.isArray(result.warnings) ? result.warnings : [];
    const fieldRows = fields.map((item) => `
      <tr><td>${escapeHtml(fieldLabel(item.field_name))}</td><td>${escapeHtml(item.original_value || "-")}</td><td>${escapeHtml(item.suggested_value || "-")}</td><td>${escapeHtml(item.reason || "未说明")}</td></tr>`).join("");
    const historical = Boolean(advisory.historical_english);
    const actionLabel = localLabel(AI_ACTION_LABELS, result.action);
    const materialLabel = localLabel(AI_MATERIAL_LABELS, result.material_assessment?.status);
    const operations = [];
    if (fields.length === 0) operations.push("暂不自动修改字段，保留标准解析结果。");
    if (["suggest_review", "insufficient_evidence", "needs_manual_review", "ambiguous"].includes(result.action)) {
      operations.push("建议人工核查原始PI证据和候选物料字段。");
    }
    if (["no_suggestion", "insufficient_evidence"].includes(result.material_assessment?.status)) {
      operations.push("暂不确认物料编码。");
    }
    if (operations.length === 0) operations.push("请将AI建议作为人工判断的辅助信息，不自动写回。");
    const historicalBanner = historical ? `
      <div class="ai-history-note">
        <div><strong>历史英文建议</strong><span>该结果来自旧版本。固定标签已中文化，原有英文建议内容保持不变且不会自动重新调用。</span></div>
        <button class="button secondary-button" id="generateAIAdvisory" data-regenerate="true" type="button">重新生成中文建议</button>
      </div>` : "";
    const regenerationError = advisory.error ? `<div class="ai-error preserved"><strong>中文建议重新生成失败</strong><span>${escapeHtml(advisory.error.message || "历史英文建议已保留，请稍后手动重试。")}</span></div>` : "";
    return `
      <div class="ai-advisory-panel completed">
        ${historicalBanner}
        ${regenerationError}
        <div class="ai-advisory-heading">
          <div><strong>AI复核建议</strong><span class="status-pill ${stateKey === "cached" ? "candidate" : "recommendation"}">${AI_STATE_LABELS[stateKey]}</span></div>
          <span class="ai-readonly">仅供参考，不会自动写回</span>
        </div>
        <div class="ai-summary-grid">
          <div><span>AI复核结论</span><strong>${escapeHtml(actionLabel)}</strong></div>
          <div><span>置信度</span><strong>${(Number(result.confidence || 0) * 100).toFixed(0)}%</strong></div>
          <div><span>物料评估</span><strong>${escapeHtml(materialLabel)}</strong></div>
        </div>
        <div class="ai-reason"><span>主要依据</span><p>${escapeHtml(result.reasoning_summary || "模型未提供补充依据。")}</p></div>
        <div class="ai-actions-block">
          <span>建议操作</span>
          <ul>${operations.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
        </div>
        ${fields.length ? `<div class="ai-fields"><h4>建议修改字段</h4><div class="table-scroll"><table class="data-table ai-fields-table"><thead><tr><th>字段</th><th>原值</th><th>建议值</th><th>修改原因</th></tr></thead><tbody>${fieldRows}</tbody></table></div></div>` : ""}
        <div class="ai-assessment"><span>物料评估说明</span><p>${escapeHtml(result.material_assessment?.reason || "未提供补充说明。")}</p></div>
        <div class="ai-list risks"><span>风险提示</span>${warnings.length ? `<ul>${warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : `<p>未提供额外风险提示，仍需由业务人员确认最终结果。</p>`}</div>
        ${renderTechnicalDetails(advisory, result)}
      </div>`;
  }
  return `<div class="ai-advisory-panel">${hint}${notice}<button class="button ai-analysis-button" id="generateAIAdvisory" type="button">AI复核建议</button></div>`;
}

function confirmAIReview() {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "ai-confirm-overlay";
    overlay.setAttribute("role", "presentation");
    overlay.innerHTML = `
      <div class="ai-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="aiConfirmTitle">
        <h2 id="aiConfirmTitle">确认生成AI复核建议</h2>
        <p>本次仅复核当前订单记录。</p>
        <p>将调用豆包模型，可能产生少量Token费用。</p>
        <p>AI结果仅供参考，不会修改正式订单数据。</p>
        <div class="ai-confirm-actions">
          <button class="button secondary-button" data-action="cancel" type="button">取消</button>
          <button class="button" data-action="confirm" type="button">确认生成</button>
        </div>
      </div>`;
    const close = (value) => {
      document.removeEventListener("keydown", onKeyDown);
      overlay.remove();
      resolve(value);
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") close(false);
    };
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) close(false);
    });
    overlay.querySelector('[data-action="cancel"]').addEventListener("click", () => close(false));
    overlay.querySelector('[data-action="confirm"]').addEventListener("click", () => close(true));
    document.addEventListener("keydown", onKeyDown);
    document.body.appendChild(overlay);
    overlay.querySelector('[data-action="confirm"]').focus();
  });
}

async function startAIAdvisory(detail, regenerateChinese = false) {
  const confirmed = await confirmAIReview();
  if (!confirmed) return;
  const button = document.getElementById("generateAIAdvisory");
  if (button) {
    button.disabled = true;
    button.textContent = "正在提交...";
  }
  const advisory = detail.ai_advisory;
  try {
    await api(`/api/tasks/${detail.job_id}/ai-enhance`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: detail.job_id,
        record_index: detail.index,
        source_record_id: advisory.source_record_id,
        source_file: advisory.source_file,
        sheet: advisory.sheet,
        line_number: advisory.line_number,
        regenerate_chinese: regenerateChinese,
      }),
    });
    renderMatch(detail.job_id, detail.index);
  } catch (error) {
    showToast(error.message);
    renderMatch(detail.job_id, detail.index);
  }
}

function unavailableEstimate(value) {
  return Number.isFinite(value) ? String(value) : "当前无法可靠估算";
}

function confirmAIEnhanced(file, preflight) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "ai-confirm-overlay";
    overlay.innerHTML = `
      <section class="ai-confirm-dialog ai-full-confirm" role="dialog" aria-modal="true" aria-labelledby="aiFullConfirmTitle">
        <h2 id="aiFullConfirmTitle">确认AI整单解析</h2>
        <dl class="confirm-list">
          <div><dt>文件</dt><dd>${escapeHtml(file.name)}</dd></div>
          <div><dt>解析方式</dt><dd>AI整单解析</dd></div>
          <div><dt>Provider / 模型</dt><dd>${escapeHtml(preflight.provider || "当前未配置")} / ${escapeHtml(preflight.model || "当前未配置")}</dd></div>
          <div><dt>Sheet / 区块数</dt><dd>确认后在本地预扫描</dd></div>
          <div><dt>预计逻辑调用数</dt><dd>${unavailableEstimate(preflight.max_logical_calls || null)}</dd></div>
          <div><dt>Token估算</dt><dd>${unavailableEstimate(preflight.token_estimate)}</dd></div>
          <div><dt>费用估算</dt><dd>${unavailableEstimate(preflight.cost_estimate)}</dd></div>
          <div><dt>失败处理</dt><dd>失败时暂停，等待你选择重试、使用标准解析重新处理或保留失败。</dd></div>
        </dl>
        <p>确认后，仅发送与订单解析有关的必要坐标化数据，不发送 Excel 二进制。AI结果仍须通过本地证据、字段合同和业务校验。</p>
        <p>AI不会生成ERP物料编码，物料编码仍由本地物料匹配层产生。</p>
        <label class="confirm-check"><input id="aiFullConsent" type="checkbox"> 我同意发送必要订单内容并承担可能产生的Token费用。</label>
        <div class="ai-confirm-actions"><button class="button secondary-button" data-action="cancel" type="button">取消</button><button class="button primary" data-action="confirm" type="button" disabled>确认并开始</button></div>
      </section>`;
    const close = (value) => { overlay.remove(); resolve(value); };
    const confirm = overlay.querySelector('[data-action="confirm"]');
    overlay.querySelector("#aiFullConsent").addEventListener("change", (event) => { confirm.disabled = !event.target.checked; });
    overlay.querySelector('[data-action="cancel"]').addEventListener("click", () => close(false));
    confirm.addEventListener("click", () => { confirm.disabled = true; close(true); });
    overlay.addEventListener("click", (event) => { if (event.target === overlay) close(false); });
    document.body.appendChild(overlay);
    overlay.querySelector("#aiFullConsent").focus();
  });
}

async function loadAIEnhancedPreflight() {
  try {
    state.aiPreflight = await api("/api/ai-enhanced/preflight");
  } catch {
    state.aiPreflight = {
      ready: false,
      v2_backend_available: false,
      provider_configured: false,
      provider_ready: false,
      real_call_requires_user_confirmation: true,
      unavailable_reason_code: "AI_PREFLIGHT_UNAVAILABLE",
      unavailable_reason_text: "AI整单解析服务当前不可用，完成配置后即可提交。",
      reason: "AI整单解析服务当前不可用，完成配置后即可提交。",
      provider: "",
      model: "",
      max_logical_calls: 0,
      token_estimate: null,
      cost_estimate: null,
    };
  }
}

async function renderMatch(jobId, index) {
  const expectedHash = `#job/${jobId}/match/${index}`;
  stopPolling();
  setActiveNav("upload");
  try {
    const detail = await api(`/api/jobs/${jobId}/matches/${index}`);
    if (window.location.hash !== expectedHash) return;
    const comparisons = detail.comparisons.map((row) => `
      <tr><td>${escapeHtml(row.field)}</td><td>${escapeHtml(row.order_value || "-")}</td><td>${escapeHtml(row.candidate_value || "-")}</td><td>${statusPill(row.status)}</td></tr>`).join("");
    const candidates = detail.candidates.map((candidate) => `
      <tr><td>${candidate.rank}</td><td>${escapeHtml(candidate.material_code)}</td><td><div class="score-cell"><div class="score-bar"><span style="width:${Math.max(0, Math.min(100, candidate.score))}%"></span></div><span>${formatReferenceScore(candidate.reference_score)}</span></div></td></tr>`).join("");
    app.innerHTML = `
      <section class="page page-detail">
        <header class="detail-header">
          <button class="back-button" id="backResult" type="button">${icon("chevron-left")}返回</button>
          <h1>匹配详情</h1><span></span>
        </header>
        <div class="detail-meta">
          <span><strong>订单行：</strong>${escapeHtml(detail.line_number)}</span>
          <span><strong>物料名称：</strong>${escapeHtml(detail.material_name || "-")}</span>
          <span><strong>规格：</strong>${escapeHtml(detail.spec || "-")}</span>
        </div>
        <section class="section">
          <h2 class="section-title">匹配结果</h2>
          <div class="match-result">
            <span class="result-code">推荐物料编码：<strong>${escapeHtml(detail.recommended_code || "暂无候选")}</strong></span>
            <span>参考匹配分数：<strong>${formatReferenceScore(detail.reference_score)}</strong></span>
            <span>状态：${statusPill(detail.status)}</span>
          </div>
          <p class="score-disclaimer">参考匹配分数未经业务真值标定，不代表准确率或正确概率；请结合可比较字段、缺失和冲突判断。</p>
        </section>
        <section class="section">
          <h2 class="section-title">AI复核建议</h2>
          <div id="aiAdvisory">${renderAIAdvisory(detail.ai_advisory)}</div>
        </section>
        <section class="section">
          <h2 class="section-title">匹配项对比</h2>
          <table class="data-table"><thead><tr><th>字段</th><th>订单内容</th><th>推荐物料</th><th>匹配状态</th></tr></thead><tbody>${comparisons}</tbody></table>
        </section>
        <section class="section">
          <h2 class="section-title">候选物料 Top 5</h2>
          ${candidates ? `<table class="data-table"><thead><tr><th>排名</th><th>物料编码</th><th>参考分数</th></tr></thead><tbody>${candidates}</tbody></table>` : `<div class="empty-state">当前订单行没有可推荐候选。</div>`}
        </section>
      </section>`;
    document.getElementById("backResult").addEventListener("click", () => navigate(`job/${jobId}/result`));
    const aiButton = document.getElementById("generateAIAdvisory");
    aiButton?.addEventListener("click", () => startAIAdvisory(detail, aiButton.dataset.regenerate === "true"));
    if (detail.ai_advisory?.state === "running") {
      state.pollTimer = window.setTimeout(() => renderMatch(jobId, index), 900);
    }
  } catch (error) {
    showToast(error.message);
  }
}

function historyStatus(job) {
  const labels = { completed: "成功", processing: "解析中", queued: "等待中", awaiting_user_decision: "等待决定", failed: "解析失败", interrupted: "已中断" };
  const key = job.status === "completed" ? "match" : job.status === "failed" ? "conflict" : "partial";
  return { key, label: labels[job.status] || "未知" };
}

function isThisMonth(value) {
  const date = new Date(value);
  const now = new Date();
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth();
}

function renderHistoryRows(jobs) {
  if (!jobs.length) return `<tr><td colspan="7"><div class="empty-state">暂无符合条件的解析记录。</div></td></tr>`;
  return jobs.map((job) => {
    const status = historyStatus(job);
    const summary = job.summary || {};
    const viewRoute = job.status === "completed" ? `job/${job.id}/result` : `job/${job.id}/progress`;
    return `
      <tr>
        <td class="filename" title="${escapeHtml(job.file_name)}">${escapeHtml(job.file_name)}</td>
        <td>${formatDate(job.created_at)}</td>
        <td><span class="mode-chip ${job.parse_mode === "ai_enhanced" ? "ai" : ""}">${escapeHtml(job.parse_mode_label || "标准解析（历史任务）")}</span>${job.fallback?.status === "confirmed" ? `<small class="fallback-inline">已回退</small>` : ""}</td>
        <td>${job.record_count || "-"}</td>
        <td>${statusPill(status)}</td>
        <td class="match-counts" title="推荐明确 / 建议人工查看 / 冲突">${job.status === "completed" ? `<span class="g">${summary.high_match}</span> / <span class="a">${summary.partial_match}</span> / <span class="r">${summary.conflict}</span>` : "-"}</td>
        <td><div class="actions"><button class="table-action view-job" data-route="${viewRoute}" type="button">查看</button>${job.artifacts.zip ? `<a class="table-action artifact-download" data-job="${job.id}" data-kind="zip" href="/api/jobs/${job.id}/download-all">下载</a>` : ""}<button class="table-action more-job" type="button" title="更多">${icon("more")}</button></div></td>
      </tr>`;
  }).join("");
}

async function renderHistory() {
  const expectedHash = "#history";
  stopPolling();
  setActiveNav("history");
  try {
    const payload = await api("/api/jobs");
    if (window.location.hash !== expectedHash) return;
    state.historyJobs = payload.jobs;
    state.historyPage = 1;
    app.innerHTML = `
      <section class="page page-history">
        <header class="history-heading"><h1>历史记录</h1></header>
        <div class="history-stats">
          <article class="history-stat"><span>本月解析订单</span><strong id="monthJobs">0<small> 份</small></strong></article>
          <article class="history-stat"><span>成功完成</span><strong id="successJobs">0<small> 份</small></strong></article>
          <article class="history-stat review"><span>需人工复核</span><strong id="reviewRecords">0<small> 条</small></strong></article>
        </div>
        <div class="filters">
          <label class="control">${icon("search")}<input id="historySearch" type="search" placeholder="搜索文件名"></label>
          <div class="control date-range">${icon("calendar")}<input id="dateStart" type="date" aria-label="开始日期"><i>至</i><input id="dateEnd" type="date" aria-label="结束日期"></div>
          <label class="control"><select id="statusFilter" aria-label="解析状态"><option value="">全部状态</option><option value="completed">成功完成</option><option value="processing">解析中</option><option value="awaiting_user_decision">等待决定</option><option value="failed">解析失败</option></select></label>
          <label class="control"><select id="modeFilter" aria-label="解析方式"><option value="">全部方式</option><option value="standard">标准解析</option><option value="ai_enhanced">AI增强整单解析</option><option value="fallback">已回退</option></select></label>
        </div>
        <div class="table-scroll">
          <table class="data-table history-table">
            <thead><tr><th>文件名</th><th>上传时间</th><th>解析方式</th><th>订单数量</th><th>解析状态</th><th>匹配情况</th><th>操作</th></tr></thead>
            <tbody id="historyBody"></tbody>
          </table>
        </div>
        <div class="pagination"><span id="historyCount">共 0 条</span><div class="page-controls"><button class="page-button" id="previousPage" aria-label="上一页">${icon("chevron-left")}</button><button class="page-button current" id="currentPage">1</button><button class="page-button" id="nextPage" aria-label="下一页">${icon("chevron-right")}</button></div></div>
      </section>`;
    ["historySearch", "dateStart", "dateEnd", "statusFilter", "modeFilter"].forEach((id) => {
      document.getElementById(id).addEventListener("input", () => {
        state.historyPage = 1;
        updateHistoryTable();
      });
    });
    document.getElementById("previousPage").addEventListener("click", () => {
      state.historyPage = Math.max(1, state.historyPage - 1);
      updateHistoryTable();
    });
    document.getElementById("nextPage").addEventListener("click", () => {
      state.historyPage += 1;
      updateHistoryTable();
    });
    updateHistoryStats();
    updateHistoryTable();
  } catch (error) {
    showToast(error.message);
  }
}

function updateHistoryStats() {
  const jobs = state.historyJobs;
  const month = jobs.filter((job) => isThisMonth(job.created_at));
  document.getElementById("monthJobs").innerHTML = `${month.length}<small> 份</small>`;
  document.getElementById("successJobs").innerHTML = `${jobs.filter((job) => job.status === "completed").length}<small> 份</small>`;
  const reviews = jobs.reduce((sum, job) => sum + Number(job.summary?.partial_match || 0) + Number(job.summary?.conflict || 0), 0);
  document.getElementById("reviewRecords").innerHTML = `${reviews}<small> 条</small>`;
}

function filteredHistoryJobs() {
  const search = document.getElementById("historySearch").value.trim().toLowerCase();
  const start = document.getElementById("dateStart").value;
  const end = document.getElementById("dateEnd").value;
  const status = document.getElementById("statusFilter").value;
  const mode = document.getElementById("modeFilter").value;
  return state.historyJobs.filter((job) => {
    const date = job.created_at.slice(0, 10);
    return (!search || job.file_name.toLowerCase().includes(search))
      && (!start || date >= start)
      && (!end || date <= end)
      && (!status || job.status === status)
      && (!mode || (mode === "fallback" ? job.fallback?.status === "confirmed" : job.parse_mode === mode));
  });
}

function updateHistoryTable() {
  const jobs = filteredHistoryJobs();
  const pageSize = 5;
  const pageCount = Math.max(1, Math.ceil(jobs.length / pageSize));
  state.historyPage = Math.min(state.historyPage, pageCount);
  const start = (state.historyPage - 1) * pageSize;
  document.getElementById("historyBody").innerHTML = renderHistoryRows(jobs.slice(start, start + pageSize));
  document.getElementById("historyCount").textContent = `共 ${jobs.length} 条`;
  document.getElementById("currentPage").textContent = state.historyPage;
  document.getElementById("previousPage").disabled = state.historyPage <= 1;
  document.getElementById("nextPage").disabled = state.historyPage >= pageCount;
  document.querySelectorAll(".view-job").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.route)));
  document.querySelectorAll(".more-job").forEach((button) => button.addEventListener("click", () => showToast("更多操作将在后续版本开放。")));
  bindDownloadLinks(document.getElementById("historyBody"));
}

function route() {
  const value = window.location.hash.replace(/^#\/?/, "") || "upload";
  const parts = value.split("/");
  if (parts[0] === "help") return renderHelp();
  if (parts[0] === "history") return renderHistory();
  if (parts[0] === "job" && parts[2] === "progress") return renderProgress(parts[1]);
  if (parts[0] === "job" && parts[2] === "result") return renderResult(parts[1]);
  if (parts[0] === "job" && parts[2] === "match") return renderMatch(parts[1], Number(parts[3]));
  return renderUpload();
}

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => navigate(button.dataset.route));
});
document.querySelectorAll(".plain-nav").forEach((button) => {
  button.addEventListener("click", () => {
    if (button.dataset.route) {
      navigate(button.dataset.route);
      return;
    }
    showToast(button.dataset.message);
  });
});
document.getElementById("displayButton").addEventListener("click", () => {
  document.body.classList.toggle("high-contrast");
  showToast("显示对比度已调整。");
});
document.getElementById("closePreview").addEventListener("click", () => previewModal.classList.add("hidden"));
previewModal.addEventListener("click", (event) => {
  if (event.target === previewModal) previewModal.classList.add("hidden");
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  previewModal.classList.add("hidden");
  document.querySelector('.ai-confirm-overlay [data-action="cancel"]')?.click();
});
window.addEventListener("hashchange", route);
window.addEventListener("beforeunload", stopPolling);
window.addEventListener("pywebviewready", () => bindDownloadLinks());

async function initialize() {
  await loadCapabilities();
  await loadAIEnhancedPreflight();
  route();
}

initialize();
