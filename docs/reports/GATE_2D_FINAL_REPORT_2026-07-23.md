# Gate 2D 最终报告

报告文件名沿用 Gate 2D 批量验证产物日期 `2026-07-23`；本轮文档收尾在 `2026-07-24` 执行。本文只记录验证摘要、字段合同和交接信息，不粘贴完整企业订单明细文本。

## 1. 基线

- 项目目录：`D:\AI-Learning\Projects\bedding-order-parser`
- 分支：`master`
- 文档收尾开始前 HEAD：`24c6e6ea99a25312d92c0a4e284a3b2d25c3c103`
- 对应提交：`feat: add party extraction and field diagnostics`
- Git 作者：`小艾 <1746762028@qq.com>`
- 基线测试：`uv run pytest`，`65 passed`

## 2. Gate 2D 目标

Gate 2D 在 Gate 2C 稳定解析器基础上补齐交易双方元数据、可确定字段和字段级解析诊断。目标是让真实 PI Excel 同时产出两类文件：

- 业务结果 JSON：保持用户指定的最终 20 字段合同，不写诊断文本。
- 解析报告 JSON：逐字段说明值来源、状态、坐标、规则和空值原因。

当前能力仍是离线规则解析，不接入 LLM、向量检索、物料编码匹配、ERP 对比、API、前端、Agent 或 Docker。

## 3. 业务定义

- `客户`：买方主体组织，即 PI 中 buyer / invoice to / bill to / sold to 等区域的组织名称。
- `业务员`：Canasin 卖方或卖方区域的联系人、业务或区域联系人。
- 买方联系人只作为辅助证据，不写入最终 20 字段业务 JSON。
- 没有明确源证据或存在冲突时，业务字段保持空字符串，原因写入解析报告。

## 4. 模块职责

- `excel/workbook_reader.py`：只读打开 Excel、计算 SHA-256。
- `excel/sheet_locator.py`：定位 PI 工作表。
- `excel/table_parser.py`：回填合并单元格、识别表头和明细区域。
- `extraction/party_extractor.py`：区分买方/卖方区域，抽取买方主体、卖方联系人和买方联系人辅助证据。
- `extraction/metadata_extractor.py`：编排交易双方、币种、发货日期、包装等订单级元数据。
- `extraction/item_extractor.py`：筛选被套行、继承相邻描述、组装结果和字段诊断。
- `normalization/field_normalizer.py`：规格、颜色、面料、成分、款式、尺寸类型、绣花等确定规则标准化。
- `diagnostics/models.py`：定义 8 类字段状态、证据、记录诊断和解析报告模型。
- `diagnostics/report_builder.py`：校验诊断字段顺序和值与业务结果一致，并汇总警告。
- `serialization/diagnostic_writer.py`：成对写入业务结果和解析报告，失败时回滚。
- `pipeline/order_parser.py`：组织读取、解析、诊断、SHA 校验和双输出写入。

## 5. 最终 20 字段合同

字段顺序保持不变：

`客户`、`币种`、`业务员`、`表头备注`、`行号`、`物料编码`、`物料名称`、`规格`、`颜色`、`面料`、`面料-涤棉成分`、`款式`、`加标方式`、`尺寸类型`、`数量`、`行备注`、`计划发货日期`、`包装方式`、`是否绣花`、`相似分数`。

其中 `相似分数` 为浮点数；其余字段为字符串。当前阶段 `物料编码` 固定为空字符串，`相似分数` 固定为 `0.0`。

## 6. 字段状态

| 状态 | 定义 |
|---|---|
| `extracted` | 从源 Excel 找到明确值，仅做无害清理。 |
| `normalized` | 源 Excel 有明确证据，按业务规则标准化后输出。 |
| `derived` | 由其他已确定字段生成。 |
| `defaulted` | 源文件未明确提供，使用已批准的固定业务默认值。 |
| `source_not_provided` | 已检查相关区域，源 Excel 未提供足够信息。 |
| `unrecognized` | 源 Excel 存在相关内容，但当前规则无法稳定转换。 |
| `ambiguous` | 存在冲突或不完整候选，无法安全确定唯一值。 |
| `not_implemented` | 该字段属于后续阶段，本阶段尚未实现。 |

## 7. 双输出

解析命令默认生成业务 JSON 和同目录解析报告 JSON。示例：

- 业务结果：`order_result.json`
- 解析报告：`order_result_parse_report.json`

