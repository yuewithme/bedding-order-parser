# Gate 4D-D3D-1｜最近一次真实订单 AI_V2_STRUCTURE_FAILED 本机离线只读诊断

## 1. 审计范围与基线

- 审计方式：只读。本次未修改、移动、删除、重试任何 Job、上传文件、工作簿或生产代码。
- 分支：`master`。
- 审计开始时 HEAD：`96fe952510197f96d171ed13f53290397fa3c441`（`96fe952 docs: report single real ark v2 acceptance`）。
- 开始时仅有既存的 6 份未跟踪交接/审计文档；不存在已跟踪代码改动。
- 目标选择：在本机桌面任务存储中找到 2 条同时满足 `parse_mode=ai_enhanced`、Contract V2、`AI_V2_STRUCTURE_FAILED` 的历史 Job；按创建时间选取唯一较新的 1 条。报告中不保存 Job ID、文件名或本机路径。
- 安全保护：每个诊断脚本均安装阻止非 loopback 连接的 socket guard。未调用 `JobService._run_job`，未构造真实 Provider，未调用 Ark、字典、物料匹配、BGE-M3、FAISS 或网络。

## 2. 目标文件与 Job 完整性

对唯一目标 Job 的元数据和唯一上传工作簿，在只读诊断前后分别计算安全摘要：

| 项目 | 结果 |
| --- | --- |
| Job 元数据 SHA-256 前缀 | `d12c1d84b8bd`，前后相同 |
| 源工作簿 SHA-256 前缀 | `e005dc8f5f3b`，前后相同 |
| 源文件大小 | 105,053 bytes，前后相同 |
| 源文件 mtime_ns | `1785946010995102700`，前后相同 |
| Job 输入文件数 / Excel 文件数 | 1 / 1 |
| 上传目录归属、文件身份、大小 | 均与 Job 元数据一致 |

该文件是有效 `.xlsx` ZIP：25 个成员，具备必需的 Content Types、workbook XML 与关系文件；没有宏、外部链接、连接、查询表或 ZIP 损坏成员。工作簿有 4 个 drawing ZIP 成员，但 `openpyxl` 没有加载图表或图片对象；没有以图像为主导致纯文本解析天然不可行的证据。

## 3. 真实工作簿的安全结构事实

以下仅记录结构、坐标和计数；不包含 sheet 全名、业务文本、单元格原文、公式内容或客户信息。

| 项目 | 结果 |
| --- | --- |
| 工作表数 | 1，且为可见、默认纳入的 `s1` |
| `openpyxl` 形式 used range | 95 行 × 16,357 列 |
| 重新计算的实际内容边界 | 行 2–95，列 1–11 |
| 实际非空单元格 / 稀疏单元格 | 414 / 499 |
| 实际边界空白比例 | 0.599613 |
| 合并区域数 | 20 |
| 隐藏行 / 列 | 0 / 0 |
| 单元格值类型 | 文本 280、数字 133、公式 1 |
| 公式视图和展示视图读取 | 均成功，且无读取 warning |

这证明极宽 used range 是格式残留，非真实 16k 列数据。`ai_full_order.preprocessing._actual_used_bounds()` 已正确收窄到实际内容边界，不能把这项格式残留当作本次失败根因。

编号行启发式识别到 3 组：行 14–73（60 行）、78–83（6 行）、86–91（6 行）。在前三行回溯中，只有第一组找到满足现行规则的表头候选（行 13）；后两组没有表头候选。该事实是后续误判的直接输入。

## 4. V2 预处理与标准解析的实际结果

对同一工作簿仅运行本地读取、预处理及标准解析函数：

| 路径 | 安全结果 |
| --- | --- |
| `preprocess_workbook()` | 成功；1 个 block、60 个预处理 records、368 个 evidence、scope 为 `s1:scope-1` |
| `build_v2_extraction_units()`（仅在只读脚本中直接调用） | 成功构建 60 个 V2 extraction units |
| `PreprocessedWorkbook.structure_status` | `ambiguous` |
| 本地结构识别请求实际发出数 | 0 |
| 标准解析 | 成功；产出 3 条正式记录 |

