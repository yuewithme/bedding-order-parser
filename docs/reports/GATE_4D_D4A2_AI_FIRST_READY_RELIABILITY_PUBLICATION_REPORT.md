# Gate 4D-D4A-2｜AI-first Technical Ready、可靠性重校验、缓存身份与五类发布语义重构报告

## 1. 基线

- 分支：`master`
- 起始完整 HEAD：`f754048899b76e68d4aa213c6b677b0dc83a8ec0`
- 起始短 HEAD：`f754048`
- D4A-1 implementation commit：`03134338580a8bf6daa8cfc51a6e3380de590f1f`
- D4A-1 report commit：`f754048899b76e68d4aa213c6b677b0dc83a8ec0`
- 本 Gate implementation commit：`0b879b7a9239143e7a84dfd42b7ff322a9592074`
- implementation commit message：`refactor: separate ai review from technical readiness`

开始时工作区不存在未知已跟踪修改。以下既有未跟踪交接/审计材料保持原样，未清理、未暂存、未提交：

```text
CODEX_GPT_FULL_PROJECT_HANDOFF_2026-08-05.md
CODEX_HANDOFF_AND_RECOVERY_2026-07-30.md
CODEX_RECOVERY_AUDIT_ROUND_1_REPORT_2026-08-01.md
docs/reports/AI_FIRST_FULL_ORDER_REFACTOR_RECOMMENDATIONS_2026-08-09.md
docs/reports/AI_FULL_ORDER_CONTRACT_V2_PREIMPLEMENTATION_READONLY_AUDIT_REPORT_2026-08-05.md
docs/reports/ARCHITECTURE_REVIEW_AI_FULL_ORDER_CONTRACT_V2_2026-08-03.md
docs/reports/GATE_4D_C2_EXECUTION_HANDOFF_STATUS_2026-08-02.md
```

## 2. 最终架构结论

D4A-2 将 V2 后半链路从“没有旧 business blocking 就碰巧成功”改为两个显式、互不推导的维度：

```text
technical_ready = 技术合同、身份、unit、canonical、provenance 均完整
review_required = 字段对照需要业务员注意
```

正式语义：

| technical_ready | review_required | 行为 |
|---|---:|---|
| `true` | `false` | 正常进入下游并发布五类结果 |
| `true` | `true` | 正常进入下游并发布五类结果，同时在解析诊断记录 review |
| `false` | 任意 | 不进入正式下游，不发布五类结果 |

AI/Python 的业务值不同、高 review、AI only、Python fill、双方为空，以及已安全降级为 Python/空值的 bound candidate content issue，均不再构成 technical non-ready。

## 3. Technical Ready 最终定义

### 3.1 Record 层

`V2CanonicalRecord.technical_ready` 只证明：

- decisions 严格按固定 17 个 AI 业务字段构成；
- 每个 formal value 均为字符串；
- record 已经经过上游 identity、scope、provenance hard validation。

`ready_for_downstream` 保留为兼容属性，但仅代理 `technical_ready`。旧 `decision.blocking` 不再参与 V2 record technical readiness。

### 3.2 Batch 层

`V2BatchAggregate` 新增并显式维护：

```text
technical_ready
review_required
review_required_count
high_review_count
comparison_summary
```

`aggregate_v2_batch()` 的 technical failure reasons 只来自：

- 缺失、重复或未知 extraction unit outcome；
- unit hard failure；
- record 数量不一致；
- record identity 重复或与 target 不一致；
- scope crossing；
- canonical 17 字段结构无效；
- accepted AI provenance 无效。

已删除聚合层旧 `high_risk_blocking_conflict` 业务阻断判断。

Review 汇总由字段 decision 独立计算，不参与 `BatchStatus.READY/ISOLATED`。

## 4. Review 与 Technical Ready 的彻底分离

下列 D4A-1 结果现被后半链路明确视为 technical success：

```text
different
ai_only
python_fill
both_missing
high review severity
semantic review
content issue -> python_fallback
content issue -> empty
```

这不是通过放宽 envelope、identity 或 evidence ownership 实现，而是因为这些字段均已形成安全 canonical value 和可审计 decision。

Review 批次的 reliability disposition 为：

- 首次执行：`EXECUTED`
- 缓存重放：`CACHED`

不会仅因 `review_required=true`、`comparison_status=different` 或 `high_review_count>0` 进入 `ISOLATED`。

## 5. Aggregate 改动

`aggregate_v2_batch()` 现在：

