# Final Documentation Audit｜订单解析助手最终事实与文档素材底稿

日期：2026-08-12
项目：`D:\AI-Learning\Projects\bedding-order-parser`
性质：只读事实审计再认证；本轮只更新这一份既有事实底稿，不是产品实现、最终 Word 或截图采集任务。

## 1. 基线、HEAD 与审计口径

| 项目 | 事实 |
|---|---|
| 分支 | `master` |
| 起始完整 HEAD | `ba3206dcf3c243811597182b7974b8063df3985f` |
| 起始短 HEAD | `ba3206d` |
| 起始提交 | `docs: capture final documentation visual assets` |
| 起始已跟踪工作区 | 干净 |
| 既有未跟踪文件 | 7 份交接/架构文档；本轮未修改、未暂存、未删除 |
| 最终事实源 | 当前 `master` 代码、测试与 `GATE_4D_D4A6F_RELEASE_BLOCKER_CLEANUP_AND_FINAL_SIGNOFF.md` |
| 历史报告用途 | 解释演变和历史真实验收；与当前代码冲突时以当前代码为准 |
| 本轮执行限制 | 未调用 Ark、外部 HTTP、真实 PI、真实字典/物料、BGE-M3 或生产 FAISS；未运行测试 |

本报告最初由提交 `38fc646ef19cba15a394206258c69cbfe92ba9a8` 建立。本轮核对 `38fc646..ba3206d`：`src/`、`tests/`、`pyproject.toml`、`AGENTS.md` 和项目 Skill 均无变化；其间只新增 16 张正式截图、4 张 SVG/PNG 架构图、素材索引和视觉素材报告。因此第 2-29 节代码与测试事实继续有效，本次只更新基线、截图素材状态和 Word 前置条件。

最终签署报告记录：`CORE IMPLEMENTATION COMPLETE`、`READY TO CLOSE`、Release Blockers = 0；完整最大安全测试为 670 collected / 670 passed / 0 skipped / 0 failed，耗时 90.17 秒（`docs/reports/GATE_4D_D4A6F_RELEASE_BLOCKER_CLEANUP_AND_FINAL_SIGNOFF.md:204-218, 290-318`）。

## 2. 当前项目最终状态

当前冻结范围已经完成两种解析模式、固定 20 字段、五类结果、桌面 Job、历史记录、AI Review、不可变 Revision、独立 Standard reprocess、帮助中心和桌面壳。项目可关闭不等于没有后续优化；第 28 节列出的事项是非阻断 backlog。

三层技术口径必须分开：

1. **项目直接实现**：Excel 几何预处理、Standard 规则解析、AI/Python 编排、严格合同、本地证据绑定、字段决策、Job 状态、缓存/恢复、原子发布、Revision、Web/API/UI。
2. **项目集成外部组件**：火山方舟 Ark Responses API、`openpyxl`、`sentence-transformers`、BGE-M3、FAISS、`pywebview`、Playwright/Pytest。
3. **外部底层理论**：Transformer、Attention、向量空间和 ANN 理论。仓库没有自行实现这些网络或理论算法。

固定正式字段由 `models/final_result.py:9-30` 的 `FINAL_FIELD_NAMES` 定义。前 19 项是字符串，`相似分数`为浮点数；AI 只可候选 17 个业务字段，`行号`由本地生成，`物料编码`和`相似分数`由匹配层生成（`models/final_result.py:32-58`；`ai_full_order/contracts.py:42-50`）。

## 3. 仓库模块结构

### 3.1 主要目录树

```text
src/bedding_order_parser/
├─ ai_full_order/   AI整单合同、结构、证据、字段决策、缓存、发布和修订
├─ desktop/         pywebview桌面壳、资源定位、单实例和服务生命周期
├─ diagnostics/     解析诊断报告构造
├─ dictionaries/    字典预览、对照和validation-only验证
├─ excel/           工作簿读取、Sheet定位、合并单元格和表格解析
├─ extraction/      Standard元数据、买卖方和订单行提取
├─ llm/             Provider端口、Ark实现、Transport、配置和Sidecar合同
├─ materials/       物料库、Embedding、FAISS、候选、混合匹配和复核
├─ models/          固定20字段、来源证据等领域模型
├─ normalization/   Standard字段规范化
├─ pipeline/        Standard主解析编排
├─ serialization/   正式结果和诊断的安全写入
└─ web/             本地HTTP、route、JobService、API与前端静态资源
```

### 3.2 模块职责索引

| 模块 | 输入 | 输出 | 主要调用方 | 关键位置 | 大白话 |
|---|---|---|---|---|---|
| `excel/` | `.xlsx` | 工作簿、目标 Sheet、表头/记录行 | Standard parser、AI preprocessing | `workbook_reader.py`、`sheet_locator.py`、`table_parser.py` | 安全打开 Excel，并把表格结构找出来 |
| `extraction/` | Sheet、行、上下文 | 客户、币种、业务员及订单行字段 | `pipeline.parse_order()` | `metadata_extractor.py`、`party_extractor.py`、`item_extractor.py` | 按确定性规则从表里取字段 |
| `normalization/` | Standard 原始字段 | Standard 规范字段 | Standard pipeline | `field_normalizer.py` | 把本地规则结果整理成固定格式 |
| `pipeline/` | Excel 路径 | `ParseSummary`、正式 JSON、诊断 | `JobService._run_standard_job()` | `order_parser.py:30-150` | Standard 总调度器 |
| `dictionaries/` | 正式字段、来源证据、字典规则 | 字典验证 JSON | Standard、AI downstream、Revision | `product_validation.py:58-266` | 提醒字段是否被规则认识，不替用户编值 |
| `materials/` | 订单业务字段、物料资料、向量索引 | TopK 候选、匹配摘要、编码/分数选择 | Standard、AI downstream、Revision | `hybrid_matcher.py:71-259` | 找相似物料并给参考候选 |
| `ai_full_order/` | 坐标化工作簿、Ark候选、Python shadow | canonical 17、诊断、五类 bundle、Revision | AI Job service | `preprocessing.py`、`field_policy.py`、`reliability_v2.py`、`downstream.py` | AI整单模式的核心安全与业务层 |
| `llm/` | 安全 JSON 请求 | Ark结构化结果、白名单 telemetry | 整单 Provider、单记录 Sidecar | `volcengine_ark.py`、`transport.py`、`settings.py` | 把本地请求安全送到 Provider，并分类返回/错误 |
| `web/` | 浏览器 HTTP/API | Job JSON、预览/下载、前端页面 | 桌面壳、本地浏览器 | `app.py`、`routes.py`、`services.py`、`static/app.js` | 本地服务、任务管理和页面 |
| `desktop/` | 本地资源和应用配置 | loopback URL、pywebview窗口 | Windows快捷方式/入口 | `launcher.py`、`server_controller.py` | 启动本地服务并套成桌面应用 |
| `serialization/` | Python对象/JSON payload | 原子写入的结果文件 | Standard pipeline | `json_writer.py`、`diagnostic_writer.py` | 防止结果只写了一半 |

## 4. Standard 完整链路

### 4.1 技术调用链

```text
app.js::startParsing(parse_mode=standard)
→ POST /api/jobs
→ routes.py::WebRequestHandler
→ services.py::JobService.create_job()/start_job()
→ JobService._run_standard_job()
→ pipeline/order_parser.py::parse_order()
→ excel loader / sheet locator / table parser
→ extraction metadata / party / item
→ normalization / FinalResult(20字段骨架)
→ serialization::write_parse_outputs()
→ dictionaries::build_product_validation_report()
→ materials::hybrid_matcher.match_orders()
→ materials::match_writer.write_match_outputs()
→ JobService登记五角色并生成Standard ZIP
→ app.js::renderResult()/renderMatch()
→ 用户可预览、单文件下载、ZIP下载、按需单记录AI Sidecar
```

关键入口：`web/routes.py:94-113`、`web/services.py:267-383, 1773-1910`、`pipeline/order_parser.py:43-150`。