因此，界面中的 `0 / 0` **不表示** V2 预处理无法发现记录，更不表示工作簿为空。相反，本地 V2 已可构建 60 个候选单元；标准解析也能在不同的表格语义规则下生成 3 条正式记录。两条路径的记录数不应直接视为同一语义：V2 当前编号行分组过宽，标准解析还使用表头、表格边界、footer 与品类筛选规则。

## 5. 第一处失败与 `0 / 0` 的准确执行链

真实 Job 的执行顺序可由当前代码和只读结构结果确定：

```text
preprocess_workbook()
  -> structure_status == "ambiguous"
  -> run_ai_enhanced_v2_job() 尝试 provider.resolve_structure(preprocessed.to_request_dict())
  -> VolcengineArkFullOrderProvider.resolve_structure() 的本地请求形状校验
  -> AIEnhancedJobPause("AI_V2_STRUCTURE_FAILED")
  -> JobService 将无 execution 的暂停安全持久化为 awaiting_user_decision，进度为 0 / 0
```

### 5.1 首个阻止执行的条件

`src/bedding_order_parser/ai_full_order/preprocessing.py` 约第 339–398 行的 `_build_blocks()`：

1. `_numbered_row_groups()`（约第 412–425 行）把首个非空值为纯编号的行聚为编号组；
2. `_header_rows_before()`（约第 428–435 行）只在每组前 3 行内查找分数至少为 2 的表头；
3. 对后两组找不到表头时，代码执行 `ambiguous = True; continue`；
4. 即使第一组已经构建有效 block，`preprocess_workbook()` 在约第 211 行仍以 `blocks and not unresolved_structure` 决定 `locally_resolved`，最终给出 `ambiguous`。

此处是当前工作簿第一次被引导至布局 AI 路径的具体函数和条件。它不是 Ark 返回失败。

### 5.2 结构识别分支的本地合同不匹配

`src/bedding_order_parser/web/ai_full_order_service.py` 约第 291–302 行的 `run_ai_enhanced_v2_job()`：

- 约第 293 行检查到 `preprocessed.structure_status == "ambiguous"`；
- 约第 295 行把 `preprocessed.to_request_dict()` 直接交给 `provider.resolve_structure()`；
- 约第 296–302 行将该阶段任意异常统一包为 `AIEnhancedJobPause("AI_V2_STRUCTURE_FAILED")`。

但 `src/bedding_order_parser/ai_full_order/preprocessing.py` 约第 162–173 行的 `PreprocessedWorkbook.to_request_dict()` 只提供 `blocks`、`records`、evidence 等预处理形状，**不含** `chunks`。

`src/bedding_order_parser/ai_full_order/volcengine_ark.py` 约第 121–138 行的 `VolcengineArkFullOrderProvider.resolve_structure()` 则要求 `manifest["chunks"]` 为 list；缺失时本地创建固定类别 `type_mismatch`、固定路径 `$.chunks` 的严格合同错误。该检查位于 `structure_call_count` 递增之前，因此：

- Provider 逻辑调用计数保持 0；
- HTTP 尝试保持 0；
- 真实 Ark 没有被调用；
- 结构识别根本没有机会返回；
- V2 unit 构建位于服务函数约第 310 行，在暂停后永远不会到达。

`src/bedding_order_parser/web/services.py` 约第 1135–1201 行在收到没有 `execution` 的 `AIEnhancedJobPause` 后以空 items 计算进度，因而界面显示 `0 / 0`、逻辑 AI 调用 0、HTTP 尝试 0。截图中的 `AI_V2_STRUCTURE_FAILED` 与上述本地失败链完全一致。

## 6. 根因判断

### 主根因

**结构歧义分支的服务层输入适配错误**：`run_ai_enhanced_v2_job()` 把 `PreprocessedWorkbook` 请求形状传给要求 chunk manifest 的正式 Ark structure Provider。这个错误发生在任何网络请求之前，导致所有落入该分支的真实订单必然以 `AI_V2_STRUCTURE_FAILED` 暂停。

### 触发因素

**当前 V2 编号行分组和表头回溯启发式过于粗糙**：后续数字区段被当作编号数据组，且缺少紧邻表头时即把整张工作表标为 ambiguous。第一有效 block 和 60 个 records 已存在，但两个辅助区段使状态翻转。标准解析得到 3 条记录也说明 V2 不能只用“纯编号行 + 三行表头”代替现有标准表格边界语义。

### 非根因

