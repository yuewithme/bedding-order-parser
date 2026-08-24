# Gate 4D-D3B-2B｜AI 整单 Contract V2 可靠性、恢复与五类原子发布离线实现报告

## 1. 基线与范围

- 分支：`master`
- 准确起始完整 HEAD：`c8068bad9991b692fcc1dc5d832a844e45dc2f2e`
- 起始短 HEAD：`c8068ba`
- 起始提交：`feat: integrate ai full-order v2 offline resolution`
- D3B-2A 实际提交文件：报告、V2 请求合同、Ark V2 function/prompt、单目标编排、Python shadow、字段政策、FakeProvider 及对应合同/Provider/字段政策/离线裁决测试，共 11 个文件。
- 起始已跟踪工作区干净；六份既有未跟踪交接、恢复和架构审计文档保留，未修改、未清理、未暂存。
- 本 Gate 未修改 `web/ai_full_order_service.py`、桌面 Job、路由、UI、标准解析、单记录 AI Sidecar、字典规则、物料算法、默认 ZIP 或 V1 可靠性实现。
- 最终提交信息：`feat: add ai full-order v2 reliability and publication`。本报告与实现位于同一提交；准确提交 hash 以提交后的 Git 核验和最终中文交接为准。

## 2. 实际修改文件

| 文件 | 目的 |
| --- | --- |
| `src/bedding_order_parser/ai_full_order/contracts.py` | 增加 V2 contract 与 normalization 职责版本常量。 |
| `src/bedding_order_parser/ai_full_order/preprocessing.py` | 增加 preprocessor 版本常量。 |
| `src/bedding_order_parser/ai_full_order/orchestration.py` | 增加 context-selection 版本；公开既有 accepted-AI provenance 重验证入口。 |
| `src/bedding_order_parser/ai_full_order/provenance.py` | 增加 provenance-binding 版本常量。 |
| `src/bedding_order_parser/ai_full_order/python_shadow.py` | 增加 Python-shadow adapter 版本常量。 |
| `src/bedding_order_parser/ai_full_order/reliability_v2.py` | 新增独立 V2 cache、state、single-flight、幂等、恢复与本地重验证链。 |
| `src/bedding_order_parser/ai_full_order/downstream.py` | 新增 V2 窄适配和五类原子发布入口；V1 入口保持不变。 |
| `tests/ai_full_order/test_v2_reliability.py` | 新增版本、缓存、并发、状态、故障和恢复矩阵。 |
| `tests/ai_full_order/test_v2_downstream.py` | 新增下游门、20 字段、诊断、五类原子发布和故障注入矩阵。 |
| `docs/reports/GATE_4D_D3B2B_AI_FULL_ORDER_V2_RELIABILITY_PUBLICATION_REPORT.md` | 本报告。 |

未新增依赖。

## 3. V1/V2 缓存与状态隔离

- V1 继续使用既有 `OfflineReliabilityStore` 的 `chunks/`、`locks/` 和 `idempotency/` 路径、`STATE_FORMAT_VERSION=1`、`CacheIdentity` 和 `OfflineReliableOrchestrator`；其实现未改动。
- V2 使用新增 `V2ReliabilityStore`，所有内容固定放在同一用户指定 runtime root 下的独立 `v2/units/`、`v2/locks/` 和 `v2/idempotency/` 命名空间。
- V2 state format 固定为 `2.0`，状态文件以 `extraction_unit_id` 的稳定 SHA 命名；锁以 V2 cache key 命名。测试直接证明同一 root 下 V1/V2 state、lock 和 idempotency 路径均不碰撞。
- V2 不读取、迁移、覆盖或按字典形状猜测 V1 cache；V1 也不知道 V2 state。

## 4. 完整 V2 Cache Identity

`V2CacheIdentity` 使用规范化 JSON（ASCII、字段排序、紧凑分隔）和 SHA-256，固定包含：

```text
source_file_sha256
provider
model
contract_version
schema_version
prompt_version
preprocessor_version
context_selection_version
normalization_version
python_shadow_adapter_version
field_policy_version
provenance_binding_version
canonical_extraction_manifest_sha256
```

