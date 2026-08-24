# Gate 4D-D3B-2A｜AI 整单 Contract V2 离线编排与字段裁决链报告

## 1. 基线与范围

- 分支：`master`
- 起始完整 HEAD：`f8cff899be0baac359e9195b04080ec8abfda9e5`
- 起始提交：`feat: add ai full-order contract v2 foundation`
- D3B-1 实际提交文件：V2 合同、provenance、FakeProvider、合同/provenance 测试及 D3B-1 报告，共 6 个文件。
- 起始已跟踪工作区：干净；既有 6 份未跟踪交接/恢复文档保留且未修改。
- 最终提交：本报告所在提交 `feat: integrate ai full-order v2 offline resolution`，实际 hash 以提交后的 `HEAD` 为准。

本 Gate 终点是离线生成可安全进入后续下游的 canonical 17 字段记录。本轮没有接入缓存、single-flight、中断恢复、桌面 Job、字典、物料匹配或五类 JSON 发布。

## 2. 修改文件

| 文件 | 目的 |
| --- | --- |
| `src/bedding_order_parser/ai_full_order/contracts.py` | 新增严格单目标 V2 请求 Schema 与验证器。 |
| `src/bedding_order_parser/ai_full_order/volcengine_ark.py` | 新增显式 V2 function、prompt 版本及 `extract_v2()`；V1 方法不变。 |
| `src/bedding_order_parser/ai_full_order/orchestration.py` | 新增稳定 extraction unit、受控 context、V2 离线运行链与 batch ready gate。 |
| `src/bedding_order_parser/ai_full_order/python_shadow.py` | 新增只读标准解析适配器，生成有本地 evidence 的非空 Python shadow。 |
| `src/bedding_order_parser/ai_full_order/field_policy.py` | 新增版本化 17 字段政策、固定裁决码、字段隔离及 canonical record。 |
| `src/bedding_order_parser/ai_full_order/fake_provider.py` | 为 V2 FakeProvider 增加显式 `extract_v2()`、请求计数与结构调用计数。 |
| `tests/ai_full_order/test_contracts.py` | 验证 V2 单目标请求和 evidence 精确集合。 |
| `tests/ai_full_order/test_volcengine_ark_full_order_provider.py` | 验证独立 V2 Ark function/Schema/Prompt/Transport 元数据。 |
| `tests/ai_full_order/test_field_policy.py` | 验证 17 字段政策和全部主要裁决分支。 |
| `tests/ai_full_order/test_v2_offline_resolution.py` | 验证三类 fixture、真实 shadow、单目标链、ready/隔离和零网络。 |
| `docs/reports/GATE_4D_D3B2A_AI_FULL_ORDER_V2_OFFLINE_RESOLUTION_REPORT.md` | 本报告。 |

未新增依赖，未修改 `reliability.py`、`downstream.py`、`web/ai_full_order_service.py`、UI、标准模式生产入口、字典、物料算法或默认 ZIP。

## 3. V2 Function、Prompt 与 Schema 版本

```text
请求/输出合同版本：V2_SCHEMA_VERSION = 2.0
字段政策版本：V2_FIELD_POLICY_VERSION = 2.0
V2 function：submit_bedding_order_candidates_v2
V2 prompt：FULL_ORDER_V2_PROMPT_VERSION = 2.0
V1 function：submit_bedding_order_full_order（保持不变）
V1 prompt：FULL_ORDER_PROMPT_VERSION = 1.0（保持不变）
```

V2 Provider 只通过显式 `extract_v2()` 进入，不按返回字典形状猜测版本。请求使用 Ark Responses 非流式边界、`store=false` 和严格 function Schema。V2 模型输出仍只有 D3B-1 的 `candidates`；Provider/model/request ID/usage/延迟/尝试数只记录在本地 `latest_telemetry`，不进入模型输出。

## 4. 单目标 Extraction Unit

每个 V2 extraction unit 只包含一个本地 target：

```text
source_file_sha256
chunk_id
extraction_unit_id
record_local_id
source_record_id
scope_id
sheet_id
source_row
允许的 evidence IDs 与精确 evidence catalog
```

`extraction_unit_id` 对 source SHA、chunk、target identity、源行和排序后的 evidence IDs 做规范化 SHA-256 摘要；相同输入重复预处理结果稳定。

V2 请求中的 evidence catalog 必须与 target evidence IDs 集合完全相等，且每项必须同 sheet、同 scope。不存在多记录数组，模型不负责回显身份。