1. 校验 outcome unit 集合与唯一性；
2. 校验 validated outcome 覆盖全部 expected unit；
3. 校验 record 数量、唯一身份、target 绑定和 scope；
4. 校验 canonical 17 字段技术结构；
5. 二次校验被正式采用的 AI 值仍具有效本地 provenance；
6. 单独统计 review field、高 review field 和 comparison status；
7. 只用 technical reasons 决定 `READY/ISOLATED`。

因此，review 批次可明确为：

```text
status = ready_for_downstream
technical_ready = true
review_required = true
```

## 6. Reliability Disposition 与 Candidate 状态

### 6.1 新状态

新写入的 V2 unit 状态：

```text
validated
validated_with_content_issue
```

`validated_with_content_issue` 表示：

- Provider envelope 和 candidate identity/ownership 已通过 hard validation；
- 某个已绑定 candidate 的内容不可采信；
- 字段政策已安全选择 Python fallback 或空字符串；
- unit 仍是技术完成态，可参与 batch aggregation 和 publication。

### 6.2 旧 `candidate_isolated`

`candidate_isolated` 不再用于新写入，仅作为历史 state 的只读兼容枚举保留。

兼容策略不是把它无条件视为 hard failure，也不是无条件视为安全 review：

```text
读取旧 state
-> 重新校验缓存中的 V2 candidate payload
-> 重跑 provenance + 当前 field policy
-> 当前结果确实存在 content issue：接受为可重放成功
-> 当前结果不再对应 content issue：v2_cached_revalidation_failure
```

测试同时覆盖了相符与不相符两条路径。

### 6.3 `ISOLATED` 的新语义

`ISOLATED` 继续保留，专用于无法形成 technical-ready batch 的真实技术失败，例如 hard contract、identity/provenance failure、缺 unit、损坏缓存或不完整结果。Business review 不进入 `ISOLATED`。

## 7. Cache Identity 最终组成

V2 cache identity 保持 V1/V2 namespace 隔离，并包含：

```text
source_file_sha256
provider
model
contract_version
schema_version
prompt_version
preprocessor_version
context_selection_version
normalization_version                 # D4A-1 Business NORMALIZATION_VERSION
evidence_normalization_version        # evidence text normalization
comparison_version                    # D4A-1 COMPARISON_VERSION
python_shadow_adapter_version
field_policy_version
provenance_binding_version
canonical_extraction_manifest_sha256
```

当前关键版本：

```text
FIELD_POLICY_VERSION = 3.0
NORMALIZATION_VERSION = 1.0
COMPARISON_VERSION = 1.0
```

相对于 D4A-1，`NORMALIZATION_VERSION` 和 `COMPARISON_VERSION` 已正式进入 cache key；原 evidence normalization 版本被保留为独立字段，不再与业务值 normalization 混为同一概念。

任一组成变化都会改变规范化 identity JSON 和 SHA-256 cache key，因此旧 Python-authority、旧 normalization 或旧 comparison 语义不能无声复用到当前 runtime。

## 8. Cache Replay 语义

缓存继续保存可安全重验证的严格 V2 candidate payload，不保存旧最终字段选择作为不可变真相。

Cache hit 执行顺序：

```text
validated candidate payload
-> validate_full_order_v2_output
-> bind_v2_candidates
-> resolve_v2_record（当前 normalization/comparison/field policy）
-> validate_v2_accepted_ai_provenance
-> aggregate technical ready + review
```

结果：

- cache hit 不重新调用 Provider；
- business review 缓存重放仍为 `CACHED` 并可发布；
- content issue 按当前政策重新形成 Python fallback/empty 和 review；
- 技术无效或状态语义不一致的缓存返回 `v2_cached_revalidation_failure`，不会被新政策错误放行。

## 9. Content Issue 与 Hard Evidence Failure

### 9.1 Bound candidate content issue

例如 supporting quote 不足、候选内容不可追溯、备注扩写等。在 candidate identity 与 evidence ownership 合法的前提下：

```text
Python 有可靠值 -> python_fallback + review
Python 无可靠值 -> empty + review
```

之后 technical-ready/reliability/downstream 不会再次把它升级为整批 hard failure，原不可采信 AI 值也不会重新进入 formal result。

### 9.2 Hard evidence / identity failure

以下边界未放宽：

```text
invalid V2 envelope
extra/forbidden/duplicate field
unknown evidence
cross-scope evidence
target/record/source identity mismatch
evidence ownership failure
invalid extraction manifest/unit
cache/state corruption
```

