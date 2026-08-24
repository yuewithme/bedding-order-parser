# Gate 4D-D3C Contract V2 Ark 单次真实合成样本验收报告

## 1. 结论

本 Gate 已在授权预算内完成一次且仅一次真实火山方舟 Ark Contract V2 字段提取验收，**真实 V2 合成样本验收通过**。

- 正式入口：桌面 `JobService` 的 `ai_enhanced` Contract V2 链。
- 真实逻辑提取调用：`1`。
- 真实外部 HTTP 尝试：`1`。
- Provider retry：`0`。
- layout 调用：`0`。
- 返回外层形态：`function_call`。
- Job 最终状态：`completed`。
- V2 Schema、provenance binder、Python shadow、字段政策与 ready gate：全部通过。
- FakeDictionaryValidator / FakeMaterialMatcher：各调用 `1` 次。
- 正式 20 字段：通过。
- 五类核心 JSON：恰好 `5` 类完整发布，无第六类业务 JSON。
- 完整请求、原始响应、Authorization、API Key、系统 Prompt、思维链：均未打印、保存或提交。

这证明当前 Contract V2 能在一份结构明确、单记录、纯人工合成输入上通过正式桌面服务链；本结论不外推为真实 PI 或所有复杂版式已经验收。

## 2. 基线与授权

- 项目：`D:\AI-Learning\Projects\bedding-order-parser`
- 分支：`master`
- 起始完整 HEAD：`e87486bbb063cfabdf7717caf826586180ed30fe`
- 起始短 HEAD：`e87486b`
- D3B-2E 实现提交：`80aa08a500e120441578f96a014b0775dd9fe48f`
- D3B-2E 报告提交：`e87486bbb063cfabdf7717caf826586180ed30fe`
- 起始已跟踪工作区：干净。
- 起始未跟踪内容：六份既有交接、恢复或架构审计文档，均保留且未暂存。

本轮授权仅限：火山方舟 Ark、人工合成单记录工作簿、最多 `1` 次逻辑调用、最多 `1` 次 HTTP 尝试、重试 `0`、当前批准模型和 Base URL、`store=false`、非流式、输出上限不高于 `2048`。真实 PI、真实字典、真实物料库、BGE-M3、FAISS 和 layout 真实调用均未授权。

## 3. 有界验收 Harness

调用前新增：

- `tests/ai_full_order/test_ark_v2_single_real_acceptance.py`

该 harness 不修改生产 Provider 或冻结合同，使用正式 `VolcengineArkFullOrderProvider` 和正式 `JobService`，仅在可注入 Transport 边界增加：

1. 一次性授权标记与单 HTTP 尝试锁；
2. 对模型、Base URL、Responses API、V2 function、strict、`store=false`、非流式和合成证据白名单的调用前检查；
3. 在内存中注入 `max_output_tokens=2048`；
4. 显式绕过系统代理，底层只执行一次 `urlopen`，无 SDK 或代理自动重试；
5. 只保留响应形态、脱敏 request ID hash、usage、延迟等白名单元数据；
6. `finally` 中形成安全摘要，并检查临时根目录没有密钥、Authorization 或原始 payload 文件；
7. Fake 下游与正式五类发布验证。

实现提交：

- `4083695cfa60c268584bf79ba3a65fff3b5c2922` `test: add bounded ark v2 acceptance harness`
- `dba76fc8d88f5b1a5df09bb597373e5fb7fb2fe6` `test: stabilize ark v2 synthetic fixture`

第二个提交只固定 `docProps/core.xml` 的 created/modified 时间并增加跨 Python 进程 SHA 测试。它在真实调用后离线完成，没有追加 Ark 请求，也没有改变合成业务内容、V2 Schema、Prompt 或字段政策。

## 4. 调用前硬门

### 4.1 Ark 配置

