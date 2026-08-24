# Gate 4D-D4A-6：最终集成验收、Release Readiness 与项目收口报告

## 1. 最终结论

```text
FAIL — RELEASE BLOCKER REMAINS

PROJECT STATUS:
NOT READY TO CLOSE

RELEASE STATUS:
RELEASE BLOCKED
```

当前 `master` 的主要业务能力已经形成完整闭环，AI-first、multi-sheet、五类原子发布、Review、Revision 和独立 Standard reprocess 均通过定向回归与真实 Edge 浏览器验收。但是最大安全完整测试仍为 `10 failed / 659 passed`，其中有 2 类可重复的生产可靠性问题和 1 类发布验证基础设施问题。因此本报告不能把当前 HEAD 宣称为 Release Candidate。

本 Gate 严格执行“验收，不继续开发”：除本报告外未修改生产代码、测试、Prompt、Schema、配置或业务文档。

## 2. 基线与工作区

- 分支：`master`
- 起始完整 HEAD：`e174b716b884040ec6700f7a635bd9a7c5272c66`
- 起始短 HEAD：`e174b71`
- D4A-5 implementation commit：`5d6e23d77723294707a0bad2c542f3126e858734`
- D4A-5 report commit：`e174b716b884040ec6700f7a635bd9a7c5272c66`
- 起始已跟踪工作区：干净
- 起始未跟踪文件：7 份既有交接/审计文档，均未修改、清理或暂存

最近 15 个提交从 `e174b71` 向前依次覆盖：独立 Standard reprocess、immutable Revision、真实 Ark multi-sheet Layout 验收、multi-sheet 结构应用、进度同步、Review UI、technical-ready/发布语义。

## 3. 最终功能盘点

| 功能 | 当前状态 | 验收证据 | Release blocker |
|---|---|---|---|
| Standard Python 主解析 | 已实现 | Standard reprocess Fake E2E；标准解析相关 154 项定向测试 | 是，embedding worker 可靠性未全绿 |
| Standard 字典与物料 TopK | 已实现 | Fake matcher E2E；材料安全套件 44 passed | 是，Windows worker retry 仍失败 |
| Standard 五类 JSON / ZIP | 已实现 | Job 完成后五角色完整；`services.py::_write_bundle()` | 否 |
| Standard 单记录 AI Sidecar | 已实现 | Web/Sidecar 回归通过 | 否 |
| AI Enhanced preprocessing | 已实现 | AI full-order 197 passed | 否 |
| 可选 multi-sheet Layout V2 | 已实现 | D4A-3D Fake 全链；D4A-3E 真实 Ark 单次验收 | 否 |
| AI 17 字段主解析 | 已实现 | field policy / V2 orchestration 回归通过 | 否 |
| Python shadow comparison/fallback | 已实现 | AI-first matrix 回归与浏览器 Review | 否 |
| technical-ready / review 分离 | 已实现 | review batch 可发布；hard evidence 仍阻断 | 否 |
| 五类原子发布 | 已实现 | failure injection、CURRENT、exactly-five 测试 | 否 |
| Review / evidence display | 已实现 | Edge 实际展开来源位置 | 否 |
| immutable Revision | 已实现 | Edge 第 1→2→3 版；刷新后 CURRENT 为第 3 版 | 否 |
| 独立 Standard reprocess | 已实现 | Edge 单击创建新 Job；原 AI Job 不变 | 否 |
| technical failure / retry / keep failed | 已实现 | Job/API 定向回归通过 | 否 |
| Legacy V1 / old V2 / historical fallback | 安全兼容 | 兼容读取测试通过，不强制迁移 | 否 |
| 失败调用 Token 安全摘要 | 部分失效 | strict schema failure 实际 18 Token 被 Job 记录为 0 | **是** |
| 全套测试可重复全绿 | 未达到 | 669 collected，10 failed | **是** |

## 4. 当前架构总览

### Standard

```text
Excel source
→ Python parser
→ DictionaryValidator
→ MaterialMatcher / TopK
→ fixed 20 fields
→ exactly five JSON
→ Standard result page / ZIP
→ optional user-triggered single-record AI Sidecar
```

### AI Enhanced

```text
Excel source
→ sparse preprocessing / local geometry
→ optional Layout Contract V2 resolution
→ single-target extraction units
→ Ark/Fake Provider V2 sparse candidates (17 business fields only)
→ hard envelope / identity / scope / evidence ownership validation
→ local provenance binding
→ Python shadow
→ AI-first normalization / comparison / resolution
→ canonical 17
→ DictionaryValidator
→ MaterialMatcher
→ local line + matcher code/score = fixed 20 fields
→ exactly five JSON atomic publication
→ Review / readable evidence
→ optional immutable local Revision
```