- 版本常量集中在各职责模块，不用临时路径、进程 ID、对象 `repr` 或不稳定字典顺序。
- canonical extraction manifest 按本地 `order` 排序，逐 unit 绑定 source SHA、chunk ID、extraction-unit ID，以及完整严格 V2 request 的 SHA；因此覆盖 target identity、顺序、evidence 集合和 evidence 内容。
- 测试逐一改变上列每个版本/身份字段，全部产生不同 cache key；相同输入及反向传入 unit 列表仍产生相同 key。

## 5. 缓存持久化与命中重验证

V2 成功状态只持久化以下最小安全内容：

```text
cache key
extraction-unit ID 与 identity SHA
状态、尝试数、owner token、固定错误码和时间
已通过 V2 Schema 的 sparse candidates
Provider、模型、request ID、usage、延迟和尝试数白名单 telemetry
```

不持久化完整 HTTP 请求、完整 Provider 原始响应、Authorization、API Key、系统提示、思维链、Excel 二进制或任意模型额外键。

每次 cache 命中均重新执行：

```text
V2 输出 Schema
unit/request identity SHA
target 与 evidence 精确集合
scope 与 provenance binder
Python shadow 17 字段、行号、identity 和 evidence 范围校验
当前字段政策与 17 字段裁决
accepted-AI provenance
batch ready gate
```

缓存不保存或直接复用 canonical 17 字段。普通候选问题以 `candidate_isolated` 状态持久化；再次读取仍按当前本地事实重算，而不是升级为无诊断成功。损坏或 identity 不符的 cache 默认隔离且不调用 Provider；只有调用方显式指定 `retry_corrupt_cache=True` 时，才删除该单个无效 state 并重新执行。

## 6. Single-flight、幂等与状态机

- V2 复用既有跨实例 `FileLease`：原子排他创建、唯一 owner token、心跳、健康锁不可抢占、过期锁内容复核后恢复、follower 有界等待。
- 同一 cache identity 的两个独立 `V2ReliableOrchestrator` 实例并发时，计数型慢 FakeProvider 只发生 1 次逻辑提取；结果分别为 `executed` 和 `cached`。
- client idempotency key、business key 和 V2 cache key 共同形成稳定 `v2-exec:*` 身份。相同请求返回同一 execution；同一 client key 跨 field-policy 版本复用会抛出明确冲突。
- V2 状态包括：`pending`、`in_progress`、`validated`、`candidate_isolated`、`failed_transient`、`hard_failed`、`interrupted`。
- batch/run 表达：ready、isolated、interrupted、in-progress、executed/cached；成功发布由返回的已校验 `PublishedBundle` 表达。
- 状态转换使用白名单。`validated`、`candidate_isolated` 和 `hard_failed` 是不可被旧写入覆盖的终态。
- 状态写入使用唯一临时文件、flush、fsync、`os.replace` 和 Windows `PermissionError` 有界重试；状态、幂等和 telemetry 读取均验证固定字段、类型、版本和身份。

## 7. 中断恢复与调用计数

- 拿到 lease 的 leader 才能把遗留 `in_progress` 转为 `interrupted`。
- `validated` 和 `candidate_isolated` unit 从安全 cache 读取并完整重验证，不再次调用 Provider。
- `pending`、`interrupted` 和未达上限的 transient unit 可继续；`hard_failed` 默认不自动重试。
- 两记录 fixture 在第 2 个 unit 调用前中断：首次 1 次调用，恢复实例只调用剩余 unit 1 次，随后完整 cache 命中为 0 次。
- 二次恢复再次在第 2 个 unit 前中断：第一次 1 次、第二次 0 次、第三次只执行剩余 unit 1 次；已验证 unit 的重复调用数为 0。
- terminal state 写入前故障：第一次 Provider 已返回但结果未持久化，因此恢复时安全重做该 unit 1 次，不猜测为成功。
- transient FakeProvider 第一次失败、第二次成功，总调用数 2；尝试数和有界退避进入状态。
- 损坏 cache 默认 Provider 调用数 0；显式 retry 后只调用 1 次并恢复成功。
- 部分 unit 完成时 batch 仍包含 `missing_extraction_units`/`record_count_mismatch`，不能越过 ready gate。

