# Gate 4D-D4A-0：AI 整单解析 AI-first 架构重构只读审计与实施蓝图

## 1. 审计结论

本 Gate 是只读架构审计。除本报告外，未修改生产代码、测试、Prompt、Contract、UI、配置或数据；未运行 Job；未调用 Ark、网络、真实 PI、真实字典、真实物料库、BGE-M3 或 FAISS；原则上未运行测试，因为本轮目标是核对代码事实和形成实施蓝图。

结论：当前 Contract V2 的失败并非由 Ark function calling、稀疏候选 envelope、单目标 extraction unit、provenance binder、缓存恢复或五类原子发布的基础设计造成。主要问题集中在 `field_policy.py` 把 Python shadow 设为事实权威，以及 `orchestration.py`、`reliability_v2.py`、`ai_full_order_service.py` 把这种业务差异逐层升级为 batch isolation、`awaiting_user_decision` 和“无五类结果”。AI-first 重构应替换字段选择政策并调整其后的 ready/Job 映射，同时保留技术合同、证据所属关系、缓存隔离、恢复和发布事务。

新产品合同与当前根目录 `AGENTS.md` 中“AI 与 Python 的高风险字段冲突必须阻止发布”存在明确冲突。后续 D4A-1 开始前必须先把这条长期规则改成“业务差异进入 review，不因差异阻断；技术完整性错误仍阻断”，否则实施任务会同时收到两套相反合同。

## 2. 当前仓库基线

| 项目 | 实际值 |
|---|---|
| 分支 | `master` |
| 起始完整 HEAD | `06d356d324ba1ab6dd929cfbc968e4d66f5391c9` |
| 起始短 HEAD | `06d356d` |
| HEAD 提交 | `fix: keep help navigation within help page` |
| 最新 AI 结构修复 | `fcdd05c fix: align ai v2 structure manifests and record geometry` |
| 最新 AI 结构修复报告 | `767e9ea docs: report ai v2 structure path fix` |
| 报告提交 | 本报告单独提交，提交信息为 `docs: audit ai-first full-order architecture` |

起始工作区只有以下既有未跟踪文档，本 Gate 未读取无关正文、未覆盖、未暂存、未删除：

```text
?? CODEX_GPT_FULL_PROJECT_HANDOFF_2026-08-05.md
?? CODEX_HANDOFF_AND_RECOVERY_2026-07-30.md
?? CODEX_RECOVERY_AUDIT_ROUND_1_REPORT_2026-08-01.md
?? docs/reports/AI_FULL_ORDER_CONTRACT_V2_PREIMPLEMENTATION_READONLY_AUDIT_REPORT_2026-08-05.md
?? docs/reports/ARCHITECTURE_REVIEW_AI_FULL_ORDER_CONTRACT_V2_2026-08-03.md
?? docs/reports/GATE_4D_C2_EXECUTION_HANDOFF_STATUS_2026-08-02.md
```

最近 12 个提交从新到旧为：

```text
06d356d fix: keep help navigation within help page
fb8586d feat: improve help center content
767e9ea docs: report ai v2 structure path fix
fcdd05c fix: align ai v2 structure manifests and record geometry
34f43d7 docs: diagnose real order structure failure
96fe952 docs: report single real ark v2 acceptance
dba76fc test: stabilize ark v2 synthetic fixture
4083695 test: add bounded ark v2 acceptance harness
e87486b docs: report desktop shortcut and v2 composition
80aa08a fix: align desktop shortcut runtime with ai v2
ac5e11d docs: report ai full-order v2 desktop ui enablement
e687612 feat: enable ai full-order v2 desktop ui
```

## 3. 已验证事实与审计依据

- `GATE_4D_D3C_ARK_V2_SINGLE_REAL_ACCEPTANCE_REPORT.md` 证明：人工合成单记录通过正式桌面 `JobService`、真实 Ark V2 function call、provenance、Python shadow、字段政策、可靠性层及五类发布，真实协议边界可用。
- `GATE_4D_D3D1_REAL_ORDER_STRUCTURE_READONLY_DIAGNOSTIC_REPORT.md` 证明：真实订单曾在 Ark 调用前因本地结构身份不一致失败，调用数为 0；这不是字段裁决失败。
- `GATE_4D_D3D2_V2_STRUCTURE_PATH_OFFLINE_FIX_REPORT.md` 及当前代码证明：标准 geometry 已用于 V2 structure manifest 和 extraction unit，对结构明确订单不调用 layout AI；显式第二订单表或无法映射的坐标继续保持 ambiguous。
- D3B-1 至 D3B-2E 已建立 V2 稀疏合同、单目标 extraction unit、provenance binder、版本化缓存、跨实例 single-flight、恢复、五类原子 bundle、桌面 Job 与 UI。重构应利用这些已验证资产。

## 4. 当前 AI 整单完整执行链

```text
上传并创建 ai_enhanced Job
  services.py::JobService.create_job()（约 238）
  -> services.py::_run_job()（约 1047，按 effective_parse_mode 分发）
  -> services.py::_run_ai_enhanced_job()（约 1135）
  -> ai_full_order_service.py::run_ai_enhanced_v2_job()（261）

本地预处理与结构
  preprocessing.py::preprocess_workbook()（206）
  -> standard_geometry.py 的标准结构映射
  -> orchestration.py::build_v2_extraction_units()（228）
  -> 结构明确：直接进入 extract；ambiguous：Provider.resolve_structure()

本地对照与 AI 提取
  python_shadow.py::build_deterministic_python_shadow()（33）
  -> reliability_v2.py::V2ReliableOrchestrator.run()（427）
  -> volcengine_ark.py::VolcengineArkFullOrderProvider.extract_v2()（203）
  -> Ark function `submit_bedding_order_candidates_v2`（常量在 34）
  -> contracts.py::validate_full_order_v2_output()（557）

证据与字段决策
  provenance.py::bind_v2_candidates()（108）
  -> 本地 target / identity / scope / evidence 绑定
  -> field_policy.py::resolve_v2_record()（111）
  -> field_policy.py::_resolve_field()（159）
  -> orchestration.py::validate_v2_accepted_ai_provenance()（464）

可靠性与批次门
  reliability_v2.py::_revalidate_output()（822）
  -> unit 原子状态与缓存
  -> orchestration.py::aggregate_v2_batch()（420）
  -> reliability disposition：EXECUTED/CACHED 或 ISOLATED/INTERRUPTED/IN_PROGRESS

下游与发布
  downstream.py::publish_ready_v2_batch()（107）
  -> _require_v2_ready()（195）
  -> adapt_v2_records_for_downstream()（151）
  -> DictionaryValidator
  -> MaterialMatcher
  -> 本地行号 + 17 字段 + 匹配层编码/分数 = 20 字段
  -> 五类 payload 严格校验
  -> _publish_bundle()（429）：不可变 bundle + 原子 CURRENT

Job 与 UI
  services.py::_complete_ai_job()（约 1333）或 _pause_ai_job()（约 1258）
  -> app.js::renderProgress()（485）
  -> completed：renderResult()（556）
  -> awaiting_user_decision：renderAwaitingDecision()（658）
```

