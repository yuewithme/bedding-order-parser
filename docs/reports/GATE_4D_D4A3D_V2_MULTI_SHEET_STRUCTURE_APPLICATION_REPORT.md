# Gate 4D-D4A-3D：V2 多 Sheet 结构上下文、受控 AI 决策与本地安全应用报告

## 1. 基线与提交

- 分支：`master`
- 起始 HEAD：`986e5ae90b3f6ea547c0dd1897b2228902e919b8`
- D4A-3C 报告提交：`986e5ae90b3f6ea547c0dd1897b2228902e919b8`（`docs: diagnose real ai structure unresolved`）
- 实现提交：`1b4a83ba48498eea7e1aca4f1f1ab439442d7442`
- 实现提交信息：`feat: resolve ai v2 multi-sheet structure safely`
- 起始工作区仅有 7 份既有未跟踪交接/审计文档；本 Gate 未修改、清理或暂存它们。

## 2. 原结构缺口与最终修复

D4A-3C 已确认旧 manifest 只遍历已形成的 block，因此“s1 已确认、s2 无 block 但导致全局 ambiguous”时，Provider 只能看到 s1，完全看不到真正待决的 s2。旧 layout 输出又只有 `status`，服务层不消费其结果并无条件暂停。

本 Gate 将链路改为：

```text
每 Sheet 本地状态
-> known_chunks + unresolved_sheets 同时构造
-> Ark/Fake 只选择本地候选 ID
-> 严格输出 Schema
-> 本地 validator / binder / apply
-> 重新构造安全 PreprocessedWorkbook 视图
-> extraction units
-> 既有 Python shadow / V2 extraction / AI-first / downstream / 五类发布
```

`resolve_structure()` 的返回值不再被丢弃。只有严格验证并成功本地应用的 `resolved` 决策才继续；`ambiguous` 仍停止为 `AI_V2_STRUCTURE_UNRESOLVED`，非法候选决策停止为 `AI_V2_STRUCTURE_DECISION_INVALID`。

## 3. Per-sheet Structure 模型

`preprocessing.py` 新增：

- `SheetStructureState`：保存 `sheet_id`、本地状态、标准几何状态、启发式状态、已知 block/record、本地候选 ID、是否需要结构决策。
- `LocalStructureCandidate`：保存稳定 candidate ID、Sheet 所属、允许角色、本地 block/record 和有限 cell range。
- `PreprocessedWorkbook.sheet_states` 与 `layout_candidates`：保留每 Sheet 独立事实，避免一个 unresolved Sheet 抹掉其他 Sheet 已确认结构。

当前本地状态包括：

- `confirmed_order`
- `unresolved_order_candidate`
- `ignored_by_local_contract`
- 应用后的 `ai_selected_local_order_candidate`
- 应用后的 `ai_confirmed_auxiliary`

`PREPROCESSOR_VERSION` 从 `1.1` 升为 `1.2`，候选 ID 包含 source SHA、预处理版本、Sheet、角色以及本地 block/record/range，稳定且可重算。

## 4. Structure Request 与安全上下文

版本：

- `STRUCTURE_MANIFEST_VERSION = 2.0`
- `STRUCTURE_CONTEXT_VERSION = 2.0`
- `LAYOUT_CONTRACT_VERSION = 2.0`
- `LAYOUT_PROMPT_VERSION = 2.0`

Provider 安全 payload 同时包含：

- `known_chunks`：已由本地确认的 Sheet/区块摘要。
- `unresolved_sheets`：Sheet ID、used range、本地状态、标准/启发式状态、结构统计、本地候选、无正文的 row pattern、受限短摘录。

上下文安全边界：

- 不发送 workbook binary、本机路径、Job ID、API Key、Authorization、隐藏 Sheet 或原始 Provider 数据。
- 摘录最多 32 项、最多 8 行、每行最多 4 项、单项最多 80 字符。
- 银行、账号、IBAN、SWIFT、付款等敏感标签所在行整行排除。
- 不发送整个 Sheet；row pattern 只有行 ID 与数值/文本计数。
- 所有可选择对象均是本地生成的 candidate ID。
- context SHA 绑定 source SHA、`PREPROCESSOR_VERSION`、上下文版本、layout 合同以及规范化 payload；任何篡改均拒绝。

## 5. Layout 输出严格合同

新输出必须完整包含：