双输出写入前会检查目标是否存在；未显式 `--overwrite` 时拒绝覆盖。覆盖模式下两份文件作为一组提交，任一步失败会恢复旧文件或清理半成品。

## 8. 代表样本

| 样本 | 记录数 | 客户 | 币种 | 业务员 | 关键验证 |
|---|---:|---|---|---|---|
| Ease Hotel `MH40090` | 2 | Bridgeway Company Limited | 人民币 | Sophia Zhao | 买方/卖方分离正确；款式为空并由报告解释。 |
| `MH90180` | 4 | Hann Philippines, Inc. | 美元 | Michael | 多行明细连续抽取；款式空值有状态。 |
| Welllife `MG20056` | 3 | Welllife Company Limited | 美元 | Tinny Tian | PO 模板可抽取买方、业务员、规格和款式。 |
| Okura `MH40078` | 2 | Asset World Wex Co., Ltd. (Branch 00004) | 美元 | Sophia Zhao | 买方分支名称保留；两条被套行正确。 |
| `MW90145` | 2 | Amin Construction Pvt Ltd | 美元 | Vincy Lu | 卖方联系人正确；不可稳定识别字段留空并预警。 |
| Annupuri `MG10095` | 2 | Annupuri Garden 2 |  | Layla Chen | 币种留空；面料 `贡缎/T400/100C`，成分 `100C`，款式 `无飞边口袋无系带式`。 |

## 9. Annupuri 币种负规则

Annupuri 样本没有明确结算币种证据，因此 `币种` 必须输出为空字符串，解析报告状态为 `source_not_provided`，规则为 `currency.explicit`。不得从客户、文件名、默认外贸习惯或金额区域推断为美元。

## 10. 批量回归指标

| 指标 | 结果 |
|---|---:|
| 唯一 PI 数 | 12 |
| 解析成功 | 12 |
| 解析失败 | 0 |
| 0 记录文件 | 0 |
| 业务 JSON schema 合法 | 12/12 |
| 报告 JSON schema 合法 | 12/12 |
| 总业务记录数 | 49 |
| 缺客户文件 | 0 |
| 缺币种文件 | 1 |
| 缺业务员文件 | 0 |
| 缺款式文件 | 4 |
| 输入 SHA 未变化 | 12/12 |
| 空字段总数 | 185 |
| 有状态解释的空字段 | 185 |
| 无状态空字段 | 0 |

## 11. 状态统计

| 状态 | 数量 |
|---|---:|
| `extracted` | 192 |
| `normalized` | 301 |
| `derived` | 82 |
| `defaulted` | 171 |
| `source_not_provided` | 127 |
| `unrecognized` | 9 |
| `ambiguous` | 0 |
| `not_implemented` | 98 |

`not_implemented` 的 98 次来自 49 条记录中的 `物料编码` 和 `相似分数`。9 次 `unrecognized` 均进入解析报告警告，不污染业务 JSON。

## 12. 测试

- 正式测试命令：`uv run pytest`
- 文档收尾前验证结果：`65 passed`
- Gate 2D 回归输出来自 `data/output/gate2d_validation/`，包含 12 份业务结果和 12 份解析报告。

## 13. Git

- 本轮文档收尾基于 `24c6e6ea99a25312d92c0a4e284a3b2d25c3c103`。
- 本项目无 tag。
- 本项目无 remote。
- 本轮不 push、不创建 tag、不添加 remote。
- 本轮只允许文档改动，不修改 `src/`、`tests/`、`pyproject.toml`、`uv.lock`、真实 Excel 或既有业务 JSON 输出。

## 14. Day01

Day01 项目位于 `D:\AI-Learning\Projects\Day01`，与本项目完全隔离。本轮只读验证其稳定 HEAD 为 `b6206bf28a9ce5499e317cee324b16ea98bf569d`，tag 为 `v2.7C`，未执行任何写入。

## 15. 未实现

- LLM 结构化抽取。
- FAISS / BGE-M3 向量召回。
- 物料编码匹配。
- ERP 差异对比。
- API、前端、Agent、Docker。
- 需要人工确认的 `unrecognized` 字段自动纠偏。

## 16. 已知空值和风险

- Annupuri 币种为空是正确负规则，不是漏提。
- 款式缺失文件为 4 个：Ease Hotel、`MH90180`、`MH30095`、`MW90145`。
- 部分成分或款式描述只具备局部信号，当前规则无法稳定映射，状态为 `unrecognized`。
- 物料编码和相似分数属于后续物料匹配阶段，不得提前编造。
- 真实 PI 模板仍可能出现新表头、新语言、新币种和非连续明细，需要继续做样本驱动回归。