### 4.2 业务链

```text
Excel进来
→ Python按表头和规则识别订单
→ 整理成固定字段
→ 字典提示哪些值认识/不认识
→ 结构化条件 + 向量检索找相似物料
→ 组装正式20字段
→ 输出五类结果和Standard ZIP
→ 用户查看候选；需要时才对单条记录调用AI复核
```

Standard 的 Python 是主解析器。单记录 AI Sidecar 由结果/匹配详情页用户操作触发，走 `/api/tasks/{job_id}/ai-enhance`，不会自动改变五类正式结果（`web/routes.py:77-92`；`web/services.py:939-1010`；`web/static/app.js:1147-1278`）。

## 5. AI Enhanced 完整链路

| 步骤 | 业务含义 | 技术动作 | 必要性/缺失风险 | 代码证据 |
|---|---|---|---|---|
| 1. 模式与授权 | 用户明确选择整单 AI | preflight 检查配置；确认必要数据和 Token | 防止启动/浏览页面误调用 AI | `app.js:371-493,1285-1338`；`web/routes.py:59-66` |
| 2. Job 与源身份 | 为本次上传建立独立任务 | 保存 `parse_mode`、source SHA、幂等身份和状态 | 文件名相同不代表内容相同 | `web/services.py:267-383` |
| 3. 预处理 | 看清各 Sheet、单元格和记录范围 | 双视图读 Excel、排除隐藏内容、合并锚点、稀疏 cell/evidence | 直接把二进制交给模型会失去边界和可追溯性 | `preprocessing.py:54-235,235-420` |
| 4. 每 Sheet 结构 | 区分已确认订单区、辅助页和待决页 | Standard geometry + local candidates + per-sheet state | 多 Sheet 中说明页可能被错当订单 | `standard_geometry.py:22-90`；`preprocessing.py:429-720` |
| 5. 可选 Layout AI | 仅在本地 unresolved 时选择候选 | 构造 bounded manifest，Ark只能选本地 candidate或unresolved | 防止模型自创坐标/record/scope | `structure_manifest.py:49-198`；`structure_resolution.py:72-275` |
| 6. Extraction Unit | 每个本地记录成为单目标提取单元 | 固定 target、scope、sheet、source row、evidence catalog | 降低跨记录串值 | `orchestration.py:245-352` |
| 7. Ark V2候选 | AI理解17个业务字段 | strict function `submit_bedding_order_candidates_v2`，稀疏 candidates | 不强迫模型编空字段或系统身份 | `volcengine_ark.py:45-66,211-235,358-369` |
| 8. 严格技术验证 | 确保返回形状可信 | V2 Schema、额外/禁止/重复字段验证 | 非法 envelope 不能进业务层 | `contracts.py:453-581` |
| 9. Evidence/Provenance | 证明候选属于当前记录和来源 | unknown/cross-scope/not-in-target hard reject；内容问题标字段 issue | 身份错误会污染其他订单 | `provenance.py:108-164,200-324` |
| 10. Python Shadow | 给 AI 一份独立本地对照 | 对同一 target 跑确定性 Python adapter | AI漏项可补空，差异可复核 | `python_shadow.py:33-111`；`ai_full_order_service.py:432-451` |
| 11. Normalization | 统一确定性格式 | Unicode/空白、币种、十进制数量、完整日期 | 表现差异不应伪装成业务冲突 | `normalization.py:13-130` |
| 12. AI-first决策 | 形成17字段正式主值和对照 | AI有效则选AI；AI缺失/内容问题才Python fill或空 | 让AI真正负责业务理解，同时不丢第二意见 | `field_policy.py:97-216,219-360` |
| 13. Technical ready | 判断技术上能否进入下游 | 17字符串完整、身份/证据硬边界通过；review独立计数 | 业务差异不能误判为技术失败 | `orchestration.py:145-165,446-518` |
| 14. Reliability | 缓存、幂等、single-flight、恢复 | 缓存validated候选，命中后按当前政策重验证 | 避免重复调用和旧政策误复用 | `reliability_v2.py:102-315,435-870` |
| 15. 字典与物料 | 对AI主值运行相同下游职责 | validator + matcher；编码/分数只来自 matcher | AI不得编ERP编码 | `downstream.py:110-153,228-335` |
| 16. 正式20字段 | 17 + 本地行号 + matcher两字段 | `FinalResult`严格组装 | 保持Standard/AI统一业务合同 | `downstream.py:304-335`；`final_result.py:9-58` |
| 17. 五类发布 | 一次展示完整结果 | staging校验、bundle目录、原子切`CURRENT` | 不能出现3新+2旧 | `downstream.py:555-722` |
| 18. Review与来源 | 用户看AI/Python差异和证据 | comparison只进parse diagnostics；UI展示sheet/range/excerpt | 可复核但不污染正式20字段 | `downstream.py:377-548`；`app.js:597-776` |
| 19. Revision | 用户保留AI、用Python或手改 | 不调Ark；重跑本地下游；发布不可变新版本 | 保留审计历史和当前版本一致性 | `revisions.py:92-365`；`web/services.py:754-823` |

## 6. Multi-sheet Structure

多 Sheet 的难点不是“Sheet多”，而是订单页、辅助说明页、隐藏页和非标准订单页角色不同。

- **confirmed sheet**：本地 Standard geometry 能稳定识别订单结构，直接形成 known chunk，不调用 Layout AI。
- **unresolved sheet**：本地不能安全确认角色，但可以构造有限候选，进入 `unresolved_sheets`。
- **local candidate**：本地根据真实 cell/block/record 几何生成稳定 `candidate_id`，角色只能是 `order` 或受控 `auxiliary`。
- **AI Layout 能做**：对每个 unresolved Sheet，从请求中已广告的候选选择一个，或返回 unresolved。
- **AI Layout 不能做**：创建 Sheet、坐标、block、record identity、scope、evidence 或任意新范围。
- **local validator/binder/apply**：验证输出数量、Sheet归属、role/reason、candidate ID重算和context SHA，再从本地对象恢复真正记录与证据。

关键代码：`structure_manifest.py:23-45,49-198,271-421`；`structure_resolution.py:29-63,72-275`。真实开发验收曾用 1 次受限 Ark Layout 调用证明这一候选选择协议可工作；D4A-6F 最终签署本身真实 Ark = 0（`GATE_4D_D4A3E_ARK_REAL_MULTI_SHEET_STRUCTURE_ACCEPTANCE_REPORT.md:69-208`）。

## 7. AI-first 与 Python Shadow

| 场景 | 正式值 | comparison | Review | 是否因业务差异阻断 |
|---|---|---|---|---|
| AI有效 + Python相同 | AI | `agree` | 通常否 | 否 |
| AI有效 + 规范化后相同 | AI派生规范值/AI显示值按字段合同 | `equivalent_after_normalization` | 通常否 | 否 |
| AI有效 + Python不同 | AI | `different` | 是，高关注字段为high | 否 |
| 仅AI有值 | AI | `ai_only` | semantic/source_summary时可要求Review | 否 |
| AI缺失 + Python有值 | Python补空 | `python_fill` | 是，`local_rule_fill` | 否 |
| 双方都空 | 空字符串 | `both_missing` | 是 | 否 |
| AI内容不可采信 + Python有值 | Python补空 | `python_fill` + content issue | 是 | 否 |
| AI内容不可采信 + Python也空 | 空字符串 | `both_missing` + content issue | 是 | 否 |
| identity/scope/evidence ownership失败 | 不形成canonical | 技术失败 | 不适用 | **硬阻断** |

高关注字段是客户、币种、业务员、数量、计划发货日期，只提高 Review 严重度，不批准/否决 AI（`field_policy.py:30-49`）。答辩表述：**AI负责业务理解，Python提供第二意见和补空，系统身份事实仍由程序保护。**

## 8. Evidence 与 Provenance

