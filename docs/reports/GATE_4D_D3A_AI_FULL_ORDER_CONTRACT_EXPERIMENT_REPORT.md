# Gate 4D-D3A AI 整单证据合同真实实验与重构决策报告

## 1. 结论

本轮以 3 类人工合成 fixture、5 种候选方案、每组 3 次重复完成了 45 次真实 Ark 调用。实验支持选择 **E：单记录稀疏候选 + 本地身份/原文 + 字段分级政策 + 字段级隔离** 作为合同 V2 的实现方向，但本轮没有替换生产合同。

关键结论：

- 当前合同 A 只有 `1/9` 次达到候选层可继续下游，结构通过率 `22.22%`；完整 17 字段和大信封使函数参数解析不稳定。
- 只增强 Prompt 的 B 把结构通过率提高到 `88.89%`，但继承和语义 fixture 仍是 `0/6` 可继续下游；Prompt 不能消除合同本身的证据矛盾。
- original_value 本地生成的 C 达到 `9/9` 结构通过和 `100%` 证据 ID 有效率，但复杂 fixture 仍因单字段失败整块拒绝，只达到 `3/9`。
- 稀疏候选 D 将总 Token 从 A 的 `51,283` 降至 `17,934`，但没有字段分级和字段级隔离时仍只有 `3/9`。
- E 的结构通过、证据引用有效和候选层可继续下游均为 `9/9`；总 Token 为 `18,444`，比 A 低 `64.03%`，平均延迟从 `21,455 ms` 降至 `8,371 ms`。
- E 不是字段准确性终点。语义 fixture 的字段有效率为 `51.85%`，三次分别为 `2/9、6/9、6/9`；11 个不合政策字段被隔离。V2 仍必须保留 Python shadow、字典/业务校验和高风险冲突发布门。

这里的“可继续下游/可发布率”是实验候选合同通过本地门的比例，不代表真实字典、真实物料匹配或正式五类 JSON 已发布。本轮正式发布调用为 `0`。

## 2. 基线与审查范围

- 开始分支：`master`
- 开始完整 HEAD：`d2be0c8bcfaaa3d6fa01eacf5c0136c54ea46c88`
- 开始提交：`test: diagnose ark full-order real extraction`
- 开始工作区只有三份既有未跟踪恢复/交接文档，无未知业务修改。

本轮审阅了 Gate 4D-A、B1、B2A、D2C、D2D、D2E 报告，以及当前 `contracts.py`、Ark 整单 Provider 请求 Schema/Prompt、证据验证、分块编排和 `resolution.py` 字段裁决实现。

## 3. 当前合同承担的职责与拒绝条件

当前模型一次承担了过多不同责任：

1. 生成固定 17 个字段对象，包括大量空字段。
2. 同时生成 `value`、`original_value`、证据引用、状态和 reason。
3. 回显文件 SHA、记录 ID、源记录 ID、scope、记录数、warnings 和 unresolved fields。
4. 按输出 Schema 生成 Provider、model、request ID、usage、延迟和尝试次数，尽管 Provider 随后会用本地 Transport 事实覆盖这些值。
5. 自己判断字段提取状态、整条记录状态和未解决字段。

当前验证器的实际语义比设计目标更窄：

- `extracted/normalized` 强制 value、original_value 和 evidence 三者同时非空。
- original_value 必须等于某一个被引证据单元格的完整原文。
- value 又必须与 original_value 在空白规范化后相等；当前没有真正允许描述字段从组合文本进行语义提取的白名单路径。
- 因此一个组合描述单元格即使明确包含颜色、面料和款式，模型提取出的短候选也会被判为 `evidence_untraceable`。
- 17 个字段全部必填会迫使模型为不存在字段制造空对象、状态、reason 和数组，增加输出 Token 与 JSON 失配概率。
- SHA、身份、scope、record count 等本地已知事实仍要求模型回显；任何错位都会整块拒绝。
- 任意字段证据失败会从 `validate_full_order_output()` 抛错，编排层将整个 chunk 标记为 `schema_or_evidence_failure`。
- 高风险字段、描述字段和备注字段先经过同一“value 必须等于完整 original”规则，字段分级只在该整块验证通过后才进入裁决，实际无法发挥设计中的差异化政策。
- 备注扩写检查当前把 `ai_value` 与其自身比较，不能单独证明备注未扩写；真正的保真仍依赖前置 value/original 严格相等。

