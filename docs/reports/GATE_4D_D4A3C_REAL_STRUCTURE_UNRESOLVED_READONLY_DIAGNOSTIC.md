# Gate 4D-D4A-3C：真实 AI_V2_STRUCTURE_UNRESOLVED 失败任务只读根因诊断

## 1. 审计范围与仓库基线

本 Gate 是严格只读诊断。除本报告外，没有修改生产代码、测试、Prompt、Contract、UI、配置、Job 状态、缓存或真实上传文件；没有重新运行失败任务，也没有进行新的 Provider 或网络调用。

- 分支：`master`
- 起始完整 HEAD：`dde486639af572dc630a84774fc22e46f3cc7169`
- 起始短 HEAD：`dde4866`
- D4A-3B implementation commit：`8a11eb76c7231a6d9e0963aa2193e06f68ca2c50`
- D4A-3B report commit：`dde486639af572dc630a84774fc22e46f3cc7169`
- 起始已跟踪工作区：干净
- 起始未跟踪内容：7 份既有交接、恢复或架构审计文档，均未修改、暂存或清理

失败 Job 创建于 D4A-3B 两个提交之前、D4A-3 报告提交之后。D4A-3B 只修改进度展示同步，不修改 `preprocessing.py`、`structure_manifest.py`、`volcengine_ark.py` 或 `ai_full_order_service.py`，因此当前 HEAD 的结构执行语义与该 Job 运行时一致。

## 2. 失败 Job 的安全身份

通过 parse mode、安全错误码、调用计数、HTTP 次数、Token、区块进度、时间和五类结果状态交叉筛选，唯一匹配截图的 Job 为：

| 安全事实 | 值 |
| --- | --- |
| Job ID | `cac47af71b404e7b8b1ba0e3bdf5c106` |
| 创建时间 | `2026-08-09T14:23:41+08:00` |
| 最后状态写入 | `2026-08-09T14:23:50.4265120+08:00` |
| 状态 | `awaiting_user_decision` |
| parse mode / effective mode | `ai_enhanced` / `ai_enhanced` |
| Contract | `2.0` |
| source SHA 安全前缀 | `b009aa358c6d` |
| 文件大小 | 58,848 bytes |
| safe error | `AI_V2_STRUCTURE_UNRESOLVED` |
| Provider / 模型 | `volcengine_ark` / `doubao-seed-2-0-lite-260428` |
| 脱敏 request ID | `resp_0...1ab6` |
| logical / layout / HTTP | `1 / 1 / 1` |
| 区块进度 | `0 / 0` |
| 五类结果 | 0 类；未发布 |

同类错误 Job 在本机共有 5 个，但只有该 Job 同时满足创建时间最新、总 Token `10572`、调用 `1/1`、区块 `0/0` 和截图所示模型，因此身份可唯一确认。

## 3. 本次真实状态时间线

以下区分代码理论路径与本次持久化证据。中间阶段没有单独时间戳，因此 T1-T6 表示确定的执行顺序，不虚构精确时刻。

| 时点 | 代码路径 | 本次输入/输出 | 实际证据 |
| --- | --- | --- | --- |
| T0 | `JobService.create_job()` | 创建 V2 `ai_enhanced` Job | Job 创建时间、Contract 2.0、source SHA |
| T1 | `JobService._run_job()` → `_run_ai_enhanced_job()` | 按 V2 分派 | requested/effective mode 均为 `ai_enhanced` |
| T2 | `run_ai_enhanced_v2_job()` → `preprocess_workbook()` | 本地双视图结构预处理 | stage history 含 `preprocessing`；纯本地复盘得到 `ambiguous` |
| T3 | `run_ai_enhanced_v2_job()` 约 297 行 | 进入 ambiguous 分支 | stage history 含 `structure_resolution` |
| T4 | `build_chunk_manifest()` → `build_structure_manifest()` | 构造 1 个 s1 chunk | 本地确定性复盘：manifest v1.0、chunk count 1 |
| T5 | `VolcengineArkFullOrderProvider.resolve_structure()` | 发起一次 `submit_bedding_order_layout` | `layout_calls=1`、HTTP=1、有效 request ID、contract diagnostic 为空 |
| T6 | `run_ai_enhanced_v2_job()` 约 316 行 | 忽略返回状态并无条件抛出 `AI_V2_STRUCTURE_UNRESOLVED` | safe error、stage history、无 Provider failure |
| T7 | `JobService._pause_ai_job()` | 写入等待用户决定 | status、0/0、无 artifacts、无 runtime cache identity |

