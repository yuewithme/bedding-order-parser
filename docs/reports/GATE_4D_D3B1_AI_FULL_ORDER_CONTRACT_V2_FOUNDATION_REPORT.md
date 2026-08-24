# Gate 4D-D3B-1｜AI 整单 Contract V2 合同与 Provenance 基础离线实现报告

## 1. 基线与范围

- 起始分支：`master`
- 起始 HEAD：`111805a7b60fde2acdf9018b9e3cc9406bccfe90`（`research: evaluate ai full-order evidence contracts`）
- 最终提交：本报告所在提交 `feat: add ai full-order contract v2 foundation`（实际 hash 以该提交后的 `HEAD` 为准）。
- 起始已跟踪工作区：无修改、无暂存修改。
- 起始未跟踪交接/恢复文档：保留，未清理、未纳入本 Gate。
- 本 Gate 只建立 V2 合同与本地 provenance 基础；未修改 `orchestration.py`、`resolution.py`、`reliability.py`、`downstream.py`、`web/ai_full_order_service.py`、UI、标准解析、字典、物料匹配、默认 ZIP 或正式发布链。

## 2. 实际修改文件

| 文件 | 修改 |
| --- | --- |
| `src/bedding_order_parser/ai_full_order/contracts.py` | 新增独立 V2 稀疏候选 Schema/验证器；收紧安全诊断路径白名单。 |
| `src/bedding_order_parser/ai_full_order/provenance.py` | 新增单目标本地 provenance binder、span、候选问题类型与 V1 兼容适配器。 |
| `src/bedding_order_parser/ai_full_order/fake_provider.py` | 新增只在测试使用的 `FakeV2CandidateProvider`。 |
| `tests/ai_full_order/test_contracts.py` | 覆盖 V2 Schema、17 字段枚举、禁止字段与 D2D 路径白名单。 |
| `tests/ai_full_order/test_provenance.py` | 新增人工合成工作簿下的 V2 binder、硬错误、字段问题、合并表头、V1 adapter 与零网络测试。 |
| `docs/reports/GATE_4D_D3B1_AI_FULL_ORDER_CONTRACT_V2_FOUNDATION_REPORT.md` | 本报告。 |

未新增依赖。

## 3. V2 Schema 最终形态

V2 与 V1 完全分离：V1 的 `FULL_ORDER_OUTPUT_SCHEMA`、`validate_full_order_output`、`_validate_record_evidence` 和现有 Provider V1 读取路径未改变语义。

V2 顶层仅允许：

```json
{"candidates": []}
```

每个 candidate 强制完整包含以下五个键，禁止额外键与 `null`：

```text
field_name             固定 17 个 AI 业务字段之一
candidate_value        非空字符串
evidence_references    非空、去重 evidence ID 数组
interpretation         direct | semantic | source_summary
supporting_quote       字符串；direct 可为空，其余解释由 binder 再校验非空
```

候选列表可为空；同一 extraction unit 内 `field_name` 不得重复。行号、物料编码、相似分数及任何 record/source/scope/SHA/provider/usage 等模型回显字段均不属于 Schema，作为额外字段严格拒绝。`V2_SCHEMA_VERSION = "2.0"` 是后续请求、缓存和 prompt 显式版本化的常量，未写进本轮要求仅有 `candidates` 的模型输出顶层。

本轮同时给现有无依赖 Schema 验证器补充了通用 `minItems` 检查，用于确保 V2 evidence 引用非空；V1 现有数组 Schema 未设置该约束，行为不变。

## 4. 单目标记录与 Provenance

`bind_v2_candidates()` 只接收一个本地 `LocalRecord` 与本地 `EvidenceItem` catalog。模型响应不携带目标身份；binder 以本地记录绑定：

```text
record_local_id / source_record_id / scope_id / sheet_id / source_row
```

每个 `BoundCandidate` 输出候选本身、被引用 evidence 的本地快照、`original_text`、`normalized_text`、sheet/scope/cell range、目标身份、验证状态、固定问题码与本地 quote span。不会输出完整请求、Provider 原始响应、模型任意键名或思维链。

span 语义固定为：在 evidence `normalized_text` 中按 Python 零基、右开区间 `[start, end)` 定位。定位仅使用既有 `normalize_evidence_text()` 的空白折叠与去首尾空白；无模糊匹配、语义匹配或新 normalizer。

- `direct`：本地以 `candidate_value` 定位，忽略模型提供的 quote。
- `semantic`、`source_summary`：本地要求并定位非空 `supporting_quote`。
- 一条 candidate 可引用多个 evidence；快照顺序保留模型引用顺序，span 选择第一个可定位的引用。
- 表头 evidence 已由预处理器继承进同 scope record；合成合并表头 `B2:D2` 的 anchor `B2` 已通过 binder 回归验证。

## 5. Hard error 与候选级问题

整 extraction unit 的 hard error：顶层或 candidate Schema 错误、额外/禁止字段、无效枚举、重复 `field_name`、重复 evidence ID、未知 evidence、跨 scope evidence、目标外 evidence、无效本地 target identity。这些均抛出 `FullOrderContractError`，并使用固定安全 stage/category。