可能 hard stop 的正确节点：结构无法安全形成 extraction unit；V2 request/output envelope 错误；target/record/scope/evidence 所属关系错误；Provider/Transport 异常；缓存身份或状态损坏；正式 20 字段或五类 Schema 无法构造；字典/匹配端口失败；原子发布失败。AI/Python 业务值不同不应再属于 hard stop。

## 5. 完整阻断 Gate Matrix

分类仅使用本轮规定值。

| # | 文件与函数（约行） | 当前触发条件 | 当前行为/错误或状态 | 阻断范围 | 新分类 | 建议新行为 |
|---|---|---|---|---|---|---|
| 1 | `preprocessing.py::preprocess_workbook` 206 | 标准 geometry 无法稳定映射、显式第二订单表等 | `structure_status=ambiguous` | 暂停提取路径 | `KEEP_HARD_BLOCK` | 继续要求安全 extraction unit；可调用 layout AI，但不得猜身份 |
| 2 | `orchestration.py::build_v2_extraction_units` 228 | 记录、scope、evidence 或 manifest 无法形成唯一单目标单元 | 抛出结构/合同错误 | unit/batch/downstream/发布 | `KEEP_HARD_BLOCK` | 原样保留 single-target 与稳定身份 |
| 3 | `contracts.py::validate_full_order_v2_request` 516 | request target/catalog/SHA/scope/sheet 不一致 | `FullOrderContractError` | unit/batch/downstream/发布 | `KEEP_HARD_BLOCK` | 原样保留；这些值必须本地产生 |
| 4 | `volcengine_ark.py::extract_v2` 203 | Transport、HTTP、响应形态或本地 Provider metadata 错误 | transient/hard Provider 错误 | 当前 unit/batch | `KEEP_HARD_BLOCK` | 保留错误分类、有限重试和安全遥测 |
| 5 | `contracts.py::validate_full_order_v2_output` 557 | 顶层额外字段、候选额外字段、错误类型、未知/禁止 field_name、重复 field_name/evidence | 严格合同错误 | unit/batch/downstream/发布 | `KEEP_HARD_BLOCK` | 不放宽 V2 envelope 和字段白名单 |
| 6 | `provenance.py::_validate_target` 200 | 输出目标与本地 record/source/scope/sheet/row 不符 | `V2ProvenanceError` | unit/batch/downstream/发布 | `KEEP_HARD_BLOCK` | 身份由本地绑定，AI 不回显或决定身份 |
| 7 | `provenance.py::_bind_evidence_reference` 250 | evidence ID 不存在、跨 scope、不属于 target | `V2ProvenanceError` | unit/batch/downstream/发布 | `KEEP_HARD_BLOCK` | 原样保留证据所属关系 |
| 8 | `provenance.py::_candidate_issue` 288 | direct value 不能在证据中按当前空白规范找到；semantic/summary quote 缺失或不可定位 | `BoundCandidate(validation_status=ISSUE)` | 当前只隔离字段；高风险可能升级 batch | `NEEDS_DESIGN` | evidence 所属错误仍 hard；内容不可追溯时该 AI candidate 不可直接成为正式值，但可 Python fill/空值 + 技术 review，不应机械整批失败 |
| 9 | `field_policy.py::_allowed_interpretations` 276 | 高风险只许 direct；描述只许 direct/semantic；备注只许 direct/source_summary | AI 候选被 policy rejection | 字段；高风险可 batch | `CONVERT_TO_REVIEW` | 保留字段语义政策作风险标签，不因合法、可绑定的 semantic 候选机械否决整批 |
| 10 | `field_policy.py::_business_constraint_error` 349 | 数量不是数字字符串、日期不是 ISO、空字符串 | AI 候选被拒，Python 优先或高风险阻断 | 字段/高风险 batch | `CONVERT_TO_NORMALIZATION` | 确定性解析为 normalized；保留 AI display；不可确定时采用 AI display 并标 review，不猜等价 |
| 11 | `field_policy.py::_resolve_field` 169 | AI 缺失、Python 有直接证据 | `PYTHON_PRESERVED_AI_MISSING` | 不阻断 | `KEEP_NON_BLOCKING` | 改名/语义为 `python_fallback` + `local_rule_fill`，明确非 AI 值 |
| 12 | `field_policy.py::_resolve_field` 175 | 双方为空且字段属于高风险 | `HIGH_RISK_MISSING`、`blocking=True` | record/batch/downstream/发布 | `CONVERT_TO_REVIEW` | 正式值为空，`both_missing` + review；只要 20 字段可构造就发布 |
| 13 | `field_policy.py::_resolve_field` 180-211 | AI candidate issue、interpretation 或格式政策失败 | 有 Python 则 Python preserved；无 Python 则 AI isolated；高风险 blocking | 字段/高风险 batch | `NEEDS_DESIGN` | 分开“技术上不可采信的 candidate”和“业务表现差异”；前者 Python fill/空 + review，后者 AI 主值 |
| 14 | `field_policy.py::_resolve_field` 227 | AI/Python 按空白规范相同 | `selected_source=both`，正式 value 实际取 Python | 不阻断但 Python 仍为权威 | `REMOVE_LEGACY_POLICY` | 正式取 AI display/normalized；comparison=`agree` |
| 15 | `field_policy.py::_resolve_field` 240 | 高风险 AI/Python direct 值不同 | 正式值清空，`HIGH_RISK_DIRECT_CONFLICT`、blocking | record/batch/downstream/发布 | `CONVERT_TO_REVIEW` | 正式采用 AI；comparison=`different`；提高 review severity但继续发布 |
| 16 | `field_policy.py::_resolve_field` 253 | 普通字段 AI/Python direct 值不同 | 正式取 Python，`PYTHON_PRESERVED_ORDINARY_CONFLICT` | 不阻断但 AI 被否决 | `REMOVE_LEGACY_POLICY` | 正式采用 AI；Python 只进 comparison |
| 17 | `field_policy.py` 213 | 备注 source summary 不等于 quote | Python preserved 或 AI isolated | 字段 | `NEEDS_DESIGN` | “只整理原文”仍应保留；允许确定性去空白/标点整理，不允许扩写；失败时 review/fill，不因业务差异阻断 |
| 18 | `field_policy.py::V2CanonicalRecord.ready_for_downstream` 94 | 任一 decision.blocking | false | record/batch/downstream/发布 | `REMOVE_LEGACY_POLICY` | ready 只反映技术完整性；业务 review 单独计数 |
| 19 | `orchestration.py::aggregate_v2_batch` 431-447 | unit 缺失、hard failure、数量/身份/scope/17字段不一致 | batch isolated | batch/downstream/发布 | `KEEP_HARD_BLOCK` | 原样保留技术聚合门 |
| 20 | `orchestration.py::aggregate_v2_batch` 448 | 任一 record 非 ready | 原因 `high_risk_blocking_conflict` | batch/downstream/发布 | `CONVERT_TO_REVIEW` | 删除业务差异 gate；改为聚合 review summary，不改变 ready |
| 21 | `orchestration.py::validate_v2_accepted_ai_provenance` 464 | 被选为 AI/both 的值没有 BOUND candidate 或 quote span | policy error | batch/downstream/发布 | `KEEP_HARD_BLOCK` | 继续保证正式 AI 值有本地 provenance；需适配新 selected_source 命名 |
| 22 | `reliability_v2.py::_run_unit` 563 | Contract/Provenance/FieldPolicy/类型错误统一归 hard | `FAILED_HARD` | unit/batch/downstream/发布 | `NEEDS_DESIGN` | 拆清技术异常与业务 review；真正技术异常仍 hard，业务差异不得抛异常 |
| 23 | `reliability_v2.py::_candidate_isolated` 842 | 任一 decision.ai_isolated | 缓存终态 `candidate_isolated` | 不必阻断 batch，但语义混合 | `KEEP_WITH_SMALL_CHANGE` 不属于规定分类，故归 `NEEDS_DESIGN` | cache 记录严格验证的候选与安全 issue；review 不应被命名为失败/隔离 |
| 24 | `reliability_v2.py::_from_validated/_all_revalidated` 679/696 | 缓存重放后 policy/isolation 与旧状态不一致 | cache corruption/hard | unit/batch | `KEEP_HARD_BLOCK` | 保留重校验；提升 field policy/normalization/comparison 版本以隔离旧缓存 |
| 25 | `reliability_v2.py::run` 544 | batch 非 ready | disposition `ISOLATED` | downstream/发布 | `CONVERT_TO_REVIEW` | 只有技术非 ready 才 isolated；有 review 的技术完整 batch 仍 EXECUTED/CACHED |
| 26 | `downstream.py::_require_v2_ready` 195 | disposition、batch、units、identity 或 record blocking 不满足 | `DownstreamError` | 字典/匹配/发布 | 混合：技术条件 `KEEP_HARD_BLOCK`，record blocking `CONVERT_TO_REVIEW` | 拆除业务 blocking 条件，保留完整性门 |
| 27 | `downstream.py::adapt_v2_records_for_downstream` 151 | V2 decision 被压成纯 17 字段 | comparison 信息不进入下游对象 | 不阻断但信息丢失 | `KEEP_WITH_SMALL_CHANGE` 不属于规定分类，故归 `NEEDS_DESIGN` | 17 字段继续窄适配；comparison 另走 diagnostics，不污染正式 20 字段 |
| 28 | `downstream.py::_v2_diagnostic_payload` 284 | 当前只记录 selected source/reason/evidence/issue/blocking | 无完整 AI/Python 对照值及规范化状态 | 不阻断 | `KEEP_NON_BLOCKING` | 扩展为白名单 comparison/review 资产，禁止进入 official result |
| 29 | `downstream.py` 字典/匹配/20字段校验 | adapter 错误、matcher 类型错误、20字段缺失/额外/null | 下游错误 | 发布 | `KEEP_HARD_BLOCK` | 保留；业务字典诊断/候选状态本身不应等同技术失败 |
| 30 | `downstream.py::_validate_bundle_payloads/_publish_bundle` 413/429 | 非五类、Schema 错、写入/占用/身份冲突 | 不切 CURRENT 或保留旧 CURRENT | 五类发布 | `KEEP_HARD_BLOCK` | 原样保留全有或全无事务 |
| 31 | `ai_full_order_service.py::run_ai_enhanced_v2_job` 389 | reliability isolated/not ready；显式识别 high-risk 原因 | `AI_V2_HIGH_RISK_CONFLICT`，暂停 | Job/结果页 | `CONVERT_TO_REVIEW` | 只映射技术失败为 awaiting；review batch继续下游并 completed |
| 32 | `services.py::_pause_ai_job` 1258 | V2 pause | `awaiting_user_decision`、清空产物角色 | UI/预览/下载 | `KEEP_HARD_BLOCK` | 仅技术失败使用；业务差异不得进入此函数 |
| 33 | `services.py::_complete_ai_job` 1333 | 五类发布成功 | `completed` | 允许结果页 | `KEEP_NON_BLOCKING` | 保留 `completed`，增加 review count/summary；不建议新建 `completed_with_review` |
| 34 | `app.js::renderResult` 556 | 仅 `completed` 且五角色完整 | 展示/下载 | UI | `KEEP_NON_BLOCKING` | 保持；增加 review 面板和修订操作，不影响下载初始 AI 结果 |
| 35 | `app.js::renderAwaitingDecision` 658 | Job awaiting | 重试/同 Job 回退/保留失败 | UI | `REMOVE_LEGACY_POLICY` | awaiting 只处理技术失败；“标准解析重新处理”创建新 standard Job |