为支持客户、币种、业务员和发货日期，V2 在不改变 V1 预处理结果的前提下，增加本地 context 选择：只纳入固定客户/币种/业务员/日期标签行及受控紧邻值行。银行、账号、IBAN、SWIFT、付款等敏感标签行不进入 V2 context；合成银行行不外发的回归已通过。隐藏内容仍由现有预处理层排除。

## 5. Python Shadow 接入与非空证明

`build_deterministic_python_shadow()` 复用现有标准解析内部最窄组合：

```text
load_pi_workbook
parse_table
extract_metadata
build_final_results_with_diagnostics
adapt_python_shadow_records
```

它只在内存中运行，不调用 `parse_order()` 写文件，不执行标准模式单记录 AI、字典或物料匹配。标准解析结果按 `sheet_id + excel source row` 绑定到本地 target；字段诊断中的单元格坐标映射为本地 evidence ID。

只有 evidence 存在、属于 target 允许集合且同 scope 的候选才保留。标准默认值或无法可靠映射 provenance 的值被显式清空，不伪造 evidence。正式行号同时由本地编号单元格验证，并与标准解析结果核对。

三类 fixture 均证明至少以下 5 个高风险字段产生非空、直接、有本地 evidence 的 Python shadow：

```text
客户、币种、业务员、数量、计划发货日期
```

工作簿解析前后 SHA 一致。

## 6. 17 字段政策矩阵

三个集合在代码中集中定义、全集等于固定 17 字段且互斥：

| 类别 | 字段 | AI interpretation | 冲突政策 |
| --- | --- | --- | --- |
| 高风险 | 客户、币种、业务员、数量、计划发货日期 | 仅 `direct` | 与 Python 直接证据冲突时 blocking；AI 问题时有 Python 则保留，否则 blocking。 |
| 描述 | 物料名称、规格、颜色、面料、面料-涤棉成分、款式、加标方式、尺寸类型、包装方式、是否绣花 | `direct` / 已绑定 `semantic` | Python direct 与 semantic/direct 冲突时确定性保留 Python 并记录 AI 隔离；Python 空时可采纳有效 AI。 |
| 备注 | 表头备注、行备注 | `direct` / `source_summary` | source_summary 的 candidate 必须与 quote 空白规范化后完全相等，禁止扩写。 |

数量继续要求数字字符串；日期继续要求 `YYYY-MM-DD`。没有引入模型评分、模糊匹配或新字典规则。

## 7. Hard Error 与字段隔离

| 层级 | 情况 | 结果 |
| --- | --- | --- |
| Hard extraction-unit error | 顶层/candidate Schema、额外/禁止字段、重复字段、未知 evidence、跨 scope、target identity、请求 evidence 集合错误 | extraction unit 失败，batch 隔离。 |
| Candidate-level issue | direct 无法定位、semantic/source_summary 缺 quote 或 quote 无法定位 | 只进入对应字段政策；普通字段隔离，高风险无 Python 时 blocking。 |
| Policy issue | interpretation 不允许、数量/日期格式错误、备注扩写 | 有有效 Python direct 时保留 Python 并显式 `ai_isolated=true`；否则普通字段隔离，高风险 blocking。 |
| 普通 direct/semantic 冲突 | 描述或备注与 Python direct 冲突 | 确定性保留 Python，记录 non-blocking AI 隔离。 |
| 高风险 direct 冲突 | 双方均有直接证据且值冲突 | `blocking_conflict`，batch 不 ready。 |

本地字段状态固定为：`accepted`、`python_preserved`、`ai_isolated`、`missing`、`blocking_conflict`。reason code 全部为固定枚举，不保存模型自由文本作为控制状态。

## 8. Canonical Record 与 Ready Gate

每个裁决结果恢复为按 `AI_BUSINESS_FIELD_NAMES` 固定顺序排列的完整 17 字段字符串对象。普通缺失或被隔离且无 Python 候选的字段写空字符串。

以下不属于 canonical 17 字段：

```text
行号（本地独立属性）
物料编码
相似分数
parse_mode / Provider / Token / provenance / decision
```

Batch ready 必须同时满足：全部 extraction unit 验证、记录数量和身份唯一、scope 一致、canonical 17 字段完整、无高风险 blocking、所有被采纳 AI 候选均为 `BOUND` 且有本地 quote span。任一条件失败只返回内存隔离结果；本轮没有调用 downstream 或发布文件。

## 9. 三类 Fixture 结果

| Fixture | 结构识别调用 | V2 提取单元 | 非空高风险 shadow | 结果 |
| --- | ---: | ---: | ---: | --- |
| 简单单记录 | 0 | 1 | 5 | `ready_for_downstream` |
| 多层/继承表头 | 0 | 1 | 5 | `ready_for_downstream` |
| 组合语义描述 | 0 | 1 | 5 | `ready_for_downstream`；Python 为空时有效 semantic 包装候选被采纳。 |