- **Evidence**：本地从 Excel 提取的具体来源对象，包含 `evidence_id`、scope、Sheet、cell range、原文和规范文本（`preprocessing.py:79-100`）。
- **Provenance**：把一个 AI candidate 绑定到合法 Evidence、当前 target 和当前 scope 的验证关系；不是单纯“模型说它有证据”（`provenance.py:108-164`）。
- **UI可见来源**：白名单 Sheet 名、cell/range、从原文压缩并截断到 180 字符的 bounded excerpt（`downstream.py:521-548`）。
- **硬身份检查**：target record/source/scope/sheet/source row、evidence存在性、scope和extraction-unit归属。
- **内容问题**：证据属于当前记录，但 direct value/quote无法在规范文本中定位；字段转为content issue并安全fallback/empty，不升级为整批身份失败。

没有 Evidence，用户无法回看 AI 从哪里理解；没有 Provenance，合法的某个单元格可能被错误借给另一个订单。

## 9. Normalization

版本：`NORMALIZATION_VERSION = "1.0"`（`ai_full_order/normalization.py:13`）。当前只做确定性转换：

| 类型 | 当前规则 | 例子 | 边界 |
|---|---|---|---|
| 通用文本 | NFKC Unicode、连续空白折叠、首尾空白 | 全角/多空格统一 | 不猜业务同义词 |
| 币种 | 白名单 `usd`/`US Dollar`/`美元` | `美元 → USD` | 未列别名不猜 |
| 数量 | 纯十进制字符串规范 | `10.0 → 10` | 不解析“一百” |
| 日期 | 完整ISO、斜线或中文年月日 | `2026年12月31日 → 2026-12-31` | 不把订单日期猜成发货日期 |
| 备注 | 仅验证空白/标点排版等价 | 换行/标点整理 | 扩写事实不接受 |

币种、数量、计划发货日期的正式值可使用 AI 值派生的规范结果，但 `selected_source`仍是`ai`。Normalization 是格式统一，不是改用 Python，也不是重新理解业务。

## 10. Dictionary Validation

`product_validation.py:30-42` 定义 `VALIDATION_VERSION=1.0`、`validation_only`，当前检查物料名称、币种、规格、颜色。状态包括 exact/equivalent/partial/ambiguous/no-match/source-not-provided/conflict；动作只有 `keep_python` 或 `manual_review`。

- Standard：`parse_order()`后运行，并写独立字典验证 JSON。
- AI Enhanced：technical-ready后，对canonical 17运行同一职责的适配器。
- Revision：每次修改业务字段后重跑本地字典验证。
- Warning/不匹配：用于诊断，不静默把AI正式值改成Python，也不自行编值。

大白话：**字典是在提醒“系统认不认识这个值”，不是替用户做最终业务决定。**

## 11. Material、Embedding、FAISS 与 TopK

### 11.1 物料资料到索引

```text
原始物料CSV
→ loader读取并计算SHA
→ normalizer规范品类/规格/颜色/纱支/密度/成分等
→ document_builder按字段拼embedding_text
→ SentenceTransformerEmbeddingAdapter本地编码并L2归一化
→ FAISS IndexFlatIP（全量 + duvet_cover索引）
→ position到material code的显式mapping + manifest/hash
```

一行物料约等于一个检索单位/一个向量。`EMBEDDING_FIELDS`包括品类、规格、颜色、面料、面料品类、纱支、密度、成分、款式、加标方式和尺寸类型（`materials/document_builder.py:10-31`）。物料表有天然行级边界，**不存在复杂长文档 chunking**。

索引使用归一化向量上的 inner product，`IndexFlatIP`不是近似分桶索引；manifest会校验模型名、revision、维度、归一化和文件哈希（`vector_index.py:56-142,180-255`；`vector_search.py:28-149`）。

### 11.2 订单查询与匹配

订单 query 来自物料名称推导品类，以及规格、颜色、面料/成分/密度、款式、加标方式、尺寸类型、行备注，拼成查询文本（`hybrid_matcher.py:262-318`）。

```text
订单业务字段
→ query embedding（短生命周期worker）
→ duvet FAISS dense recall（默认vector_recall_k=300）
→ SQLite结构化候选
→ 两路候选去重合并
→ 逐字段比较并剔除硬冲突
→ prototype score排序
→ 候选JSON/摘要JSON + 匹配层选择
```

- 通用 `search_vector_index()` 的默认 `top_k=10`（`vector_search.py:28-40`）。
- 正式 hybrid matcher 为提高召回默认先取 300 个向量候选，再过滤/排序；UI匹配详情展示 Top 5（`hybrid_matcher.py:71-88,143-220`；`app.js:1340-1393`）。所以 TopK 不是全链唯一固定数字。
- 原始向量内积先映射为 `(clamp(score,-1,1)+1)/2`；prototype score是可比较结构化字段 0.75 + 规范向量分数 0.25（`field_comparator.py:454-486`；`hybrid_matcher.py:725-755`）。
- 分数是工程参考分数，没有经业务真值标定，不是准确率或正确概率。
- matcher还处理结构化召回、字段比较、缺失、硬冲突、重复物料文本、Top1 margin和证据不足；不是“FAISS第一名直接写回”。
- AI不能生成物料编码，因为编码必须存在于本地物料主数据并由matcher候选返回；否则为空编码和0.0。

### 11.3 BGE-M3与worker

当前模型合同为 `BAAI/bge-m3`（`query_embedding_contract.py:9`；`vector_index.py:61`），通过 `sentence-transformers`本地加载，输出归一化`float32`向量。查询编码使用短生命周期子进程隔离模型内存、超时/取消和Windows异常退出恢复（`query_embedding_worker.py`、`query_embedding_runner.py`）。项目实现了worker协议、生命周期、索引、检索和恢复；**没有训练或实现BGE-M3神经网络本身**。

## 12. RAG 判断

结论：**本项目使用语义 Embedding、FAISS TopK 检索和混合物料匹配，但不应把整个项目称为典型 RAG 问答系统。**

原因：物料检索结果用于本地候选比较、编码和参考分数，没有作为知识上下文再次送入 LLM 生成回答。仓库未发现“retrieval → LLM context augmentation → generation”的物料链。可说“具备 RAG 中的 retrieval 技术组件”，不能说“完整实现了RAG生成链”。

## 13. Transformer 判断

结论：**项目没有实现、训练或微调 Transformer。** 项目调用的 Ark大模型和BGE-M3外部模型可能以Transformer为底层背景，但当前repo不包含它们的网络结构实现，也不足以证明具体Ark模型内部架构。正式文档应把Transformer放在“外部模型背景知识”，引用官方文档/论文后再写。

## 14. Revision

Revision合同在`ai_full_order/revisions.py:45-110`：

- Revision 0：第一次成功五类发布的不可变初始版本。
- `INITIAL`：永远指向初始版本。
- `CURRENT`：指向用户当前采用版本。
- `parent_revision`：形成线性历史。
- `history`：本地元数据记录版本号、父版本和安全操作事实。

允许动作：`keep_ai`、`use_python`、`manual_override`（`revisions.py:61-64`）。只能改17个业务字段中的目标字段；不能改行号、物料编码、相似分数、identity/scope/evidence或系统元数据。

Revision不重调Ark，因为已有AI值、Python值和用户输入；它重构canonical记录，重跑字典和MaterialMatcher，并原子发布新五类bundle。这样新业务值对应新的字典/候选/编码，不会留下不一致下游。

- **Optimistic concurrency**：请求携带`expected_current_revision`；如果CURRENT已变化，拒绝陈旧写入（`revisions.py:190-229`）。
- **Idempotency**：相同父版本和同一操作身份可返回已存在结果，不重复产生不同版本。
- **Immutable**：已发布bundle/metadata内容不同则冲突，不原地覆盖。
- **Atomic CURRENT switch**：新五类先完整发布，最后单指针切换。

大白话：保留第一版，修改时另存一套完整结果；最后只把“当前查看哪一版”的书签挪过去。

## 15. Atomic Publication

固定五类角色（`web/services.py:93-120`）：