## 8. V2 Downstream Adapter

`publish_ready_v2_batch()` 是新增窄入口：

1. 只接受 `executed`/`cached` 且完整 ready 的 `V2ReliableRunResult`；
2. 要求全部 extraction unit 为 validated outcome、记录身份唯一、无高风险 blocking；
3. 通过 `adapt_v2_records_for_downstream()` 把 canonical 17 字段、本地行号、identity 和固定 reason/evidence 映射到既有 `ResolvedRecord` 端口；
4. 复用既有 dictionary validator、material matcher、20 字段组装、payload 校验和 bundle publisher；
5. 物料编码和相似分数只接受 matcher 的同身份 `MaterialSelection`，相似分数继续要求非 bool 的 float。

未复制字典或物料匹配算法，测试仅注入 FakeDictionaryValidator 和 FakeMaterialMatcher。AI sparse candidates 不包含物料编码或相似分数；禁止字段候选在 V2 Schema 层 hard fail，下游调用数为 0。

## 9. 五类 JSON 与原子发布证明

成功仍只生成既有五种文件：

```text
ai_full_order.json
ai_full_order_parse_report.json
ai_full_order_dictionary_validation.json
material_match_candidates.json
material_match_summary.json
```

- 正式业务 JSON 严格按 `FINAL_FIELD_NAMES` 生成 20 字段；前 19 项为字符串，`相似分数`为 JSON number/float。本地行号为 `1`，测试 matcher 提供 `MAT-001` 和 `0.75`。
- V2 cache、版本、unit 状态、固定字段 reason/status、隔离计数和白名单 telemetry 只进入既有 parse diagnostics 的受控 `ai_enhanced` 区域。
- sparse candidates、完整 provenance snapshot、cache state、staging、请求/响应和 telemetry 不会形成第六类业务 JSON。
- 复用既有 staging bundle、五文件重验证、目录级原子安装和单一 `CURRENT` 原子入口。
- 分别在第 1、第 3、第 5 个 JSON 写入时注入故障，最终 bundle、`CURRENT` 和任何半套 JSON 均不存在。
- 已发布 bundle 后以相同 cache identity 生成语义不同内容会拒绝；旧 `ai_full_order.json` 和 `CURRENT` 保持原样。
- 首次发布与 validated-cache 命中后再次发布的五个规范化内容 SHA 完全一致，第二次复用既有 bundle，Provider 调用数为 0。
- 模拟 Windows 占用 `CURRENT` 时，有界重试后成功复用 bundle。

## 10. 字段门与故障矩阵

- 高风险客户 direct conflict：reliability batch 隔离，字典/匹配调用均为 0，不创建发布目录。
- unknown evidence：unit `hard_failed`，重复运行不再次调用 Provider，下游调用为 0。
- 禁止物料字段：V2 Schema hard fail，下游调用为 0。
- 普通包装字段 direct 无法追溯：unit 持久化为 `candidate_isolated`；canonical 记录仍完整且无高风险 blocking，可以发布；正式字段为空，固定隔离原因只出现在诊断。
- 非法 Python shadow evidence：在 Provider 调用前拒绝，调用数为 0。
- state JSON 损坏、state identity 不符、幂等内容损坏、telemetry 非白名单或终态旧写入均不能被解释为成功。

## 11. 测试命令与精确结果

最终最小充分扩展回归命令：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\ai_full_order\test_contracts.py `
  tests\ai_full_order\test_provenance.py `
  tests\ai_full_order\test_field_policy.py `
  tests\ai_full_order\test_v2_offline_resolution.py `
  tests\ai_full_order\test_v2_reliability.py `
  tests\ai_full_order\test_v2_downstream.py `
  tests\ai_full_order\test_preprocessing.py `
  tests\ai_full_order\test_resolution.py `
  tests\ai_full_order\test_orchestration.py `
  tests\ai_full_order\test_reliability.py `
  tests\ai_full_order\test_downstream.py `
  tests\ai_full_order\test_acceptance_diagnostics.py `
  tests\ai_full_order\test_volcengine_ark_full_order_provider.py `
  tests\pipeline\test_order_parser.py `
  tests\serialization\test_json_writer.py `
  tests\serialization\test_diagnostic_writer.py `
  tests\web\test_ai_full_order_jobs.py::test_standard_dispatch_remains_on_existing_path `
  tests\web\test_ai_advisory.py::test_cached_sidecar_prevents_a_second_provider_call -q
```

