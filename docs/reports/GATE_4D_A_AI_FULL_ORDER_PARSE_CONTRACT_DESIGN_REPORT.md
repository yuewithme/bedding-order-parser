# Gate 4D-A AI增强整单解析严格合同与架构设计报告

生成日期：2026-08-01
项目目录：`D:\AI-Learning\Projects\bedding-order-parser`

## 1. 当前Git基线

- 分支：`master`
- 初始完整 HEAD：`aa0fcdc88b5ba470dfac16141c64d9ee54674ccf`
- 初始短 HEAD：`aa0fcdc`
- 最近提交：`aa0fcdc fix: handle real ark advisory responses`、`126e67e feat: localize desktop ai advisory`、`4d6b008 feat: connect desktop ai advisory flow`。
- 初始工作区只有任务明确允许保留的两份未跟踪恢复文档：`CODEX_HANDOFF_AND_RECOVERY_2026-07-30.md`、`CODEX_RECOVERY_AUDIT_ROUND_1_REPORT_2026-08-01.md`。
- 未发现未提交业务代码，满足进入本轮设计的前置条件。
- 本轮只新增本报告，不更新交接文档，不修改生产代码、前端、测试、配置或数据。

## 2. 产品目标与不可变边界

产品增加两个互斥入口：`standard`（标准解析）与 `ai_enhanced`（AI增强整单解析）。二者共享上传、Job、字典验证、物料匹配、结果页、历史记录和下载体系，最终都必须发布相同五类核心 JSON：正式 20 字段业务 JSON、解析诊断 JSON、字典验证 JSON、物料候选 JSON、物料匹配摘要 JSON。

不可变边界：

- `FINAL_FIELD_NAMES` 的字段名称、顺序和类型不变；前 19 项为字符串，`相似分数`为浮点数，禁止 `null`、缺字段和额外字段。
- AI 整单阶段只能提取 18 个业务字段，不能生成、建议、回显或确认 ERP `物料编码`，也不能生成任何`相似分数`。
- `物料编码`和`相似分数`仍由现有 SQLite 召回、BGE-M3、FAISS、硬冲突过滤及候选排序阶段产生，再组合为完整 20 字段结果。
- 标准模式冻结：现有 Python 确定性解析、单记录 AI 建议 Sidecar 和五类 JSON 行为不得被新模式改变。
- AI 不是无条件覆盖层。所有非空 AI 值必须有同订单范围内的可验证单元格证据，并经过本地字段决策与现有校验。

## 3. 双模式定义与 `parse_mode`

严格枚举只有 `standard` 和 `ai_enhanced`。禁止布尔型 `allow_ai`、自由文本别名或空字符串。`parse_mode` 是 Job 创建后不可变的原始选择；回退使用独立 `effective_parse_mode` 与 `fallback` 元数据表达，不能篡改原始选择。

| 位置 | 合同 |
| --- | --- |
| 上传请求 | `multipart/form-data` 增加必填 `parse_mode`；服务端枚举校验。新 UI 必须显式提交。兼容旧客户端时，只能在版本化兼容层把缺失值解释为 `standard` 并记录 `parse_mode_source=legacy_default`。 |
| Job 元数据 | `job.json` 持久化 `parse_mode`、`effective_parse_mode`、`parse_contract_version`、`fallback.status/reason/user_confirmed_at`、模型和合同版本；原子写入。 |
| 历史记录 | API 返回原始/有效模式、中文标签和回退状态。旧 Job 缺字段时只读显示“标准解析（历史任务）”，不回写旧文件。 |
| 结果页面 | 固定显示模式。回退时显示“AI增强解析 -> 已确认回退为标准解析”和原因，不得伪装成 AI 成功。 |
| 解析诊断 | 顶层记录模式、合同版本、AI 执行摘要、字段决策和回退；正式业务 JSON 仍只有 20 字段。 |

沿用现有 `queued/processing/completed/failed/interrupted` 顶层状态，在 AI 增强内部持久化 `preprocessing`、`python_shadow_parse`、`ai_layout_recognition`、`ai_block_extraction`、`evidence_validation`、`field_resolution`、`dictionary_validation`、`material_matching`、`publishing`、`awaiting_user_decision` 子阶段。`completed` 只表示五类 JSON 已原子发布，隔离区部分结果不能构成完成。