1. `official_result`：严格20字段业务记录。
2. `parse_diagnostics`：解析、AI/Python comparison、Review、Evidence和安全telemetry。
3. `dictionary_validation`：字典检查结果。
4. `material_candidates`：逐记录候选及字段比较。
5. `material_summary`：匹配汇总和分数合同。

AI发布流程：先在唯一 `.staging` 目录写UTF-8 JSON，逐个flush/fsync并重算canonical SHA；五个均验证后把整个目录移动为不可变bundle，再原子替换`CURRENT`。失败清理staging且不切CURRENT（`downstream.py:630-722`）。因此旧任务不会看到“3个新版+2个旧版”。Comparison只进入parse diagnostics；official result由`FinalResult`验证，仍恰好20字段。

Standard写入路径采用成对正式结果/诊断临时文件与rollback，以及匹配输出临时目录（`serialization/diagnostic_writer.py:21-110`；`materials/match_writer.py:30-68`）。

## 16. Cache、Identity、Reliability 与 SHA-256

### 16.1 V2 cache identity

`V2CacheIdentity`实际包含（`reliability_v2.py:102-124,251-315`）：

```text
source_file_sha256
provider / model
contract_version / schema_version / prompt_version
preprocessor_version / context_selection_version
normalization_version / evidence_normalization_version
comparison_version
python_shadow_adapter_version / field_policy_version
provenance_binding_version
canonical_extraction_manifest_sha256
```

不能只用文件名：同名文件内容可能不同，Provider/model/Prompt/Schema/字段政策变化也会改变结果；错误复用会把旧候选或旧决策当成当前真相。

### 16.2 Reliability

- 客户端idempotency key、业务key、cache key共同约束执行身份。
- 文件租约包含owner token、心跳、过期判断；同cache key只有一个leader，follower有界等待或读缓存。
- 状态原子写，支持pending/in-progress/validated/content-issue/transient/hard/interrupted等单调转换。
- validated缓存保存可重新验证的候选和安全telemetry，不保存原始Provider响应。
- cache hit不调用Provider；重新执行当前Schema、provenance、normalization、comparison和field policy，再计算technical-ready/review（`reliability_v2.py:435-590,702-870`）。
- 重启时仅恢复未完成/允许重试单元，已验证单元不重调AI。

### 16.3 SHA-256实际用途

| 用途 | 位置 | 含义 |
|---|---|---|
| 上传/source identity | `web/services.py:308-358`；`preprocessing.py:242-398` | 证明处理的是同一字节内容 |
| source record identity | `contracts.py:245-256` | 绑定source SHA、Sheet、scope、row、evidence |
| structure context | `structure_manifest.py:120-194` | 防止Layout决定套用到不同上下文 |
| extraction manifest/cache | `reliability_v2.py:234-315` | 版本化请求身份 |
| 物料库/索引 | `materials/loader.py:23-30`；`vector_index.py:340-405` | 检查源、索引和mapping未错配 |
| 五类artifact | `downstream.py:642-722` | staging/已有bundle内容校验 |
| Revision ID/operation | `revisions.py:136-180,237-305,578-608` | 稳定版本与幂等操作身份 |
| Standard reprocess | `web/services.py:2030-2045` | 新Job只复用服务端可信原上传 |

SHA-256在这里是完整性和身份指纹，不是“把订单加密”。

## 17. Job 生命周期

主要公开状态来自`web/services.py:154-155,317-383,562-680`：

| 状态 | 语义 |
|---|---|
| `queued` | 已创建，等待后台执行 |
| `running`/`processing` | 正在处理；公开UI通常看到processing |
| `awaiting_user_decision` | AI技术链未能安全完成，等待重试/新建Standard处理/保留失败 |
| `completed` | 五类结果完整并可访问 |
| `failed` | 终止且无可发布完整结果 |
| `interrupted` | 桌面关闭/恢复边界安全中断 |

每次解析是独立Job，才能持久化源身份、进度、调用/Token、安全错误、五类结果和历史，并隔离并发与失败。

AI Job不能原地变成Standard。`reprocess_ai_job_as_standard()`验证原AI Job仍是awaiting、读取服务端可信原上传、校验SHA，然后创建新的Standard Job ID；原AI Job的parse mode、调用和失败记录不变（`web/services.py:386-452,2030-2084`）。这避免一份历史同时声称“请求AI、实际Standard”。

## 18. Web、API、HTTP 与前后端

真实技术栈：

- Python >=3.12；`openpyxl`、`faiss-cpu`、`sentence-transformers`、`pywebview`（`pyproject.toml:7-22`）。
- Web不是Flask：`ThreadingHTTPServer` + `BaseHTTPRequestHandler`（`web/app.py:6-49`；`web/routes.py:10-27`）。
- 前端无框架：原生`index.html`、`styles.css`、`app.js`。
- 桌面：`pywebview`窗口加载`127.0.0.1` loopback服务（`desktop/launcher.py:41-118`；`desktop/server_controller.py:26-106`）。
- Ark HTTP：可注入`JSONTransport`，生产实现为`urllib.request`；Authorization仅Transport请求头使用（`llm/transport.py:26-103`；`llm/volcengine_ark.py:154-181`）。

大白话链：

```text
用户在桌面页面点按钮
→ 原生JS向127.0.0.1发HTTP
→ WebRequestHandler匹配route
→ JobService创建/读取任务
→ Standard或AI业务模块运行
→ JSON状态/结果返回
→ JS轮询并更新页面
```

核心API包括：创建/列出/读取Job、五角色预览/下载、下载全部、匹配详情、AI Review、Revision、AI retry/keep-failed、独立Standard reprocess和单记录AI advisory（`web/routes.py:44-212`）。

## 19. UI 页面/Surface 清单（14项）

1. **上传首页** `#upload`：拖放/选择xlsx、两种模式和开始解析。
2. **AI整单确认弹窗**：Provider/模型、发送范围、Token/费用不可可靠估算提示和同意勾选。
3. **Standard进度页** `#job/{id}/progress`：圆形进度、五阶段和预计时间。
4. **AI Enhanced进度页**：同路由，另显示结构/区块、调用、HTTP、Token、Provider、Contract。
5. **AI等待处理决定页**：技术未ready时重试、独立Standard重新处理、保留失败。
6. **普通失败页**：Standard或不可恢复错误的安全消息。
7. **Standard完成页** `#job/{id}/result`：五类文件、匹配统计、Excel占位和Standard ZIP。
8. **AI完成页**：五类文件、Review summary、17字段对照和Revision信息。
9. **AI Review字段区**：全部/待复核/高风险筛选，AI/Python/formal值和状态。
10. **Evidence/Revision展开区**：来源Sheet/range/excerpt；保留AI、使用本地规则、手动修改。
11. **物料匹配详情页** `#job/{id}/match/{index}`：推荐编码、参考分数、字段比较、Top 5。
12. **单记录AI复核Surface**：匹配详情内生成/重新生成建议及确认弹窗。
13. **历史记录页** `#history`：统计、搜索、日期/状态/模式筛选、分页、查看/下载。
14. **帮助中心** `#help`：术语、使用方法、两种处理流程及页内导航。

路由函数见`web/static/app.js:1519-1527`；主要render函数见`app.js:304,371,525,571,792,905,1147,1340,1426`。

## 20. UI按钮/控件总表（38项）