这些失败仍产生 failed outcome 和 `ISOLATED`，下游 dictionary/material 端口调用数为 0，最终目录无五类产物。

## 10. Downstream Ready Gate

`_require_v2_ready()` 不再读取 business `blocking`。它现在防御性验证：

- disposition 必须为 `EXECUTED` 或 `CACHED`；
- batch 必须 `technical_ready` 且无 technical failure reasons；
- outcomes 必须完整且全部 `VALIDATED`；
- record identity 必须唯一并与 extraction unit target 对齐；
- canonical record 必须严格形成 17 字段；
- 所有正式采用的 AI 值必须再次通过 accepted provenance 校验。

进入既有窄 downstream port 时，V2 comparison/review 不会伪装成旧 `ResolvedRecord.blocking`。

DictionaryValidator 和 MaterialMatcher 的业务边界未改变：

- 字典层不改变 AI/Python 主值选择；
- MaterialMatcher 仍唯一生成物料编码和相似分数；
- AI 仍不能生成行号、物料编码或相似分数。

## 11. Parse Diagnostics Comparison Schema

V2 `parse_diagnostics` 新增白名单字段级对照：

```text
field_name
formal_value
ai_display_value
ai_normalized_value
ai_evidence_ids
python_display_value
python_normalized_value
python_evidence_ids
comparison_status
status
selected_source
review_required
review_severity
reason_codes
technical_candidate_status
candidate_issue_code
```

Record 级白名单：

```text
source_record_id
scope_id
line_number
fields
```

顶层新增：

```text
technical_readiness
review_summary
contract_versions
result_identity
unit_states
provider_telemetry
```

不再把完整 `cache_identity` 复制进解析诊断；仅保留 Bundle 校验所需的 opaque cache key/source SHA 与非敏感合同版本。`JobService` 增加了窄兼容读取，可读取新 `contract_versions`，也可继续读取历史 Bundle 的 `cache_identity`。

诊断未写入 Prompt、原始 Provider response、Authorization、API Key、本机路径、CoT 或完整缓存身份。

## 12. Official Result 与五类原子发布

`official_result` 继续严格由以下 20 字段组成：

```text
17 个 canonical business fields
+ 本地正式行号
+ MaterialMatcher 物料编码
+ MaterialMatcher 相似分数
```

Comparison、review、模型、Token、evidence 和 cache 元数据均未进入正式业务记录。固定字段顺序、前 19 项字符串和相似分数 float 的验证未改变。

业务产物仍恰好五类：

```text
official_result
parse_diagnostics
dictionary_validation
material_candidates
material_summary
```

原子发布机制未修改：唯一 staging、逐文件校验、五文件完整校验、Bundle 目录原子替换、单一 `CURRENT` 切换、失败 staging 清理和 Windows 占用有界重试均保持。Review batch 可完整原子发布；任一 schema/write/CURRENT 失败仍不发布半套结果。

## 13. Standard、V1 与 Sidecar 保护

本 Gate 未修改：

```text
standard parser
standard 主值选择
字典业务规则
MaterialMatcher 算法、权重、阈值、TopK
standard 五类 JSON Schema
Excel/ZIP
单记录 AI Sidecar
V1 field resolution semantics
Ark Provider/Prompt/Contract V2 envelope
```

共享 Bundle 读取只增加新旧 V2 diagnostics identity 的兼容分支。Standard dispatch、legacy V1 Job 和单记录 AI advisory 定向回归均通过。

## 14. 修改文件

### 生产代码

```text
src/bedding_order_parser/ai_full_order/field_policy.py
src/bedding_order_parser/ai_full_order/orchestration.py
src/bedding_order_parser/ai_full_order/reliability_v2.py
src/bedding_order_parser/ai_full_order/downstream.py
src/bedding_order_parser/web/services.py
```

### 测试

```text
tests/ai_full_order/test_v2_offline_resolution.py
tests/ai_full_order/test_v2_reliability.py
tests/ai_full_order/test_v2_downstream.py
tests/web/test_ai_full_order_jobs.py
```

## 15. 测试命令与精确结果

未运行完整 pytest。使用项目既有 `.venv`，未安装依赖。