## 17. 下一阶段建议

1. 先进入 Gate 2E 或 Gate 3 前置审计，扩大真实 PI 样本并维护人工黄金样本。
2. 建立人工复核清单，优先处理 `unrecognized` 和缺款式样本。
3. 在不污染业务 JSON 的前提下，继续丰富诊断报告中的证据和规则名称。
4. 进入物料库阶段前，先冻结最终 20 字段合同和空值策略。
5. LLM 阶段只作为复杂表格语义抽取补强，不能绕过现有规则、测试和报告体系。

## 18. 交付文件

- [Gate 2D comparison JSON](<../../data/output/gate2d_validation/gate2d_comparison.json>) - `D:\AI-Learning\Projects\bedding-order-parser\data\output\gate2d_validation\gate2d_comparison.json`
- [Gate 2D comparison Markdown](<../../data/output/gate2d_validation/gate2d_comparison.md>) - `D:\AI-Learning\Projects\bedding-order-parser\data\output\gate2d_validation\gate2d_comparison.md`
- [Ease Hotel 业务结果 JSON](<../../data/output/gate2d_validation/all_results/3402510MH40090 Proforma Invoice【Ease Hotel】- Canasin 20251023_gate2d.json>) - `D:\AI-Learning\Projects\bedding-order-parser\data\output\gate2d_validation\all_results\3402510MH40090 Proforma Invoice【Ease Hotel】- Canasin 20251023_gate2d.json`
- [Ease Hotel 解析报告 JSON](<../../data/output/gate2d_validation/all_reports/3402510MH40090 Proforma Invoice【Ease Hotel】- Canasin 20251023_gate2d_parse_report.json>) - `D:\AI-Learning\Projects\bedding-order-parser\data\output\gate2d_validation\all_reports\3402510MH40090 Proforma Invoice【Ease Hotel】- Canasin 20251023_gate2d_parse_report.json`
- [Annupuri 业务结果 JSON](<../../data/output/gate2d_validation/all_results/3402510MG10095 Canasin Proforma Invoice-Annupuri Garden 2-Sep.23.2025 V4_gate2d.json>) - `D:\AI-Learning\Projects\bedding-order-parser\data\output\gate2d_validation\all_results\3402510MG10095 Canasin Proforma Invoice-Annupuri Garden 2-Sep.23.2025 V4_gate2d.json`
- [Annupuri 解析报告 JSON](<../../data/output/gate2d_validation/all_reports/3402510MG10095 Canasin Proforma Invoice-Annupuri Garden 2-Sep.23.2025 V4_gate2d_parse_report.json>) - `D:\AI-Learning\Projects\bedding-order-parser\data\output\gate2d_validation\all_reports\3402510MG10095 Canasin Proforma Invoice-Annupuri Garden 2-Sep.23.2025 V4_gate2d_parse_report.json`
- [Okura 解析报告 JSON](<../../data/output/gate2d_validation/all_reports/3402510MH40078  Proforma Invoice for Okura 20251020_gate2d_parse_report.json>) - `D:\AI-Learning\Projects\bedding-order-parser\data\output\gate2d_validation\all_reports\3402510MH40078  Proforma Invoice for Okura 20251020_gate2d_parse_report.json`
- [Gate 2D 最终报告](GATE_2D_FINAL_REPORT_2026-07-23.md) - `D:\AI-Learning\Projects\bedding-order-parser\docs\reports\GATE_2D_FINAL_REPORT_2026-07-23.md`
- [当前 Codex 交接文档](../handoffs/CODEX_CURRENT_HANDOFF.md) - `D:\AI-Learning\Projects\bedding-order-parser\docs\handoffs\CODEX_CURRENT_HANDOFF.md`
- [Gate 2D 归档交接文档](../handoffs/archive/CODEX_HANDOFF_2026-07-23_GATE2D.md) - `D:\AI-Learning\Projects\bedding-order-parser\docs\handoffs\archive\CODEX_HANDOFF_2026-07-23_GATE2D.md`
- [Codex 交付协议](../workflow/CODEX_DELIVERY_PROTOCOL.md) - `D:\AI-Learning\Projects\bedding-order-parser\docs\workflow\CODEX_DELIVERY_PROTOCOL.md`