| # | 页面 | 控件 | 显示条件 | 行为/API | 用户结果 |
|---:|---|---|---|---|---|
| 1 | 全局 | 订单解析 | 始终 | route `upload` | 回上传页 |
| 2 | 全局 | 历史记录 | 始终 | route `history` | 查看历史 |
| 3 | 全局 | 帮助 | 始终 | route `help` | 打开帮助 |
| 4 | 全局 | 显示对比度 | 始终 | 切`high-contrast` | 改善显示 |
| 5 | 上传 | 拖放区 | 上传页 | 接收xlsx | 显示选中文件 |
| 6 | 上传 | 选择文件 | 上传页 | 打开文件选择器 | 选择xlsx |
| 7 | 上传 | 移除文件 | 已选文件 | 清除前端选择 | 恢复空状态 |
| 8 | 上传 | Standard单选 | 上传页 | `parse_mode=standard` | 采用本地规则 |
| 9 | 上传 | AI整单解析单选 | 后端能力可用 | `parse_mode=ai_enhanced` | 显示AI说明 |
| 10 | 上传 | 开始解析 | 文件有效且模式ready | `POST /api/jobs` | 进入进度页 |
| 11 | AI确认 | 同意费用/发送勾选 | AI提交前 | 启用确认按钮 | 明确授权 |
| 12 | AI确认 | 取消 | AI提交前 | 关闭弹窗 | 不创建Job |
| 13 | AI确认 | 确认并开始 | 已勾选 | 创建AI Job | 进入进度页 |
| 14 | 进度 | 自动轮询 | active Job | `GET /api/jobs/{id}` | 更新阶段/百分比 |
| 15 | AI等待 | 重试未完成部分 | awaiting | `POST .../ai-actions/retry` | 恢复允许重试部分 |
| 16 | AI等待 | 使用标准解析重新处理 | awaiting | `POST .../reprocess-standard` | 新建Standard Job并跳转 |
| 17 | AI等待 | 保留失败并结束 | awaiting | `POST .../ai-actions/keep-failed` | 原AI Job转failed |
| 18 | 结果 | 五类结果预览 | completed且角色存在 | `GET .../preview` | JSON弹窗 |
| 19 | 结果 | 五类单文件下载 | completed且角色存在 | `GET .../artifacts/{role}` | 保存文件 |
| 20 | Standard结果 | 下载全部ZIP | Standard有zip | `GET .../download-all` | 下载五类ZIP |
| 21 | 结果 | 导出Excel | 当前按钮存在 | 当前仅提示后续/以界面可用为准 | 不生成Excel |
| 22 | 结果 | 推荐明确统计卡 | completed | 打开对应首条match | 查看详情 |
| 23 | 结果 | 建议人工查看统计卡 | completed | 打开对应首条match | 查看详情 |
| 24 | 结果 | 冲突统计卡 | completed | 打开对应首条match | 查看详情 |
| 25 | AI Review | 全部字段筛选 | AI completed | 本地过滤 | 看全部字段 |
| 26 | AI Review | 待复核筛选 | 有Review | 本地过滤 | 只看差异/补空 |
| 27 | AI Review | 高风险筛选 | 有high review | 本地过滤 | 聚焦五类字段 |
| 28 | AI Review | 查看来源位置 | 有evidence | 展开本地panel | Sheet/range/excerpt |
| 29 | Revision | 保留AI | 可修订字段 | `POST .../ai-review/revisions` | 新不可变版本 |
| 30 | Revision | 使用本地规则 | Python值可用 | 同Revision API | 当前值切Python并重跑下游 |
| 31 | Revision | 手动修改 | AI completed | 展开输入区 | 输入用户值 |
| 32 | Revision | 保存手动Revision | 输入合法 | 同Revision API | 新CURRENT版本 |
| 33 | 匹配详情 | 返回 | 详情页 | 回result route | 返回结果 |
| 34 | 匹配详情 | 生成AI复核建议 | Standard单记录、用户触发 | `POST /api/tasks/{id}/ai-enhance` | 显示Sidecar建议 |
| 35 | 历史 | 搜索/日期/状态/模式 | 历史页 | 本地过滤 | 缩小任务列表 |
| 36 | 历史 | 上一页/下一页 | 多页 | 本地分页 | 切页 |
| 37 | 历史 | 查看 | 每个Job | progress或result route | 打开任务 |
| 38 | 帮助 | 三张顶部入口卡 | help页 | `scrollIntoView`，不改hash | 页内滚动到术语/方法/流程 |

## 21. Screenshot Shot List 与现有素材（16张）

当前 `master` 已在 `docs/documentation_assets/screenshots/` 保存 16 张截图，均由真实当前前端渲染，并只使用 synthetic workbook/Fake Provider，不含真实客户、订单、路径或密钥。采集与逐图验收事实见 `docs/reports/FINAL_DOCUMENTATION_VISUAL_ASSETS_REPORT.md`。

| 编号/文件名 | 目的与必须展示 | 建议状态 | Fake需求 | 裁剪与报告位置 |
|---|---|---|---|---|
| `01_首页_模式选择.png` | 文件区、Standard/AI单选、说明 | 无Job | 否 | 主内容+侧栏；功能概览 |
| `02_AI整单解析_授权确认.png` | Provider/模型、发送范围、同意勾选 | AI preflight ready | Fake配置 | 仅弹窗；AI设计 |
| `03_AI整单解析_结构确认进度.png` | 12%左右、结构确认、右侧阶段推进 | synthetic active | 慢速Fake stage | 进度区；AI流程 |
| `04_AI整单解析_字段提取进度.png` | chunk/调用/Token与阶段 | synthetic active | Fake | 主进度+telemetry |
| `05_AI整单解析_完成页.png` | 正式记录数、Review summary、五类完整 | completed | Fake全链 | 首屏；项目成果 |
| `06_AI_Python对照.png` | different/ai_only/python_fill示例 | completed review | Fake差异 | Review列表；AI-first |
| `07_Evidence来源展开.png` | Sheet、cell/range、bounded excerpt | 有安全证据 | Fake | 单字段展开；Provenance |
| `08_Revision_使用本地规则.png` | before/current revision和按钮 | Python值可用 | Fake下游 | Revision局部 |
| `09_Revision_手动修改.png` | 输入、保存、版本变化 | manual override | Fake下游 | 输入区；Revision |
| `10_AI技术失败页.png` | 安全码、重试/Standard新Job/保留失败 | structure unresolved | Fake failure | 决策区；可靠性 |
| `11_Standard重新处理.png` | 新Standard Job ID/进度，原AI不变 | reprocess child active | Fake/本地 | 新Job页；Job设计 |
| `12_Standard进度页.png` | 五阶段推进 | Standard synthetic | Fake matcher或轻量资源 | 进度区；Standard |
| `13_Standard完成与ZIP.png` | 五类、统计、ZIP | completed | synthetic resources | 结果页；Standard成果 |
| `14_物料匹配详情.png` | Top5、字段比较、分数免责声明 | completed | Fake/合成索引 | 详情页；向量匹配 |
| `15_历史任务.png` | 搜索、日期、状态、模式和任务列表 | synthetic jobs | Fake Job列表 | 完整页面；UI与Job章节 |
| `16_Help中心.png` | 术语、使用方法、处理流程三入口 | 静态Help页面 | 否 | 完整页面；交付与可用性章节 |

另有 4 张正式架构图，每张同时提供 SVG 与 PNG：系统总体架构、双模式业务流程、AI证据与字段决策、物料向量与混合匹配。索引和建议章节见 `docs/documentation_assets/README.md`。

## 22. 《项目设计与实现报告》建议目录

| 章节 | 内容重点 | 代码事实/素材 | 图像建议 |
|---|---|---|---|
| 1 项目背景与目标 | 人工订单录入痛点、固定20字段、两模式 | `AGENTS.md`、`final_result.py` | 01 |
| 2 需求与边界 | Standard日常稳定、AI复杂理解、编码归属 | `contracts.py`、`field_policy.py` | 模式对比图 |
| 3 总体架构 | Desktop/Web/业务/AI/向量/存储分层 | 第3、18节 | 架构图 |
| 4 数据与业务流程 | 上传到五类结果 | 第4、5节 | 双泳道流程图 |
| 5 页面与用户功能 | 14 surfaces、38 controls | 第19、20节 | 01-15 |
| 6 Standard设计 | Excel、规则提取、字典、物料 | `pipeline/`、`extraction/` | 12、13 |
| 7 AI Enhanced设计 | 结构、V2、证据、AI-first、Review | `ai_full_order/` | 02-07 |
| 8 多Sheet结构 | known/unresolved/local candidate | `structure_manifest.py` | 结构候选示意图 |
| 9 向量物料匹配 | 物料行向量、FAISS、混合评分 | `materials/` | 14 + 检索图 |
| 10 安全与可靠性 | identity、cache、single-flight、atomic | `reliability_v2.py`、`downstream.py` | 状态/发布图 |
| 11 Review与Revision | comparison、不可变历史、CURRENT | `revisions.py` | 06-09 |
| 12 Job/API/桌面 | HTTP route、Job生命周期、pywebview | `web/`、`desktop/` | 03、10、11 |
| 13 测试与验收 | 670/670、Edge/Desktop、历史真实Ark | 第27节 | 测试证据表 |
| 14 成果、限制与展望 | READY TO CLOSE + backlog | 第28节 | 无或路线表 |
| 15 总结 | 技术价值与诚实边界 | 全文 | 双模式成果图 |