这解释了 D2C/D2E 的真实失败：Ark 返回形态已经兼容，失败不在 Responses 包装，而在模型字段与统一证据三元关系之间。

## 4. 实验方法

### 4.1 Fixture

全部数据均为人工合成，不含真实 PI 或客户信息：

- `simple_record`：每个主要字段有独立、直接证据，期望验证最理想输入。
- `multilevel_inheritance`：客户/币种/业务员/备注来自上层表头，颜色、成分和款式位于同一个组合描述证据中。
- `semantic_description`：产品、尺寸、颜色、面料、款式、绣花和数量位于一段组合描述中，备注单独保留原文。

每个请求额外包含一个不同 scope 的合成干扰证据，用于检查越界引用。所有方案均使用相同模型、同一证据目录、`store=false`、非流式、严格 function schema 和 `LLM_MAX_RETRIES=0`。

### 4.2 方案

| 方案 | 模型输出责任 | 本地责任 | 隔离策略 |
| --- | --- | --- | --- |
| A | 当前生产 Schema 与当前 Prompt | 仅覆盖 Transport 元数据 | 任一错误整块拒绝 |
| B | 当前生产 Schema，增强三元关系和空字段 Prompt | 同 A | 任一错误整块拒绝 |
| C | 17 字段完整输出，但不返回 original_value | 从 evidence ID 生成 original_value；身份仍由模型回显 | 任一字段错误整块拒绝 |
| D | 稀疏 `field_name/candidate_value/evidence_references/interpretation` | original、身份、scope、SHA、count、Provider 元数据本地附加 | 任一候选错误整块拒绝 |
| E | 与 D 相同的稀疏 Schema，加字段分级 Prompt | 与 D 相同，并执行字段政策 | 普通字段失败隔离字段；硬边界仍整块拒绝 |

### 4.3 指标定义

- 结构通过率：固定函数参数可解析且通过对应实验 Schema。
- 字段有效率：对人工真值中应提取字段，候选值、证据和字段政策同时有效的比例；结构失败计为零。
- 证据有效率：可读取的非空候选中，evidence ID 存在、属于当前记录且同 scope 的比例。
- 幻觉/错误字段：非预期字段值、错误语义或违反字段政策的候选数量。
- 可继续下游率：方案自身的块级门通过；E 允许普通字段隔离。它不是正式五类发布率。

Function arguments 仅在 `TemporaryDirectory` 临时保存以完成合成数据统计；45 次分析结束后断言目录已删除。没有保存完整 HTTP 响应、请求头、Authorization、API Key、系统 Prompt 或真实数据。

## 5. 方案真实数据总表

| 方案 | 调用 | 结构通过 | 字段有效 | 证据有效 | 候选层可继续下游 | 错误候选 | 隔离字段 | Input Token | Output Token | Total Token | 平均延迟 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 9 | 22.22% | 11.90% | 57.89% | 11.11% | 9 | 0 | 38,586 | 12,697 | 51,283 | 21,455 ms |
| B | 9 | 88.89% | 59.52% | 65.00% | 33.33% | 30 | 0 | 39,243 | 11,967 | 51,210 | 25,667 ms |
| C | 9 | 100% | 60.71% | 100% | 33.33% | 36 | 0 | 32,010 | 9,724 | 41,734 | 18,132 ms |
| D | 9 | 100% | 60.71% | 100% | 33.33% | 33 | 0 | 14,298 | 3,636 | 17,934 | 7,908 ms |
| E | 9 | 100% | 84.52% | 100% | 100% | 13 | 11 | 14,793 | 3,651 | 18,444 | 8,371 ms |

45 次调用总计：input `138,930`、output `41,675`、total `180,605` Token；Provider 延迟累计 `733,796 ms`。实际逻辑调用 `45`、HTTP 尝试 `45`、重试 `0`，所有响应信封均表现为 `function_call`。