| 检查 | 实际结果 |
| --- | --- |
| Provider enabled | `true` |
| API Key present | `true`，仅布尔事实 |
| Provider | `volcengine_ark` |
| 模型 | `doubao-seed-2-0-lite-260428` |
| Base URL | 批准的北京 Ark API v3 安全标识 |
| Responses API | `true` |
| stream | `false` |
| store | `false` |
| LLM_MAX_RETRIES | `0` |
| Transport 最大 HTTP attempts | `1` |
| max output tokens | `2048` |
| SDK 隐式重试 | 无 SDK |
| 代理自动重试 | 系统代理已显式绕过 |

预检、fixture 构造和 Job 创建阶段 Transport 尝试均为 `0`。

### 4.2 人工合成 Fixture

内容类别仅包括：虚构客户、虚构业务员、USD/美元币种提示、通用床品名称、尺寸、棉质/白色描述、数量 `10` 和日期 `2026-12-31`。没有真实客户、地址、联系人、订单号、银行、付款、物料编码或相似分数。

- 单 Sheet：是。
- 单订单 scope：是。
- 单明细记录：是。
- 隐藏行列：无。
- 结构歧义：无。
- 实际真实调用进程内 fixture SHA256：`1db654b1f9fb8f9a5b6585e6c62e33117fdc71e21b460d7e424870f16a7d4ead`。
- 真实调用后固定 XLSX core metadata 后的跨进程稳定 SHA256：`c8da9dc059fa9055e5ac1648cc19d555b4deac71b04bc11c4da3d5b4895d3897`。

两者业务单元格、结构和证据类别相同。实际调用只使用前者，且其进程内预检 SHA、正式 Job 输入 SHA 与发往 V2 请求的 source SHA 完全绑定；后续稳定化仅修复 XLSX 元数据导致的跨进程字节差异，没有重跑真实调用。

### 4.3 本地预演

- `structure_status`：`locally_resolved`。
- target record：`1`。
- extraction unit：`1`。
- 进度预期：`0/1`。
- evidence：`19` 个同 target/scope 证据项。
- V2 request Schema：通过。
- target identity、scope、evidence 集合：通过。
- Python shadow：通过。
- 客户、币种、业务员、数量、计划发货日期：`5/5` 具有本地直接证据。
- layout Provider 调用：`0`。
- 提取 Provider 调用：`0`。
- HTTP 尝试：`0`。
- 真实字典、物料库、BGE-M3、FAISS 加载：`0`。

## 5. 唯一真实调用

使用正式函数 `submit_bedding_order_candidates_v2`，由 `JobService._run_job()` 进入当前 V2 编排；没有直接脱离产品链调用 Provider。

### 5.1 调用与 Transport

| 项目 | 实际值 |
| --- | --- |
| V2 extraction 逻辑调用 | `1` |
| 外部 HTTP attempts | `1` |
| retry | `0` |
| layout calls | `0` |
| max output tokens | `2048` |
| store / stream | `false / false` |
| 返回外层形态 | `function_call` |
| 安全解析阶段 | `strict_contract_passed` |
| 脱敏 request ID | `sha256:278c58afe28b` |
| input tokens | `2400` |
| output tokens | `501` |
| total tokens | `2901` |
| Provider 延迟 | `7453 ms` |

第一次外部 HTTP 尝试后本 Gate 授权立即耗尽。没有模型切换、Prompt/Schema 修改、fixture 修改后重试或第二次调用。

### 5.2 合同与发布结果

- V2 顶层及 candidate Schema：通过。
- 禁止字段或额外字段：无。
- evidence ID：全部属于请求内 target。
- 跨 scope：无。
- provenance binder：通过。
- 采纳候选的本地 quote/span 约束：通过。
- 高风险 blocking conflict：无。
- canonical 17 字段：完整。
- ready gate：通过。
- FakeDictionaryValidator：`1` 次。
- FakeMaterialMatcher：`1` 次。
- 正式 20 字段：字段顺序、类型和完整性通过。
- 五类角色：全部完整。
- 当前 Bundle JSON 数量：`5`。
- 第六类业务 JSON：无。
- Job：`completed`，chunk `1/1`，fallback `not_requested`，safe error code 为空。