## 23. 《技术解析与答辩学习手册》建议目录

按业务流程讲技术，每节固定回答“定义、白话、本项目位置、自研/外部、易错点”。

1. Excel进入系统：Workbook/Sheet/Cell、merged/sparse、openpyxl。
2. Standard规则解析：表头、元数据、订单行、20字段。
3. AI整单前处理：结构几何、scope、extraction unit。
4. LLM调用：Provider、API/HTTP、Prompt、Token、Function Calling、JSON Schema。
5. Transformer关系：外部背景，不是项目自研。
6. Evidence与Provenance：内容证据和身份绑定区别。
7. AI-first与Python Shadow：主值、对照、fallback、hard failure。
8. Normalization：确定性格式，不做模糊业务判断。
9. 字典Validation：认识/不认识提示，不静默覆盖。
10. 物料资料与Embedding：一行物料、embedding_text、BGE-M3 worker。
11. Vector/FAISS/TopK：向量召回、结构化过滤、混合分数。
12. Chunking与RAG判断：为何本项目不是典型RAG。
13. MaterialMatcher：硬冲突、候选、编码归属、分数免责声明。
14. Cache/SHA/Single-flight/Retry：身份和调用可靠性。
15. Atomic Publication：五类、staging、CURRENT。
16. Revision：immutable、INITIAL/CURRENT、乐观并发和幂等。
17. Job/API/前后端/桌面：从点击到后台状态。
18. Fake、synthetic与真实验收：测试金字塔和安全边界。
19. 常见误述：使用第24节逐条练习。
20. 50道答辩题：使用第26节进行30秒口述训练。

## 24. Common Misstatements / Claims To Avoid（15项）

| 说法 | 判断 | 推荐答辩表述 | 依据 |
|---|---|---|---|
| 本项目实现了Transformer | 错误 | 项目集成外部模型能力，未实现Transformer网络 | `pyproject.toml`、无网络模型代码 |
| 本项目训练了大语言模型 | 错误 | 使用Ark Responses API调用已训练模型 | `llm/volcengine_ark.py` |
| 本项目训练了BGE-M3 | 错误 | 本地加载预训练BGE-M3做Embedding | `embedding_model.py` |
| 本项目就是RAG系统 | 部分正确但误导 | 使用检索组件，不存在物料retrieval再喂LLM生成的典型RAG链 | `hybrid_matcher.py` |
| FAISS就是向量数据库 | 错误 | 本项目把FAISS作为本地向量索引/搜索库，元数据另有mapping/SQLite | `vector_index.py` |
| AI直接读取整个Excel二进制 | 错误 | 本地先转为有界坐标化证据和单记录unit | `preprocessing.py` |
| AI负责生成物料编码 | 错误 | 编码/分数只由MaterialMatcher候选产生 | `contracts.py`、`downstream.py` |
| Python负责批准AI结果 | 错误 | AI是AI Enhanced主值；Python只对照和补空 | `field_policy.py` |
| AI和Python不一样就解析失败 | 错误 | business difference产生Review但可发布 | `comparison.py`、`orchestration.py` |
| 所有20字段都是AI生成 | 错误 | AI候选17字段；行号本地；编码/分数matcher | `FINAL_FIELD_NAMES`、`contracts.py` |
| 用户修改会覆盖AI原结果 | 错误 | Revision不可变，INITIAL保留，CURRENT切新版本 | `revisions.py` |
| Standard重新处理会把原AI任务变Standard | 错误 | 新建独立Standard Job，原AI Job不变 | `services.py:386-452` |
| 相似分数就是准确率 | 错误 | 是未用业务真值标定的工程参考分数 | `hybrid_matcher.py:725-755` |
| FAISS第一名会自动成为最终正确物料 | 错误 | 还经过结构字段、硬冲突、证据充分度和人工复核语义 | `hybrid_matcher.py:551-604` |
| 字典验证会自动修正订单 | 错误 | 当前是validation-only，保留值或提示人工查看 | `product_validation.py:30-42` |

## 25. Glossary（56项）

