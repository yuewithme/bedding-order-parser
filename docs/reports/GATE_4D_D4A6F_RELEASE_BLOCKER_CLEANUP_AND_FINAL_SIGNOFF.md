# Gate 4D-D4A-6F｜Release Blocker Cleanup、完整测试全绿与最终项目签署

日期：2026-08-11
项目：`D:\AI-Learning\Projects\bedding-order-parser`
分支：`master`

## 1. 基线与提交

- 起始 HEAD：`d8445e26d4ab2b16b31394287dcd0eede78c5ba9`
- 起始短 HEAD：`d8445e2`
- D4A-6 报告提交：`d8445e26d4ab2b16b31394287dcd0eede78c5ba9`（`docs: close ai full-order project after final acceptance`）
- 实现提交：`eb18e2a3ab3995c8c9726188e995f28055600d9e`（`fix: clear final release blockers`）
- 开始时已跟踪工作区：干净
- 开始时已有 7 份未跟踪交接/架构文档；本 Gate 未读取后改写、未暂存、未删除。

D4A-6 的最大安全完整测试基线为：

```text
collected = 669
passed = 659
failed = 10
```

本 Gate 只处理 D4A-6 已确认的 3 类 release blocker，以及 1 项帮助文案偏差；未扩展产品功能。

## 2. 修改前复现

| 问题 | 修改前结果 | 结论 |
|---|---:|---|
| strict schema failure usage | 预期 18，Job 保存 0 | 稳定复现 |
| embedding worker 整文件 | 14 passed / 2 failed | 两个 opaque pre-encode exit 未重试 |
| AI disabled 断言 | 旧文案正则失败 | 产品行为未变，测试陈旧 |
| Desktop 污染顺序 | 14 passed / 3 failed | `faiss` 已由前序测试载入后，测试误判 Desktop eager-load |

复现没有使用真实 Ark、真实订单、真实字典、真实物料库、BGE-M3 或生产 FAISS 索引。

## 3. Blocker 1：AI failure/pause usage delta

### 根因

`VolcengineArkFullOrderProvider` 在成功收到 HTTP 响应后，已经先记录安全 telemetry 和累计 `usage_summary`，随后严格 Schema 校验才失败。问题不在 Transport，也不在 Provider 计数，而在 V1 桌面编排异常边界：

- `run_ai_enhanced_job()` 成功路径直接读取 Provider session 累计 usage；
- `ISOLATED`、`INTERRUPTED`、`IN_PROGRESS` 和 downstream failure 创建 `AIEnhancedJobPause` 时没有携带本 Job usage；
- `_pause_ai_job()` 只能读取异常中的 `usage`，缺失时按安全默认写 0；
- 因此“已产生 Token、随后严格验证失败”的 Job 丢失了本次调用事实。

### 修复

在 `src/bedding_order_parser/web/ai_full_order_service.py`：

1. V1 Job 绑定依赖后立即记录 extraction/layout/HTTP/usage 基线；
2. 成功、隔离、中断、进行中和发布失败统一使用本 Job delta；
3. `AIEnhancedJobPause` 携带本 Job 的调用、HTTP 和 usage delta；
4. V1 成功结果不再返回 Provider session 累计 usage；
5. V2 在已发生 layout 调用后才发现无 extraction unit 或超预算时，也保留 layout/HTTP/usage delta；
6. `JobService` 对 V1/V2 均消费异常中已经计算好的 Job-local counters，不再从共享 Provider 反推累计值。

### 验证结果

| 场景 | Provider session 基线 | 本 Job usage | Job 保存结果 |
|---|---:|---:|---:|
| success | 0 | 11/7/18 | 11/7/18 |
| strict schema failure | 600/400/1000 | 11/7/18 | 11/7/18 |
| strict failure 后 Provider session | 600/400/1000 | +11/+7/+18 | 611/407/1018 |
| Provider failure before usage | 0 | 0/0/0 | 0/0/0 |
| V2 既有多 operation delta | session total 1530 | total 30 | 30 |

用量仍来源于 Transport/Provider 安全 telemetry；没有根据失败类型伪造 Token，也没有改变 retry policy。

## 4. Blocker 2：Windows embedding worker

### 根因

原 `_process_is_alive()` 在 Windows 上只要 `OpenProcess()` 能获得句柄就返回存活。Windows 已退出进程的内核对象在句柄/对象尚未释放期间仍可被打开，因此：

```text
worker return code = 3
OpenProcess succeeds
worker_exit_confirmed = false
_is_retryable_pre_encode_exit() refuses bounded retry
```

同时，原 Win32 调用通过未声明签名的 `ctypes.windll` 执行，没有可靠启用 `use_last_error`，HANDLE 返回类型也没有显式使用指针宽度。在进程恰好退出的竞态中，会出现失真的 `WinError 0`，覆盖原始 timeout/cancel 诊断。

