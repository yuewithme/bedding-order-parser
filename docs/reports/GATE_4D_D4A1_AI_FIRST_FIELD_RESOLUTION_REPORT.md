# Gate 4D-D4A-1：AI-first 字段决策、规范化与对照层重构报告

## 1. 结果与基线

本 Gate 完成了 Contract V2 的 AI-first 字段决策核心。`ai_enhanced` 模式中，技术上可信的 AI candidate 现在是业务字段正式主值；Python shadow 只提供独立对照，或在 AI 缺失、AI candidate 内容不可采信时提供明确标识的本地补空。AI/Python 业务差异不再由字段政策产生 blocking。

| 项目 | 实际值 |
|---|---|
| 起始分支 | `master` |
| 起始完整 HEAD | `678ff3c08726ee234cd0c256023fd4b70def195b` |
| D4A-0 审计报告提交 | `678ff3c08726ee234cd0c256023fd4b70def195b` |
| 实现提交 | `03134338580a8bf6daa8cfc51a6e3380de590f1f` |
| 实现提交信息 | `feat: make ai full-order resolution ai-first` |
| 本报告提交 | 本文件独立提交，提交信息为 `docs: report ai-first field resolution` |

本 Gate 未修改 `orchestration.py` 的聚合逻辑、`reliability_v2.py` 的状态/缓存实现、`downstream.py` 的发布门、桌面 Job/路由/UI、Provider、Prompt、V2 envelope、标准解析、字典规则、物料匹配、默认 ZIP 或单记录 AI Sidecar。真实 Ark、HTTP、真实 PI、真实字典、真实物料库、BGE-M3 和 FAISS 调用均为 `0`。

## 2. AGENTS.md 长期规则更新

只更新了与新产品合同冲突的两处稳定规则：

- `ai_enhanced` 现在明确为“整单 AI 是业务字段主解析器”，Python shadow 只做独立对照和 AI 缺值时的本地补空。
- AI/Python 业务值不同现在必须形成可审计 review；高风险字段只提高 review 醒目程度，不得仅因业务差异阻断 canonical、下游或五类发布。identity、scope、evidence ownership、正式 20 字段和原子发布等技术完整性失败仍 hard block。

`standard` 仍是 Python 主解析，单记录 AI Sidecar 仍只在用户确认后做只读复核。

## 3. 实际架构

本次没有把所有逻辑塞回 `field_policy.py`。实际采用三个窄层：

```text
BoundCandidate + PythonShadowRecord
        |
        v
normalization.py
  BusinessValueView
  display_value / normalized_value / status / rule
        |
        v
comparison.py
  AI/Python comparison_status + review_required + review_severity
        |
        v
field_policy.py
  formal value + selected_source + reason_codes + technical candidate state
```

这样拆分的原因：evidence text normalization 仍留在原有 contract/provenance 层；业务值 normalization 不再被误用作 evidence 的逐字验证；comparison 不再依赖旧 `blocking` 推断；D4A-2 可以在不重写字段选择的前提下，把明确的 review 数据接入缓存、诊断和发布。

### 版本

| 常量 | 值 | 用途 |
|---|---|---|
| `V2_FIELD_POLICY_VERSION` | `3.0` | 隔离旧 Python-authority 字段政策缓存 |
| `NORMALIZATION_VERSION` | `1.0` | 标识本地业务值 normalization 规则集 |
| `COMPARISON_VERSION` | `1.0` | 标识 AI/Python comparison/review 语义 |

本 Gate 只提升了已被 V2 cache identity 采用的 `field_policy_version`。`NORMALIZATION_VERSION` 与 `COMPARISON_VERSION` 尚未进入 cache identity，这是 D4A-2 的明确任务，不能在没有重审可靠性链的情况下在本 Gate 擅自修改。

## 4. 新字段决策模型

`V2FieldDecision` 保留了现有消费者所需的 `value`、`selected_source`、`evidence_ids`、`blocking`、`ai_isolated` 和兼容 `reason_code` 属性，同时新增：