### Recovery

```text
AI technical failure
→ retry allowed missing/recoverable work
or
→ create an independent Standard Job from the trusted original upload

The original AI Job never mutates into Standard.
```

## 5. Standard 最终 E2E

`tests/web/test_standard_reprocess.py::test_reprocess_creates_independent_standard_job_from_original_upload` 使用 synthetic workbook bytes、Fake parser 与 Fake matcher 完整执行：

```text
create Standard child
→ queued
→ existing Standard dispatch
→ parser output
→ dictionary/match output adapters
→ ZIP bundle
→ completed
```

实际证明：

- `parse_mode = effective_parse_mode = standard`；
- 新 Job 使用原始上传字节和相同 source SHA；
- 五类角色完整；
- official record 按固定 20 字段构造；
- 行号来自本地 Standard 结果；
- 物料编码/相似分数来自 matcher 边界；
- whole-order AI calls、HTTP、Token 均为 0；
- Standard 不获得 AI whole-order Review/Revision。

限制：Windows embedding worker 的 transient exit retry 测试仍稳定失败，因此 Standard 核心功能已存在，但 release 可靠性不能判 PASS。

## 6. AI Enhanced 本地明确结构 E2E

使用仓库 `_single_workbook_bytes()`、`FakeV2CandidateProvider`、`FakeDictionaryValidator`、`FakeMaterialMatcher` 执行真实 `JobService` 链路：

- 本地 structure 明确，layout call 为 0；
- AI extraction logical call 为 1；
- AI candidate 为业务主值；
- Python 只进入 comparison/fallback；
- review count 为 17、高风险 review count 为 5，但 Job 仍为 `completed`；
- dictionary 与 matcher 各调用 1 次；
- 五类角色恰好 5 个；
- official result 恰好 20 字段，`相似分数`为 float；
- comparison/review/evidence 只在 `parse_diagnostics.ai_enhanced`，未进入 official result。

## 7. AI Enhanced multi-sheet E2E

D4A-3D 类型 synthetic fixture 与 `tests/ai_full_order/test_v2_multi_sheet_structure.py` 证明：

```text
s1 confirmed order records
+ s2 unresolved auxiliary candidate
→ one bounded Fake Layout decision
→ same-sheet local candidate validation
→ local binder/apply
→ s1 records preserved
→ s2 excluded as auxiliary
→ extraction units
→ downstream
→ five artifacts
```

- 已知 s1 记录不丢失；
- s2 不创建假订单；
- unknown/cross-sheet candidate、missing/duplicate decision、identity tampering 均 hard reject；
- 本地明确结构仍保持 layout call 0；
- prior D4A-3E 已用 1 次真实 Ark layout / 1 次 HTTP 验证 Layout Contract V2，total tokens 1265；本 Gate 未重复真实调用。

## 8. AI-first 字段矩阵与规范化

| 场景 | 正式值 | Review | Technical ready |
|---|---|---|---|
| AI valid + Python same | AI | 否或 equivalent | 是 |
| AI valid + Python different | AI | 是 | 是 |
| AI only | AI | 按政策提示 | 是 |
| AI missing + Python reliable | Python fallback | 是，local rule fill | 是 |
| both missing | 空字符串 | 是 | 是 |
| bound content issue + Python | Python fallback | technical review | 是 |
| bound content issue + no Python | 空字符串 | technical review | 是 |
| unknown/cross-scope/wrong-target evidence | 无正式值 | 不适用 | 否，hard failure |

规范化回归通过：

- `美元 → USD`；
- `10.0 → 10`；
- 确定完整日期转为 `YYYY-MM-DD`；
- normalization 后 `selected_source` 仍为 AI，不伪装成 Python；
- 客户简称等不确定等价不自动合并；
-备注只做安全、lossless 的格式整理，不允许语义扩写。

## 9. 五类正式结果合同

成功路径始终只有：

1. `official_result`
2. `parse_diagnostics`
3. `dictionary_validation`
4. `material_candidates`
5. `material_summary`

浏览器 harness 的 completed AI Job 实际读取结果：

