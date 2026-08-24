# Gate 4D-D3B-2C｜AI 整单 Contract V2 桌面后端与 Job 生命周期离线接入报告

## 1. 基线、提交与范围

- 分支：`master`
- 准确起始完整 HEAD：`22bd374dbc1878a4031f72081554e4f09b0d9971`
- 起始短 HEAD：`22bd374`
- 起始提交：`feat: add ai full-order v2 reliability and publication`
- 准确实现提交：`e1196f278c04220eebf1275c71f082880e7a034c`
- 实现提交信息：`feat: integrate ai full-order v2 desktop backend`
- 报告采用任务规定的两提交方式：实现先提交，本报告随后单独提交；报告提交准确哈希由提交后的最终中文交接给出，避免 Markdown 自引用哈希不可能固定的问题。
- 起始已跟踪工作区干净；六份既有未跟踪交接、恢复和架构审计文档保持原样，未修改、未清理、未暂存。
- 本 Gate 只接入桌面后端、Job 生命周期、API 状态和既有页面兼容；未修改前端 HTML/CSS/JavaScript。

## 2. 实际修改文件

| 文件 | 修改目的 |
| --- | --- |
| `src/bedding_order_parser/web/ai_full_order_dependencies.py` | 正式桌面依赖工厂显式声明 Contract V2。 |
| `src/bedding_order_parser/web/ai_full_order_service.py` | 增加 V2 桌面窄编排入口，组合预处理、单目标 unit、Python shadow、V2 可靠性与 V2 发布。V1 入口保留。 |
| `src/bedding_order_parser/web/services.py` | 新 Job V2 持久化、legacy 判定、V1/V2 显式分派、阶段进度、暂停/恢复/回退、五角色和 Bundle 身份校验。 |
| `tests/web/test_ai_full_order_jobs.py` | 增加 V2 Job、legacy、缓存、恢复、并发、字段隔离、硬失败、发布失败和结果 API 离线矩阵。 |
| `tests/ai_full_order/test_volcengine_ark_full_order_provider.py` | 增加正式 Ark V2 Provider + FakeTransport 桌面成功链；历史桌面用例显式标记 legacy V1。 |
| `tests/ai_full_order/test_acceptance_diagnostics.py` | 历史 D2 诊断矩阵显式标记 legacy V1，继续验证 V1 白名单诊断与清理。 |

未新增依赖，未修改冻结的 V2 Schema、provenance、字段政策、可靠性、发布实现或标准解析算法。

## 3. 新 Job 的 V2 Composition 路径

新建 `ai_enhanced` Job 固定记录 `ai_contract_version=2.0`，由 `JobService._run_ai_enhanced_job()` 按持久化版本显式调用 `run_ai_enhanced_v2_job()`：

```text
上传与 Job 创建
-> preprocess_workbook
-> 本地 structure_status 判断
-> build_v2_extraction_units
-> build_deterministic_python_shadow
-> Provider.extract_v2
-> V2ReliableOrchestrator / V2ReliabilityStore
-> evidence binding 与 V2 字段裁决
-> publish_ready_v2_batch
-> 既有五类核心 JSON
-> completed
```

- V2 不先尝试 V1，不按响应字典形状猜版本，不失败后静默切换 V1 或 standard。
- 正式依赖工厂仍构造 `VolcengineArkFullOrderProvider`，但本轮通过 FakeTransport 验收，真实网络为 0。
- Provider import、实例化、配置检查、预检、Job 创建、历史与结果查看均不调用 Transport。
- 本地结构明确时直接构造单目标 extraction units；两记录 fixture 对应 2 个 V2 提取调用，layout 调用为 0。
- 本地结构歧义时只调用现有 fake layout 边界 1 次，字段 extraction 为 0。由于当前 layout 返回尚不能被本地确定性地绑定成可靠区块，Job 安全暂停为 `AI_V2_STRUCTURE_UNRESOLVED`，未制造不可靠 unit。

## 4. Legacy V1 兼容规则