```json
{
  "layout_contract_version": "2.0",
  "status": "resolved | ambiguous",
  "decisions": [
    {
      "sheet_id": "s2",
      "role": "order | auxiliary | unresolved",
      "candidate_id": "本地候选ID或空字符串",
      "reason": "固定枚举"
    }
  ]
}
```

对象禁止额外字段。reason 仅允许：

- `selected_local_order_candidate`
- `auxiliary_non_order_content`
- `insufficient_structure`
- `conflicting_candidates`
- `no_applicable_candidate`

旧 `{"status":"resolved"}` 不会被误读为新合同。Provider 使用 strict function calling，并在 Provider 边界先做输出形状验证。

## 6. AI 权限与本地 Hard Boundary

AI 可以：

- 对每个 required unresolved Sheet 选择 `order`、`auxiliary` 或 `unresolved`。
- 对 `order/auxiliary` 选择请求中同 Sheet、同角色的本地 candidate ID。
- 返回固定 reason category。

AI 永远不能生成或应用：

- source SHA、Sheet/record/scope/block/evidence identity。
- 新坐标、新范围、新 record 或新 extraction unit。
- 行号、物料编码、相似分数。
- 任意自由解释文本。

本地 `structure_resolution.py` 逐项验证：输出精确字段、版本、required Sheet 全覆盖、无重复 Sheet、Sheet 所属、候选存在、角色一致、reason 一致、candidate ID 可重算、overall status 与 per-sheet decision 一致。任何未知、跨 Sheet、重复、漏项、额外字段、错误枚举、identity/context 篡改均 hard fail。

## 7. Auxiliary Eligibility 与第二订单 Sheet 保护

本地只在下列事实同时成立时生成 `auxiliary` 候选：

- Sheet 可见且有内容；
- 标准几何为 `standard_table_unresolved`；
- 本地没有 heuristic block；
- 本地没有正式 record candidate；
- 候选不包含 block/record identity。

AI 选择 auxiliary 后，本地再次验证候选所属、稳定 ID、角色以及“候选不含任何订单 block/record”，通过后才排除该 Sheet。AI 不能在没有本地 auxiliary eligibility 的情况下自行宣告忽略。

反例 fixture 包含已确认 s1 与实际带订单候选的 s2。s2 的本地候选角色为 `order`，选择后本地保留其 block、records、scope 和 evidence；它不能被当作 auxiliary 静默忽略。若没有可安全应用的本地 order candidate，则只能保持 unresolved。

## 8. Known + Unresolved 与真实几何克隆

人工合成的 D4A-3C 等价场景：

- s1：本地确认，3 records。
- s2：可见、有内容，`standard_table_unresolved`，无编号记录、无正式 record，存在受控 auxiliary eligibility。
- 隐藏 s3：不进入 Provider payload。

manifest 同时包含 s1 `known_chunks` 与 s2 `unresolved_sheets`。Fake layout 选择 s2 的本地 auxiliary candidate 后，本地应用保留 s1 三条记录，形成 3 个 extraction units，执行 3 次 Fake extraction，并完整发布恰好五类结果。

若 Fake layout 返回 s2 unresolved：1 次 Fake layout 后立即停止；Fake extraction、字典、物料和五类发布调用均为 0。

## 9. 本地应用、持久化与重试

成功应用只从本地候选恢复 block、record、scope、evidence；辅助 Sheet 不贡献任何记录。应用结果重新过滤本地结构对象并验证至少能够形成 block、record 与 evidence。

Job 仅持久化白名单摘要：

- structure/layout/prompt 版本；
- context SHA 与 operation identity SHA；
- overall status、validation/apply status；
- Sheet ID、role、本地 candidate ID、固定 reason。

不持久化请求正文、Sheet 摘录、Prompt、原始响应或业务字段值。

已 `resolved + applied` 的摘要只有在以下身份全部相同才可重放：

- source/context SHA（间接绑定 source SHA、preprocessor、context/layout version）；
- Provider；
- model；
- layout prompt version。

精确命中时重跑只重放本地应用，layout call 为 0；模型或任何上述身份变化时必须重新调用 layout。旧 status-only 或缺少 operation identity 的历史摘要只读保留，但不能进入新重放路径。`ambiguous` 摘要不自动复用为成功，用户 retry 可重新发起受控结构调用。

## 10. 单 Job Token 与遥测

V2 Job 在执行前记录 Provider 累计计数与 usage 快照，完成或暂停时保存 delta：