附加故障矩阵证明：高风险直接冲突阻止 batch；普通 candidate issue 只隔离字段且 batch 仍 ready；未知 evidence 和重复字段使 extraction unit/batch 隔离；稳定 unit ID、精确 evidence 范围、本地行号与禁止物料字段均通过。

## 10. 测试与结果

最终定向命令：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\ai_full_order\test_contracts.py `
  tests\ai_full_order\test_provenance.py `
  tests\ai_full_order\test_field_policy.py `
  tests\ai_full_order\test_v2_offline_resolution.py `
  tests\ai_full_order\test_preprocessing.py `
  tests\ai_full_order\test_resolution.py `
  tests\ai_full_order\test_orchestration.py `
  tests\ai_full_order\test_acceptance_diagnostics.py `
  tests\ai_full_order\test_volcengine_ark_full_order_provider.py `
  tests\pipeline\test_order_parser.py `
  tests\web\test_ai_full_order_jobs.py::test_standard_dispatch_remains_on_existing_path `
  tests\web\test_ai_advisory.py::test_cached_sidecar_prevents_a_second_provider_call -q
```

结果：`132 passed in 6.55s`。

另执行：

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\bedding_order_parser\ai_full_order tests\ai_full_order\test_field_policy.py tests\ai_full_order\test_v2_offline_resolution.py
git diff --check
```

结果均通过。未运行完整 pytest。

## 11. 调用与安全计数

| 项目 | 实际次数 |
| --- | ---: |
| 真实网络 | 0 |
| 真实 Ark API | 0 |
| 真实 PI | 0 |
| 真实字典 | 0 |
| 真实物料库 | 0 |
| BGE-M3 | 0 |
| FAISS | 0 |
| 字典/物料 downstream | 0 |
| 五类 JSON 发布 | 0 |

Provider 测试只使用注入的 FakeTransport；端到端离线测试使用 FakeV2CandidateProvider 并安装 socket guard。没有读取本机真实凭证，没有保存请求/响应、Authorization、API Key 或思维链。

## 12. 发现并解决的问题

1. 现有桌面 AI 路径确实只生成空业务 shadow；新增只读 adapter 后，代表 fixture 可生成非空、有坐标 evidence 的确定性候选，无需修改标准模式。
2. V1 预处理 target 只含表格表头与明细行，不含订单级 metadata。V2 通过独立受控 context 补充固定 metadata 行，不改变 V1 请求和缓存语义。
3. 初版 V2 context 若纳入全部表格前单元格会扩大数据范围；已收紧为固定标签/受控值行，并显式排除银行与付款类敏感行。
4. 单一字段状态无法同时表达“保留 Python”与“隔离 AI”；裁决对象新增本地 `ai_isolated` 布尔事实，同时保持固定主状态和 reason code。

## 13. 留给 D3B-2B 的接口与风险

1. 将 `V2_SCHEMA_VERSION`、`FULL_ORDER_V2_PROMPT_VERSION`、`V2_FIELD_POLICY_VERSION`、provenance binding 版本及 context/preprocessor 版本纳入 cache identity；V1/V2 缓存必须物理隔离，禁止自动迁移。
2. 将单目标 `extraction_unit_id` 映射到 single-flight、原子状态和按 unit 恢复；已验证 unit 不得重复调用 Provider。
3. 把本轮 `V2BatchAggregate.ready_for_downstream` 窄适配到既有 B3 downstream 和五类 JSON 原子发布；不得绕过现有发布校验。
4. 设计缓存中可持久化的最小安全 V2 结果；不得持久化完整 Provider 原始响应或模型请求。
5. 桌面 Job 和真实 Provider 切换仍未接入；D3B-2B 先完成可靠性和发布，再单独进入桌面/真实调用 Gate。

当前没有阻止 D3B-2B 的合同冲突；主要风险是遗漏任一版本项导致 V1/V2 或字段政策之间错误复用。

## 14. 未改变的正式合同与最终工作区

未改变固定 17/20 字段、标准正式行号、物料编码/相似分数生产权、V1 Provider/Prompt/输出验证器/编排/缓存读取语义、标准模式、单记录 AI Sidecar、字典规则、物料算法、五类 JSON、默认 ZIP 和 C2 UI。

提交前只显式暂存本 Gate 文件；提交后已跟踪工作区应为空。既有未跟踪交接/恢复文档继续保留，不暂存、不清理。