## 4. AI输入合同

不得上传 Excel 二进制文件。必须先在本地以只读方式计算 SHA-256、双视图加载、裁剪实际使用区域、建立坐标化结构、识别候选订单区块并排除无关数据，再发送版本化 JSON。

建议两个严格请求：

- `WorkbookStructureRequest v1.0`：只识别订单区块和表头/明细作用域，不能返回业务字段。
- `OrderBlockExtractionRequest v1.0`：每次只包含一个或一组不会跨订单证据边界的区块，提取 18 字段。

共同顶层字段固定为 `schema_version`、`prompt_version`、`parse_mode`（const `ai_enhanced`）、`source_file_sha256`、`workbook_manifest_id`、`request_chunk_id`、`sheet_catalog`、`blocks`、`limits`。本地路径、Job ID、API Key、Authorization 和用户账户名不进入 Provider 请求。

### 4.1 Excel双视图与使用区域

同一工作簿本地只读加载两次：`data_only=false`取得公式文本，`data_only=true`取得缓存展示值。读取前后文件 SHA 必须一致；不执行宏，不跟随外部链接。不能直接信任 `max_row/max_column`，应按非空值、公式、合并区域和必要标题重算最小实际范围，剔除仅有格式的远端空白单元格。

每个 Sheet 本地登记 `sheet_id/name/ordinal/visibility/used_range/merged_ranges/hidden_rows/hidden_columns/estimated_chars`。隐藏 Sheet、行列默认不发送；只有本地确认其为当前订单必要证据且确认框单独披露后，才发送相关最小范围，否则标记 `excluded_hidden`。

### 4.2 单元格与结构表示

单元格严格表示为：

```json
{
  "cell_id": "s1!B12",
  "sheet_id": "s1",
  "ref": "B12",
  "display_text": "King Duvet Cover",
  "formula_text": "",
  "value_type": "string",
  "number_format": "General",
  "merged_anchor": "",
  "row_hidden": false,
  "column_hidden": false
}
```

`cell_id`由本地生成且请求内唯一，模型只能引用已有 ID。合并单元格只在锚点保存值，其余位置指向锚点，禁止复制文本制造多重证据。展示值与公式值都不得为 `null`；公式无缓存值时标记 `formula_value_missing`，模型不得自行计算外部引用。空单元格一般不发送，以稀疏坐标和行列边界保持结构。

本地候选区块登记 `block_id/sheet_id/range/block_type/parent_block_id/header_row_ranges/item_row_ranges/section_title_ranges/note_ranges/footer_ranges/candidate_order_scope_id`。多层表头保留层级与合并关系；空行只作边界；章节标题只向同 scope 的后续明细传播；多个订单区块必须有不同 scope；表头和明细作用域为 `workbook/sheet/order_block/record`。备注与页脚仅在业务相关时发送，银行信息、签名、无关联系人等默认排除。

## 5. 方案比较与最终推荐

| 方案 | 优点 | 主要问题 | 结论 |
| --- | --- | --- | --- |
| 单次整表调用 | 实现少 | 易超 Token、串记录、失败重做成本高 | 不采用 |
| 按 Sheet 调用 | 边界直观 | Sheet 内可有多订单，大 Sheet 仍超限 | 不单独采用 |
| 按区块分块调用 | 证据清晰、可恢复 | 依赖可靠分块与表头继承 | 作为提取主体 |
| 预处理后一次结构化调用 | 输入干净 | 大文件和单点失败问题仍在 | 仅作小文件优化 |
| 两阶段识别与提取 | 能处理多 Sheet、多区块 | 编排更复杂、调用更多 | 推荐 |

最终推荐：**本地确定性结构预处理 + 两阶段识别与提取 + 按订单区块发布**。

```text
Excel双视图只读加载
-> 本地稀疏结构清单与候选区块
-> 阶段1：结构识别（只返回区块/作用域/坐标）
-> 本地验证并冻结scope
-> 阶段2：按scope分块提取18字段
-> 严格Schema与证据校验
-> Python shadow字段级对照
-> 字典验证与物料匹配
-> 原子发布五类核心JSON
```