A 的 7 次、B 的 1 次在 function call 参数提取/JSON 解析边界失败；本轮只记录固定 `SchemaValidationError` 类别，没有保存失败参数或原始响应。C/D/E 均为 `9/9` 参数可解析。

## 6. Fixture 分层结果

| 方案 | Fixture | 结构通过 | 字段有效 | 证据有效 | 可继续下游 | Total Token | 平均延迟 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | simple | 33.33% | 33.33% | 100% | 33.33% | 17,134 | 20,802 ms |
| A | multilevel | 0% | 0% | 100%* | 0% | 17,735 | 22,781 ms |
| A | semantic | 33.33% | 3.70% | 20.00% | 0% | 16,414 | 20,781 ms |
| B | simple | 100% | 100% | 100% | 100% | 17,124 | 20,698 ms |
| B | multilevel | 100% | 70.00% | 63.64% | 0% | 17,597 | 26,589 ms |
| B | semantic | 66.67% | 7.41% | 20.00% | 0% | 16,489 | 29,713 ms |
| C | simple | 100% | 100% | 100% | 100% | 13,912 | 17,521 ms |
| C | multilevel | 100% | 70.00% | 100% | 0% | 14,518 | 20,136 ms |
| C | semantic | 100% | 11.11% | 100% | 0% | 13,304 | 16,740 ms |
| D | simple | 100% | 100% | 100% | 100% | 6,081 | 6,573 ms |
| D | multilevel | 100% | 70.00% | 100% | 0% | 6,609 | 8,760 ms |
| D | semantic | 100% | 11.11% | 100% | 0% | 5,244 | 8,391 ms |
| E | simple | 100% | 100% | 100% | 100% | 6,246 | 7,463 ms |
| E | multilevel | 100% | 100% | 100% | 100% | 6,784 | 9,505 ms |
| E | semantic | 100% | 51.85% | 100% | 100% | 5,414 | 8,146 ms |

`*` A/multilevel 三次均未得到可解析参数，没有 emitted candidate；证据率按“无可评估候选”记为 100%，不能解释为成功，必须与结构通过率一起读取。

## 7. 逐次调用记录

字段列为“有效字段/fixture 期望字段”；证据列为“有效证据候选/非空候选”。