`build_v2_extraction_units()` 位于上述无条件抛出之后，本次没有执行；Python shadow、`extract_v2`、证据绑定、字段裁决、字典、物料和发布均未开始。

## 4. 本地 preprocessing 判定

使用当前 HEAD 的 `preprocess_workbook(path)`，不传 `structure_resolver`，在内存中只读重建结构事实。该 helper 自带读取前后 SHA 一致校验，不写 Job、缓存或上传文件。

### Sheet 结构摘要

| Sheet ID | 可见 | used range | sparse cells | 合并锚点 | Standard geometry | Heuristic |
| --- | --- | --- | ---: | ---: | --- | --- |
| `s1` | 是 | `A1:I31` | 260 | 31 | stable，`standard_geometry_aligned` | 1 block / 3 records / 非歧义 |
| `s2` | 是 | `A1:R12` | 192 | 0 | unstable，`standard_table_unresolved` | 0 block / 0 record / ambiguous |

### s1 的可证明结构

- Standard header rows：9、10。
- Standard record rows：11、12、13。
- Standard parsed records：3；selected records：3。
- 本地 aligned block：`s1:block-1`，scope `s1:scope-1`，范围 `A9:I13`。
- 本地 records：3；证据总数：29；evidence mapping failure：0。
- 没有辅助编号行，也没有显式第二订单表信号。

### s2 的歧义触发

- s2 有 12 个非空结构行，但标准解析器无法建立标准表格几何，reason 为 `standard_table_unresolved`。
- `_numbered_row_groups()` 得到 0 组；因此 `_build_blocks()` 在 `preprocessing.py` 约 442 行执行 `ambiguous = not data_groups`，结果为 `true`。
- s2 有表头特征行，但没有可绑定的编号记录组，所以 heuristic 也无法形成 block、record identity、scope 或 evidence catalog。
- `preprocess_workbook()` 对所有 included Sheet 使用 `unresolved_structure = unresolved_structure or ambiguous`；即使 s1 已安全对齐，s2 的 `true` 仍使工作簿最终为 `ambiguous`。

结论：本次不是 s1 的三条订单记录对不齐，也不是合并单元格、隐藏内容、第二订单表信号或 evidence mapping failure。直接触发条件是第二个可见 Sheet 无法由 Standard geometry 或编号行 heuristic 形成安全记录边界。

## 5. Structure manifest 摘要

本地复盘得到：

```text
manifest_version = 1.0
source SHA prefix = b009aa358c6d
chunk count = 1
chunk = s1:block-1 / s1:scope-1 / A9:I13
record identities = 3
record local IDs = 3
evidence IDs = 29
status = pending
```

这里存在决定性的上下文缺口：

1. `build_chunk_manifest()` 只遍历已经形成的 `preprocessed.blocks`；s2 没有 block，因此不会生成 chunk。
2. `build_structure_manifest()` 只有在整个 `chunk_payloads` 为空时，才调用 `_unresolved_sheet_chunks()`。
3. 因为 s1 已经有一个 chunk，s2 的 unresolved sheet fallback 不会加入 manifest。
4. Provider 实际收到的 `safe_manifest` 只含 `chunks`；不包含 s2，也不包含任何单元格文本或 sparse geometry。

因此这次 layout 调用没有得到导致全局 ambiguous 的 s2 结构。它只能看到 s1 的一个已知 chunk 身份摘要，无法据此解决 s2。

## 6. Structure Provider operation 与结果边界

### 已确认的事实

- operation 是 `resolve_structure()`，函数名 `submit_bedding_order_layout`。
- `structure_call_count` 增加 1，HTTP attempt 增加 1。
- Ark 响应通过 `_structured_result()`、Provider metadata/usage 校验和 layout 严格枚举校验；否则会映射为 `AI_V2_STRUCTURE_PROVIDER_FAILED`，而不是本次错误码。
- `latest_contract_diagnostic` 为空，说明没有 request/schema/metadata 失败。

### 无法从持久化证据确认的事实

Provider 返回的具体 status 没有保存。当前 `_LAYOUT_SCHEMA` 只允许：

```text
{"status": "resolved"}
或
{"status": "ambiguous"}
```

`run_ai_enhanced_v2_job()` 调用 `provider.resolve_structure(structure_manifest)` 时没有接收返回值，随后无条件抛出 `AI_V2_STRUCTURE_UNRESOLVED`。Job 目录没有结构结果文件、缓存或 runtime state，日志代码也没有安全持久化该 status。