- 用户可见模式仍只有 `standard` 和 `ai_enhanced`；V1/V2 只是 `ai_enhanced` 内部协议版本。
- 明确 `ai_contract_version=1.0` 的 AI Job 固定走既有 `run_ai_enhanced_job()` 与 V1 `OfflineReliableOrchestrator`。
- `ai_enhanced` Job 缺少版本字段时只读解释为 `Legacy V1`，来源固定为 `legacy_missing_version`，不得解释成 V2，也不回写旧 Job。
- 新 Job 固定为 V2；未知合同版本安全报错，不使用 Provider 返回形状推断。
- legacy V1 完成任务仍可读取历史和五类结果；V1 Ark FakeTransport 成功、失败及 D2 白名单诊断矩阵继续通过。
- 未完成 legacy V1 继续采用既有安全中断语义；V1 cache/state 不迁移、不读取为 V2。

## 5. Job 持久化合同

新 Job 在既有原子 `job.json` 边界中新增或明确持久化：

```text
parse_mode / requested_parse_mode / effective_parse_mode
ai_contract_version / ai_contract_source
source_identity.sha256 / size_bytes
client_idempotency_identity
business_identity
runtime_cache_identity.cache_key / manifest_sha256 / execution_id / disposition
ai_execution.contract_version / stage / stage_history
ai_execution.completed_chunks / total_chunks
ai_execution.logical_call_count / http_attempt_count / layout_call_count
ai_execution.cache_hit / isolated_field_count / resume_count / last_resume_at
ai_execution.provider / model / request_id / token_summary / safe_error_code
ai_user_decision.status / action / decided_at
fallback.status / reason / user_confirmed_at
```

- `parse_mode` 创建后不可变；测试直接证明修改会被拒绝。
- 回退只改变 `effective_parse_mode`，保留原始 `parse_mode=ai_enhanced`、确认动作、原因和时间。
- API 只返回长度受控、类型校验后的身份和执行摘要；不写入 API Key、Authorization、完整请求/响应、系统 Prompt、模型自由文本或完整 provenance。
- 旧 Job 缺新增字段时由安全默认值读取，不因 Schema 扩展崩溃。

## 6. 阶段与进度映射

V2 成功链的实际 `stage_history` 固定为：

```text
preprocessing
structure_resolution
python_shadow
ai_extraction
evidence_binding
field_resolution
cache_revalidation
dictionary_validation
material_matching
publication
completed
```

阶段使用固定进度基线，`JobService._set_ai_progress()` 取当前进度与新阶段进度的最大值，保证恢复或并发写入不造成无解释倒退。cache 结果仍经过本地重验证与发布阶段；Provider 等待不会显示成裁决完成；下游未执行时不会显示 publication。普通字段隔离完成后，`isolated_field_count` 同时进入 Job/API 和 parse diagnostics。

## 7. 失败、暂停、恢复与回退映射

| V2 事实 | Job 状态 | 固定安全码/行为 |
| --- | --- | --- |
| 结构无法本地确认 | `awaiting_user_decision` | `AI_V2_STRUCTURE_UNRESOLVED` |
| layout fake 调用失败 | `awaiting_user_decision` | `AI_V2_STRUCTURE_FAILED` |
| hard Schema/provenance/identity/scope 失败 | `awaiting_user_decision` | `AI_V2_CONTRACT_FAILED` |
| 高风险 direct conflict | `awaiting_user_decision` | `AI_V2_HIGH_RISK_CONFLICT` |
| transient Provider 当前运行失败 | `awaiting_user_decision` | `AI_V2_TRANSIENT_FAILURE` |
| cache 损坏或重验证失败 | `awaiting_user_decision` | `AI_V2_CACHE_CORRUPT`；不静默删除 |
| 同 cache leader 仍执行 | `awaiting_user_decision` | `AI_V2_IN_PROGRESS`；不重复提取 |
| 应用中断或重启发现遗留 active V2 | `awaiting_user_decision` | `AI_V2_INTERRUPTED`；允许恢复未验证 unit |
| 下游或原子发布失败 | `awaiting_user_decision` | `AI_V2_PUBLICATION_FAILED`；不暴露半套结果 |
| 普通字段 candidate issue | `completed` | 字段隔离，固定隔离计数和诊断 |
| 用户选择保留失败 | `failed` | 持久化 `keep_failed` 决定 |
| 用户确认回退 | 标准路径结果 | 原始模式仍为 AI，有效模式变为 standard；不混入部分 AI 结果 |