## 6. Hard safety 与 business policy 分界

### 必须继续 hard block

1. V2 request/output 不是合法严格 envelope，含额外字段、错误类型、重复字段或禁止字段。
2. 本地 source SHA、extraction unit、record identity、scope、sheet、source row 无法唯一绑定。
3. evidence ID 不存在、跨 scope、不属于 target，或被选为正式 AI 值却没有本地可验证 provenance。
4. 结构无法形成安全、稳定、单目标 extraction unit。
5. Provider/Transport、usage/metadata、缓存身份、状态机或 single-flight 出现技术损坏。
6. 17 字段 canonical 对象、正式行号、匹配层编码/float 分数或固定 20 字段无法构造。
7. 字典/物料端口发生技术异常，或五类 payload/原子发布失败。

### 必须转换为 review 或 normalization

- AI 与 Python 任意业务字段不同，包括现有五个高风险字段。
- 一方有值、一方为空；双方为空。
- 数量、日期、币种等存在可确定性等价表示。
- 普通字段 direct/semantic 理解差异。
- AI 候选满足技术 provenance 但不能与 Python 值机械判等。

### 需额外区分的边界

“candidate value 不能在引用 evidence 中逐字找到”不等于“evidence ID 不存在或跨 scope”。后者必须 hard block；前者应根据 interpretation 和字段政策判断：可本地确定性规范化则接受并标 normalization；可证明 semantic provenance 则接受并 review；无法证明来源则隔离该 AI candidate，使用 Python fill 或空值并标技术 review。它不应仅因字段属于高风险就把整批变成失败。