所以可以确认“Provider 返回了一个严格合法的状态”，但无法确认究竟是 `resolved` 还是 `ambiguous`。报告不会通过 Token、0/0 或历史 fixture 猜测结果。

## 7. Extraction unit、缓存与发布状态

- `extract_v2` logical calls：0。
- field extraction HTTP attempts：0。
- validated extraction units：0。
- cached extraction units：0。
- `ai-runtime`：不存在。
- V2 reliability state：不存在。
- `ai-bundle`：不存在。
- results/match：目录存在但文件数均为 0。
- runtime cache identity：cache key、manifest SHA、execution ID、disposition 均为空。
- dictionary、material matcher、五类发布：均未调用。

`0 / 0` 的含义不是“0 个 unit 已成功处理”，而是 ambiguous 分支在 `build_v2_extraction_units()` 之前抛出，`AIEnhancedJobPause.execution` 为空；`JobService` 因此将 completed 和 total 都写为 0。

## 8. Telemetry 与 10572 Token 来源

截图中的 `10572` 不是本次调用独占 Token，而是同一 Provider 进程生命周期的累计 `usage_summary`。

同一 owner session、同一 PID 中的安全累计事实：

| 顺序 | Job 类型 | 累计 input | 累计 output | 累计 total | 相对前一 Job 增量 |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | 先前成功 AI Job | 6474 | 1504 | 7978 | - |
| 2 | 同 source 的第一次 structure pause | 7734 | 1541 | 9275 | 1297 |
| 3 | 本次目标 structure pause | 8994 | 1578 | 10572 | 1297 |

代码原因：

- `VolcengineArkFullOrderProvider._structured_result()` 将每次 usage 累加到 `self.usage_summary`。
- `JobService._pause_ai_job()` 优先持久化 `usage_summary`，不是 `latest_telemetry` 的单次 usage。

因此，本次结构调用的可证明差分是：

```text
input = 1260
output = 37
total = 1297
```

`10572` 由前一成功任务 `7978`，加第一次同源结构调用 `1297`，再加本次结构调用 `1297` 组成。逻辑调用数和 HTTP 次数仍是本次 Job 的 delta；只有 Token UI 使用了 Provider 会话累计口径。

## 9. AI_V2_STRUCTURE_UNRESOLVED 的全部代码来源

| 来源 | 触发条件 | 是否调用 Provider | 是否已有 AI result | 用户文案 | 可 retry |
| --- | --- | --- | --- | --- | --- |
| `run_ai_enhanced_v2_job()` 约 297-321 行 | preprocessed=`ambiguous`；manifest 合法；Provider 返回合法 status；随后无条件 pause | 是 | 有合法 status，但未持久化 | 订单结构暂时无法安全确认 | 是；当前会重新执行完整结构调用 |
| `run_ai_enhanced_v2_job()` 约 323-329 行 | 非 ambiguous，但 `build_v2_extraction_units()` 返回空 | 否 | 无 | 同一安全文案 | 是 |

本次属于第一行，证据是 `layout_calls=1`、HTTP=1、stage history 到 `structure_resolution`、contract diagnostic 为空。

Provider/Transport 异常另有 `AI_V2_STRUCTURE_PROVIDER_FAILED`；本地 manifest 身份失败另有 `AI_V2_STRUCTURE_MANIFEST_INVALID`，都不是本次路径。

## 10. 当前 HEAD 的 resolved 结构应用能力

当前 HEAD 不能把 Provider 的 `resolved` 结果应用为 extraction units，且“resolved manifest”这一历史叫法并不精确：

- Provider output Schema 只返回一个 `status`，根本不返回 chunks、block boundary、record mapping、scope mapping 或 evidence mapping。
- service 不读取 status 值，也不保存它。
- ambiguous 分支无论 status 为 `resolved` 还是 `ambiguous` 都立即 pause。
- extraction units 仍只能由本地 `PreprocessedWorkbook.blocks/records` 构造。

所以当前缺口不是“已有完整 resolved manifest，但 binder 尚未接上”，而是三层能力同时缺失：

1. request manifest 没有覆盖实际 unresolved Sheet；
2. output contract 没有可应用的结构决策或映射；
3. service 没有 validate/bind/apply 路径。

## 11. 关键问题逐项回答

### Q1 为什么本地 preprocessor 把这份订单判定为 ambiguous？

**结论：** s1 已安全识别为 3 条记录；s2 是可见且有内容的 Sheet，但 Standard geometry 返回 `standard_table_unresolved`，heuristic 又找不到编号记录组，因此 s2 被判 ambiguous，并通过工作簿级 OR 汇总使全局 ambiguous。

