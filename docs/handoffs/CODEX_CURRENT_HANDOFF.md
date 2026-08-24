# Codex 当前交接文档

本文件是新 Codex 会话进入 Bedding Order Parser 项目前必须先读的当前交接入口。新会话不要直接开发，先按本文末尾的只读检查确认仓库状态、阶段边界和用户目标。

## 1. 项目身份

- 中文项目名称：床品订单智能解析与物料匹配系统。
- 正式课题名称：基于LLM与向量检索的床品订单智能解析与物料匹配系统研发。
- 英文项目名称：Bedding Order Parser。
- Python 包名：`bedding_order_parser`。
- 项目目录：`D:\AI-Learning\Projects\bedding-order-parser`。
- 当前开发环境：Windows 11、VS Code、Python 3.12、uv、Git、pytest、openpyxl。

当前项目没有 GUI、Web 前端、API 服务、Agent、Docker、LLM 调用、Embedding、FAISS 或向量检索运行时。

## 2. Day01 隔离

Day01 位于 `D:\AI-Learning\Projects\Day01`，是独立的企业文件整理助手项目。稳定 HEAD 为 `b6206bf28a9ce5499e317cee324b16ea98bf569d`，tag 为 `v2.7C`。Bedding Order Parser 不得写入 Day01，不得共享源码、虚拟环境、依赖锁文件或 Git 历史。除只读验证外，不要碰 Day01。

## 3. 当前 Git 基线

- 分支：`master`。
- Gate 2D 业务代码基线 HEAD：`24c6e6ea99a25312d92c0a4e284a3b2d25c3c103`。
- Gate 3A-A 审计开始 HEAD：`0ca607cbba9b799c9a25b51780eeb6da953c31a3`。
- Gate 3A-A 提交类型：docs-only，提交信息为 `docs: audit PI rule and style dictionaries`。
- Git 作者必须保持：`小艾 <1746762028@qq.com>`。
- 本仓库当前不需要 remote，不创建 tag，不 push，除非用户明确授权。

## 4. Gate 历史

| Gate | 关键提交/状态 | 内容 |
|---|---|---|
| Gate 0 | `260270b` | 初始化独立 Python 项目、Git、uv、目录和冒烟测试。 |
| Gate 0.1 | `0fa1a6a` | 建立 `AGENTS.md`、项目背景、范围和架构文档。 |
| Gate 1 | `18b5dbd` | 建立离线 PI 到最终 20 字段 JSON 基线解析器。 |
| Gate 2A/2B | `52f4bc0` | 多模板真实 PI 回归后改进解析规则。 |
| Gate 2C | `92e1248`、`65ac8f2` | 保留签名块买方抽取，处理复杂结构和黄金样本规则。 |
| Gate 2D | `24c6e6e` | 增加交易双方抽取、字段级诊断和双输出。 |
| Gate 2D 收尾 | `0ca607c` | 增加 Gate 2D 报告、交付协议和交接文档。 |
| Gate 3A-A | 本文档提交 | 规则字典与款式字典只读审计，仅文档和本地忽略审计产物。 |

## 5. 当前能力

Gate 2D 已能读取真实 PI Excel、筛选被套商品，并输出：

- 最终 20 字段业务 JSON；
- 与业务 JSON 成对的字段级解析报告 JSON；
- 输入 SHA-256 校验；
- 交易双方识别、币种、业务员、商品明细、款式、面料、成分等确定性规则结果。

最终 20 字段顺序固定为：

`客户`、`币种`、`业务员`、`表头备注`、`行号`、`物料编码`、`物料名称`、`规格`、`颜色`、`面料`、`面料-涤棉成分`、`款式`、`加标方式`、`尺寸类型`、`数量`、`行备注`、`计划发货日期`、`包装方式`、`是否绣花`、`相似分数`。

业务 JSON 中不得出现诊断状态、提示语、空值原因或人工复核文本。没有明确证据的字段保持空字符串。`物料编码` 当前固定为空字符串，`相似分数` 当前固定为 `0.0`。

## 6. Gate 3A-A 审计结论