- 重试复用 C1/C2 现有 `retry_missing_chunks` 动作，并持久化 `resume_count`、时间和用户决定。
- cache 损坏只有在该显式动作后才设置受控 discard-and-retry；默认运行不清理损坏 state。
- 完成态必须先验证 Bundle 恰好包含五个既有文件且均存在，随后才写 Job `completed`。
- `completed`、`failed`、`interrupted` 继续受既有终态写保护；用户确认回退仍是唯一受控终态覆盖边界。

## 8. Provider、Layout、Cache、恢复与并发调用计数

| 场景 | V2 extraction | layout | HTTP | 已验证 unit 重复调用 |
| --- | ---: | ---: | ---: | ---: |
| 两记录明确结构首次成功 | 2 | 0 | 0 | 0 |
| 单记录明确结构首次成功 | 1 | 0 | 0 | 0 |
| 歧义结构 fake layout | 0 | 1 | 0 | 0 |
| 第 2 unit transient 失败后恢复 | 首次 2，恢复 1 | 0 | 0 | 0 |
| 服务重启后恢复上述部分结果 | 新 Provider 仅 1 | 0 | 0 | 0 |
| 损坏 cache 默认运行 | 0 | 0 | 0 | 0 |
| 损坏 cache 显式重试 | 1 | 0 | 0 | 0 |
| 两线程竞争同一两-unit Job | 合计 2 | 0 | 0 | 0 |
| 完成后反复读取 Job/历史/预览/下载路径 | 0 | 0 | 0 | 0 |
| 正式 Ark V2 Provider + FakeTransport 单记录 | 1 | 0 | 1（FakeTransport） | 0 |

底层 V2 cache 命中回归证明 Provider 调用数为 0；桌面结果页、历史和预览反复读取也为 0。相同 client idempotency 与跨实例 single-flight 的执行身份和只执行一次规则由 D3B-2B 测试继续回归通过。

## 9. 五类发布与结果 API 证明

V2 completed Job 仍只暴露：

```text
official_result
parse_diagnostics
dictionary_validation
material_candidates
material_summary
```

- 成功测试验证五个角色全部存在，正式业务记录通过既有 20 字段组装，物料编码与相似分数仅来自 FakeMaterialMatcher。
- V2 `CURRENT` 解析额外核对 diagnostics 的 `protocol=v2`、cache key 与 `cache_identity.contract_version=2.0`。
- `CURRENT` 损坏或 cache identity 不一致时，预览/下载安全失败。
- 第三个 JSON 写入故障时，Job 保持 awaiting，最终目录没有 `CURRENT`，API 不暴露任何半套角色。
- ordinary candidate issue 可完成，但 parse diagnostics 明确记录 `candidate_isolated` 和隔离字段数。
- API/UI 不新增 candidates、provenance、cache、state 或 Sidecar 业务角色，不形成第六类 JSON。
- 打开 Job、历史、结果预览和按角色解析路径均不会再次调用 Provider。

## 10. 测试命令与精确结果

桌面 V2 主矩阵：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/web/test_ai_full_order_jobs.py -q
```

最终结果：`19 passed in 6.16s`。

最终最小充分扩展回归：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/ai_full_order/test_v2_offline_resolution.py `
  tests/ai_full_order/test_v2_reliability.py `
  tests/ai_full_order/test_v2_downstream.py `
  tests/ai_full_order/test_volcengine_ark_full_order_provider.py `
  tests/ai_full_order/test_acceptance_diagnostics.py `
  tests/web/test_ai_full_order_jobs.py `
  tests/web/test_gate4c2_routes.py `
  tests/web/test_gate4c2_frontend.py `
  tests/web/test_gate4b_routes.py `
  tests/web/test_gate4b_frontend.py `
  tests/web/test_job_persistence.py `
  tests/web/test_services.py `
  tests/web/test_routes.py `
  tests/web/test_ai_advisory.py `
  tests/pipeline/test_order_parser.py `
  tests/serialization/test_json_writer.py `
  tests/serialization/test_diagnostic_writer.py `
  tests/llm/test_advisory_schema.py `
  tests/llm/test_llm_contracts.py `
  tests/llm/test_volcengine_ark_provider.py -q
