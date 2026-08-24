# Codex 交接归档：Gate 3A-A

归档日期：2026-07-24  
归档对象：规则字典与款式字典只读审计 Gate。  
结论：`CONDITIONAL PASS`

## 1. 项目身份

- 中文项目名称：床品订单智能解析与物料匹配系统。
- 英文项目名称：Bedding Order Parser。
- Python 包名：`bedding_order_parser`。
- 项目目录：`D:\AI-Learning\Projects\bedding-order-parser`。
- 当前环境：Windows 11、Python 3.12、uv、Git、pytest、openpyxl。

## 2. 审计边界

Gate 3A-A 是审计 Gate，不是功能 Gate。本轮只读审计字典源文件，未实现字典加载器，未修改生产解析逻辑，未修改测试，未安装依赖，未提交真实 Excel 或业务 JSON。

禁止范围仍包括：

- LLM / OpenAI API；
- Embedding / FAISS / BGE-M3；
- 物料匹配、物料编码、相似分数；
- ERP 对比；
- API、前端、Agent、Docker；
- 修改 Day01。

## 3. 基线

| 项目 | 状态 |
|---|---|
| 分支 | `master` |
| Gate 2D 业务代码基线 | `24c6e6ea99a25312d92c0a4e284a3b2d25c3c103` |
| Gate 3A-A 审计开始 HEAD | `0ca607cbba9b799c9a25b51780eeb6da953c31a3` |
| 测试 | `65 passed` |
| Day01 HEAD | `b6206bf28a9ce5499e317cee324b16ea98bf569d` |
| Day01 状态 | 干净 |

## 4. 审计文件

| 文件 | 角色 | SHA-256 | 结论 |
|---|---|---|---|
| `PI单提取规则.xlsx` | PI 规则源 | `8d527595f671b63762a15b1f5aa89004df4e773f68e776c824c37d57dece3c7c` | 2 个可见 sheet；可读；不能直接作为生产运行时字典 |
| `款式表_structured.xlsx` | 款式字典源 | `75faab06a151ee8f9d6d9dcb28ca4679414f4008fb86ae5d88acf5d0ee60660c` | 1 个可见 sheet；105 行结构款式；可用于契约设计 |

辅助只读参考：

- `cover_res_template.xlsx`，SHA-256 `9a21411dbc0d8946d56af7f4891fe46c79b47552104fec3caf33d0ea8c5a7bca`。
- `20251231 被套 系统下单语言（11行）.xlsx`，SHA-256 `1d7d121ed72b487a148103a0876ff98d51b0adf5fc5f25eea175d245a2eeeb37`。
- `PI被套产品行-下单语言部分参考数据（非ERP标准字段）.xlsx`，SHA-256 `e8d87f4e9d21b24c9515acd827865fc531347e3562e28cc5c1b2031d26615c6c`。

`material_info.csv` 仅记录存在，未分析。

## 5. 主要结论

- `PI单提取规则.xlsx`：总业务行 110，有效规则行 96，说明/文档行 14；`needs_normalization` 79 行，`needs_manual_restructuring` 17 行，`machine_ready` 0 行。
- `PI单提取规则.xlsx`：完全重复规则 20，同一触发词多标准值提示 5。
- `款式表_structured.xlsx`：有效规则 105 行，唯一标准款式 105 个，完全重复 0。
- `款式表_structured.xlsx`：一对多触发冲突提示 23，近似冲突提示 50。
- 11 行黄金款式 11/11 原文命中款式表。
- 当前 49 条业务输出中，款式 36/36 非空原文命中；成分 42/42 非空原文命中；面料 17/49 原文命中，30 未命中，2 粒度歧义。

## 6. 风险

Critical 风险：0。

High 风险：

- H001：`PI单提取规则.xlsx / 被套 提取规则` 依赖自然语言、合并单元格和跨行语义，不能直接生产运行。
- H002：`款式表_structured.xlsx / Sheet1` 缺稳定主键、优先级、排除词和冲突处理列。
- H003：`PI单提取规则.xlsx / 面料类价格表` 可见列没有价格字段；适合面料标准，不适合价格/物料语义。

## 7. Gate 3A-B 准入

准入判定：`CONDITIONAL PASS`。

允许 Gate 3A-B 讨论：

- 字典源 SHA-256 版本契约；
- 中间规范 JSON/CSV 字段；
- 款式结构定义、优先级、冲突处理；
- 面料、颜色、成分、密度标准值与别名；
- 字典加载失败的显式警告或 fallback 设计；
- 只读加载器测试方案。

仍不得直接实现：

- 生产字典加载器接入解析流程；
- 直接替换 Gate 2D 硬编码规则；
- LLM、Embedding、FAISS、物料匹配、ERP、API、前端、Agent、Docker；
- 真实 Excel 或业务 JSON 入库提交。

## 8. 交付文件

正式提交文档：

- `docs/reports/GATE_3A_A_DICTIONARY_AUDIT_2026-07-24.md`
- `docs/handoffs/CODEX_CURRENT_HANDOFF.md`
- `docs/handoffs/archive/CODEX_HANDOFF_2026-07-24_GATE3A_A.md`
- `README.md`
- `AGENTS.md`

本地忽略审计产物：

- `data/output/gate3a_audit/dictionary_manifest.json`
- `data/output/gate3a_audit/pi_rule_workbook_audit.json`
- `data/output/gate3a_audit/style_dictionary_audit.json`
- `data/output/gate3a_audit/current_rule_conflicts.json`
- `data/output/gate3a_audit/current_output_coverage.json`
- `data/output/gate3a_audit/gate3a_audit_summary.json`
- `data/output/gate3a_audit/gate3a_audit_summary.md`

## 9. 新会话提醒

新会话必须先读 `AGENTS.md`、`README.md`、`docs/project_scope.md`、`docs/project_context.md`、`docs/architecture.md`、`docs/workflow/CODEX_DELIVERY_PROTOCOL.md` 和 `docs/handoffs/CODEX_CURRENT_HANDOFF.md`。Gate 3A-A 后仍不能直接开发字典功能；如用户要继续，应先进入 Gate 3A-B 的数据契约和加载器设计任务。