## 6. 安全摘要与清理

安全摘要在临时目录清理前形成，只包含固定配置事实、调用计数、返回形态、脱敏 request ID、Token、延迟、Job/门状态和角色完整性。

- 完整 HTTP 请求：未打印、未持久化、未提交。
- 原始 Ark 响应：未打印、未持久化、未提交。
- Authorization / API Key：未打印、未持久化、未提交。
- 系统 Prompt、完整外发正文、思维链：未打印、未持久化、未提交。
- 合成 xlsx：已删除。
- 临时 Job/runtime/cache/state/staging/publish：已删除。
- 原始 Provider payload 文件：`0`。
- 本 Gate 启动的 server 或遗留进程：`0`。

复核时发现一个由 Windows Explorer 在本 Gate 之前启动的桌面 `pythonw.exe` 实例；它不是本 Gate 启动的进程，因此未终止。当前用户失败 Job 及其工作簿未读取、未恢复、未重跑、未清理。

## 7. 离线测试与零额外网络证明

调用前：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ai_full_order\test_ark_v2_single_real_acceptance.py -q
# 3 passed in 0.95s

.\.venv\Scripts\python.exe -m pytest `
  tests\ai_full_order\test_volcengine_ark_full_order_provider.py `
  tests\ai_full_order\test_v2_offline_resolution.py `
  tests\ai_full_order\test_v2_reliability.py `
  tests\ai_full_order\test_v2_downstream.py `
  tests\web\test_ai_full_order_jobs.py -q
# 68 passed in 11.23s
```

真实调用后，先固定 fixture 跨进程元数据并得到 `4 passed in 2.34s`，再使用 Python socket guard 阻断所有非 loopback 连接，运行 V2 Provider、合同、provenance、字段政策、可靠性、下游、桌面 Job、D3B-2D UI、D3B-2E runtime、标准模式、单记录 Sidecar 与 D2D 诊断定向矩阵：

```text
288 passed in 34.65s
```

该回归阶段真实 Ark、其它外网、真实字典、真实物料库、BGE-M3、FAISS 和真实 PI 调用均为 `0`。未运行完整 pytest。

## 8. 修改文件与未改变范围

修改文件：

- `tests/ai_full_order/test_ark_v2_single_real_acceptance.py`
- `docs/reports/GATE_4D_D3C_ARK_V2_SINGLE_REAL_ACCEPTANCE_REPORT.md`

生产代码修改：`0`。未修改 `contracts.py`、Provider、Prompt、17 字段、正式行号、provenance、field policy、cache identity、ready gate、五类发布、标准解析、字典/物料算法、默认 ZIP、C2/D3B-2D UI 或单记录 AI Sidecar。

## 9. 未执行事项

- 未读取、复制、分析、发送或重跑用户截图对应的真实失败订单。
- 未调用 `resolve_structure()`。
- 未使用真实 PI、真实客户、真实联系人、真实银行或商业资料。
- 未调用真实字典、真实物料库、BGE-M3 或 FAISS。
- 未执行第二次 Ark 调用。
- 未运行完整 pytest。

## 10. 提交、工作区与下一步

- Harness 实现提交：`4083695cfa60c268584bf79ba3a65fff3b5c2922`。
- Fixture 稳定化提交：`dba76fc8d88f5b1a5df09bb597373e5fb7fb2fe6`。
- 报告提交信息：`docs: report single real ark v2 acceptance`。
- 报告提交完整哈希：由本报告提交后的 Git 核验和最终交接给出。
- 最终工作区目标：无已跟踪修改，仅保留六份既有未跟踪交接/恢复/架构审计文档。

下一步唯一阻塞：当前真实用户订单仍在本地结构阶段出现 `AI_V2_STRUCTURE_FAILED`（截图计数为逻辑调用 `0`、HTTP `0`、Token `0`、区块 `0/0`）。应另开独立、默认离线的结构预处理诊断 Gate，并取得对该订单最小只读访问的明确授权；本 Gate 的真实 Ark 授权已经耗尽，不得沿用。