- artifact role count：5；
- official record field count：20；
- `行号 = "1"`；
- `物料编码 = "MAT-001"`，来自 Fake matcher；
- `相似分数 = 0.75`，类型 float；
- `parse_diagnostics.ai_enhanced.field_decisions[*].fields[*]` 含 comparison/review/evidence 白名单字段；
- official result 不含 model、Token、cache、comparison、review、evidence、revision metadata；
- publication failure tests 保持旧 CURRENT，不留下半套结果；
- 没有第六类业务 JSON。

## 10. Review 最终浏览器 E2E

使用真实 Microsoft Edge（Playwright CLI，`--browser msedge --headed`）连接 loopback 应用，完成：

- 页面标题为“AI整单解析完成”；
- 显示 17 个待复核、5 个高风险待复核、8 个本地规则补全；
- 五类结果保持完整可预览/下载；
- “AI 与本地规则对照”显示 formal、AI、Python、当前来源和中文 comparison；
- 点击“查看来源位置”实际展开 bounded evidence：Sheet、单元格和局部来源内容；
- Review 没有把 Job 变为 failure/awaiting，也没有禁用五类结果。

## 11. Revision 最终 E2E

同一 Edge 会话实际执行：

1. 初始结果为第 1 版；
2. 对“客户”点击“使用本地规则”，生成第 2 版；
3. 对“币种”执行手动修改为 `CNY`，生成第 3 版；
4. 刷新 result route 后仍显示“当前结果：第 3 版”；
5. 切换“全部”筛选后可见 `CNY`；
6. 五类结果仍完整。

定向测试继续证明：

- INITIAL 永远保留 revision 0；
- CURRENT 原子推进；
- parent chain 与 history 完整；
-旧 revision 五文件 SHA 不变；
- `comparison_status` 保留原始解析事实，`review_status` 独立变化；
- stale expected CURRENT 被拒绝；
- duplicate operation 幂等复用；
- matcher/publication failure 保持旧 CURRENT；
- Revision 重跑 dictionary + matcher，但 Ark/HTTP/Token delta 为 0；
-用户不能修改行号、物料编码或相似分数。

## 12. 独立 Standard reprocess E2E

Edge 中从 `AI_V2_STRUCTURE_UNRESOLVED` synthetic awaiting Job 单击“使用标准解析重新处理”：

- 无第二确认；
- route 从原 AI Job 跳到新 Job progress；
- 新 Job ID 不同；
- child `parse_mode = effective_parse_mode = standard`；
- source SHA 与原上传一致；
- child AI calls = 0，Token = 0；
- original 仍为 `awaiting_user_decision`；
- original `parse_mode/effective_parse_mode` 仍为 `ai_enhanced`；
- original Token 仍为 12，错误与 artifacts 未被修改；
- Standard progress 页面不显示 AI whole-order Review controls。

静态搜索 `src/`：

```text
fallback_to_standard = 0
_confirmed_fallback_update = 0
data-ai-action="fallback" = 0
action === "fallback" = 0
```

历史 same-Job fallback 只保留兼容 reader，不存在新写路径。

## 13. 历史兼容

定向回归覆盖并通过：

- Legacy V1；
- old V2 without comparison；
- old V2 without evidence display；
- historical fallback Job；
- old extraction-only CURRENT；
- pre-revision V2 bundle；
- old completed Job。

这些对象可以安全读取，不 crash、不伪造 comparison/revision、不强制迁移。旧任务不会自动获得所有新能力。

## 14. Progress、Browser 与 Desktop smoke

### AI Progress

Edge 实际状态：

| backend stage | 当前阶段 | 右侧五阶段 |
|---|---|---|
| `structure_resolution` | 正在确认表格结构 | 文件读取进行中，其余等待 |
| `ai_extraction` | 正在提取订单候选字段 | 文件读取完成，字段提取进行中 |
| `dictionary_validation` | 正在验证业务字段 | 前两项完成，字典进行中 |
| `material_matching` | 正在匹配参考物料 | 前三项完成，物料进行中 |
| `publication` | 正在生成结果 | 前四项完成，结果生成进行中 |
| `completed` | 解析完成 | 五项全部完成 |

### 其他浏览器 smoke

- Upload：Standard 与“AI整单解析”两个 radio 均存在；
- Help：三入口和三大内容均存在；
- History：可以加载 synthetic Job 列表；
- 900×800 result viewport：document scroll width = 900，无横向溢出；
- Review/Revision/reprocess route 均未错误跳转。

### Desktop