## 7. 所有旧 high-risk / Python-authority 政策位置

1. `field_policy.py:24`：`V2_HIGH_RISK_FIELDS` 固定客户、币种、业务员、数量、计划发货日期。
2. `field_policy.py:169-211`：AI 缺失、candidate issue、interpretation/格式失败时 Python preserved；无 Python 的高风险字段 blocking。
3. `field_policy.py:227-239`：双方一致仍取 Python value。
4. `field_policy.py:240-258`：高风险冲突清空并阻断；普通冲突取 Python。
5. `field_policy.py:276-281`：高风险 direct-only。
6. `field_policy.py:349-356`：数量只接受数字字符串，日期只接受 ISO。
7. `field_policy.py:94-96`：任一 blocking decision 令 record non-ready。
8. `orchestration.py:448-449`：record non-ready 被聚合成 `high_risk_blocking_conflict`。
9. `reliability_v2.py:544-549`：batch non-ready 变成 `ISOLATED`。
10. `ai_full_order_service.py:389-406`：high-risk 原因映射 `AI_V2_HIGH_RISK_CONFLICT` 并暂停。
11. `AGENTS.md`：长期规则仍冻结“高风险冲突阻止发布”，必须在实施前更新。

## 8. 规范化事实与目标建议

当前 `contracts.py::normalize_evidence_text()`（241）只压缩空白并 `strip()`；`field_policy.py::_same_value()`（359）只调用该函数。当前没有币种别名、中文数字、数字小数等价、中文日期或日期格式的确定性规范化。数量和日期反而在 `_business_constraint_error()` 中被当作拒绝门。

建议新增独立、版本化、纯本地 normalization 层，不修改 evidence 原文：

```text
FieldValueView
  display_value: str           # AI 或 Python 原始可展示值
  normalized_value: str        # 仅确定性转换；无法确定则等于 display 或留独立状态
  normalization_status: exact | normalized | not_applicable | uncertain
  normalization_rule: 固定白名单规则代码
```

第一阶段仅实现低争议规则：空白/Unicode 形式、明确币种别名、纯数字和 `.0` 等价、可无歧义解析的完整日期。客户简称/全称、买方/收货方、开单日期/发货日期、业务员昵称/姓名、行数量/订单总量不得猜测相等；应采用 AI 主值并标 `different`。

正式 20 字段中的显示/规范值需要产品决定。架构建议：对于数量、日期、币种等有既有下游格式要求的字段，正式值使用由 AI display 确定性派生的 normalized value，并在 diagnostics 保留 AI display；其 `selected_source` 仍是 AI，不能记成 Python。没有明确下游格式要求的字段保留 AI display。

## 9. AI-first resolution 目标模型

建议保留 17 字段 canonical record，但重构 decision，不让 `blocking` 表达业务冲突：

```text
AIFirstFieldDecision
  field_name
  formal_value
  ai_display_value
  ai_normalized_value
  ai_evidence_ids / quote_span
  python_display_value
  python_normalized_value
  python_evidence_ids
  comparison_status
  selected_source
  review_required
  review_severity
  reason_codes[]
  technical_candidate_status
```

选择矩阵：

| AI | Python | 正式值 | selected_source | comparison_status | 是否 review |
|---|---|---|---|---|---|
| 有有效值 | 语义一致 | AI（必要时 AI 派生 normalized） | `ai` | `agree` 或 `equivalent_after_normalization` | 否/低 |
| 有有效值 | 有值但不同 | AI | `ai` | `different` | 是；高风险提高等级但不阻断 |
| 有有效值 | 空 | AI | `ai` | `ai_only` | 可提示，不阻断 |
| 空/无候选 | 有可证明值 | Python | `python_fallback` | `python_fill` | 是，状态 `local_rule_fill` |
| 双方为空 | 空字符串 | `none` | `both_missing` | 是，不阻断 |
| AI candidate 技术不可采信 | Python 有值 | Python | `python_fallback` | `python_fill` + technical issue | 是 |
| AI candidate 技术不可采信 | Python 空 | 空字符串 | `none` | `both_missing` + technical issue | 是；是否允许发布取决于 canonical/下游可构造，而非字段名称风险 |

