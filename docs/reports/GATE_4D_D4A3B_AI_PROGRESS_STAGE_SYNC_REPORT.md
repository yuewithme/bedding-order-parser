# Gate 4D-D4A-3B: AI 整单解析进度页阶段同步修复报告

## 1. 基线与范围

- 起始分支：`master`
- 起始完整 HEAD：`bec0c83435099e88a16bbbd44b6510831a1a83bc`
- D4A-3 implementation commit：`d8c8c6dbd566caa1298754953a0c68817e0b1d81`
- D4A-3 report commit：`bec0c83435099e88a16bbbd44b6510831a1a83bc`
- 本 Gate implementation commit：`8a11eb76c7231a6d9e0963aa2193e06f68ca2c50`

本 Gate 仅修复 AI Enhanced 任务进度页五阶段状态不同步问题。未修改 AI-first 字段决策、technical-ready、结构解析算法、Provider、Prompt、五类发布、Review 完成页或 Standard 业务逻辑。

## 2. 问题复现与实际根因

用户观察到 AI Enhanced 真实任务在进行时，左侧百分比和“当前阶段”会变化，而右侧五个步骤始终为“等待中”。

代码证据如下：

- `src/bedding_order_parser/web/services.py:JobService.create_job()` 初始创建五个 `job["stages"]`，状态均为 `waiting`。
- 修复前 `JobService._set_ai_progress()` 只更新顶层 `progress`、`current_stage` 和 `ai_execution.stage`，没有更新 `job["stages"]`。
- `src/bedding_order_parser/web/static/app.js:renderProgress()` 左侧圆环直接读取 `job.progress`；AI 当前阶段文字通过 `job.ai_execution.stage` 映射；右侧仅通过 `stageRows(job.stages)` 渲染。

因此同一 Job 内存在两份未同步的展示来源：AI 真实阶段驱动左侧，但初始化时的静态阶段数组驱动右侧。右侧并非不知道任务在推进，而是从未收到阶段数组更新。

## 3. 修复设计：单一阶段展示来源

在 `src/bedding_order_parser/web/services.py` 新增 `AI_STAGE_PRESENTATION`。每个后端 AI stage 在一个位置定义：

- 百分比基线；
- 对应的五阶段索引；
- 用户可见中文阶段文本。

`JobService._set_ai_progress()` 现在以该映射为唯一来源，同步持久化：

```text
progress
current_stage
stages[5]
ai_execution.stage
```

其中 `ai_execution.stage` 继续保留真实后端技术阶段，用于诊断和兼容；`current_stage` 是持久化的用户可见文本；`stages` 是右侧五步骤的实时状态。`_ai_stage_rows()` 统一生成 `waiting`、`processing`、`completed`。

前端新增 `progressPresentation(job)`，让左侧百分比、当前阶段文字、右侧 `stageRows()` 和预计剩余时间从同一个已持久化 Job 展示模型读取。旧 Job 的 raw stage 仍会通过现有 `aiStageLabels` 进行回退显示，不要求迁移历史 Job。

未修改 `ai_full_order_service.py`。后端执行阶段、任务顺序和 AI telemetry 均保持原状。

## 4. 实际后端阶段到五阶段映射

| 后端 stage | 用户可见阶段 | 百分比基线 | 右侧五阶段状态 |
| --- | --- | ---: | --- |
| `preprocessing` | 正在读取订单 | 5 | 文件读取处理中 |
| `structure_resolution` | 正在确认表格结构 | 12 | 文件读取处理中 |
| `python_shadow` | 正在执行本地解析对照 | 22 | 文件读取处理中 |
| `ai_extraction` | 正在提取订单候选字段 | 35-57 | 文件读取完成，订单字段提取处理中 |
| `evidence_binding` | 正在绑定来源证据 | 58 | 订单字段提取处理中 |
| `field_resolution` | 正在处理字段差异 | 68 | 订单字段提取处理中 |
| `cache_revalidation` | 正在复核本地缓存 | 76 | 订单字段提取处理中 |
| `dictionary_validation` | 正在验证业务字段 | 82 | 字典校验处理中 |
| `material_matching` | 正在匹配参考物料 | 88 | 物料匹配处理中 |
| `publication` | 正在生成结果 | 94 | 结果生成处理中 |
| `completed` | 解析完成 | 100 | 五步骤全部完成 |
| `awaiting_user_decision` | 等待你的处理决定 | 95 | 保留结果生成阶段展示；既有等待决策页逻辑不变 |