### 核心、安全、恢复、发布、Job 与 UI 合同组合回归

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ai_full_order/test_contracts.py tests/ai_full_order/test_provenance.py tests/ai_full_order/test_field_policy.py tests/ai_full_order/test_v2_offline_resolution.py tests/ai_full_order/test_v2_reliability.py tests/ai_full_order/test_v2_downstream.py tests/ai_full_order/test_v2_structure_path.py tests/web/test_ai_full_order_jobs.py tests/web/test_ai_advisory.py tests/web/test_d3b2d_ui_enablement.py -q
```

结果：`152 passed in 54.98s`

### V1 orchestration/downstream、standard dispatch 与 legacy V1 回归

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ai_full_order/test_orchestration.py tests/ai_full_order/test_downstream.py tests/web/test_ai_full_order_jobs.py::test_standard_dispatch_remains_on_existing_path tests/web/test_ai_full_order_jobs.py::test_legacy_ai_job_without_contract_version_stays_on_v1 -q
```

结果：`18 passed in 1.41s`

### 最终 V2 publication 专项复验

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ai_full_order/test_v2_downstream.py -q
```

结果：`15 passed in 1.56s`

### 编译与 diff 检查

```powershell
.\.venv\Scripts\python.exe -m compileall -q src/bedding_order_parser/ai_full_order src/bedding_order_parser/web/services.py
git diff --check
```

结果：均通过，无输出错误。

测试明确覆盖：

- high review difference、ordinary difference、AI only、Python fill、both missing；
- content issue + Python fallback、content issue + empty；
- unknown evidence、cross-scope、identity、forbidden field 等 hard safety；
- normalization/comparison/field policy cache identity 失效；
- cache hit 零 Provider 调用与当前本地政策重校验；
- legacy `candidate_isolated` 的相符/不相符重校验；
- single-flight、中断恢复、terminal state protection、cache corruption；
- review diagnostics 白名单、正式 20 字段无污染、恰好五类产物；
- staging/CURRENT 原子失败、Windows 占用重试；
- standard、V1、Sidecar 与现有 UI 合同。

## 16. 真实调用计数

```text
Ark 真实逻辑调用：0
HTTP/外部网络调用：0
真实 PI：0
真实字典：0
真实物料库：0
BGE-M3：0
FAISS：0
```

全部 AI、字典、物料测试均使用 FakeProvider、FakeDictionaryValidator 和 FakeMaterialMatcher；网络创建在相关测试中被显式阻断。

## 17. 兼容风险

1. `candidate_isolated` 仍存在于枚举和历史 state reader 中，仅用于兼容；D4A-3 不应继续把这个名称作为用户可见产品语义。
2. 当前 Job 摘要仍使用历史字段 `isolated_field_count` 作为兼容 view；它不会阻断 Job，但名称容易误导，应在 D4A-3 迁移为 review/content-issue 摘要。
3. 新 parse diagnostics 不再暴露完整 cache identity；Bundle reader 已兼容新旧结构，其他仓库外消费者若直接依赖旧内部字段，需要按新白名单合同迁移。
4. `technical_ready` 只表达发布前技术完整性，不表示字典或物料业务结果“正确”；业务员仍需读取 diagnostics/review 和候选信息。
5. 当前原子 Bundle 仍以 extraction cache key 作为发布身份。未来 user revision 必须使用独立 revision identity/version，不能覆盖初始 AI Bundle。

## 18. 留给 D4A-3 的具体事项

1. Job/API 明确暴露 `review_required_count`、`high_review_count` 和 comparison summary。
2. 将历史 `isolated_field_count` 用户可见语义迁移为 review/content issue，不再显示“隔离字段”。
3. 结果页展示 AI/Python 对照，并支持按 record/field 查看 evidence ID 对应位置。
4. 实现用户选择“保留 AI / 改用 Python / 手动输入”的 revision 数据模型。
5. revision 不调用 Ark，只重建 canonical 17、重跑受影响的本地下游并发布新版本 Bundle。
6. 保留初始 AI Bundle，revision 使用独立 hash/version 和原子 `CURRENT` 切换，保证可审计和可回退。
7. Review 不得映射为 `awaiting_user_decision`；只有 technical failure 才进入失败决策流程。

下一轮最危险的风险是：为了尽快做 review UI，直接修改当前 Bundle 或正式业务 JSON，造成初始 AI 结果不可审计、五类文件版本混合，或者把 comparison 字段污染进固定 20 字段。D4A-3 应先冻结 revision identity 与 Bundle 版本策略，再接 UI 操作。

## 19. 最终工作区目标

报告提交后，所有本 Gate 已跟踪修改应全部提交；工作区仅保留开始前已经存在的七份未跟踪交接/审计材料。未删除、未覆盖、未暂存这些材料。