AI 永远不能产生正式行号、物料编码、相似分数。正式行号继续取本地 record geometry；物料编码与 float 相似分数继续只取 MaterialMatcher。

## 10. Comparison / review 正式诊断资产

当前已有数据来源：

- AI candidate、interpretation、evidence IDs、本地 quote span：`provenance.py::BoundCandidate`。
- Python shadow value、evidence IDs、是否 direct：`resolution.py::PythonFieldCandidate/PythonShadowRecord`，由 `python_shadow.py` 构造。
- 现有 field decision、reason、selected source、AI issue：`field_policy.py::V2FieldDecision`。
- 正式行号、record/source/scope/sheet/source row：`preprocessing.py::LocalRecord`、V2 target。
- 当前 parse diagnostics 入口：`downstream.py::_v2_diagnostic_payload()`。

建议 diagnostics 中每条 comparison 至少为：

```json
{
  "record_identity": "本地稳定身份",
  "line_number": "正式行号",
  "field_name": "固定17字段之一",
  "ai_display_value": "...",
  "ai_normalized_value": "...",
  "ai_evidence": ["固定 evidence ID + 本地坐标/跨度"],
  "python_display_value": "...",
  "python_normalized_value": "...",
  "python_evidence": ["固定 evidence ID"],
  "comparison_status": "agree|equivalent_after_normalization|different|ai_only|python_fill|both_missing",
  "selected_source": "ai|python_fallback|none|user_override",
  "review_required": true,
  "review_severity": "low|medium|high",
  "user_revision_status": "unreviewed|keep_ai|use_python|manual_override"
}
```

具体 JSON Schema 留给实施 Gate；禁止把 comparison、模型、Token、缓存或证据放入 official result。业务差异进入 `parse_diagnostics`，五类角色不增加第六类。

## 11. 五类发布与 Job 终态建议

推荐继续使用 `completed`，并增加：

```text
review_required_count
high_review_count
comparison_summary
has_unreviewed_differences
result_revision
```

原因：当前 `app.js::renderProgress()` 和 `renderResult()`、Artifact API、历史列表、Job 终态保护及下载均以 `completed` + `has_complete_five_results` 为成熟合同。引入 `completed_with_review` 会把一个业务展示维度升级成新的任务终态，扩大到路由、历史、终态保护、导出和兼容旧 Job，收益低而回归风险高。

新发布门应是：

```text
技术完整 V2 batch
-> canonical 17（AI-first + Python fill）
-> DictionaryValidator
-> MaterialMatcher
-> 本地行号 + matcher 两字段 = 20
-> 五类严格校验
-> 原子 bundle
-> Job completed（可带 review）
```

字典验证结果和 Material TopK 仍是诊断/候选，不应反向把 Python 设成 AI 模式主解析器。物料编码与分数仍完全服从匹配层。

## 12. 用户修订与不可变发布设计

当前 `_publish_bundle()` 已采用 `<cache_key>/` 不可变 bundle 和原子 `CURRENT`，具备版本化基础；但同一 cache key 若内容不同会拒绝覆盖，当前 Job state 没有 revision，diagnostics 也没有 override lineage。

建议：

1. 保留 extraction cache key，只代表 AI 调用和合同身份，不因用户修订改变。
2. 新增本地 `revision_id`/`publication_identity`，由 extraction cache key、父 revision、规范化 override 清单、字典/匹配/发布版本确定性散列产生。
3. 初始 AI 结果为不可变 revision 0；用户选择保留 AI、改用 Python、手动输入只产生本地 override，不再次调用 Ark。
4. 根据 override 重建完整 17 字段，仅重跑受影响的本地字典/物料适配（首版可保守重跑整批本地下游），生成新的不可变 bundle，最后原子切换 CURRENT。
5. 保留 `INITIAL` 或 Job 元数据中的初始 publication identity、当前 revision、parent revision、时间和用户动作；不要覆盖旧 bundle。
6. revision metadata 进入 Job state 和 parse diagnostics，不成为第六类业务 JSON。
7. 发布失败时 CURRENT 仍指向上一完整 revision。

当前代码没有可直接复用的 revision API、override Schema 或 revision history，需要单独 Gate，不应与核心字段政策一次完成。

## 13. 废弃同 Job fallback，创建独立 standard Job

当前链路：

- `routes.py::_serve_ai_job_action()`（102）把 `fallback` 路由到 `JobService.fallback_to_standard()`。
- `services.py::fallback_to_standard()`（1101）确认后把同 Job 的 `effective_parse_mode` 改成 `standard`，清除 AI 产物，再调用 `_run_job()`。
- `services.py::_run_job()`（1047）按 `effective_parse_mode` 分发，因此原 AI Job 会运行标准路径。
- `services.py::_confirmed_fallback_update()`（1655）是唯一允许覆盖 terminal state 的特例。
- `app.js::renderAwaitingDecision()`（658）、`confirmAIFallback()`（672）、`performAIJobAction()`（684）提供“回退为标准解析”。
- `modeMeta()`（647）和 history 显示原始/有效模式及 fallback。

建议替代合同：

```text
POST /api/jobs/{ai_job_id}/ai-actions/reprocess-standard
  -> 验证用户明确确认、原 AI Job、原上传文件仍可安全读取
  -> 调用现有 create_job(..., parse_mode="standard") 创建全新 Job
  -> 记录 parent/source relationship（不含本机路径）
  -> 原 AI Job 的 parse_mode/effective_parse_mode 始终 ai_enhanced
  -> 新 standard Job 独立 start_job()
  -> API 返回新 Job ID，UI 跳转新 Job progress
```