**证据：** s1 `A1:I31`、aligned records=3；s2 `A1:R12`、numbered groups=0、blocks=0、records=0、heuristic_ambiguous=true；`possible_secondary_table_count=0`、`evidence_mapping_failure_count=0`。

**置信度：** 高，当前代码和真实文件的纯本地确定性复盘一致。

### Q2 截图中的 1 次逻辑 AI 调用是否确认是 resolve_structure()？

**结论：** `CONFIRMED`。它是一次 `resolve_structure()` / `submit_bedding_order_layout`，不是 `extract_v2()`。

**证据：** `layout_calls=1`、logical calls=1、HTTP=1；stage history 为 preprocessing → structure_resolution → awaiting；ambiguous 分支的 pause 将 logical calls 计算为 provider calls 0 + layout calls 1；可靠性运行时不存在。

**置信度：** 高。

### Q3 Provider 结构结果到底是什么？

**结论：** `not persisted / INSUFFICIENT EVIDENCE`，无法在 `resolved` 与 `ambiguous` 之间确认；但可以确认它是严格合同允许的合法枚举值。

**证据：** 若响应解析、metadata、usage 或 status 枚举失败，会进入 `AI_V2_STRUCTURE_PROVIDER_FAILED`；本次进入 unresolved 且 contract diagnostic 为空。Job/runtime/cache 没有保存 status。

**置信度：** 对“合法枚举”高；对具体枚举值无法判断。

### Q4 如果 resolved，在哪个本地函数/条件被挡住？

**结论：** 如果返回 `resolved`，它在 `run_ai_enhanced_v2_job()` 的 ambiguous 分支中被挡住：约 308 行调用 Provider，返回值被丢弃，约 316 行无条件抛出 `AI_V2_STRUCTURE_UNRESOLVED`。没有进入约 323 行的 extraction unit 构造。

**证据：** 当前函数没有结果变量或 status 分支；layout Schema 也只返回 status，不返回可绑定 manifest。

**置信度：** 高，但这是条件性结论；本次是否 resolved 无法确认。

### Q5 如果 ambiguous，具体缺什么？

**结论：** 若 Provider 返回 `ambiguous`，现有持久化证据无法提供模型 reason；从 request 侧可以确定，它根本没有收到实际歧义来源 s2，只收到 s1 的单个 chunk 身份摘要，而且没有单元格结构内容。因此不能将结果归因于模型能力不足，更强证据指向 request/context 和 output contract 不足。

**证据：** manifest chunk count=1，仅 `s1:block-1`；`_unresolved_sheet_chunks()` 只有全局无 chunk 时才启用；layout output Schema 只有 status，无 reason/category/mapping。

**置信度：** 对 request/context 缺口高；对 Provider 内部判断原因无法判断。

### Q6 10572 Token 来自哪里？

**结论：** `CONFIRMED` 为同一 Provider 会话累计值，不是本次结构调用独占值。本次调用差分为 input 1260、output 37、total 1297。

**证据：** 同一 owner session/PID 的三个 AI Job 累计 total 依次为 7978、9275、10572；两次差分均为 1297；代码持久化累计 `usage_summary`。

**置信度：** 高。

### Q7 为什么区块进度是 0/0，是否在 extraction 前失败？

**结论：** `CONFIRMED` 在字段 extraction 前停止。0/0 表示 extraction units 尚未构造，非“构造了 0 个并执行完”。

**证据：** ambiguous 分支在 `build_v2_extraction_units()` 之前抛出；pause 没有 execution，JobService 因而写 0/0；无 `ai-runtime`、无 unit state、无 cache identity、无 bundle；extract_v2 calls=0。

**置信度：** 高。

### Q8 当前是否仍有 resolved-manifest 应用缺口？

**结论：** `YES`，而且比历史措辞更基础。当前既没有完整 resolved manifest 输出合同，也没有本地 apply/bind 路径；即使 status=`resolved`，仍会无条件 pause。

**证据：** `_LAYOUT_SCHEMA` 只有 status；service 丢弃结果；manifest 还遗漏实际 unresolved s2。

**置信度：** 高。

## 12. 根因树