Gate 3A-A 是审计 Gate，不是功能 Gate。本轮没有实现字典加载器，没有修改 `src/`、`tests/`、依赖、Schema 或解析流程。

核心审计文件：

| 文件 | SHA-256 | Sheet 数 | 结论 |
|---|---|---:|---|
| `PI单提取规则.xlsx` | `8d527595f671b63762a15b1f5aa89004df4e773f68e776c824c37d57dece3c7c` | 2 | 可读、版本明确；规则表达混合自然语言和合并单元格，不能直接作为生产运行时字典 |
| `款式表_structured.xlsx` | `75faab06a151ee8f9d6d9dcb28ca4679414f4008fb86ae5d88acf5d0ee60660c` | 1 | 可读、结构较稳定；适合契约设计和校验，但缺少主键、优先级、排除词和冲突策略 |

关键统计：

- PI 规则总业务行 110，有效规则行 96，说明/文档行 14。
- PI 规则 `needs_normalization` 79 行，`needs_manual_restructuring` 17 行，`machine_ready` 0 行。
- PI 规则完全重复 20 条，同一触发词多标准值提示 5 条。
- 款式字典有效规则 105 行，唯一标准款式 105 个，完全重复 0 条。
- 款式字典一对多触发冲突提示 23 组，近似冲突提示 50 组。
- 11 行黄金款式 11/11 原文命中款式字典。
- 当前 49 条业务输出中，款式非空 36 条且 36/36 原文命中；面料 49 条中 17 条原文命中、30 条未命中、2 条粒度歧义；成分 42 条非空且 42/42 原文命中。
- Critical 风险 0，High 风险 3，Medium 风险 2。

审计判定：`CONDITIONAL PASS`。允许进入 Gate 3A-B 的数据契约和加载器设计讨论，但不能直接实现生产加载器，也不能直接用字典替换 Gate 2D 硬编码规则。

## 7. Gate 3A-B 可以讨论什么

Gate 3A-B 可以讨论并设计：

- 字典源 SHA-256 版本契约；
- 中间规范 JSON/CSV 的字段；
- PI 规则表的 include/exclude/default/alias/standard_value 拆分；
- 款式表的 `style_rule_id`、组件字段、优先级、冲突处理草案；
- 面料、颜色、成分、密度的标准值和别名策略；
- 字典加载失败时的显式警告或 fallback 策略；
- 只读加载器的测试方案。

## 8. Gate 3A-B 仍不得直接实现什么

除非用户给出新的明确 Gate 指令，否则不得：

- 把规则 Excel 接入生产解析流程；
- 直接替换 `normalize_style`、`normalize_fabric`、`normalize_component` 或商品筛选逻辑；
- 创建 LLM、Embedding、FAISS、BGE-M3、物料匹配、ERP、API、前端、Agent 或 Docker 能力；
- 伪造 `物料编码` 或 `相似分数`；
- 提交真实 Excel、真实 PI 或 `data/output/` 生成结果；
- 修改 Day01。

## 9. 本轮交付文件

正式提交文件：

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

## 10. 新会话第一批只读检查

在任何开发前先执行：

```powershell
cd D:\AI-Learning\Projects\bedding-order-parser
git status --short
git rev-parse HEAD
git log --oneline --decorate -5
git config --get user.name
git config --get user.email
uv run pytest
Test-Path docs\reports\GATE_3A_A_DICTIONARY_AUDIT_2026-07-24.md
Test-Path data\output\gate3a_audit\gate3a_audit_summary.json
```

如需确认 Day01 隔离，只读执行：

```powershell
cd D:\AI-Learning\Projects\Day01
git status --short
git rev-parse HEAD
git tag -n
```

## 11. 新会话不要直接开发

新会话必须先读 `AGENTS.md`、`README.md`、`docs/project_scope.md`、`docs/project_context.md`、`docs/architecture.md`、`docs/workflow/CODEX_DELIVERY_PROTOCOL.md` 和本文件，确认用户要求属于当前 Gate 边界，再提出或执行下一步。若用户要求进入字典加载、LLM、物料匹配、ERP、API、前端或 Agent，应先明确这是新 Gate，并先做只读状态确认。