小且结构明确的工作簿可由本地预处理器把阶段 1 判为 `locally_resolved`，但仍使用同一中间合同和证据校验。这是可记录优化，不是第三种产品模式。

## 6. 分块与Token控制

以下是离线实现的初始安全默认值，必须通过 fixture 和真实 API 验收校准，且不能高于 Provider 实际上下文限制：

| 限制 | 初始值 | 超限行为 |
| --- | ---: | --- |
| 上传文件 | 沿用 25 MiB | 上传前拒绝 |
| 候选 Sheet 数 | 12 | 调用前提示改标准或精简 |
| 每 Sheet 实际行/列 | 5,000 / 128 | 仅按完整区块切分；无法安全切分则拒绝 AI 模式 |
| 全工作簿非空候选单元格 | 60,000 | 0 次调用并提示超限 |
| 规范化候选字符总数 | 240,000 | 分块；超过总预算则不调用 |
| 单提取块字符数 | 45,000 | 在记录边界继续拆块 |
| 单 Job 逻辑调用数 | 12 | 保存未发布状态并提示选择 |
| 重试后 HTTP 尝试总数 | 24 | 终止，不无限重试 |

调用前对最终序列化请求、提示和 Schema 估算 Token。优先使用与模型一致的本地 tokenizer；没有可靠 tokenizer 时用 UTF-8 字节和字符数计算保守上界，并记录 `estimation_method`。任何块超过配置输入上限 80% 时继续拆块。拆块只能按 scope 和完整记录，不能任意字符截断；重复表头上下文也计费。响应按 `request_chunk_id/scope_id/record_local_id`去重排序，记录数和身份异常时整批不发布。

## 7. AI输出严格Schema

Provider 函数参数只包含模型有权产生的业务对象；`provider/model/request_id/usage/latency_ms/attempt_count`由本地 Transport 从真实响应写入最终信封，禁止信任模型自报。

`AIOrderExtractionEnvelope v1.0` 顶层固定为：

```text
schema_version, parse_mode, provider, model, source_file_sha256,
prompt_version, preprocessor_version, request_chunk_ids, records,
evidence_catalog, record_count, warnings, unresolved_fields, usage, request_id,
latency_ms, attempt_count
```

所有 object 使用 `additionalProperties:false`，所有字段必填，不允许 `null`。空数组用 `[]`，空字符串用 `""`。`usage`固定为三个非负整数；多块由本地汇总。顶层批次 `request_id`由本地生成，逐调用脱敏 ID 只进入安全诊断。

`evidence_catalog`不是模型自由生成内容，而是本地从已冻结输入目录复制被引用项后组装；每项严格包含 `evidence_id/sheet_name/cell_range/original_text/normalized_text`。字段只返回 `evidence_id`，最终信封仍可自足解析到 Sheet、单元格或范围和原始文本，并可与输入 SHA 复核。

每条记录固定为 `source_record_id/record_local_id/scope_id/sheet_id/primary_row_range/record_ordinal/fields/extraction_status/reasoning_summary/warnings/unresolved_fields`。`record_local_id`由本地生成，模型原样返回。稳定身份为：

```text
sha256(source_file_sha256 + sheet_id + scope_id + primary_row_range
       + record_ordinal + canonical_evidence_cell_id_digest)
```

文件名、Job ID 和本机路径不参与身份；相同 SHA、结构和证据产生相同身份，证据范围变化即失效。

记录级 `extraction_status`只允许 `complete/partial/unresolved/invalid`；只要一个字段为 `ambiguous/invalid`，记录不能标为 `complete`。该状态只描述 AI 提取完整性，不替代后续字段决策和正式发布状态。

严格 18 字段为：客户、币种、业务员、表头备注、行号、物料名称、规格、颜色、面料、面料-涤棉成分、款式、加标方式、尺寸类型、数量、行备注、计划发货日期、包装方式、是否绣花。

每个字段必须出现且只有：

```json
{
  "value": "",
  "original_value": "",
  "evidence_references": [],
  "extraction_status": "source_not_provided",
  "reason": "源文件未提供可验证信息"
}
```