### 修复

在 `src/bedding_order_parser/materials/query_embedding_runner.py`：

- 使用 `ctypes.WinDLL("kernel32", use_last_error=True)`；
- 为 `OpenProcess`、`GetExitCodeProcess`、`TerminateProcess`、`WaitForSingleObject`、`CloseHandle` 声明 Win32 参数和返回类型；
- `_process_is_alive()` 以 `GetExitCodeProcess() == STILL_ACTIVE` 判断真实存活状态；
- `_terminate_exact_pid()` 在终止前检查退出码；已经退出视为可接受终态；
- `TerminateProcess()` 与退出竞态时再次检查退出码，避免用终止错误覆盖原始失败；
- 无法确认进程状态时保持保守，不把未知状态当作安全退出。

### Retry 边界

仅以下情况允许现有的一次有界重试：

- failure kind 为 unexpected process exit 或 Windows abnormal termination；
- Provider/worker 没有给出确定性 Python error；
- completed query count 为 0；
- worker 退出已被确认；
- 非 timeout、非 cancel。

以下情况继续不重试：

- 确定性 Python exception；
- 已完成至少一个 query 后失败；
- timeout/cancel；
- 无法确认 worker 已退出；
- 第二次 opaque exit（最多仅一次 retry）。

没有取消 worker 隔离，没有扩大 timeout，没有无限 retry，也没有吞掉 crash。

### 五次独立稳定性

```text
run 1: 17 passed in 3.80s
run 2: 17 passed in 3.82s
run 3: 17 passed in 3.80s
run 4: 17 passed in 3.81s
run 5: 17 passed in 3.78s
```

新增 1 条 Windows 专用保护测试：子进程以 code 3 退出后，即使进程对象仍可查询，也必须判定为非存活，且再次请求终止不得报错。

## 5. Desktop 测试隔离

### 根因

生产 Desktop 启动仍保持 lazy import；失败来自测试把“整个 pytest 进程从未导入过 `faiss`”错误当成 Desktop 的责任。前序 synthetic vector-index 测试合法加载 `faiss` 后，三个 Desktop 断言必然失败。

### 修复

- 纯 import boundary 在 `python -I` 隔离子进程中验证；
- controller/preflight 和 downstream factory 测试记录操作前 `sys.modules` 快照，并验证操作没有新增或替换 matching runtime 模块；
- 未修改任何 Desktop 生产代码。

污染顺序重放：

```text
tests/materials/test_vector_index.py
-> 三个 Desktop lazy-import 测试
= 17 passed in 2.04s
```

Desktop 独立新进程最终结果：

```text
27 passed in 5.14s
```

## 6. AI disabled 陈旧断言

当前正式 preflight 安全码仍为：

```text
AI_PROVIDER_DISABLED
```

当前用户文案为：

```text
AI整单解析尚未在本机启用，完成配置后即可提交。
```

测试改为同时断言稳定安全码和“尚未在本机启用”的当前语义，不再依赖已经废弃的“当前不能启动任务”全文。生产 API、Job 创建行为和 UI 文案均未回退。

## 7. Help 导出文案

原文暗示 Excel/ZIP 均可用。现改为：

```text
处理完成后可以预览和下载五类结果；
标准解析当前支持完整结果 ZIP；
Excel 导出以界面可用状态为准。
```

没有新增 Excel export、AI ZIP 或任何下载能力。

## 8. 定向测试

主要定向组合：

```text
acceptance diagnostics
V2 session usage delta
embedding worker
tests/desktop
AI disabled Job
Gate 4E Help
```

结果：

```text
99 passed in 14.28s
```

此外，修改后的 worker 首次单独运行即为 `17 passed in 3.83s`，随后再完成上述 5 次独立全绿验证。

## 9. 完整最大安全 pytest

执行前显式关闭 LLM/Ark 凭证环境。真实 acceptance 入口保持显式调用，不在 pytest 收集期间触发。

```text
collected = 670
passed = 670
skipped = 0
failed = 0
duration = 90.17s
```

相比 D4A-6 的 669 项，增加 1 条 Windows 退出态保护测试；没有删除、skip 或弱化任何既有安全测试。

完整 suite 包含 synthetic FAISS unit operations，但没有加载生产物料索引、真实物料库或 BGE-M3。

## 10. Edge final smoke

使用真实 Microsoft Edge、Playwright CLI 离线缓存包和 `127.0.0.1` loopback synthetic/Fake harness 验证：