```text
comparison_status
review_required
review_severity
reason_codes
ai_display_value
ai_normalized_value
ai_evidence_ids
python_display_value
python_normalized_value
python_evidence_ids
technical_candidate_status
```

`reason_code` 是 `reason_codes` 的第一个兼容视图，避免当前诊断消费者因本 Gate 的数据模型升级而立即失效；D4A-2 应把完整 comparison/reason_codes 以白名单方式写入 diagnostics。

### 17 字段选择矩阵

| 条件 | formal value | selected_source | comparison_status | review | blocking |
|---|---|---|---|---|---|
| AI 可采信，Python 同值 | AI 值 | `ai` | `agree` | direct 时否；semantic/source_summary 时是 | `false` |
| AI 可采信，经确定性规范化后与 Python 等价 | AI 派生 normalized 值 | `ai` | `equivalent_after_normalization` | semantic/source_summary 时是 | `false` |
| AI 可采信，Python 不同 | AI 值 | `ai` | `different` | 是 | `false` |
| AI 可采信，Python 为空 | AI 值 | `ai` | `ai_only` | direct 时否；semantic/source_summary 时是 | `false` |
| AI 缺失，Python 有可靠直接证据 | Python 值 | `python_fallback` | `python_fill` | 是，`local_rule_fill` 由 reason 表达 | `false` |
| AI 与 Python 都缺失 | 空字符串 | `none` | `both_missing` | 是 | `false` |
| AI 内容 issue，Python 有可靠值 | Python 值 | `python_fallback` | `python_fill` | 是，含 technical issue | `false` |
| AI 内容 issue，Python 为空 | 空字符串 | `none` | `both_missing` | 是，含 technical issue | `false` |

所有 17 个字段仍会得到一个字符串决策。正式行号仍由 Python shadow/local geometry 提供；`物料编码`和`相似分数`不属于 AI 17 字段，因此仍不可能由本层生成。

## 5. High-review 新语义

原有五个字段保留，但常量改为 `V2_HIGH_REVIEW_FIELDS`：

```text
客户
币种
业务员
数量
计划发货日期
```

为兼容旧读取代码，`V2_HIGH_RISK_FIELDS` 仍是同一只读集合的别名；新决策代码不再使用“risk”作为 blocking/publish 含义。

这些字段的 AI/Python 差异现在产生：

```text
selected_source = ai
comparison_status = different
review_required = true
review_severity = high
blocking = false
```

直接、同值的高 review 字段不会因为字段名称本身被强制人工复核；semantic/source_summary 或实际差异才产生 review。这避免了把所有正常 AI 提取都变成无意义的待办。

## 6. Display、normalized 与 formal 的关系

`normalization.py` 新增了独立 `BusinessValueView`：

```text
display_value
normalized_value
normalization_status
normalization_rule
```

第一版只包含确定性、低风险转换：

- NFKC Unicode 与空白整理；
- 明确币种白名单：`美元`、`USD`、`US Dollar` -> `USD`；
- 非负普通十进制数量：`10.0` -> `10`；
- 完整无歧义日期：`YYYY-MM-DD`、`YYYY/MM/DD`、`YYYY年M月D日` -> `YYYY-MM-DD`。

没有实现中文自然语言数字、客户简称/全称、买方/收货方、业务员昵称、订单日期/计划发货日期或行数量/订单总量等模糊推理。

正式 `formal value` 的规则：

- 对币种、数量、计划发货日期，若存在确定性转换，使用 AI 派生的 normalized 值；`selected_source` 仍是 `ai`。
- 其他字段保留 AI display value，避免为了整齐而改变业务语义。
- comparison 永远保留 display 与 normalized 事实，D4A-2 再把它们安全发布到诊断。

## 7. Evidence ownership 与 content issue

本 Gate 没有改 `provenance.py`、V2 Schema 或 Provider。

继续 hard block 的技术边界：

- unknown evidence ID；
- cross-scope evidence；
- evidence 不属于当前 target；
- target/record/sheet/scope/source-row identity 不一致；
- V2 envelope、额外字段、禁止字段、重复字段或类型错误。