`extraction_status`只允许 `extracted/normalized/source_not_provided/ambiguous/invalid`。`extracted/normalized`要求两个值非空且至少一个证据；`source_not_provided`要求值和证据均空；`ambiguous/invalid`要求正式候选 `value`为空，可保留同 scope 冲突原文并引用证据。`reason`必须简短可展示，禁止私有思维链。`物料编码`或`相似分数`出现在模型参数任意层级即 Schema 失败。`record_count`必须等于数组长度，`unresolved_fields`必须结构化。

## 8. 18字段与最终20字段关系

```text
18字段AI候选 + Python shadow + 本地字段决策
-> 18字段resolved records
-> 现有字典验证
-> 现有物料匹配（只读18字段查询）
-> 匹配层产生ERP物料编码与原型相似分数
-> 按FINAL_FIELD_NAMES组装20字段
-> FinalResult严格校验
-> 五类JSON原子发布
```

AI 请求、响应和字段决策中间件中均不存在可写的物料编码或相似分数槽位。只有现有匹配层拥有这两个字段的生产权；模型即使在理由或 warning 中输出疑似 ERP 编码，也应触发内容安全拒绝，不能传入匹配器。

## 9. 字段证据校验

每个非空字段依次验证：

1. 引用 ID 存在于本次请求冻结证据目录。
2. Sheet 和单元格/范围存在，工作簿 SHA 未变化。
3. 引用落在当前 scope 允许范围内，不能引用其它订单。
4. `original_value`可由所引 `display_text`或允许的公式缓存值按明确规则得到。
5. `value`可由原值通过字段白名单规范化器得到；常识补全、翻译性改写和模糊相似不是证据。
6. 表头级字段只可沿已登记继承链提供，不能跨 Sheet 或订单猜测。
7. 合并引用统一解析到锚点，重复引用不增加证据强度。
8. 同一证据被分配给不同订单且值冲突时，相关字段均为 `ambiguous`。

允许的规范化必须版本化，例如空白清理、Unicode 宽窄字符、批准的币种映射、日期格式、数量无损格式和已批准字典同义词。无证据字段保持空字符串并标记状态。出现身份错位、跨 scope、伪造单元格或值无法追溯时，整个响应块隔离，不能只采纳其中“看起来正确”的字段。

## 10. Python对照和官方结果决策矩阵

Python 在 AI 模式中始终执行同版本 shadow 解析，但在决策完成前不直接发布。比较单位是同一稳定记录的单字段。

| 情形 | 默认决策 | 发布 |
| --- | --- | --- |
| AI 与 Python 一致且 AI 证据有效 | 使用该值，标记 `ai_python_agree` | 可 |
| AI 有证据、Python 为空 | 描述类可用 AI；高风险字段再过确定性验证 | 通过可，否则复核 |
| Python 有证据、AI 为空 | 使用 Python，记录 `ai_omitted` | 可 |
| 冲突且仅一方有直接有效证据 | 用有直接证据者；默认/推导不压过直接证据 | 可，带告警 |
| 双方都有直接证据但冲突 | 不自动选边 | 高风险字段阻止 |
| 双方都无证据 | 空字符串、`source_not_provided` | 可 |
| AI 违反字典/业务约束，Python 合法 | 拒绝 AI，使用 Python | 可，记录原因 |
| 双方均无合法值 | 不生成值 | 关键字段阻止；非关键可空值告警 |
| 记录数、身份、scope 不一致 | 不做字段级合并 | 整批阻止 |

风险分组：

- A 组高风险：客户、币种、业务员、行号、数量、计划发货日期。AI 可提取，但必须通过坐标唯一性、表头作用域、类型/范围、日期/数量无损解析。与直接 Python 证据冲突必须人工复核。
- B 组描述：物料名称、规格、颜色、面料、面料-涤棉成分、款式、加标方式、尺寸类型、包装方式、是否绣花。AI 可作主候选，但必须有同记录证据并过字典/业务约束。
- C 组自由文本：表头备注、行备注。优先保真，AI 只能摘取或按批准规则合并同 scope 原文，不得扩写。

阻止正式 JSON 的条件：记录身份/数量异常、跨订单证据、Schema 失败、A 组未解决冲突、数量或日期不能无损校验、客户作用域冲突、出现模型生成的物料编码/分数、部分块未完成、输入 SHA 改变。回退标准模式只在同 SHA 的 Python 标准管线完整成功且用户调用前预授权或失败后明确确认时允许，禁止静默回退。