- `tests/desktop` 独立新进程：`27 passed`；
- Desktop launcher 使用 `edgechromium`、本地动态 URL、单实例锁和有界 server lifecycle；
-桌面快捷方式实际存在：`订单解析助手.lnk`；
- target：项目 `.venv\Scripts\pythonw.exe`；
- arguments：`-m bedding_order_parser.desktop`；
- working directory：项目根目录；
-本 Gate 未重新打包发行版。

## 15. Help 与用户文案审计

未发现主 UI/Help 仍宣称：

- same-Job fallback；
-高风险冲突必然失败；
- AI 结果必须由 Python 批准。

发现一项用户文案不准确：Help 写有“导出 Excel / ZIP：处理完成后按需要导出订单结果或完整结果包”，但当前 Excel 按钮仅提示“下一阶段开放”，AI Enhanced 也没有 ZIP。这是 documentation/UI release issue，归入 non-blocking backlog；本 Gate 未修改。

## 16. Excel / ZIP 当前真实状态

| 模式 | Excel | ZIP | 五类单文件 | Revision CURRENT-aware |
|---|---|---|---|---|
| Standard | 未实现，按钮为占位 | 已实现，默认五类 ZIP | 已实现 | 不适用 |
| AI Enhanced | 未实现，按钮为占位 | 未生成 | 已实现，可预览/下载 | 是，五类预览/下载读取最新 CURRENT |

冻结 scope 的 mandatory contract 是五类正式结果预览/下载，而不是 AI Excel/ZIP，因此这项缺口本身不是 release blocker；Help 文案应在最终修复 Gate 一并校正或降级描述。

## 17. Material / Vector 状态

- MaterialMatcher / TopK 适配与候选语义存在；
-材料测试在排除 embedding worker 与 synthetic FAISS 文件后：`44 passed`；
-标准解析、字典、Excel、extraction、normalization、pipeline、serialization：`154 passed`；
-完整 pytest 对 synthetic vectors 执行了 FAISS 单元测试；未加载真实业务索引；
-未启动真实 BGE-M3；
-未读取真实物料库；
-发现 Windows embedding worker retry/exit confirmation release blocker，见第 22 节。

## 18. 安全最终审计

公开 Job/API/Review/Revision 响应未发现暴露：

- API Key / Authorization；
-完整 Prompt；
- raw Provider request/response；
- CoT；
-本机绝对路径；
-完整 cache identity；
-无必要的完整订单正文。

Review evidence 是 bounded human-readable display，只展示允许的 Sheet、cell/range 和局部来源文本。Revision API 只接受固定 action、record identity、field name、expected CURRENT 和 manual value；禁止系统字段。Standard reprocess 只读取服务端可信原始上传，不接受客户端 path。

Hard safety 回归继续通过：invalid envelope、extra/forbidden/duplicate field、unknown evidence、cross-scope evidence、target/record/source identity mismatch 均不能进入 downstream 或五类发布。

## 19. Provider / Token 语义

成功路径和 multi-sheet layout delta 语义通过：

- logical calls、layout calls、extract calls、HTTP attempts 均按 Job operation delta 记录；
-旧 Provider session cumulative Token 不进入新 Job；
- D4A-3E 真实单次 Layout 为 `1 logical / 1 HTTP / 1265 total tokens`。

失败路径存在 blocker：`strict_schema_failure` 的 FakeTransport 返回 usage `11 / 7 / 18`，但 `JobService._pause_ai_job()` 最终保存 `0 / 0 / 0`。`tests/ai_full_order/test_acceptance_diagnostics.py::test_strict_response_failure_forms_schema_summary_before_cleanup` 在独立进程稳定失败。安全 request ID 和 failure stage 仍保留，但失败调用成本口径不正确。

## 20. 测试执行结果

### 静态检查

| 命令 | 结果 |
|---|---|
| `python -m compileall -q src tests` | PASS |
| `node --check src/bedding_order_parser/web/static/app.js` | PASS |
| `git diff --check`（报告前） | PASS |

Ruff/Black 未作为当前环境的项目强制工具安装，本 Gate 未新增依赖。

### 完整最大安全 pytest

运行前清空真实授权和密钥环境变量；两份 Ark real acceptance 文件的 pytest 用例均为 FakeTransport，真实入口只在显式 `--real` main 中，未执行。

```text
collected: 669
passed: 659
skipped: 0
failed: 10
excluded real/manual pytest nodes: 0
manual real entrypoints not invoked: 2
duration: 98.04s
```

失败分布：