- extraction logical calls；
- layout calls；
- HTTP attempts；
- input/output/total tokens。

测试从 Provider 会话累计 `1500 total tokens / 100 HTTP attempts` 起步；当前 Job 实际新增 1 次 layout + 3 次 extraction，页面保存 `30 total tokens / 4 HTTP attempts`，不会再显示会话累计 `1530 / 104`。

## 11. 快速路径、进度与后半链保护

- 全部 Sheet 本地明确时仍不构造 layout 请求，`layout calls = 0`。
- 沿用现有 `structure_resolution` stage，没有新增漂移的前端 stage；D4A-3B 的统一进度映射保持。
- 结构应用成功后接入既有 V2 extraction、provenance、AI-first field resolution、review diagnostics、technical ready、可靠性、字典、物料和原子发布。
- 未修改 normalization、comparison、field policy、review UI、五类 Schema、字典规则或 MaterialMatcher。
- Standard 主解析、Standard 五类结果、TopK、默认导出和单记录 AI Sidecar 均未改变。

## 12. 修改文件

生产代码：

- `src/bedding_order_parser/ai_full_order/preprocessing.py`
- `src/bedding_order_parser/ai_full_order/structure_manifest.py`
- `src/bedding_order_parser/ai_full_order/structure_resolution.py`
- `src/bedding_order_parser/ai_full_order/volcengine_ark.py`
- `src/bedding_order_parser/ai_full_order/orchestration.py`
- `src/bedding_order_parser/ai_full_order/fake_provider.py`
- `src/bedding_order_parser/web/ai_full_order_service.py`
- `src/bedding_order_parser/web/services.py`

测试：

- `tests/ai_full_order/test_v2_multi_sheet_structure.py`
- `tests/ai_full_order/test_v2_structure_path.py`
- `tests/ai_full_order/test_volcengine_ark_full_order_provider.py`
- `tests/web/test_ai_full_order_jobs.py`

## 13. 测试与结果

最终定向命令覆盖：contracts、preprocessing、orchestration、provenance、field policy、V2 offline resolution、V2 reliability、V2 downstream、structure path、新 multi-sheet matrix、Ark full-order Provider、桌面 AI Job、progress、review、Sidecar、routes、services 与单记录 Ark Provider。

结果：

```text
265 passed in 57.69s
git diff --check: passed
compileall: passed
```

虚拟环境未安装 Ruff/Black，本 Gate 未安装任何新依赖；格式与语法通过 `git diff --check`、`compileall` 和定向测试验证。

核心调用计数：

- s1+s2 auxiliary E2E：Fake layout 1，Fake extract 3。
- s1+s2 unresolved：Fake layout 1，Fake extract 0，下游 0，发布 0。
- 第二订单 Sheet 本地 binder/apply 反例：Provider 0，仅验证本地候选应用。
- confirmed-local 快速路径：Fake layout 0，Fake extract 1。
- 已应用摘要同身份重放：第二次 Fake layout 0；模型身份变化后 Fake layout 1。
- 真实 Ark calls：0。
- 真实 external HTTP：0。
- 真实 PI、真实字典、真实物料、BGE-M3、FAISS：0。
- 本轮未读取或重跑用户真实订单；local-only real workbook inspection：未执行。

## 14. 剩余风险与真实验收条件

当前已具备进入“单次真实 Ark 合成多 Sheet 小样本验收”的代码条件：请求包含真正 unresolved Sheet，上下文有界，输出严格版本化，结果可本地验证应用，失败证据可通过白名单 Job 摘要保留。

剩余风险：

- 真实模型是否稳定遵守逐 Sheet decision 数量、candidate ID 与 reason 枚举，仍需一次授权真实合成样本确认。
- 本地候选质量决定 AI 的可选空间；完全无法形成 order candidate 的非标准无编号订单 Sheet仍会保持 unresolved，而不会让 AI 自创 boundary。这是有意保留的安全限制。
- 第一版 auxiliary eligibility 依赖“无本地 block/record candidate + 标准结构 unresolved + 受控 AI role 选择”；真实复杂模板可能需要后续扩展更多本地候选类型，但不能改成自由坐标输出。

## 15. 最终工作区

实现提交后，仅保留起始时已经存在的 7 份未跟踪交接/审计文档；本 Gate 报告将单独提交。无其他已跟踪修改、无暂存残留。