| # | 方案 | Fixture | 重复 | In | Out | Total | 延迟ms | 结构 | 字段 | 证据 | 可继续 | 固定失败类别 |
|---:|:---:|---|---:|---:|---:|---:|---:|:---:|---:|---:|:---:|---|
| 1 | A | simple | 1 | 4334 | 1339 | 5673 | 15828 | N | 0/9 | - | N | function arguments SchemaValidationError |
| 2 | B | simple | 1 | 4407 | 1397 | 5804 | 24062 | Y | 9/9 | 9/9 | Y | - |
| 3 | C | simple | 1 | 3604 | 1008 | 4612 | 20109 | Y | 9/9 | 9/9 | Y | - |
| 4 | D | simple | 1 | 1636 | 391 | 2027 | 8360 | Y | 9/9 | 9/9 | Y | - |
| 5 | E | simple | 1 | 1691 | 391 | 2082 | 7375 | Y | 9/9 | 9/9 | Y | - |
| 6 | A | multilevel | 1 | 4472 | 1439 | 5911 | 26062 | N | 0/10 | - | N | function arguments SchemaValidationError |
| 7 | B | multilevel | 1 | 4545 | 1244 | 5789 | 26391 | Y | 7/10 | 7/11 | N | evidence_untraceable |
| 8 | C | multilevel | 1 | 3740 | 1121 | 4861 | 21031 | Y | 7/10 | 11/11 | N | whole_record_rejected |
| 9 | D | multilevel | 1 | 1772 | 432 | 2204 | 9188 | Y | 7/10 | 10/10 | N | candidate_field_failure |
| 10 | E | multilevel | 1 | 1827 | 435 | 2262 | 8000 | Y | 10/10 | 10/10 | Y | - |
| 11 | A | semantic | 1 | 4056 | 1408 | 5464 | 18188 | N | 0/9 | - | N | function arguments SchemaValidationError |
| 12 | B | semantic | 1 | 4129 | 1154 | 5283 | 25765 | Y | 1/9 | 2/10 | N | evidence_untraceable |
| 13 | C | semantic | 1 | 3326 | 1131 | 4457 | 14563 | Y | 1/9 | 9/9 | N | whole_record_rejected |
| 14 | D | semantic | 1 | 1358 | 396 | 1754 | 8766 | Y | 1/9 | 9/9 | N | candidate_field_failure |
| 15 | E | semantic | 1 | 1413 | 391 | 1804 | 7281 | Y | 2/9 | 9/9 | Y | 7 fields isolated |
| 16 | A | simple | 2 | 4334 | 1402 | 5736 | 28453 | N | 0/9 | - | N | function arguments SchemaValidationError |
| 17 | B | simple | 2 | 4407 | 1250 | 5657 | 21109 | Y | 9/9 | 9/9 | Y | - |
| 18 | C | simple | 2 | 3604 | 1042 | 4646 | 19766 | Y | 9/9 | 9/9 | Y | - |
| 19 | D | simple | 2 | 1636 | 391 | 2027 | 5422 | Y | 9/9 | 9/9 | Y | - |
| 20 | E | simple | 2 | 1691 | 391 | 2082 | 8922 | Y | 9/9 | 9/9 | Y | - |
| 21 | A | multilevel | 2 | 4472 | 1467 | 5939 | 24156 | N | 0/10 | - | N | function arguments SchemaValidationError |
| 22 | B | multilevel | 2 | 4545 | 1443 | 5988 | 26031 | Y | 7/10 | 7/11 | N | evidence_untraceable |
| 23 | C | multilevel | 2 | 3740 | 1110 | 4850 | 19688 | Y | 7/10 | 11/11 | N | whole_record_rejected |
| 24 | D | multilevel | 2 | 1772 | 432 | 2204 | 8359 | Y | 7/10 | 10/10 | N | candidate_field_failure |
| 25 | E | multilevel | 2 | 1827 | 433 | 2260 | 8703 | Y | 10/10 | 10/10 | Y | - |
| 26 | A | semantic | 2 | 4056 | 1406 | 5462 | 26828 | Y | 1/9 | 2/10 | N | evidence_untraceable |
| 27 | B | semantic | 2 | 4129 | 1300 | 5429 | 28547 | Y | 1/9 | 2/10 | N | evidence_untraceable |
| 28 | C | semantic | 2 | 3326 | 1090 | 4416 | 15125 | Y | 1/9 | 9/9 | N | whole_record_rejected |
| 29 | D | semantic | 2 | 1358 | 387 | 1745 | 8453 | Y | 1/9 | 9/9 | N | candidate_field_failure |
| 30 | E | semantic | 2 | 1413 | 392 | 1805 | 9469 | Y | 6/9 | 9/9 | Y | 3 fields isolated |
| 31 | A | simple | 3 | 4334 | 1391 | 5725 | 18125 | Y | 9/9 | 9/9 | Y | - |
| 32 | B | simple | 3 | 4407 | 1256 | 5663 | 16922 | Y | 9/9 | 9/9 | Y | - |
| 33 | C | simple | 3 | 3604 | 1050 | 4654 | 12687 | Y | 9/9 | 9/9 | Y | - |
| 34 | D | simple | 3 | 1636 | 391 | 2027 | 5938 | Y | 9/9 | 9/9 | Y | - |
| 35 | E | simple | 3 | 1691 | 391 | 2082 | 6093 | Y | 9/9 | 9/9 | Y | - |
| 36 | A | multilevel | 3 | 4472 | 1413 | 5885 | 18125 | N | 0/10 | - | N | function arguments SchemaValidationError |
| 37 | B | multilevel | 3 | 4545 | 1275 | 5820 | 27344 | Y | 7/10 | 7/11 | N | evidence_untraceable |
| 38 | C | multilevel | 3 | 3740 | 1067 | 4807 | 19688 | Y | 7/10 | 10/10 | N | whole_record_rejected |
| 39 | D | multilevel | 3 | 1772 | 429 | 2201 | 8734 | Y | 7/10 | 10/10 | N | candidate_field_failure |
| 40 | E | multilevel | 3 | 1827 | 435 | 2262 | 11812 | Y | 10/10 | 10/10 | Y | - |
| 41 | A | semantic | 3 | 4056 | 1432 | 5488 | 17328 | N | 0/9 | - | N | function arguments SchemaValidationError |
| 42 | B | semantic | 3 | 4129 | 1648 | 5777 | 34828 | N | 0/9 | - | N | function arguments SchemaValidationError |
| 43 | C | semantic | 3 | 3326 | 1105 | 4431 | 20532 | Y | 1/9 | 10/10 | N | whole_record_rejected |
| 44 | D | semantic | 3 | 1358 | 387 | 1745 | 7953 | Y | 1/9 | 9/9 | N | candidate_field_failure |
| 45 | E | semantic | 3 | 1413 | 392 | 1805 | 7687 | Y | 6/9 | 9/9 | Y | 3 fields isolated |