已绑定 candidate 的内容问题不再按字段风险扩大为 blocking：

- direct candidate 无法从已绑定 evidence 追溯；
- semantic/source summary 缺少可定位 quote；
- `source_summary` 被用于非备注字段；
- 备注 candidate 超出 quote 可证明的范围。

这类情况通过 `technical_candidate_status=content_issue`、`candidate_issue_code` 和 reason codes 保存。字段改用 `python_fallback` 或空字符串，并标 review；它们没有放宽 provenance，也没有让无来源 AI 内容成为 formal value。

## 8. Interpretation 与备注策略

`direct`、`semantic`、`source_summary` 现在决定 provenance/复核策略，不再决定 Python 是否自动胜出：

- `direct`：所有 17 字段可采用；
- `semantic`：合法 bound candidate 可采用，标 review；高 review 字段给 high severity；
- `source_summary`：仅限 `表头备注`、`行备注`，且只能是确定性排版等价；
- 备注仅允许 NFKC、空白、换行和安全标点整理；不得补充事实或扩写。

备注扩写不再杀整单：Python 有可靠值时补空；否则正式值为空并记录 technical review。

## 9. 修改文件

| 文件 | 修改目的 |
|---|---|
| `AGENTS.md` | 把长期 AI enhanced 冲突政策更新为 AI 主值 + Python 对照/补空 + 技术 hard block |
| `src/bedding_order_parser/ai_full_order/normalization.py` | 新增保守、版本化业务值 normalization |
| `src/bedding_order_parser/ai_full_order/comparison.py` | 新增稳定 comparison、review severity、technical candidate 状态 |
| `src/bedding_order_parser/ai_full_order/field_policy.py` | 重构为 AI-first field resolution；移除高风险 blocking/ Python authority 分支 |
| `tests/ai_full_order/test_field_policy.py` | 覆盖 17 字段、AI 主值、normalization、fallback、both missing、content issue、semantic 和备注 |
| `tests/ai_full_order/test_v2_offline_resolution.py` | 高 review 差异改为 AI 主值 + batch ready；调整新状态/原因 |
| `tests/ai_full_order/test_v2_reliability.py` | 验证缓存重放保留 AI 主值，content issue 仍有隔离标记 |
| `tests/ai_full_order/test_v2_downstream.py` | 验证高 review 差异可进入现有下游；更新 policy version 断言 |
| `tests/web/test_ai_full_order_jobs.py` | 验证现有 Job 自然完成并发布五类结果，不再因高 review 差异暂停 |

未修改生产侧：`orchestration.py`、`reliability_v2.py`、`downstream.py`、`ai_full_order_service.py`、`services.py`、`routes.py`、`app.js`、Provider、Prompt、标准解析、字典、物料算法。

## 10. 测试与验证

使用项目既有 `.venv`，未安装依赖、未运行完整 pytest。

```powershell
.\.venv\Scripts\python.exe -m compileall -q src/bedding_order_parser/ai_full_order/normalization.py src/bedding_order_parser/ai_full_order/comparison.py src/bedding_order_parser/ai_full_order/field_policy.py tests/ai_full_order/test_field_policy.py tests/ai_full_order/test_v2_offline_resolution.py
```

结果：通过。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ai_full_order/test_field_policy.py tests/ai_full_order/test_v2_offline_resolution.py tests/ai_full_order/test_contracts.py tests/ai_full_order/test_provenance.py -q
```

结果：`63 passed in 1.38s`。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ai_full_order/test_v2_reliability.py tests/ai_full_order/test_v2_downstream.py tests/web/test_ai_full_order_jobs.py tests/web/test_d3b2d_ui_enablement.py -q
```