- 非真实 Ark / 网络失败：本次实际 Ark HTTP 尝试为 0。
- 非 Excel 损坏、宏、外部链接、隐藏内容、二进制图像主导或超宽格式范围问题。
- 非 V2 unit 无法生成：只读直接调用已生成 60 个。
- 非字段 Schema、evidence、字段裁决、字典、物料匹配或五类发布失败：执行在这些阶段之前停止。

## 7. 当前测试缺口

已有 provider 单测 `tests/ai_full_order/test_volcengine_ark_full_order_provider.py` 约第 317 行直接把带 `chunks` 的手工 manifest 传给 `resolve_structure()`；它覆盖 provider 的独立契约。

已有桌面 Job 测试 `tests/web/test_ai_full_order_jobs.py` 约第 610 行用能接受预处理形状的 FakeProvider 覆盖 ambiguous 分支；它没有把正式 `VolcengineArkFullOrderProvider` 与服务层 ambiguous 分支一起运行。

因此，现有测试能分别验证两端，却遗漏了两种 manifest 形状在真实注入路径中的适配。该缺口允许本次本地、零网络失败进入 UI。

## 8. 已执行的离线回归

所有测试在假的本机凭据、`LLM_MAX_RETRIES=0`、loopback-only Base URL 下运行；没有真实 Provider、网络、BGE-M3、FAISS、真实字典或真实物料匹配调用。

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\ai_full_order\test_preprocessing.py `
  tests\ai_full_order\test_orchestration.py `
  tests\ai_full_order\test_volcengine_ark_full_order_provider.py `
  tests\web\test_ai_full_order_jobs.py -q
# 42 passed in 8.09s

.venv\Scripts\python.exe -m pytest `
  tests\excel\test_table_parser.py `
  tests\extraction\test_item_extractor.py `
  tests\web\test_services.py `
  tests\web\test_ai_advisory.py -q
# 52 passed in 3.88s
```

这 94 项测试证明现有覆盖仍通过；它们不等同于已覆盖本报告识别的正式 Provider + ambiguous 服务适配缺口。

## 9. 诊断期间的后续状态变化

完成首次目标快照后，为补充标准解析行号而再次按同一条件定位 Job 时，本机任务元数据已不再保留这条 `AI_V2_STRUCTURE_FAILED` 匹配状态。该变化发生在本次诊断之外，可能来自正在运行的桌面程序或用户操作。本 Gate 没有对该 Job 执行写入，因此没有猜测、没有追读其他真实订单，也没有把后续状态归因于本 Gate。

首次快照已记录源和 Job 在读前读后完全相同，且已成功完成标准解析 3 条记录和 V2 60 单元的只读对照；足以支撑本报告的根因结论。

## 10. 本 Gate 操作计数与最终状态

| 项目 | 数量 |
| --- | ---: |
| 真实 Ark / 网络 HTTP | 0 / 0 |
| Provider 逻辑调用 | 0 |
| 结构识别调用 | 0 |
| 单记录 AI Sidecar 调用 | 0 |
| 真实字典、真实物料、BGE-M3、FAISS | 均为 0 |
| 修改的 Job / 工作簿 / 源码文件 | 0 / 0 / 0 |
| 本 Gate 新增文件 | 仅本报告 |

## 11. 下一步最小 Gate 建议

建议单独执行一个**纯离线、最小修复 Gate**，而不是重试真实订单：

1. 在 `run_ai_enhanced_v2_job()` 与 `resolve_structure()` 之间引入窄的、显式的结构识别 manifest 适配器，保证正式 Provider 永远收到含 `chunks` 的既有结构合同；不要放宽 Provider Schema。
2. 补充正式 Ark Provider + ambiguous Job 分支的集成测试，断言本地请求形状通过、未授权时网络仍为 0。
3. 用脱敏合成 fixture 覆盖“主表后有编号辅助区段但没有重复表头”的预处理策略。根据冻结的 Contract V2 决定这些区段应被忽略、成为独立 scope，或才触发布局识别；不得把 `ambiguous` 静默视作可发布。
4. 在全离线通过后，才由用户决定是否对同一真实订单进行一次新的、明确授权的运行；该运行应另设 Gate 与调用预算。

本报告不包含或泄露真实订单业务内容，且不建议以关闭结构、evidence、字段裁决或发布门来绕过该本地失败。