兼容的 V1 整单阶段 `python_shadow_parse`、`local_structure_resolution`、`ai_layout_recognition`、`ai_block_extraction`、`evidence_validation`、`publishing` 也映射到相同五阶段，不会因本次 UI 修复失去展示。

## 5. 关键用户场景

```text
确认表格结构
  -> 文件读取：处理中
  -> 其余四步：等待中

AI 字段提取
  -> 文件读取：已完成
  -> 订单字段提取：处理中

字典校验
  -> 前两步：已完成
  -> 字典校验：处理中

物料匹配
  -> 前三步：已完成
  -> 物料匹配：处理中

结果生成
  -> 前四步：已完成
  -> 结果生成：处理中

完成
  -> 五步：全部已完成
```

百分比仍服从原有后台阶段语义；本 Gate 没有尝试按五步骤等分或由前端猜测后端状态。

## 6. Standard、完成页与失败页保护

- `JobService._set_progress()` 及 Standard 的阶段生成逻辑未改；新增定向测试确认 Standard 在物料匹配时仍为前三步完成、第四步处理中、第五步等待。
- `renderResult()`、AI/Python Review、五类结果预览与下载逻辑未改；现有 AI Review/完成页回归通过。
- `_pause_ai_job()`、`renderAwaitingDecision()`、`AI_V2_STRUCTURE_UNRESOLVED` 的结构解析与失败映射均未改。技术失败仍使用现有等待用户决策页面，本 Gate 仅确保失败前已上报的阶段能被正确展示。

## 7. 测试与离线浏览器验收

执行命令：

```powershell
.venv\Scripts\python.exe -m pytest tests/web/test_ai_progress_frontend.py tests/web/test_ai_full_order_jobs.py tests/web/test_ai_review.py tests/web/test_ai_review_frontend.py tests/ai_full_order/test_v2_downstream.py tests/web/test_d3b2d_ui_enablement.py tests/web/test_services.py tests/web/test_routes.py tests/web/test_job_persistence.py tests/web/test_gate4b_frontend.py tests/web/test_gate4b_routes.py tests/web/test_gate4c2_frontend.py tests/web/test_gate4c2_routes.py tests/web/test_ai_advisory.py tests/web/test_gate4e_help_center.py -q
node --check src/bedding_order_parser/web/static/app.js
git diff --check
```

结果：`136 passed in 15.98s`；JavaScript 语法检查通过；Git 空白检查通过。

新增 `tests/web/test_ai_progress_frontend.py` 使用 Node 受控运行实际生产前端的 `progressPresentation()` 与 `stageRows()`，覆盖结构确认、字段提取、字典校验、物料匹配、发布、完成、旧 raw stage 回退和 Standard 展示。`tests/web/test_ai_full_order_jobs.py` 覆盖所有当前 V2 后端阶段对五步骤的持久化状态。

另使用 FakeProvider、人工合成工作簿和临时本地 loopback 服务进行了实际浏览器验收：

- `structure_resolution` / 12%：页面左侧为“正在确认表格结构”，右侧“文件读取”为“进行中”，其余为“等待中”。
- `ai_extraction` / 42%：页面左侧为“正在提取订单候选字段”，右侧“文件读取”为“已完成”，“订单字段提取”为“进行中”。

本地服务和浏览器测试标签页均在验收后关闭。

## 8. 调用与安全边界

- 真实 Ark/API 调用：0
- 外部 HTTP 调用：0
- 真实 PI：0
- 真实字典、真实物料库、BGE-M3、FAISS：0
- Provider 逻辑调用：仅测试 FakeProvider

浏览器验收只访问本机 `127.0.0.1` 的临时离线服务，不使用用户真实订单。

## 9. 修改文件与工作区

实现修改：

- `src/bedding_order_parser/web/services.py`
- `src/bedding_order_parser/web/static/app.js`
- `tests/web/test_ai_full_order_jobs.py`
- `tests/web/test_ai_progress_frontend.py`

未修改后端解析合同、Provider、Prompt、结构解析、AI-first 决策、technical-ready、五类发布、Standard 业务逻辑、AI Review 完成页或技术失败处理。

本报告提交后，工作区仅保留开始前已有的七份未跟踪交接/审计文档；本 Gate 的已跟踪文件无未提交修改。