## 11. 字典与物料匹配衔接

字段决策后的 18 字段适配为现有 `FinalResult`形状：临时填 `物料编码=""`、`相似分数=0.0`，只为复用验证和匹配接口，不代表 AI 生成。

顺序固定：现有字典验证 -> SQLite 结构化召回 -> BGE-M3 -> FAISS Top 300 -> 硬冲突过滤 -> 字段比较/候选排序 -> Top 10 与摘要 -> 最终 20 字段组装。算法、权重、阈值、物料主数据本阶段不改。AI 中间信封、原请求、Provider 响应和分块状态不进默认 ZIP；解析诊断只放模式、字段决策和脱敏调用摘要。

## 12. 失败和回退

| 场景 | 策略 | 正式JSON |
| --- | --- | --- |
| LLM 未 ready | UI 禁用，API 拒绝 | 不发布；可改标准 |
| 用户取消费用确认 | 不创建 AI Job，不调用 | 不发布 |
| 网络/超时/429 | 有界重试，耗尽后等待用户选择 | 未确认回退前不发布 |
| 非法 Schema | 同版本不自动重试，保存安全诊断 | 不发布 |
| 证据无效/跨记录 | 整块隔离 | 不发布 |
| 记录数/身份异常 | 整批拒绝 | 不发布 |
| Token 超限 | 调用前阻止，调用数 0 | 不发布 |
| 部分分块成功 | 隔离保存，优先续跑缺块 | 不发布半份 |
| 应用关闭 | `interrupted`，按 SHA/版本恢复 | 恢复前不发布 |
| 重复提交 | 返回同活动 Job 或成功缓存 | 不重复调用/发布 |
| 字典/匹配失败 | AI 结果留隔离区，沿用 Job 失败语义 | 不发布 |

默认是“暂停并询问”，确认框可让用户预选“AI失败时暂停并询问（默认）”或“AI失败时允许生成标准结果”。任何回退都记录 `parse_mode=ai_enhanced`、`effective_parse_mode=standard`、原因和确认时间。部分 AI 结果只用于续跑或诊断，不能混入标准回退结果。

## 13. 成本、缓存和幂等

调用前显示 Provider、模型、Sheet/区块/单元格数、隐藏区域、估算输入 Token、最大输出 Token、预计调用数、重试上限、费用区间和回退策略。费用由本地版本化价格配置计算；价格未知或过期时显示“当前无法可靠估算金额”，不能伪造 0 元。

缓存键：

```text
sha256(source_file_sha256 + provider + model + extraction_schema_version
       + prompt_version + preprocessor_version + normalization_rules_version
       + canonical_chunk_manifest_sha256)
```

文件改名但 SHA/结构相同可复用；模型、Schema、Prompt、预处理、规范化或块清单任一变化即失效。复用前重新验证 SHA、Schema、证据和当前业务规则。成功缓存只保存严格输出、规范化摘要、证据索引和调用元数据，不保存完整 HTTP 响应。timeout/429/网络失败只记录短退避；确定性 Schema/证据失败按版本缓存以防无限付费，但允许用户显式强制重试一次。

客户端提交 `idempotency_key`，服务端同时以文件 SHA、模式和合同版本生成业务键。同键只允许一个活动 Job；每 Job 锁外增加跨 Job cache-key single-flight 锁。块状态原子持久化 `pending/running/succeeded/failed/validated`，恢复时只跑未验证块。分别统计逻辑调用数与 HTTP 尝试数，不能隐藏重试。

## 14. 隐私与安全

允许发送的内容只有用户确认范围内、与 PI 提取直接相关的 Sheet 名、坐标、展示值、必要公式、合并/表头/区块关系，以及 18 字段 Python shadow 候选与脱敏诊断。客户、产品、数量、日期和备注属于会外发的业务数据，确认框必须明确说明。

禁止发送或保存到 Provider 诊断：API Key、Authorization、Cookie、环境变量原值、本机路径/用户名/Job 根目录、无关联系人、银行账户、签名、默认排除的隐藏内容、完整 Excel 二进制、完整 HTTP 请求/响应、系统提示和私有思维链。