```

结果：`210 passed in 24.45s`。

另执行：

- 目标模块及测试 `compileall`：通过。
- `git diff --check` 与 staged `git diff --cached --check`：通过。
- staged 文件范围及敏感词扫描：通过。
- 未运行完整 pytest。

## 11. 离线与安全调用计数

| 项目 | 实际次数 |
| --- | ---: |
| 真实网络 | 0 |
| 真实 Ark API | 0 |
| 真实 PI | 0 |
| 真实字典工作簿 | 0 |
| 真实物料库 | 0 |
| BGE-M3 | 0 |
| FAISS | 0 |

测试只使用人工合成 workbook、`FakeV2CandidateProvider`、故障注入派生 Provider、FakeTransport、FakeDictionaryValidator 和 FakeMaterialMatcher。测试设置 socket guard；FakeTransport 的 HTTP 计数只是本地接口尝试，不是网络请求。

## 12. 发现并解决的问题

1. 桌面服务此前只组合 V1 `OfflineReliableOrchestrator`。新增独立 V2 runner，并由 Job 持久化版本显式分派，V1 代码未删除或放宽。
2. 新 Job 原先没有稳定保存内部合同、源身份和幂等身份。创建时改为确定性记录 V2、文件 SHA、client/business identity 和运行时 cache 摘要。
3. 用户重试决定会在成功完成时被清空。完成逻辑不再覆盖已持久化决定，因此重启后仍能解释此次完成来自显式恢复。
4. 历史 D1/D2 测试默认把“新建 AI Job”视为 V1，和本 Gate 的新 Job 必须 V2 冲突。测试 fixture 改为显式 legacy V1，生产新 Job 未回退。
5. 仅写五类角色描述不足以证明 completed。完成前新增五文件名称与存在性校验；V2 读取再校验 `CURRENT`、cache 和 contract identity。
6. 应用关闭/重启对 V2 继续使用旧 `interrupted` 终态会阻断恢复。V2 active Job 改为明确的 awaiting 决定，可靠性层只恢复未验证 unit；标准和 legacy V1 旧语义保持不变。
7. 当前 fake layout 结果没有冻结的“AI 输出到本地区块”绑定合同。为避免猜测结构，歧义路径调用一次 layout 后安全暂停；这不是字段 extraction 失败。

## 13. 未改变的合同

- 用户模式仍只有 `standard` / `ai_enhanced`，没有第三种 UI 模式。
- 标准解析算法、正式输出、默认 ZIP、字典规则、物料匹配算法/权重/阈值均未修改。
- V1/V2 Schema、17 个 AI 业务字段、本地正式行号、provenance、字段政策、cache identity 和五类原子发布合同均未放宽。
- 物料编码与相似分数仍只由匹配层生成。
- 单记录 AI Sidecar 与缓存保持独立；标准模式和页面查看不会调用整单 Provider。
- 未修改 C2 UI、帮助中心或静态资源。

## 14. 进入真实 V2 验收前的风险与阻塞

- 离线正式 Ark V2 Provider + FakeTransport 已通过桌面链路，但真实 Ark V2 function-call 返回形态、严格 sparse candidates 服从率、Token 与延迟尚未在本 Gate 验收。
- 当前真实 Provider 配置就绪不代表真实调用成功；下一轮必须继续使用人工合成数据、严格调用预算、`LLM_MAX_RETRIES=0` 和 D2D 白名单诊断。
- 歧义结构的 layout 返回尚无冻结的本地确定性应用合同，因此当前只能安全暂停，不能把真实 layout 结果直接转成 extraction units。若下一轮只验收本地明确 workbook，这不是阻塞；若要验收歧义结构端到端，需先单独冻结结构绑定合同。
- 真实 V2 输出若失败，只能依据白名单诊断做 Provider 边界的等价响应兼容；不得放宽 V2 Schema、evidence、scope、字段政策或发布门。
- 本 Gate 不存在阻止“本地结构明确、单次真实 V2 extract 小样本验收”的离线代码阻塞。

## 15. 最终工作区状态

- 实现提交后已跟踪工作区干净。
- 本报告是实现提交后的唯一新增 Gate 文件，将单独显式暂存并提交。
- 六份开始前已存在的未跟踪交接、恢复和架构审计文档继续保留，未修改、未清理、未暂存。
- 真实调用总数：0。

下一步唯一建议：在本地结构明确、人工合成数据、一次逻辑调用与一次 HTTP 尝试、`LLM_MAX_RETRIES=0` 的限制下，执行正式桌面 JobService Contract V2 `extract_v2` 真实小样本验收；失败时先输出 D2D 白名单诊断，不追加调用、不猜测修复。