| # | 术语 | 正式定义 | 大白话 | 本项目使用/位置 |
|---:|---|---|---|---|
| 1 | Workbook | 一个Excel工作簿文件 | 整份Excel | 是，`excel/workbook_reader.py` |
| 2 | Sheet | 工作簿中的工作表 | Excel底部一个页签 | 是，`preprocessing.py` |
| 3 | Cell | 行列交叉的数据单元 | 一个格子 | 是 |
| 4 | Merged Cell | 跨多个坐标共享锚点的单元格 | 合并格 | 是，`preprocessing.py:520` |
| 5 | Sparse | 只保留实际有用的非空/结构单元 | 不把整张空白网格都传下去 | 是，`SparseCell` |
| 6 | Preprocessing | 正式解析前的本地整理 | 先看清表格 | 是，`preprocess_workbook()` |
| 7 | Block | 本地确认的一段订单区域 | 一块表格 | 是，`OrderBlock` |
| 8 | Scope | 证据可被引用的隔离范围 | 证据活动边界 | 是 |
| 9 | Record | 一条订单业务记录 | 一行/一件订单项 | 是 |
| 10 | Extraction Unit | 单目标AI提取请求单元 | 一次只让AI看一条目标 | 是，`V2ExtractionUnit` |
| 11 | LLM | 大语言模型 | 能理解/生成语言的外部模型 | 集成Ark |
| 12 | Prompt | 给模型的任务指令 | 告诉AI怎么做 | 是，`volcengine_ark.py` |
| 13 | Token | 模型计费和上下文的离散文本单位 | AI读写量单位 | 是，telemetry |
| 14 | Context | 模型本次可见的信息范围 | AI这次能看到什么 | 是，有界payload |
| 15 | API | 程序间约定的调用接口 | 软件之间的门 | 是，Web/Ark |
| 16 | HTTP | Web请求/响应协议 | 页面和本地服务讲话方式 | 是 |
| 17 | JSON | 键值结构化文本格式 | 程序可读的数据文件 | 是 |
| 18 | JSON Schema | JSON形状和类型规则 | 数据的硬模板 | 是，`contracts.py` |
| 19 | Function Calling | 让模型按函数参数Schema返回 | 不让AI自由写散文 | 是，Ark strict tools |
| 20 | Ark Responses API | 火山方舟模型响应接口 | 项目调用的AI服务 | 是，`/responses` |
| 21 | Embedding | 把文本映射为数值向量 | 把意思变成数字坐标 | 是，BGE-M3 |
| 22 | Vector | 有固定维度的数值序列 | 一串表示语义的数 | 是 |
| 23 | Vector Index | 支持向量检索的数据结构 | 快速找相近向量 | 是 |
| 24 | FAISS | Meta开源的向量索引/搜索库 | 本地向量搜索工具 | 是，`IndexFlatIP` |
| 25 | TopK | 返回分数最高的K个结果 | 取前K名 | 是，多层K |
| 26 | Similarity | 向量或混合特征的相近程度 | 像不像 | 是；非准确率 |
| 27 | RAG | 检索后把知识增强到生成模型 | 先查资料再让AI回答 | 非完整实现 |
| 28 | Chunk | 被单独处理的一段输入 | 切出的一块 | AI结构/旧兼容使用 |
| 29 | Chunking | 把长输入切块的策略 | 怎么切 | 物料表无复杂chunking |
| 30 | Evidence | 本地可定位的来源内容 | 这句话从哪格来 | 是 |
| 31 | Provenance | 候选与合法来源/身份的绑定链 | 证明这证据真属于这条记录 | 是 |
| 32 | Normalization | 确定性格式统一 | 同一种写法整理一致 | 是 |
| 33 | Dictionary Validation | 用字典规则检查字段 | 系统认不认识这个值 | 是 |
| 34 | MaterialMatcher | 物料候选和正式编码选择端口 | 找相似物料的本地层 | 是 |
| 35 | Python Shadow | 与AI独立的本地解析对照 | 第二意见和补空 | 是 |
| 36 | AI-first | AI有效值优先作为业务主值 | AI模式让AI主导 | 是，V2 field policy |
| 37 | technical_ready | 技术身份和canonical结构可安全发布 | 数据结构安全过关 | 是 |
| 38 | review_required | 业务差异需要人看 | 能发布，但建议复核 | 是 |
| 39 | Cache | 保存可安全复用的中间结果 | 不重复花钱做同一件事 | 是 |
| 40 | SHA-256 | 256位密码学哈希函数 | 内容指纹 | 是；非加密订单 |
| 41 | Job | 一次独立解析任务及其状态 | 一次订单处理档案 | 是 |
| 42 | Revision | 对已发布结果的不可变新版本 | 修改另存一版 | 是 |
| 43 | Immutable | 发布后内容不原地改变 | 老版本不覆盖 | 是 |
| 44 | Atomic | 操作对外要么全成要么不成 | 不露半套 | 是 |
| 45 | CURRENT | 当前可见bundle的单一指针 | 当前书签 | 是 |
| 46 | INITIAL | 初始Revision的固定指针 | 第一版书签 | 是 |
| 47 | Idempotency | 重复同一请求不重复产生副作用 | 点两次仍是一件事 | 是 |
| 48 | Optimistic Concurrency | 写入前确认当前版本未变化 | 防止旧页面覆盖新结果 | 是 |
| 49 | Retry | 对允许的瞬时失败有限重试 | 暂时失败再试有限次 | 是 |
| 50 | Single-flight | 同一身份同时只允许一个leader执行 | 同一任务不重复调用AI | 是 |
| 51 | Provider | 对外AI能力的本地适配器 | 统一AI接口 | 是 |
| 52 | Transport | 实际发送HTTP的可替换层 | 网络快递员 | 是，urllib/FakeTransport |
| 53 | Sidecar | 不改正式结果的附加建议产物 | 旁边的一份AI意见 | Standard单记录AI |
| 54 | Standard | Python规则主导的解析模式 | 日常本地规则模式 | 是 |
| 55 | AI Enhanced | AI主导17业务字段的整单模式 | AI整单理解模式 | 是 |
| 56 | Manifest | 版本化且可校验的结构/单元清单 | 要处理哪些块的目录 | 是 |

## 26. 高价值答辩问题（50题）

| # | 问题 | 30秒回答要点 | 代码/事实 | 难度 |
|---:|---|---|---|---|
| 1 | 为什么同时保留Standard和AI Enhanced？ | 稳定确定性日常路径与复杂语义理解各有优势，用户明确选模式 | `AGENTS.md` | 基础 |
| 2 | 固定20字段怎么组成？ | 17业务字段+本地行号+matcher编码/分数 | `final_result.py` | 基础 |
| 3 | 为什么AI只提取17字段？ | 系统身份和ERP事实不能交给模型生成 | `contracts.py` | 中等 |
| 4 | Standard主链是什么？ | Excel→Python→字典→物料→五类→ZIP | 第4节 | 基础 |
| 5 | AI Enhanced主链是什么？ | 预处理→结构→Ark候选→证据→AI-first→下游→五类 | 第5节 | 基础 |
| 6 | 为什么AI不能生成物料编码？ | 编码必须来自本地物料主数据候选 | `downstream.py` | 基础 |
| 7 | 为什么还需要Python Shadow？ | 对照、补空、Review，不是审批AI | `field_policy.py` | 中等 |
| 8 | AI/Python不一致为何还能发布？ | 业务分歧不等于技术身份失败 | `comparison.py` | 中等 |
| 9 | 什么情况下AI整单必须硬失败？ | envelope/identity/scope/evidence ownership/cache/publication损坏 | `provenance.py` | 技术 |
| 10 | Evidence是什么？ | 可定位的Excel来源对象 | `EvidenceItem` | 基础 |
| 11 | Provenance和Evidence差别？ | 前者是候选与来源/身份的绑定关系 | `bind_v2_candidates()` | 中等 |
| 12 | 为什么要scope？ | 防止一个订单借用另一个订单证据 | `provenance.py` | 技术 |
| 13 | AI如何看Excel？ | 不看二进制；看本地坐标化、有界证据 | `preprocessing.py` | 基础 |
| 14 | 多Sheet为什么困难？ | 订单页/辅助页/非标准页角色不同 | `structure_manifest.py` | 中等 |
| 15 | Layout AI能自由划表吗？ | 不能，只能选本地candidate或unresolved | `structure_resolution.py` | 技术 |
| 16 | 什么是Extraction Unit？ | 绑定一个本地target和证据范围的单目标请求 | `orchestration.py` | 中等 |
| 17 | Function Calling解决什么？ | 强制模型按Schema返回结构化参数 | `volcengine_ark.py` | 中等 |
| 18 | JSON Schema为何不够？ | 只能管形状；identity/provenance仍需本地验证 | `contracts.py`+`provenance.py` | 技术 |
| 19 | Prompt是什么？ | 模型任务和禁止范围，不替代本地安全校验 | Provider instructions | 基础 |
| 20 | Token是什么？ | 模型输入/输出计量单位，项目记录安全usage | telemetry | 基础 |
| 21 | Normalization为何不等于Python改值？ | 业务判断仍来自AI，只统一确定格式 | `normalization.py` | 中等 |
| 22 | 当前规范化支持什么？ | Unicode/空白、USD、十进制数量、完整日期、备注排版 | `normalization.py` | 中等 |
| 23 | 字典验证会改正式值吗？ | validation-only，不静默覆盖 | `product_validation.py` | 基础 |
| 24 | Embedding是什么？ | 文本到归一化向量的外部模型能力 | `embedding_model.py` | 基础 |
| 25 | 一条什么数据对应一个物料向量？ | 一行物料的规范字段拼接文本 | `document_builder.py` | 中等 |
| 26 | FAISS具体做什么？ | 对归一化向量做本地inner-product检索 | `vector_index.py` | 中等 |
| 27 | FAISS是数据库吗？ | 本项目中是索引库；metadata在mapping/SQLite | `vector_index.py` | 中等 |
| 28 | TopK是多少？ | 通用search默认10；hybrid召回300；UI展示5 | `vector_search.py`、`hybrid_matcher.py` | 技术 |
| 29 | 相似分数为何不是准确率？ | 工程混合分数，无业务真值校准 | score contract | 中等 |
| 30 | MaterialMatcher比向量搜索多做什么？ | 结构候选、字段比较、硬冲突、排序、摘要 | `hybrid_matcher.py` | 技术 |
| 31 | 本项目是RAG吗？ | 有retrieval，无检索结果再喂LLM生成的典型闭环 | 第12节 | 中等 |
| 32 | 本项目实现Transformer了吗？ | 没有；只集成外部模型 | 第13节 | 基础 |
| 33 | BGE-M3是自己训练的吗？ | 否，本地加载预训练模型 | `query_embedding_contract.py` | 基础 |
| 34 | 为什么Embedding放子进程？ | 隔离模型内存、崩溃、超时和取消 | `query_embedding_runner.py` | 技术 |
| 35 | Cache key为什么不能用文件名？ | 内容/模型/Prompt/合同/政策都影响结果 | `V2CacheIdentity` | 技术 |
| 36 | cache hit会重新调用AI吗？ | 不会；会按当前本地政策重验证候选 | `reliability_v2.py` | 技术 |
| 37 | Single-flight解决什么？ | 同身份并发只允许一个leader调用Provider | lease代码 | 技术 |
| 38 | Retry为什么必须有限？ | 防止瞬时故障无限消费/循环 | reliability/worker | 中等 |
| 39 | SHA-256在项目中做什么？ | 内容身份和完整性，不是订单加密 | 第16.3节 | 中等 |
| 40 | 什么是Atomic Publication？ | 五类完整后一次切CURRENT | `downstream.py` | 中等 |
| 41 | 为什么不能分别替换五个文件？ | 中途失败会混合新旧版本 | `_publish_bundle()` | 中等 |
| 42 | Revision是什么？ | 不覆盖初始结果的本地新版本 | `revisions.py` | 基础 |
| 43 | Revision为何不调Ark？ | 已有AI/Python/用户值，仅重跑本地下游 | `apply_revision()` | 中等 |
| 44 | 为什么Revision要重跑Matcher？ | 业务字段变了，编码/分数和候选必须同步 | `revisions.py` | 中等 |
| 45 | 什么是乐观并发？ | expected CURRENT防止陈旧页面写回 | `apply_revision()` | 技术 |
| 46 | 为什么AI失败后Standard要新建Job？ | 保留原AI模式、成本和失败历史，避免mode mutation | `reprocess_ai_job_as_standard()` | 中等 |
| 47 | 为什么采用本地桌面部署？ | 文件/索引/Job留本机，UI用loopback，只有授权AI请求外发 | `desktop/` | 中等 |
| 48 | 为什么测试不用每次真实Ark？ | 成本、隐私、稳定性；FakeTransport可覆盖协议/故障 | tests/ai_full_order | 基础 |
| 49 | 670/670说明什么？ | 冻结安全suite全绿，不等于所有未来数据100%正确 | D4A6F报告 | 基础 |
| 50 | 最终验收如何区分Fake与真实？ | 全套用synthetic/Fake；开发期有预算受限真实Ark协议验收；D4A6F真实0 | 第27节 | 中等 |