本地可保存原上传文件（沿用现有边界）、SHA、最小结构清单、严格请求摘要、严格输出、证据验证、字段决策、安全 request ID、usage、耗时和错误分类。日志只记录数量、版本、阶段、脱敏 ID 和错误码。Provider 请求继续 `store=false`；错误只落白名单诊断；Git fixture 只能用人工脱敏数据。

## 15. UI流程

上传页使用单选：

```text
解析方式
● 标准解析
○ AI增强解析
```

AI 模式说明：整份 PI 的必要订单内容会发送给豆包；会产生 Token 费用且更慢；结果仍经过本地校验；AI 不会生成 ERP 物料编码。LLM 未 ready 时禁用 AI 项并显示配置状态，标准模式始终可用。

选择 AI 后先本地预扫描，再弹确认框，显示数据范围、模型、调用数、Token/费用、隐藏范围和回退策略。用户必须明确同意数据发送与费用。进度依次显示读取、结构预处理、Python 对照、区块识别、AI 分块、证据校验、字段决策、字典、匹配和发布。

失败页显示失败阶段、是否已调用、已用 Token、可续跑块，以及“重试缺失块 / 明确回退标准 / 保留失败退出”。结果首屏和历史列表显示原始/有效模式、回退、模型、Token 和耗时；存在发布阻断时只有预览，下载不可用。标准模式单记录 AI 复核仍是独立手动 Sidecar，不能与整单模式混成一个开关。

## 16. 测试与验收计划

| # | 内容 | 模型分工 | 通过标准 |
| ---: | --- | --- | --- |
| 1 | 严格 Schema、无 null/额外字段、18/20 隔离、身份/证据单测 | GPT-5.6 主导；GPT-5.5 补 fixture | 物料编码/分数注入必失败 |
| 2 | FakeProvider 整单、块汇总、usage、缓存 | GPT-5.5 实现；GPT-5.6 审聚合 | 0 网络、可重复注错 |
| 3 | 多 Sheet、合并、多层表头、公式、隐藏、多区块、页脚 fixture | GPT-5.5 构造；GPT-5.6 复核异常 | 坐标/scope 可追踪 |
| 4 | Python shadow 逐字段比较矩阵 | GPT-5.6 主导 | 所有分支有测，高风险冲突不发布 |
| 5 | 字典、SQLite、BGE-M3、FAISS、硬冲突衔接 | GPT-5.6 设计；GPT-5.5 回归 | 不改权重，五类身份一致 |
| 6 | 大文件、分块、重试、取消、关闭恢复、重复提交 | GPT-5.6 主导并发；GPT-5.5 压测 | 不重复收费、不半发布 |
| 7 | 单份复杂 PI 真实 API | 必须 GPT-5.6 | 用户逐次授权，记录真实 Token/耗时 |
| 8 | 五类 JSON、20 字段、ZIP | GPT-5.6 审发布门 | 缺一类即不发布 |
| 9 | 桌面双模式、确认、失败、历史、缓存 UI | GPT-5.5 实现；GPT-5.6 验收 | 模式/回退无误认，多视口正常 |
| 10 | 12 份 PI 标准模式冻结回归 | GPT-5.5 执行；异常交 GPT-5.6 | 49 条 18 字段零差异，匹配不回归 |

阶段 1 至 6 完全离线；阶段 7 是唯一真实 Provider Gate，必须另行取得数据发送、调用次数和费用授权。完整 pytest、BGE-M3/FAISS 和 12 PI 回归只在对应后续 Gate 执行，本设计轮均不执行。

## 17. 风险清单

| 风险 | 控制 |
| --- | --- |
| 多区块串证据 | scope 冻结、引用白名单、跨 scope 整块拒绝 |
| 伪使用区域过大 | 重算范围、稀疏表示、调用前硬限 |
| 合并/多层表头丢语义 | 锚点、层级表头、继承链 |
| 公式缓存过期 | 双视图、公式状态、确定性校验，不执行公式 |
| 无证据幻觉 | 非空字段强制证据，无法追溯即空/拒绝 |
| AI/Python 冲突 | 风险分组矩阵和人工门 |
| 部分块成功 | 隔离、全批发布门、续跑缺块 |
| 重试/重复多收费 | 幂等、single-flight、总尝试上限 |
| 升级复用旧缓存 | 所有版本进入缓存键 |
| PI 过度外发 | 最小范围、隐藏默认排除、确认披露 |
| 原始响应落盘 | 白名单诊断，不存 HTTP body |
| 标准模式回归 | 独立编排、标准默认、12 PI 保护 |
| 模型注入物料编码 | Schema 无槽位、内容拒绝、匹配层唯一生产权 |
| 中断假完成 | 原子状态、五产物一次发布门 |