```text
AI_V2_STRUCTURE_UNRESOLVED
|
+-- 本地触发
|   +-- s1：3 条标准记录已安全对齐
|   +-- s2：可见、有内容，但 standard_table_unresolved
|       +-- heuristic numbered groups = 0
|       +-- 无 block / record / scope / evidence binding
|       +-- workbook 级 ambiguous = true
|
+-- Structure request 缺口
|   +-- manifest 只遍历已有 blocks
|   +-- s1 已有 chunk，阻止 unresolved-sheet fallback
|   +-- 实际歧义来源 s2 未进入请求
|   +-- 请求也不含可分析的 sparse cell geometry/text
|
+-- Structure output 合同缺口
|   +-- 只允许 status=resolved|ambiguous
|   +-- 无 reason、boundary、record mapping、scope/evidence mapping
|
+-- 本地应用缺口
|   +-- Provider 返回值未接收、未持久化
|   +-- 无论 status 都无条件 pause
|   +-- extraction units / extract_v2 / downstream 均未开始
|
+-- Telemetry 展示问题（非主失败原因）
    +-- Token 使用 Provider 会话累计值
    +-- UI 的 10572 不是本次单次调用成本
```

## 13. 下一 Gate 建议

建议下一 Gate 为：

```text
Gate 4D-D4A-3D：V2 多 Sheet 结构上下文、受控结构决策与本地绑定合同离线实现
```

建议范围按以下顺序：

1. 先冻结 Sheet role 政策：有已对齐订单 Sheet 时，另一个无编号记录的可见 Sheet应被认定为辅助 Sheet，还是必须交给结构 AI；不能继续用“任一 visible Sheet unresolved → 全局 ambiguous”而不说明角色。
2. 修改 manifest 生成语义，使已知 chunks 与 unresolved sheets 可以同时存在；不得再因 s1 有 chunk而遗漏 s2。
3. 给 Provider 发送最小、受控、无敏感正文的结构几何候选，且只允许 AI 从本地候选 ID 中选择或分组，不允许 AI 生成 source SHA、record identity、scope 或证据身份。
4. 设计版本化 layout output，至少包含可本地验证的 sheet/chunk decision 与固定 reason category；不要仅返回 status。
5. 建立 local validator/binder/apply 边界，通过后才能生成 extraction units；unknown ID、跨 Sheet/scope、缺失 record identity 继续 hard block。
6. 安全持久化 operation status、固定 reason 和单次 usage；不要保存 raw response，也不要把进程累计 Token当单 Job Token。
7. 先用合成多 Sheet fixture 和当前真实文件的纯本地只读 geometry 做离线验收；真实 Ark 重试应另设调用授权 Gate。

不建议当前直接增强 Prompt或换模型。现有调用没有获得 s2 上下文，模型能力尚未被有效测试。

## 14. 调用计数与未执行事项

- 本次新 Ark logical calls：0
- 本次新 Provider calls：0
- 本次新外部 HTTP attempts：0
- 本次真实 PI 上传/重跑：0
- 本次 `extract_v2` calls：0
- 被诊断历史 Job 的 structure calls：1
- 被诊断历史 Job 的 extract_v2 calls：0
- BGE-M3 / FAISS /真实字典 /真实物料：0
- pytest：未运行，符合只读诊断 Gate 原则

执行过的动态检查只有无副作用的本地 deterministic inspection：读取现有 workbook 两个视图、重算 SHA/used range/geometry、构造内存 manifest 摘要；没有传入 structure resolver，没有创建 Job/runtime/cache，也没有保存业务内容。

## 15. 未修改代码与现场保护证明

- 除本报告外，Git 没有已跟踪修改。
- 没有修改或清理开始前的 7 份未跟踪文档。
- 真实 Job 的 `job.json` 在审计前安全哈希前缀为 `c58f8ffc8a8e`，最后修改时间保持 `2026-08-09T14:23:50.4265120+08:00`；提交前再次核验。
- 真实上传文件 source SHA 前缀保持 `b009aa358c6d`，最后修改时间保持 `2026-08-09T14:23:41.0006374+08:00`；预处理 helper 也验证读取前后完整 SHA 一致。
- 没有输出或提交真实订单正文、文件名、本机绝对路径、API Key、Authorization、raw request、raw response、Prompt 或私有思维链。

## 16. 最终结论

一句话根因：**第二个可见 Sheet 无法形成本地安全记录边界，导致工作簿进入 ambiguous；但 layout 请求只携带第一个已解析 Sheet 的 chunk，当前 Provider 又只能返回且本地不保存一个状态枚举，service 随后无条件暂停，因此任务在 extraction units 构造前以 `AI_V2_STRUCTURE_UNRESOLVED` 结束。**

这不是已证实的“模型能力不足”，也不是 AI/Python 业务字段冲突。它是结构输入覆盖、输出合同和本地应用路径三者共同缺失造成的确定性架构暂停。