结果：`181 passed in 13.75s`。

状态安全补强后再次运行：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\ai_full_order\test_v2_reliability.py `
  tests\ai_full_order\test_v2_downstream.py `
  tests\ai_full_order\test_reliability.py `
  tests\ai_full_order\test_downstream.py -q
```

结果：`44 passed in 7.33s`。

另执行 `compileall` 和 `git diff --check`，均通过。未运行完整 pytest。

## 12. 离线与安全调用计数

| 项目 | 实际次数 |
| --- | ---: |
| 真实网络 | 0 |
| 真实 Ark API | 0 |
| 真实 PI | 0 |
| 真实字典工作簿 | 0 |
| 真实物料库 | 0 |
| BGE-M3 | 0 |
| FAISS | 0 |

所有工作簿均由测试即时人工合成；V2 测试使用 autouse socket guard。Provider 仅为计数型 `FakeV2CandidateProvider` 或故障注入派生类；字典和物料仅为可注入 fake adapters。

## 13. 发现并解决的问题

1. V1 cache identity 缺少 V2 contract、context、shadow、field-policy 和 provenance 版本，无法安全复用。采用独立 V2 identity 和物理 namespace，未扩大或放宽 V1。
2. D3B-2A 内存链只生成 canonical record，不能作为 cache 内容直接信任。改为缓存严格 sparse candidates，并在每次读取时重跑所有本地绑定和裁决。
3. 仅核对 Python shadow record ID 不足以证明当前本地输入。补充 17 字段顺序、行号、identity、候选类型和 evidence 集合校验。
4. 损坏 cache 若只隔离会形成不可恢复死路。默认仍安全隔离；新增显式单-unit discard-and-retry 开关，禁止静默清理或使用。
5. V2 diagnostics 若记录本次是 `executed` 还是 `cached`，会让同一正式结果重复发布时内容 SHA 变化。诊断改为记录稳定 cache identity、unit 状态和首次持久化的安全 telemetry，不写本次调用处置，从而保证 bundle SHA 稳定。

## 14. 留给 D3B-2C 的接口与风险

- 桌面 `web/ai_full_order_service.py` 仍只组合 V1 `OfflineReliableOrchestrator` 和 `publish_ready_batch()`；D3B-2C 需要在 composition root 中显式选择 V2，而不能按响应字典形状猜测协议。
- D3B-2C 应调用现有 V2 预处理/extraction-unit、确定性 Python shadow、`V2ReliableOrchestrator` 和 `publish_ready_v2_batch()`，并把 provider/model/client/business identity 从 Job 合同稳定传入。
- ambiguous structure recognition 仍属于 extraction-unit 形成之前的本地优先编排阶段；本可靠性入口不自行发起布局 AI。桌面接入必须保持“本地明确时 0 次布局调用”，歧义时通过现有显式结构入口处理后再进入 V2 unit reliability。
- 桌面失败映射需要把 `v2_cache_corrupt`、`v2_hard_contract_or_resolution_failure`、`v2_transient_*`、blocking conflict 和 interrupted 转换为既有安全 Job code；不得静默回退标准模式。
- 当前无阻止 D3B-2C 离线接入的合同冲突。风险集中在桌面状态映射、旧 Job 兼容和 V1/V2 composition 选择，可靠性、20 字段和五类发布边界已形成独立可测试接口。

## 15. 未改变的正式合同与最终工作区

- 未改变固定 17 个 AI 业务字段、正式 20 字段顺序和类型、本地正式行号、物料编码/相似分数生产权、hard evidence/identity/scope 边界、字段政策、五类业务角色或原子 bundle 格式。
- 未改变 V1 可靠性缓存语义、V1 Provider 路径、标准模式、单记录 AI Sidecar、标准 ZIP、桌面/UI、字典或物料算法。
- 提交后预期工作区无已跟踪修改；六份既有未跟踪交接/恢复/架构文档继续保留，不纳入本 Gate。