1. 首页同时显示 Standard 与 AI 整单解析；
2. completed AI Job 显示“AI整单解析完成”、17 个待复核、5 个高风险待复核和完整五类结果；
3. “查看来源位置”实际展开 Sheet、单元格和 bounded excerpt；
4. 点击“使用本地规则”后从第 1 版进入第 2 版，五类结果继续完整；
5. `AI_V2_STRUCTURE_UNRESOLVED` technical failure 显示独立“使用标准解析重新处理”；
6. 点击后创建新 Job ID，并跳转新 Standard Job 的 progress route；
7. 浏览器会话、Playwright snapshot、synthetic workbook、Job state 和临时 server harness 全部清理。

结果：`PASS`。

浏览器只访问本机 loopback；external HTTP 为 0。

## 11. Desktop final smoke

- `tests/desktop` 独立运行：`27 passed in 5.14s`；
- 覆盖 Desktop import、resource paths、controller 生命周期、preflight、runtime identity、shortcut/launcher 合同和 V2 composition；
- 未重新打包，不修改快捷方式，不加载真实物料资源。

结果：`PASS`。

## 12. 静态检查

| 检查 | 结果 |
|---|---|
| `python -m compileall -q src tests` | PASS |
| `node --check src/bedding_order_parser/web/static/app.js` | PASS |
| `git diff --check` | PASS |
| Ruff / Black | 未安装，按 Gate 边界未新增依赖 |

## 13. 真实调用与数据边界

| 项目 | 实际次数 |
|---|---:|
| 真实 Ark API | 0 |
| external HTTP | 0 |
| 真实 PI | 0 |
| 真实字典工作簿 | 0 |
| 真实物料库 | 0 |
| BGE-M3 | 0 |
| 生产 FAISS/index | 0 |
| synthetic FAISS unit operations | 有，仅完整测试中的受控单元测试 |

没有保存请求正文、原始 Provider 响应、Authorization、API Key 或思维链。

## 14. 修改文件

生产/用户文案：

1. `src/bedding_order_parser/materials/query_embedding_runner.py`
2. `src/bedding_order_parser/web/ai_full_order_service.py`
3. `src/bedding_order_parser/web/services.py`
4. `src/bedding_order_parser/web/static/app.js`

测试：

5. `tests/ai_full_order/test_acceptance_diagnostics.py`
6. `tests/materials/test_query_embedding_worker.py`
7. `tests/desktop/test_d3b2e_runtime_and_composition.py`
8. `tests/desktop/test_resource_paths.py`
9. `tests/web/test_ai_full_order_jobs.py`
10. `tests/web/test_gate4e_help_center.py`

本 Gate 没有修改 AI-first field policy、multi-sheet/Layout Contract、Prompt、Provider 主协议、Review/Revision 产品语义、五类 Schema、Standard parser、字典规则、MaterialMatcher 算法或 Standard reprocess 合同。

## 15. 最终 Release Checklist

| 能力/边界 | 结果 |
|---|---|
| Standard core | PASS |
| AI Enhanced core | PASS |
| multi-sheet / Layout Contract | PASS |
| AI-first resolution | PASS |
| evidence / provenance hard safety | PASS |
| technical readiness 与 business review 分离 | PASS |
| 五类 JSON 原子发布 | PASS |
| Review | PASS |
| immutable Revision / CURRENT | PASS |
| 独立 Standard reprocess | PASS |
| progress UX | PASS |
| legacy compatibility | PASS |
| failure usage delta | PASS |
| Windows worker lifecycle/retry | PASS |
| Desktop lazy import | PASS |
| security / zero real calls | PASS |
| Edge browser smoke | PASS |
| Desktop smoke | PASS |
| full regression | PASS（670/670） |
| workspace tracked state | PASS |

## 16. Remaining blockers 与 non-blocking backlog

Release blockers：`0`。

仍保留但不阻断当前 frozen scope 的 backlog：

1. 大订单 Revision 全量本地下游性能；
2. 多进程 revision writer lock 的吞吐增强；
3. 大量 Review 的分页/折叠体验；
4. Revision timeline / rollback UI；
5. Excel export 与 AI ZIP；
6. 无本地 order candidate 的复杂 Sheet 仍安全失败；
7. 模型字段漏提取由 Python fallback、both-missing review 和人工 Revision 承接。

Help 文案偏差已在本 Gate 修复，因此不再列入 backlog。

## 17. Project Closure Decision

```text
PROJECT STATUS:
CORE IMPLEMENTATION COMPLETE

RELEASE STATUS:
READY TO CLOSE

RELEASE BLOCKERS:
0

NEXT DEVELOPMENT:
None required for current frozen scope
```

## 18. 最终工作区

实现提交后、报告提交前：

- 已跟踪生产代码与测试：干净；
- 本报告为唯一新增报告；
- 7 份开始前已存在的未跟踪交接/架构文档仍保持未跟踪且未改动；
- 无临时 browser harness、Playwright snapshot、synthetic Job 或 worker runtime 残留。