- 1：strict response failure usage 18 被记录为 0；
- 3：Desktop “faiss 尚未加载”断言受全套先前 synthetic FAISS 测试顺序污染；新进程 3/3 通过；
- 5：Windows embedding worker；独立重跑后 14/16 通过，2 项 retry/exit confirmation 稳定失败；
- 1：AI disabled 的产品文案已改为“尚未在本机启用”，测试仍硬编码旧“当前不能启动任务”。

### 定向复验

| Suite | 结果 |
|---|---|
| AI full-order（除单独诊断文件） | `197 passed` |
| Web（仅 deselect 已确认 stale 文案断言） | `134 passed, 1 deselected` |
| Desktop 独立新进程 | `27 passed` |
| Standard parser/dictionary/excel/extraction/normalization/pipeline/serialization | `154 passed` |
| Materials（不含 embedding worker 与 synthetic FAISS 文件） | `44 passed` |
| strict usage failure 单独重跑 | `1 failed` |
| embedding worker 文件单独重跑 | `14 passed, 2 failed` |
| stale AI-not-ready 文案单独重跑 | `1 failed` |

## 21. Release Checklist

| 项目 | 结论 | 证据 |
|---|---|---|
| Standard core | **FAIL** | 主链通过，但 embedding worker retry 可靠性未全绿 |
| AI Enhanced core | **FAIL** | 成功主链通过，但失败响应 Token 遥测不正确 |
| multi-sheet structure | PASS | Fake 全链 + prior real Ark Layout V2 |
| AI-first | PASS | AI/Python matrix 与 normalization 回归 |
| evidence/provenance | PASS | ownership hard；content issue 可 fallback/review |
| technical safety | PASS | hard gate regression |
| five artifacts | PASS | exactly five + atomic CURRENT |
| Review | PASS | Edge evidence interaction |
| Revision | PASS | Edge 3 revisions + immutability tests |
| CURRENT/immutability | PASS | stale/idempotency/failure injection |
| Standard independent reprocess | PASS | Edge + service E2E |
| progress UX | PASS | Edge 6-stage observations |
| legacy compatibility | PASS | V1/old V2/historical fallback tests |
| API/security | PASS | whitelist/path/security tests |
| browser UX | PASS | Edge headed E2E + 900px viewport |
| desktop smoke | PASS | 27 passed + shortcut identity |
| regression tests | **FAIL** | 669 中 10 failed |
| workspace hygiene | PASS |只有报告和既有 7 份未跟踪文档 |

## 22. Release blockers

### Blocker 1：AI 失败调用 Token 遥测丢失

- 位置：`web/services.py::_pause_ai_job()` 与 AIEnhancedJobPause usage 传播链；
-表现：Transport 已得到 usage，strict schema 失败后 Job token summary 归零；
-影响：失败任务的 Token/成本与安全摘要不可信；
-不得通过删除旧 D2B 诊断断言处理。

### Blocker 2：Windows embedding worker 退出确认与 retry 不稳定

- 位置：`materials/query_embedding_runner.py::_failure_diagnostics()`、`_process_is_alive()`、`_is_retryable_pre_encode_exit()`；
-表现：worker 已返回 process code 3，但 `worker_exit_confirmed` 仍可能为 false，导致预编码 transient exit 不重试；全套压力下还出现 exact-PID terminate WinError 0；
-影响：Standard 物料匹配的隔离 worker 在 transient/timeout 场景下恢复不可靠。

### Blocker 3：全套测试不具备稳定的 release-gate 语义

- Desktop lazy-import tests 依赖全局 `sys.modules` 尚未被其他测试污染；
- AI disabled 测试仍硬编码旧文案；
-完整 suite 因顺序/陈旧断言额外产生 4 个非产品失败；
-影响：当前无法得到可信的全绿 release baseline。

Release blocker 数量：**3**。

## 23. Non-blocking backlog

| 项目 | 分类 | 说明 |
|---|---|---|
| Revision 大订单全量 downstream 性能 | 未来优化 | 当前每次修订重跑本地下游，正确但可能较慢 |
| 多进程 revision writer lock | 已知设计限制 | 当前 optimistic concurrency/atomic CURRENT 已安全，跨进程吞吐可继续增强 |
| 大量 Review 分页/折叠 | 可接受 backlog | 当前可用，超大订单浏览效率可优化 |
| Revision timeline / rollback UI | 可接受 backlog | history 有数据，尚无完整回滚界面 |
| AI/Standard Excel 与 AI ZIP | 可接受 backlog | Standard ZIP 已有；Excel 和 AI ZIP 不在当前 frozen mandatory scope |
| Help 导出文案与实际能力不完全一致 | documentation/UI issue | 应与现有导出能力对齐 |
| 无本地 order candidate 的复杂 Sheet | 已知设计限制 | 安全失败优于模型凭空创建 identity |
| 模型能力导致字段漏提取 | 已知设计限制 | 由 Python fallback、both-missing review 和人工 Revision 承接 |