结果：`119 passed in 8.69s`。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/web/test_ai_advisory.py tests/web/test_ai_full_order_jobs.py::test_standard_dispatch_remains_on_existing_path tests/web/test_ai_full_order_jobs.py::test_legacy_ai_job_without_contract_version_stays_on_v1 tests/ai_full_order/test_orchestration.py::test_formal_line_number_matches_standard_mode_semantics -q
```

结果：`24 passed in 1.92s`。

验证覆盖：AI/Python 高 review 和普通差异、AI-only、Python fill、both missing、content issue、语义 candidate、备注扩写拒绝、Unicode/空白、币种/数量/日期确定性 normalization、17 字段边界、unknown evidence、cross-scope、identity、禁止字段、缓存重放、五类发布、standard dispatch、Legacy V1 与单记录 AI Sidecar。

## 11. 真实调用与安全

| 项目 | 次数 |
|---|---:|
| Ark 逻辑调用 | 0 |
| HTTP 尝试 | 0 |
| 外部网络调用 | 0 |
| 真实 PI | 0 |
| 真实字典/物料库 | 0 |
| BGE-M3 / FAISS | 0 |

测试只使用 FakeProvider、FakeDictionaryValidator 与 FakeMaterialMatcher。提交前已运行 `git diff --check`，仅显式暂存 Gate 实现文件；未发现 API Key、Authorization、Bearer、真实响应或真实业务数据。

## 12. 留给 D4A-2 的旧阻断点

字段政策不再产生 business blocking，现有下游会因此自然允许一些高 review 差异完成。这是本 Gate 的必要产品结果，但 D4A-2 仍必须专门完成以下工作：

1. 将 `NORMALIZATION_VERSION`、`COMPARISON_VERSION` 加入 V2 cache identity，并定义旧缓存迁移/重放语义。
2. 重命名或重审 `candidate_isolated` cache state，使其仅表达 content issue，不被误解为 AI/Python 业务差异。
3. 修改 `aggregate_v2_batch()`、`_require_v2_ready()` 和 reliability revalidation 的显式 gate：技术 non-ready 继续阻断，review 不应依赖 `blocking` 的偶然行为。
4. 把新 comparison/review 白名单数据写入 V2 parse diagnostics；当前下游只序列化旧的单一 reason/evidence 字段。
5. 把 Job `isolated_field_count`、safe error mapping 和 UI 待处理语义从旧 high-risk blocking 语汇中分离；本 Gate 未碰 Job/UI。
6. 增加“review difference 仍完整发布”与“技术失败仍绝不发布”的跨层正式矩阵，并覆盖 cache hit/recovery。

## 13. D4A-2 最容易出错的风险

最危险的错误是为了让 review batch 发布而把 `candidate_isolated`、technical content issue、unknown/cross-scope evidence 混为同一类，进而放宽真正的 provenance hard block。正确区分应是：

```text
AI/Python business difference -> completed path + review
bound candidate content issue -> Python fill/empty + review，可发布
unknown/cross-scope/identity/envelope failure -> hard failure，不得下游或发布
```

第二个风险是只修改 runtime policy 而未将 normalization/comparison 版本加入 cache identity，从而让旧 Python-authority 缓存静默重用。第三个风险是把 comparison 全量写进官方 20 字段 JSON；它只能进入解析诊断和后续 Job/UI 摘要。

## 14. 最终工作区

本 Gate 的实现和报告均独立提交。保留且未暂存的既有未跟踪文档：

```text
CODEX_GPT_FULL_PROJECT_HANDOFF_2026-08-05.md
CODEX_HANDOFF_AND_RECOVERY_2026-07-30.md
CODEX_RECOVERY_AUDIT_ROUND_1_REPORT_2026-08-01.md
docs/reports/AI_FIRST_FULL_ORDER_REFACTOR_RECOMMENDATIONS_2026-08-09.md
docs/reports/AI_FULL_ORDER_CONTRACT_V2_PREIMPLEMENTATION_READONLY_AUDIT_REPORT_2026-08-05.md
docs/reports/ARCHITECTURE_REVIEW_AI_FULL_ORDER_CONTRACT_V2_2026-08-03.md
docs/reports/GATE_4D_C2_EXECUTION_HANDOFF_STATUS_2026-08-02.md
```

除此以外没有未提交的已跟踪代码或测试修改。本报告是本 Gate 唯一新增报告。