后续删除/废弃：同 Job `fallback_to_standard()`、`_confirmed_fallback_update()` 终态特例、按 fallback 修改 `effective_parse_mode` 的执行语义、旧 fallback 按钮文案与确认框。兼容旧 Job 时仍只读显示历史 `effective_parse_mode=standard`/confirmed fallback，不再创建这种状态。原 AI Job 的调用、Token、失败、partial cache 和日志保持原样；新 standard Job 的五类结果与耗时完全独立。

## 14. 基础设施复用清单

| 组件 | 结论 | 代码证据与调整 |
|---|---|---|
| Contract V2 sparse candidate envelope | `KEEP` | `contracts.py:432-580` 已严格限制 17 字段、无额外字段、可稀疏；正适合 AI 主候选 |
| Ark function calling Provider | `KEEP` | `volcengine_ark.py:34,203-227,351-361` 已真实验收，strict、store=false、非流式、遥测安全 |
| single-target extraction units | `KEEP` | `orchestration.py:228-334` 将每次响应绑定唯一 record，降低 identity 风险 |
| standard geometry | `KEEP` | `preprocessing.py:206-318` 与 D3D-2 测试已对齐标准记录几何 |
| structure manifest | `KEEP` | D3D-2 修复后稳定；结构无法安全映射仍应 hard |
| provenance binder | `KEEP_WITH_SMALL_CHANGE` | `provenance.py:108-321` 的 ID/scope/target hard boundary 保留；candidate 内容 issue 分类需配合 normalization/review |
| V2 cache identity | `KEEP_WITH_SMALL_CHANGE` | `reliability_v2.py:95-108,238-270` 已包含合同、Schema、Prompt、预处理、context、normalization、shadow、field policy、provenance、manifest；必须 bump 新版本 |
| single-flight | `KEEP` | 文件 lease、owner token、heartbeat、bounded wait 已有跨实例测试 |
| interrupted recovery | `KEEP_WITH_SMALL_CHANGE` | validated candidate 不重调 Provider；重放时采用新版 policy/comparison，旧缓存因版本失效 |
| atomic state | `KEEP` | 唯一临时文件、fsync、replace、终态单调和损坏安全失败已覆盖 |
| five-artifact atomic publication | `KEEP_WITH_SMALL_CHANGE` | `downstream.py:413-470` 全有或全无保留；增加 publication revision identity |
| dictionary adapter | `KEEP` | 继续消费 canonical 17，不编造源值 |
| material adapter | `KEEP` | 编码/float 分数仍只由匹配层产生，算法和 TopK 不变 |
| desktop shortcut/runtime identity | `KEEP` | D3B-2E 已验证真实快捷方式运行身份和 V2 依赖组装 |
| AI UI mode selection | `KEEP_WITH_SMALL_CHANGE` | 两模式选择保留；结果页增加 comparison/revision，失败页替换同 Job fallback |
| 当前 `field_policy.py` 决策模型 | `REPLACE` | Python-authority、blocking 和格式拒绝与新产品合同冲突；可保留字段集合和数据输入接口 |
| 当前 high-risk blocking 聚合 | `REMOVE` | `record.blocking -> high_risk_blocking_conflict -> awaiting` 应删除，风险改为 review severity |
| V1 compatibility reader | `KEEP` | 旧 Job 仍需读取；不得原地放宽 V1 或反向影响 standard |

## 15. Standard 模式保护边界

AI-first 改动应限制在 `ai_full_order/field_policy.py` 及 V2 编排/可靠性/下游/Job/UI 窄接口。禁止修改标准 parser、字典规则、MaterialMatcher 算法/阈值/TopK、五类正式 Schema、Excel/ZIP 和单记录 AI Sidecar。

具体保护措施：

1. 不修改 `resolution.py` 的 V1/旧合同行为；若只为复用 `PythonShadowRecord`，优先保持类接口或以后迁到独立 shadow contract 并提供兼容导入。
2. Standard `_run_standard_job()` 路径不导入 AI-first selector；共享 downstream 只接收已经完成的 17 字段，不参与主值选择。
3. AI comparison 只进入 AI parse diagnostics 和 Job 摘要；standard 五类 JSON 内容不增加 AI 字段。
4. MaterialMatcher 继续拥有物料编码/相似分数唯一生产权。
5. 单记录 AI 复核 Sidecar 仍只由 standard 结果页用户单记录触发，与 AI 整单 Provider 保持独立响应合同。
6. 新 standard reprocess Job 直接使用现有 standard 创建/执行路径，而不是给 standard 增加 AI-first 分支。

## 16. 测试迁移矩阵