Non-blocking backlog 数量：**8**。

## 24. Frozen business rules

- AI Enhanced 中 AI 是 17 个业务字段的主判断；
- Python 是 comparison / fallback，不是 AI 的裁判；
-业务 disagreement 产生 review，不阻断技术发布；
- identity/scope/provenance ownership failure 继续 hard block；
-行号只能本地生成；
-物料编码和相似分数只能由 MaterialMatcher 生成；
-正式业务结果固定 20 字段；
-正式业务产物恰好五类；
-用户可以保留 AI、改用 Python、手动修改；
-用户不能直接修改行号、物料编码、相似分数；
- Revision 不重新调用 Ark；
- INITIAL 永远保留，CURRENT 原子切换；
- Standard reprocess 创建新 Job；
-原 AI Job 永远不被改成 Standard。

## 25. 本项目形成的核心工程能力

- 结构化 Excel preprocessing：把稀疏单元格、合并锚点、隐藏内容和多层表头转成可追踪几何证据。
- LLM strict function calling：Ark Responses API 只接受冻结 Schema 和单目标输入。
- AI/Python 双通道：AI 主解析，Python 提供独立对照和安全补空。
- provenance/evidence：模型候选必须绑定本地 evidence identity，内容问题与 ownership failure 分层处理。
- cache identity：合同、Prompt、preprocessor、provenance、field policy、normalization、comparison 版本共同隔离缓存。
- single-flight/reliability：同 identity 有界协调、状态持久化、cache replay 和中断恢复。
- atomic publication：五类结果 staging 后由单一 CURRENT 原子切换，全有或全无。
- optimistic concurrency：Revision 用 expected CURRENT 防止 stale writer 覆盖。
- immutable revision：Initial 和历史 bundle 不变，用户选择只生成新的本地版本。
- browser behavior testing：真实 Edge、Node fake DOM 和 loopback server 共同覆盖交互与 route。
-向量/TopK 物料匹配：AI 不生成 ERP 编码，候选与参考分数由受控 matcher 产生。

## 26. 真实调用与数据边界

本 Gate：

```text
真实 Ark calls = 0
真实 external HTTP = 0
真实 PI = 0
真实字典 = 0
真实物料库 = 0
真实 BGE-M3 = 0
真实生产 FAISS/index calls = 0
```

完整 pytest 执行了 synthetic FAISS library unit operations；未加载生产索引、真实物料或 BGE-M3。浏览器只访问 `127.0.0.1` loopback。临时 harness、synthetic workbook、Job state 和 Playwright 输出均已清理。

## 27. Minimal final fix Gate

只建议一个后续 Gate：

```text
Gate 4D-D4A-6F：Release Blocker Cleanup 与全绿复验
```

唯一范围：

1. 修复 AI pause/failure 路径的 per-Job usage delta 传播；
2. 修复 Windows embedding worker 已退出 PID 的稳定确认、retry 分类和有界终止；
3. 将 Desktop lazy-import 测试改为隔离进程或基线差分，更新 AI disabled 测试为稳定错误码/当前文案合同；
4. 修正 Help 中与实际 Excel/ZIP 能力冲突的一句文案；
5. 重新运行 669 项完整安全 pytest、Edge smoke、compileall、node check、git diff check。

不得扩展到新功能、合同重构、新 UI、真实 Ark 或真实业务数据。只有完整安全 suite 全绿后，才重新签署 `READY TO CLOSE`。

## 28. Project Closure Decision

```text
PROJECT STATUS:
NOT READY TO CLOSE

RELEASE STATUS:
RELEASE BLOCKED

NEXT DEVELOPMENT:
One minimal Gate required: Gate 4D-D4A-6F
```

核心产品架构已经完成，剩余工作不再是新产品路线，而是一次窄范围 release blocker cleanup。当前不能关闭项目；完成 D4A-6F 并取得全绿证据后即可重新进行最终签署。

## 29. 最终工作区

本 Gate 只新增本报告。报告提交时只显式暂存：

```text
docs/reports/GATE_4D_D4A6_FINAL_INTEGRATION_ACCEPTANCE_AND_PROJECT_CLOSEOUT.md
```

七份既有未跟踪交接/审计文档保持原状，不在本 Gate 提交范围内。