## 8. 失败模式与决策

### A：当前合同

失败有两层：7/9 在函数参数提取/JSON 边界失败；能够读取的复杂样本又因 value 无法等于组合证据完整原文而被拒绝。大而重复的 17 字段对象和本地可知信封既增加 Token，也扩大格式失配面。

### B：只增强 Prompt

B 证明 Prompt 可以让简单、独立单元格输入稳定达到 3/3，但组合描述仍反复触发 `evidence_untraceable`。这不是继续堆 Prompt 能解决的问题：要求模型提取短语，同时要求短语等于完整单元格原文，本身矛盾。

### C：original_value 本地生成

C 将结构和证据 ID 有效率稳定到 100%，证明 original_value 不应由模型生成。但全 17 字段与整块失败仍保留，因此复杂 fixture 的错误候选会拖垮整个记录。

### D：稀疏候选

D 把输出 Token 和延迟显著降低，结构稳定，但没有明确字段政策时，模型会把组合描述中的直接/语义关系混用；任何错误候选仍造成整块失败。

### E：稀疏候选 + 分级政策 + 字段隔离

E 是唯一在三类 fixture、三次重复中均保持结构、证据和候选层门稳定的方案。它的优势是缩小模型权责和失败半径，不是取消验证。语义字段的候选准确性仍不充分，因此字段隔离是必要条件，而不是容错美化。

## 9. 推荐合同 V2

推荐模型输出只包含：

```json
{
  "candidates": [
    {
      "field_name": "固定17字段枚举之一",
      "candidate_value": "非空候选",
      "evidence_references": ["本次请求内证据ID"],
      "interpretation": "direct | semantic | source_summary"
    }
  ]
}
```

所有 object 仍为 `additionalProperties=false`，字段完整、禁止 null。`candidates=[]` 合法，模型不再生成 17 个空字段。

本地负责：

- source SHA、chunk、record identity、scope、record count、顺序和 Provider 元数据；
- 由 evidence 目录生成 original_value/原文集合，不接受模型回写原文；
- 对重复 field_name、未知 evidence、跨 scope、禁止字段和顶层结构进行硬拒绝；
- 把合法稀疏候选适配到现有 17 字段裁决结构，缺失字段由本地标记 `source_not_provided`；
- 继续执行 Python shadow、字典/业务验证、物料匹配和 B3 正式发布门。

字段政策：

- 高风险字段（客户、币种、业务员、数量、计划发货日期）只接受 `direct`，并经本地无损类型/格式校验；与 Python 直接证据冲突仍阻止发布。
- 描述字段允许 `direct` 或有同 scope 证据的 `semantic`；semantic 不是“字符串等于原文”，但必须通过字段专用校验、字典/业务规则和 Python 对照。
- 表头备注、行备注只允许 `direct/source_summary`，由本地证明是原文摘取、顺序整理或批准的空白合并，不允许扩写。
- 普通字段 evidence/value/policy 失败只隔离该字段，并保留合法 Python 候选；不得因为一个颜色候选失败而丢弃同记录的数量等合法字段。