## 27. 当前测试与最终验收事实

当前`tests/`有549个显式`def test_`/测试类行；参数化后最终收集670项。最终签署事实：670 collected、670 passed、0 skipped、0 failed、90.17秒。

| 类别 | 当前证据 | 说明 |
|---|---|---|
| Unit | contracts、normalization、field comparator、parser等 | 函数/规则级边界 |
| Integration | AI orchestration/reliability/downstream、Standard pipeline、Web Job | 多模块合成链 |
| Browser | 真实Microsoft Edge + Playwright CLI + loopback synthetic/Fake harness | 模式、Review/Evidence、Revision、独立Standard reprocess |
| Desktop | `tests/desktop` 27 passed | 启动、路径、单实例、runtime identity、V2 composition |
| Fake Provider/Transport | 大多数AI协议和失败矩阵 | 网络0、计数可断言 |
| Synthetic Excel/FAISS | 人工工作簿和受控FAISS单元操作 | 不用真实PI/生产索引 |
| Real bounded acceptance | 开发期间D2/D3/D4A-3E有明确授权的小样本Ark验收 | 只证明协议/边界，不代表最终业务全集 |
| Final D4A-6F | 真实Ark=0、external HTTP=0、BGE-M3=0、生产FAISS=0 | 与历史真实验收严格区分 |

D4A-6F还通过：99项定向回归、Windows embedding worker五次独立17/17、Desktop 27/27、Edge final smoke、`compileall`、`node --check`和`git diff --check`（签署报告:183-250）。

## 28. 已知限制 / Non-blocking Backlog

| 项目 | 影响当前使用 | 冻结范围/诚实表述 |
|---|---|---|
| 大订单Revision全量重跑本地下游 | 小/中订单可用，大单可能慢 | 正确性优先；未来做增量性能优化 |
| 多进程revision writer lock吞吐 | 当前有乐观并发和原子CURRENT | 安全可用，跨进程吞吐可增强 |
| 大量Review分页/折叠 | 超大订单浏览效率下降 | 当前可筛选；未来分页 |
| Revision timeline/rollback UI | 历史数据存在，UI不完整 | 当前可连续修订，无完整时间线回滚界面 |
| Excel export | 按钮存在但不应声称已实现 | 五类预览/下载是冻结交付；Excel以界面可用状态为准 |
| AI Enhanced ZIP | 当前未实现 | Standard ZIP已有；AI可逐项下载五类 |
| 无本地order candidate的复杂Sheet | 会安全unresolved | 宁可技术失败，也不让AI自创坐标/身份 |
| 模型字段漏提取 | 可能出现python fill或both-missing Review | 由对照、Review、Revision承接，不承诺100% |

## 29. External Theory Verification Needed（5项）

1. **当前获批Ark模型的具体Transformer架构**：repo只保存Provider/model字符串，不足以证明内部层数、Attention变体或训练方法；需查火山方舟官方模型文档。
2. **BGE-M3模型架构与训练目标细节**：repo证明使用`BAAI/bge-m3`，不证明其完整网络/多功能训练机制；需查官方模型卡/论文。
3. **FAISS理论体系**：repo明确使用`IndexFlatIP`，若手册扩展到IVF/HNSW/PQ等未使用算法，应查FAISS官方文档且标注“背景”。
4. **归一化inner product与cosine的数学等价条件**：repo验证L2归一化和IP配置；教学推导应引用可靠数学/FAISS资料。
5. **LLM Token切分和Ark计费细则**：repo只消费usage，不包含目标模型tokenizer/价格合同；需查当前官方说明，避免写死易变价格。

## 30. 两份Word制作前的素材状态与剩余输入

仓库内技术素材已经具备：本事实底稿、16 张 synthetic/Fake 正式截图、4 张 SVG/PNG 架构图、素材索引、固定 20 字段/五类结果事实、56 项术语、50 道答辩题和最终 670/670 验收依据均已存在。

正式 Word 生成前仍需用户或外部来源补充的不是代码事实，而是文档出版输入：

1. 学校/组织的 Word 模板、封面、目录、页眉页脚、字号、引用格式和篇幅要求。
2. 作者、班级/部门、指导人、项目日期等非仓库元数据。
3. 对第 29 节外部理论使用官方文档/论文独立查证并形成引用；不得由 repo 事实替代外部理论来源。
4. 确定正式文档是否公开具体模型名、历史物料规模等部署信息；默认使用概括表述。
5. 从现有 synthetic 素材中选择最终版面组合；不得换成真实客户或物料截图。
6. 技术学习手册若需要长答案，应在本报告 50 道“30秒回答要点”上扩写，而不改变项目事实。

取得模板与署名等出版输入后，可直接生成：

- 《订单解析助手项目设计与实现报告》：偏业务、架构、页面、成果和验收。
- 《订单解析助手技术解析与答辩学习手册》：偏流程化技术解释、术语、误述纠正和答辩训练。

## 31. 本轮再认证变更与安全证明

- 生产代码：未修改。
- 测试：未修改、未运行。
- Prompt/Contract/UI：未修改。
- 截图/Word：本轮未生成；当前 master 已包含上一独立任务提交的 16 张合成截图和 4 组架构图，未在本轮改动。
- 真实Ark、外部HTTP、真实PI、真实字典/物料、BGE-M3、生产FAISS：均为0。
- 报告未包含真实客户、订单正文、API Key、Authorization、raw Ark request/response或本机秘密配置。
- 唯一修改文件：`docs/reports/FINAL_DOCUMENTATION_AUDIT_AND_MATERIALS_REPORT.md`。
- 当前结论：截图采集条件与素材已经完成；两份 Word 的技术事实和视觉素材均已具备，只待模板、署名及外部理论引用等出版输入。