| 测试 | 当前冻结内容 | 处理 | 理由 |
|---|---|---|---|
| `test_field_policy.py::test_high_risk_direct_conflict_blocks_ready` | 高风险冲突阻断 | **改写** | 改为 AI 正式值 + high review + ready |
| `test_field_policy.py::test_high_risk_rejects_semantic_but_preserves_valid_python` | direct-only + Python authority | **改写** | 测试 semantic 风险政策，不再机械 Python 胜出 |
| `test_field_policy.py::test_high_risk_quantity_and_date_keep_existing_deterministic_format_rules` | 非数字/ISO 即拒绝 | **替换** | 测 display/normalized 和不可确定 review |
| `test_field_policy.py::test_description_semantic_is_accepted_only_when_python_direct_is_absent` | Python 有值时拒 AI semantic | **改写** | 有有效 AI semantic 时 AI 主值，Python comparison |
| `test_field_policy.py::test_ordinary_direct_conflict_is_deterministic_and_nonblocking` | 普通冲突 Python preserved | **改写** | 改为 AI 主值 + different review |
| `test_field_policy.py::test_candidate_issue_isolates_only_its_ordinary_field...` | 字段级技术隔离 | **保留并调整术语** | 继续证明坏 candidate 不扩大整批，但补 Python fill/空 + review |
| `test_v2_offline_resolution.py::test_high_risk_direct_conflict_blocks_the_batch` | batch blocking | **改写** | 改为 ready + comparison |
| `test_v2_reliability.py::test_high_risk_conflict_revalidates_from_cache_and_stays_blocked` | 缓存重放旧政策 | **改写** | 新 policy version、缓存重放仍 AI-first |
| `test_v2_downstream.py::test_nonready_high_risk_conflict_never_calls_downstream_or_publishes` | 不发布 | **改写** | 必须调用下游并完整发布五类 |
| `test_ai_full_order_jobs.py::test_high_risk_conflict_waits_without_downstream...` | awaiting | **改写** | 应 completed + review + 五角色 |
| `test_ai_full_order_jobs.py::test_fallback_requires_confirmation...` | 同 Job mode mutation | **替换** | 新 standard Job、原 AI Job 模式不变 |
| `test_gate4c2_frontend.py` fallback 文案/动作断言 | 旧 UI | **替换** | 新建 standard Job 并跳转 |
| `test_contracts.py` V2 17 字段、额外/禁止/重复/类型 | strict safety | **原样保留** | 技术合同不可放宽 |
| `test_provenance.py` unknown/cross-scope/target/quote span | evidence safety | **原样保留** | provenance 硬边界 |
| `test_v2_reliability.py` cache version、single-flight、恢复、状态单调、无敏感数据 | reliability safety | **原样保留** | 与业务值选择无关 |
| `test_v2_downstream.py` 五类/20字段/写失败/CURRENT/Windows retry | atomic publication | **原样保留并增加 revision** | 事务边界不可弱化 |
| `test_v2_structure_path.py` geometry/ambiguous/identity | structure safety | **原样保留** | 不属于 AI/Python 冲突政策 |
| `test_volcengine_ark_full_order_provider.py` strict request/response、安全 metadata | Provider safety | **原样保留** | Provider 已验证 |
| `test_ai_full_order_jobs.py::test_standard_dispatch_remains_on_existing_path` | standard 隔离 | **原样保留并扩展** | 防止 AI-first 反向渗透 |
| 单记录 Ark/Sidecar 回归 | standard 单记录 AI | **原样保留** | 两种 AI 能力必须隔离 |

未来必须新增：17 字段完整 AI-first 矩阵；币种/数量/日期 normalization；不可确定等价；AI-only/Python-fill/both-missing；高风险差异仍发布；review diagnostics 白名单；completed + review 下载；初始/修订 bundle 不可变；手动 override 不调用 Ark；修订失败不切 CURRENT；新 standard Job 关系与原 AI Job 不变；旧 fallback Job 只读兼容；standard 五类 SHA/ZIP/Sidecar 不变。

绝不能删除 unknown evidence、cross-scope、identity、forbidden field、cache corruption、atomic publication failure 等安全测试来“让新架构通过”。

## 17. 最终建议数据流

```text
Excel
  |
  v
Local Structure / Standard Record Geometry
  |  [HARD: 无法形成安全 extraction unit]
  v
Single-target Extraction Units
  |
  v
Ark V2 Sparse AI Candidates
  |  [HARD: Provider/Transport 或 V2 envelope 错误]
  v
Hard Technical Validation
  |  [HARD: forbidden/duplicate/type/identity/scope/evidence ownership]
  v
Provenance Binding
  |  [字段 issue: 内容不可追溯 -> candidate 不采信，但不按字段名扩大失败]
  v
AI Business Value Views ----+
                             |
                             v
                    Comparison Layer <---- Python Shadow
                             |
                             v
                    AI-first Resolution
                    - AI valid -> AI
                    - AI missing -> Python fill
                    - disagreement -> AI + review
                    - both missing -> empty + review
                             |
                             v
                       Canonical 17
                             |  [HARD: 无法构造固定字段/类型]
                             v
                   Dictionary Validation
                             |
                             v
                    Material Matching
                             |
                             v
          Local line + 17 + matcher code/score = Formal 20
                             |  [HARD: 20字段/五类 Schema 错误]
                             v
                 Five JSON Atomic Publication
                             |  [HARD: 写入/校验/原子切换失败]
                             v
                       Job completed
                             |
                             v
                 Result Page + Review Count
                 + AI/Python Comparison
                 + Keep AI / Use Python / Manual Override
                 + Download allowed before review
```

## 18. 分阶段实施蓝图

建议拆成 **6 个 Gate**。revision 和同 Job fallback 涉及不同持久化/迁移风险，不应塞入同一 UI Gate。

### D4A-1：AI-first resolution、normalization 与 comparison 核心

- **目标**：先更新 `AGENTS.md` 冲突规则；新增版本化 normalization/value view；替换 V2 字段决策为 AI 主值、Python fill、差异 review；不接 Job/UI。
- **主要文件**：`AGENTS.md`、`contracts.py`（仅版本/共享类型如需要）、`field_policy.py`、可能新增 `normalization.py`/`comparison.py`、相关 V2 单元测试。
- **风险**：错误区分“技术不可采信 candidate”和“业务差异”；17 字段/行号边界被误改。
- **前置依赖**：本报告；产品确认正式 20 字段使用 display 还是确定性 normalized。
- **验收**：全 17 字段矩阵；AI/Python 冲突不 blocking；Python 只补空；identity/evidence hard 测试不变；零网络。
- **建议配置**：GPT-5.6 Terra，高度推理；核心政策跨合同、证据与兼容边界，需较强推理但不需最高配置。

### D4A-2：ready gate、可靠性重校验与五类发布

- **目标**：移除业务 blocking 的 aggregate/reliability/downstream 门；升级 field policy、normalization、comparison 版本；review batch 可进入字典、匹配、20字段和五类发布。
- **主要文件**：`orchestration.py`、`reliability_v2.py`、`downstream.py`、对应缓存/恢复/发布测试。
- **风险**：旧缓存错误复用；把技术 non-ready 误放行；诊断值污染 official result。
- **前置依赖**：D4A-1 稳定 decision/comparison 对象。
- **验收**：高风险差异完整发布；未知证据等仍 hard；版本变更缓存失效；中断恢复不重复 Ark；五类 SHA/原子失败测试全过。
- **建议配置**：GPT-5.6 Terra，高度推理；可靠性和发布门耦合高。

### D4A-3：Job/API completed-with-review 语义与结果展示