## 10. 必须保留的硬边界

以下情况仍整块拒绝，不能字段级降级：

- 顶层或 candidate Schema 错误、额外字段、null、重复 field_name；
- 未知记录或错误的本地记录绑定；
- evidence ID 不存在、跨 scope 或请求证据目录被篡改；
- 模型试图输出行号、物料编码、相似分数或合同外字段；
- source SHA/记录数/身份/scope 的本地一致性失败；
- 高风险字段与 Python 直接证据存在未解决冲突；
- 任一预期 chunk 未验证或 B2A/B2B ready 门未满足。

正式 20 字段、物料编码/相似分数生产权、标准模式、默认 ZIP、C2 UI、物料匹配算法和五类发布合同均不变。

## 11. 迁移模块与下一 Gate

需要迁移的最小模块：

- `ai_full_order/contracts.py`：新增版本化 V2 稀疏 Schema、候选白名单验证和严格固定诊断路径；保留 V1 兼容读取，不原地放宽。
- `ai_full_order/volcengine_ark.py`：新增 V2 Prompt/函数 Schema；Provider 只返回候选并附加本地 Transport 元数据。
- `ai_full_order/orchestration.py`：按本地绑定的单记录/单 scope 接受稀疏候选，区分块级失败与字段级隔离。
- `ai_full_order/resolution.py`：实现 direct/semantic/source_summary 分级政策、真正的备注保真校验和 Python fallback。
- `ai_full_order/reliability.py`：V2 Schema/Prompt/normalization/policy 版本进入缓存键，禁止复用 V1 确定性失败缓存。
- `web/ai_full_order_service.py` 与安全诊断：只接收已经版本化验证的 V2 结果；修正 D2D 固定路径清洗残余问题。
- 定向测试：合成简单、继承、组合语义、跨 scope、重复字段、禁止字段、字段隔离、高风险冲突和 V1/V2 缓存失效。

下一 Gate 建议为 **Gate 4D-D3B：离线并行实现证据合同 V2 与 V1 适配器**。范围仅包括版本化 Schema、FakeTransport/FakeProvider、字段政策、字段级隔离、缓存失效和对现有 B2A/B2B/B3 的窄适配；默认生产合同仍保持 V1，不调用真实 Ark，不修改 UI、标准模式、20 字段或五类发布。D3B 通过后再单独授权 V2 真实复验。

## 12. 调用、安全、测试与清理

- 实际真实逻辑调用：`45`
- 实际 HTTP 尝试：`45`
- 重试：`0`
- 模型：`doubao-seed-2-0-lite-260428`
- Base URL：`https://ark.cn-beijing.volces.com/api/v3`
- 真实 PI、真实字典、真实物料库、BGE-M3、FAISS、正式发布：均为 `0`
- 临时 function arguments：仅人工合成数据，统计后已删除；清理断言通过。
- 完整 HTTP 请求/响应、Authorization、API Key、请求头、系统 Prompt、私有推理：均未保存或提交。

真实实验后显式禁用 LLM、清空 Ark Key，并运行既有定向回归：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ai_full_order\test_contracts.py tests\ai_full_order\test_acceptance_diagnostics.py tests\ai_full_order\test_volcengine_ark_full_order_provider.py tests\llm\test_volcengine_ark_provider.py tests\web\test_ai_full_order_jobs.py tests\web\test_gate4c2_routes.py tests\web\test_gate4c2_frontend.py tests\web\test_ai_advisory.py tests\web\test_services.py tests\web\test_routes.py tests\desktop\test_server_controller.py -q
```

结果：`148 passed in 17.41s`。`compileall` 与 `git diff --check` 通过；未运行完整 pytest。

## 13. 修改与提交

本轮只新增：

- `docs/reports/GATE_4D_D3A_AI_FULL_ORDER_CONTRACT_EXPERIMENT_REPORT.md`

提交信息：`research: evaluate ai full-order evidence contracts`。

本报告将在同一 Gate 提交中提交；完整哈希与最终工作区由提交后的 Git 核验和最终回复给出。三份既有未跟踪恢复/交接文档继续保留，不暂存、不清理。