普通候选问题不伪装为 provenance 成功，也不在本轮决定发布：

| 问题 | `CandidateIssueCode` |
| --- | --- |
| direct 值无法在引用 evidence 定位 | `direct_candidate_untraceable` |
| semantic/source_summary 缺 quote | `supporting_quote_required` |
| semantic/source_summary quote 无法定位 | `supporting_quote_untraceable` |

上述候选返回 `validation_status=candidate_issue`，为 D3B-2 的字段政策和隔离层保留结构化输入；本 Gate 未接入字段裁决或发布门。

## 6. V1 兼容读取

`adapt_verified_v1_record_to_v2_candidates()` 是未被生产链引用的纯函数。它首先调用既有 `validate_full_order_output()`；仅把已严格验证、状态为 `extracted` 或 `normalized` 的 V1 字段映射为 V2 `direct` candidate，再通过同一个本地 binder 绑定 identity/scope/evidence。

无效 V1 的 value/original_value/evidence 不能进入 adapter。未实现 V1/V2 cache 自动迁移、缓存写入或桌面集成。

## 7. D2D 安全诊断白名单修复

`_safe_contract_path()` 已移除“允许固定 prefix 后任意 suffix”的逻辑，改为固定 root、block、evidence、record、17 个 V1 field/subfield、usage 与 V2 candidate subfield 的精确集合。

以下路径已明确验证不会进入安全摘要：

```text
$.records[].untrusted_generated_field
$.records[].fields.any_model_generated_key
$.evidence_catalog[].arbitrary_suffix
$.candidates[].arbitrary_model_key
```

合法 V1/V2 固定路径仍保留；诊断仅返回允许的 stage/category/path、固定字段名、类型和计数，不回显模型键名或业务值。

## 8. 测试与离线证明

执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\ai_full_order\test_contracts.py `
  tests\ai_full_order\test_provenance.py `
  tests\ai_full_order\test_preprocessing.py `
  tests\ai_full_order\test_acceptance_diagnostics.py `
  tests\ai_full_order\test_volcengine_ark_full_order_provider.py `
  tests\web\test_ai_full_order_jobs.py::test_standard_dispatch_remains_on_existing_path `
  tests\web\test_ai_advisory.py::test_cached_sidecar_prevents_a_second_provider_call -q
```

实际结果：`69 passed in 5.94s`。

覆盖项包括：V1 合法/负例回归、V2 空/单/多候选与完整 17 字段枚举、禁止/额外字段、重复字段、未知/跨 scope/目标外证据、direct/semantic/source_summary 的定位与问题码、多 evidence、合并 anchor 与表头继承、V1 adapter、D2D 任意 suffix、Ark Provider FakeTransport 边界、标准 Job 路径与单记录 AI Sidecar 缓存路径。

所有调用使用 `FakeFullOrderProvider`、`FakeV2CandidateProvider` 或既有 `FakeTransport`；socket/真实 transport 在相关测试中被阻断。真实网络、Ark API、真实 PI、真实字典/物料库、BGE-M3 和 FAISS 调用数均为 `0`。未运行完整 pytest。

## 9. 发现并解决的问题

1. 既有 Schema 验证器没有 `minItems` 支持，V2 的“非空 evidence 引用”无法仅凭 Schema 表达；已以通用、未影响 V1 现有 Schema 的最小检查补齐。
2. D2D 路径净化原先对固定容器使用 prefix 放行，会让任意后缀进入摘要；已改为精确固定路径匹配并补回归。
3. 合并的文档标题不必然属于预处理后的记录 scope，不能错误当作可绑定证据；测试改为验证真实进入 target evidence IDs 的合并表头 anchor，保持 evidence 范围的实际语义。

## 10. 留给 D3B-2 的问题

1. V2 单目标 extraction unit 如何接入现有 chunk manifest 与 Provider 请求/prompt/function Schema，且不得影响 V1 Provider 路径。
2. 字段政策如何将 `bound` 与 `candidate_issue` 结合 Python shadow：高风险字段、描述字段和备注字段的采纳/隔离矩阵需要落地为裁决输入。
3. V2 的 `contract_version`、schema/prompt/normalization/field-policy/provenance-binding 版本如何进入 cache identity、single-flight、恢复与 V1 缓存隔离。
4. 在 existing batch ready 门之前，字段级隔离记录如何汇总为记录/块/批次状态，且不绕过五类 JSON 原子发布门。
5. V1 compatibility reader 是否仅用于读/迁移辅助；建议继续禁止自动 cache 迁移和任何基于 V1 形状的 V2 自动猜测。

## 11. 正式合同未发生的变化与最终状态

未改变 17 字段定义、正式 20 字段、正式行号、物料编码/相似分数归属、V1 evidence/identity/scope 验证、字段裁决、缓存身份、五类 JSON 发布、标准模式、Sidecar 或默认 ZIP。

最终工作区没有已跟踪未提交修改；既有未跟踪交接/恢复文档继续保留且不纳入本 Gate 提交。