## 18. 推荐实施拆分

1. **Gate 4D-B1：离线合同基础。** 实现 `parse_mode`领域枚举、Excel 稀疏结构/证据模型、整单输入输出 Schema、FakeProvider、证据验证和纯单测；不接 UI、真实 API、BGE-M3/FAISS。
2. **Gate 4D-B2：离线编排与决策。** 实现 Python shadow、分块聚合、字段矩阵、隔离区、缓存、幂等和恢复。
3. **Gate 4D-B3：五类产物衔接。** 不改权重地连接字典和匹配，验证 18->20 与原子发布。
4. **Gate 4D-C：桌面双模式 UI。** 上传单选、费用确认、进度、失败选择、结果/历史；仍用 FakeProvider。
5. **Gate 4D-D：单份复杂 PI 真实 API。** 用户另行授权并限制调用次数。
6. **Gate 4D-E：冻结验收。** 五类 JSON、双模式、缓存/恢复及 12 PI 标准回归。

每个 Gate 单独报告、提交并记录真实调用次数；不得跨 Gate 偷跑真实 API 或修改匹配权重。

## 19. 适合使用GPT-5.5的任务

- 按冻结合同实现简单 dataclass、序列化、路由字段和 UI 文案。
- 批量编写脱敏 Excel/FakeProvider fixture 和参数化反例。
- 执行整理定向测试、12 PI 标准回归和多视口页面检查。
- 实现无争议的历史显示、中文标签、进度映射和文档。
- 在 GPT-5.6 已冻结的决策表下补机械分支测试。

GPT-5.5 不应独立修改严格 Schema、证据信任边界、高风险字段裁决、发布门、缓存身份或真实 API 方案。

## 20. 必须使用GPT-5.6的任务

- 严格输入/输出 Schema、稳定身份和证据引用合同的首次实现与终审。
- 多区块/跨 Sheet 作用域、分块聚合、字段矩阵和发布阻断。
- 隐私最小化、Provider 安全、物料编码/分数隔离和缓存失效。
- single-flight、关闭恢复、部分成功隔离和重复收费防护。
- 字典/匹配首次衔接与 18->20 最终发布审查。
- 单份复杂 PI 真实 API Gate 及 Schema/证据不兼容诊断。
- 12 PI 回归出现差异时的根因与修复决策。

## 21. 是否具备进入离线实现条件

结论：**具备，但仅限 Gate 4D-B1 离线合同基础。** 本报告已定义双模式、输入结构、输出 Schema、18/20 分工、证据、Python 对照、失败回退、缓存幂等、隐私、UI 和验收顺序。初始限制值仍须用脱敏 fixture 校准；B1 至 B3 完成前不具备真实 API 或正式 PI 验收条件。

本轮真实 API 调用 0，未解析真实 PI，未运行 BGE-M3、FAISS 或 pytest，未修改任何正式结果。

## 22. 下一步唯一建议

**Gate 4D-B1：仅离线实现 `parse_mode`领域合同、Excel 稀疏证据预处理、AI 整单严格输入/输出 Schema、证据验证器和 FakeProvider 单元测试；不接前端、不调用真实 API、不运行 BGE-M3/FAISS、不修改物料匹配算法。**

## 23. 本轮Git与交付说明

- 本轮只提交 `docs/reports/GATE_4D_A_AI_FULL_ORDER_PARSE_CONTRACT_DESIGN_REPORT.md`。
- 提交信息：`docs: design ai enhanced order parsing`。
- 不执行 `git add .`、amend、tag 或 push。
- 报告与提交同处一个 commit，哈希无法在提交前自引用；以提交后 Git 输出和最终回复为准。
- 两份既有未跟踪恢复文档保持原状，不清理、不暂存、不提交。