- **目标**：保持 `completed`，新增 review summary/count；comparison 通过 parse diagnostics/API 白名单展示；结果页在未处理差异时仍可预览下载。
- **主要文件**：`ai_full_order_service.py`、`services.py`、`routes.py`（必要窄接口）、`app.js`、`styles.css`、Web/UI 定向测试。
- **风险**：把 review 误映射 awaiting；泄露内部 prompt/cache/provider 原文；窄窗口可用性。
- **前置依赖**：D4A-2 可发布 review batch。
- **验收**：completed + review；五角色可用；AI/Python/evidence 对照可读；standard 页面与 Sidecar 不变；浏览器交互回归。
- **建议配置**：GPT-5.6 Luna，高度推理；跨后端合同和 UI，但核心算法已冻结。

### D4A-4：用户修订与不可变 bundle revision

- **目标**：实现保留 AI/改用 Python/手动输入；不调用 Ark；重建 17、重跑本地下游、发布新 revision；保留 initial 和完整 lineage。
- **主要文件**：新增 revision 服务/合同，`downstream.py` 发布身份扩展，`services.py`/`routes.py`/`app.js`，原子发布和 UI 测试。
- **风险**：覆盖初始结果、CURRENT 指向半成品、并发修订、手动值验证、revision 与 extraction cache 混用。
- **前置依赖**：D4A-3 comparison API 稳定；产品确认手动值校验和 revision 保留策略。
- **验收**：零 Ark；初始 bundle 不变；新 revision 原子可见；失败保留旧 CURRENT；本地字典/匹配调用可计数；审计链完整。
- **建议配置**：GPT-5.6 Terra，高度推理；原子版本与状态一致性风险高。

### D4A-5：废弃同 Job fallback，独立 standard reprocess Job

- **目标**：新增基于原上传文件的 standard 子 Job；原 AI Job 模式、Token、结果/失败保持；旧 fallback Job 只读兼容；更新失败页动作。
- **主要文件**：`services.py`、`routes.py`、`app.js`、历史/Job/UI 定向测试。
- **风险**：原文件保留期、重复创建幂等、父子关系、终态迁移兼容。
- **前置依赖**：D4A-3 Job/UI 新语义；与 D4A-4 可并行但建议随后做。
- **验收**：确认后返回新 standard Job ID 并跳转；原 AI Job `effective_parse_mode` 不变；新 Job 纯 standard；旧 Job 可读；无 AI 结果混入。
- **建议配置**：GPT-5.6 Luna，中度推理；范围明确但需谨慎兼容状态。

### D4A-6：Fake 全链、真实 Ark 与真实订单分级验收

- **目标**：先离线故障矩阵，再人工合成真实 Ark，再经单独授权的小样本真实订单；验证 AI-first 输出、review、修订、下载和 standard 隔离。
- **主要文件**：验收 harness/fixtures/tests；只有真实证据明确时才做 Provider 边界最小修复；唯一报告。
- **风险**：真实数据安全、调用预算、结构与字段政策混淆、把一次成功当稳定。
- **前置依赖**：D4A-1 至 D4A-5 全部完成。
- **验收**：业务差异不阻断；技术错误仍 hard；完整五类；revision 零 Ark；标准 SHA/ZIP/Sidecar 回归；逐次安全摘要与调用计数。
- **建议配置**：GPT-5.6 Terra，高度推理；真实验收需要跨层诊断。只有出现冻结合同根本冲突或无法解释的并发/数据一致性问题才升级 Sol/极高。

## 19. 已知风险与仍需产品决定的问题

1. **正式值格式**：数量、日期、币种有确定性 normalization 时，official result 使用 normalized（架构推荐）还是 AI display；无论选择哪种，diagnostics 都应保留二者并标 selected source=AI。
2. **技术无效单字段**：AI candidate evidence 所属合法但内容不可追溯、Python 又为空时，是否允许空值发布并 review。架构建议允许，只要固定 20 字段可构造；未知/跨 scope 或身份错误仍整 unit hard。
3. **备注政策**：只允许原文整理的边界应明确到允许操作（空白、换行、标点）并版本化，禁止模型扩写。
4. **review 严重级别**：五个现有高风险字段是否继续固定，还是由字段 + 差异类型共同决定。建议只影响排序/醒目程度，不影响发布。
5. **手动 override 校验**：用户手动值是否只做类型/长度安全检查，还是也要求字典警告；建议允许保存但把字典结果显式展示，不静默改值。
6. **修订保留策略**：保存全部 revision 还是设置本地保留上限；审计要求至少永久保留 initial 和 current，不能覆盖后失去来源。
7. **standard reprocess 原文件生命周期**：AI Job 失败后原上传文件保留多久、清理前如何提示；必须保证新 Job 创建时源 SHA 一致。
8. **ambiguous layout 成功后的继续策略**：当前服务即使 Provider 返回 resolved manifest 仍会暂停以避免未实现的安全映射；这是独立结构课题，不应混入字段 AI-first Gate。可在 D4A-6 前单独决定是否实施安全 manifest-to-unit 映射。
9. **用户修订权限/并发**：桌面单用户仍需处理重复点击和过期 revision；建议使用 expected current revision 做乐观并发控制。

## 20. 本 Gate 未修改代码证明

- 审计期间仅执行 Git/文本只读命令，未运行测试、Job 或任何网络命令。
- 唯一新增文件是本报告。
- 显式暂存和提交时只包含 `docs/reports/GATE_4D_D4A0_AI_FIRST_ARCHITECTURE_AUDIT.md`。
- 起始工作区的 6 个未跟踪文档保持原样，不属于本 Gate。
- Provider、API、网络、真实 Ark、真实 PI、字典、物料、BGE-M3、FAISS 调用数均为 `0`。

## 21. 最终架构判断

不要“推翻 AI 整单重做”。应保留已经真实验证的 V2 候选合同、单记录目标、证据绑定、Ark Provider、缓存恢复和五类原子发布，替换位于中间的 Python-authority 字段政策，并让后续 ready/Job/UI 正确承载 review。最关键的设计原则是：**业务理解不同必须可见、可下载、可修订；技术身份与证据边界仍必须不可绕过。**
