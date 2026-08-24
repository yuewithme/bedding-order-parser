# Gate 3A-A 字典源只读审计报告

审计日期：2026-07-24  
审计类型：只读审计，不实现功能，不修改解析器，不提交真实 Excel 或生成 JSON。  
结论：`CONDITIONAL PASS`

## 1. 初始状态

| 项目 | 结果 |
|---|---|
| 仓库 | `D:\AI-Learning\Projects\bedding-order-parser` |
| 分支 | `master` |
| 审计开始 HEAD | `0ca607cbba9b799c9a25b51780eeb6da953c31a3` |
| Gate 2D 业务代码基线 | `24c6e6ea99a25312d92c0a4e284a3b2d25c3c103` |
| 初始工作区 | 干净 |
| Python | `Python 3.12.10` |
| uv | `uv 0.11.28` |
| 初始测试 | `65 passed` |
| Day01 HEAD | `b6206bf28a9ce5499e317cee324b16ea98bf569d` |
| Day01 状态 | 干净，tag `v2.7C` |

事实：Gate 2D 已能从真实 PI Excel 输出最终 20 字段业务 JSON 和字段级解析报告 JSON。  
边界：本轮只审计字典源，未创建加载器、数据类、匹配算法、LLM、Embedding、FAISS、API 或前端。

## 2. 审计数据清单

核心审计文件：

| 文件 | 角色 | 相对路径 | SHA-256 |
|---|---|---|---|
| `PI单提取规则.xlsx` | PI 规则源 | `data/reference/PI单提取规则.xlsx` | `8d527595f671b63762a15b1f5aa89004df4e773f68e776c824c37d57dece3c7c` |
| `款式表_structured.xlsx` | 款式字典源 | `data/reference/款式表_structured.xlsx` | `75faab06a151ee8f9d6d9dcb28ca4679414f4008fb86ae5d88acf5d0ee60660c` |

辅助只读参考文件：

| 文件 | 相对路径 | SHA-256 | 用途 |
|---|---|---|---|
| `cover_res_template.xlsx` | `data/reference/cover_res_template.xlsx` | `9a21411dbc0d8946d56af7f4891fe46c79b47552104fec3caf33d0ea8c5a7bca` | 20 字段模板对照 |
| `20251231 被套 系统下单语言（11行）.xlsx` | `data/golden/20251231 被套 系统下单语言（11行）.xlsx` | `1d7d121ed72b487a148103a0876ff98d51b0adf5fc5f25eea175d245a2eeeb37` | 11 行黄金款式覆盖验证 |
| `PI被套产品行-下单语言部分参考数据（非ERP标准字段）.xlsx` | `data/golden/PI被套产品行-下单语言部分参考数据（非ERP标准字段）.xlsx` | `e8d87f4e9d21b24c9515acd827865fc531347e3562e28cc5c1b2031d26615c6c` | PI 行与下单语言辅助对照 |

发现但未分析：`data/reference/material_info.csv`。原因：本轮明确禁止审计物料库、ERP 或物料匹配阶段资料。

## 3. 重名、版本与 SHA

| 检查项 | 结果 |
|---|---|
| 核心文件是否定位 | 2/2 成功 |
| 辅助文件是否定位 | 3/3 成功 |
| 同名文件 | 未发现同名候选 |
| 副本/旧版/copy/backup 候选 | 未发现可疑候选 |
| Git 跟踪状态 | 5 个审计/辅助 Excel 均未跟踪 |
| Git 忽略状态 | 5 个审计/辅助 Excel 均在 `data/reference/` 或 `data/golden/` 下被忽略 |
| 源文件审计前后 SHA | 全部一致 |

事实：当前版本明确，可以作为 Gate 3A-B 设计输入。  
风险：字典源仍是本地忽略文件，后续需要以 SHA-256 固化版本契约。

## 4. `PI单提取规则.xlsx` 结构

| Sheet | 可见性 | 范围 | 表头行 | 数据行 | 有效列 | 合并单元格 | 公式 | 错误值 | 判定 |
|---|---|---|---:|---|---|---:|---:|---:|---|
| `被套 提取规则` | visible | `A1:L36`，业务值 `A:E` | 1 | 2-36 | A-E | 10 | 0 | 0 | 正式规则数据，但需人工结构化 |
| `面料类价格表` | visible | `A1:E76` | 1 | 2-76 | A-E | 0 | 0 | 0 | 面料/颜色/成分/密度标准源 |

事实：OOXML 声明范围、openpyxl 范围、实际业务非空范围均可解释，没有 `XFD` 型大范围污染。  
推断：`被套 提取规则` 的合并单元格承担字段继承语义，不能直接逐行读取为独立规则。  
建议：Gate 3A-B 应先生成清洗后的中间规范文件，再考虑运行时加载。

## 5. 规则类型与 20 字段映射

PI 规则统计口径：两张可见 sheet 的数据行；排除表头行，标记说明/文档行单独统计。

| 指标 | 数量 |
|---|---:|
| 总业务行 | 110 |
| 有效规则行 | 96 |
| 说明/文档行 | 14 |
| `machine_ready` | 0 |
| `needs_normalization` | 79 |
| `needs_manual_restructuring` | 17 |
| 完全重复规则 | 20 |
| 同一触发词多标准值 | 5 |
| 缺失目标字段 | 10 |
| 缺失标准值 | 35 |
| 缺失触发条件 | 35 |

| 规则类型 | 数量 |
|---|---:|
| `fabric_mapping` | 45 |
| `format_rule` | 15 |
| `style_mapping` | 5 |
| `default_value` | 3 |
| `composition_mapping` | 1 |
| `unknown` | 41 |

20 字段覆盖判断：

| 字段组 | 字典中有直接或间接来源 | 结论 |
|---|---|---|
| 物料名称、规格、颜色、面料、面料-涤棉成分、款式、尺寸类型、行备注、是否绣花 | 有 | 可进入 Gate 3A-B 数据契约设计 |
| 币种 | 有文字痕迹 | 当前仅可视为说明，不足以替换 Gate 2D 币种规则 |
| 客户、业务员、表头备注、行号、数量、计划发货日期、包装方式 | 无 | 继续依赖 Gate 2D 确定性解析 |
| 物料编码、相似分数 | 无 | 后续物料匹配阶段，不得伪造 |

## 6. 面料与成分字典

事实：`面料类价格表` 有 75 行数据、5 个业务列：面料品类、面料、颜色、涤棉成份、密度。  
事实：该表名包含“价格表”，但当前可见业务列没有价格字段。  
推断：它更适合作为面料/颜色/成分/密度标准源，而不是价格或物料匹配源。  
风险：当前 Gate 2D 输出面料粒度较粗，例如输出聚合标准，而字典保留完整面料结构；直接 exact match 会造成大量未命中。

建议：Gate 3A-B 先定义 `fabric_family`、`fabric_standard`、`component_standard`、`density`、`color_default` 的契约，不把价格或物料编码纳入本阶段。

## 7. 款式字典与组件模型

`款式表_structured.xlsx` 结构：

| Sheet | 可见性 | 范围 | 表头行 | 数据行 | 有效列 | 合并单元格 | 公式 | 错误值 |
|---|---|---|---:|---|---|---:|---:|---:|
| `Sheet1` | visible | `A1:H106` | 1 | 2-106 | A-H | 0 | 0 | 0 |

列结构：

| 列 | 含义 |
|---|---|
| `被套款式` | 标准款式名称 |
| `飞边 (Flange)` | 飞边结构 |
| `系带 (Tie)` | 系带结构 |
| `拉链 (Zipper)` | 拉链结构 |
| `是否口袋式 (Has Pocket)` | 口袋结构 |
| `是否迎宾式 (Is Welcome Style)` | 迎宾式结构 |
| `其他款式结构 (Other Structure)` | 其他结构 |
| `备注尺寸 (Dimensions)` | 尺寸/备注辅助信息 |

统计口径：Sheet1 数据行 2-106；对比较键执行无损审计标准化，不改写原值。

| 指标 | 数量 |
|---|---:|
| 总行数 | 105 |
| 有效规则行 | 105 |
| 唯一标准款式 | 105 |
| 可机器读取行 | 105 |
| 完全重复 | 0 |
| 缺失标准款式 | 0 |
| 缺失识别特征 | 0 |
| 一对多触发冲突提示 | 23 |
| 近似冲突提示 | 50 |

事实：款式表比 PI 规则表更结构化，可作为数据契约设计的主要来源。  
风险：它没有稳定主键、优先级、排除词、同义词列或冲突处理列，不能直接替换 `normalize_style`。  
建议：Gate 3A-B 先把它加载为只读 `StyleDefinition`/校验数据，先用于覆盖检查和诊断，不直接改变业务 JSON。

## 8. 11 行黄金覆盖

来源：`data/output/gate2d_validation/gate2d_comparison.json` 中的 11 行黄金款式预期，只读对照 `款式表_structured.xlsx`。

| 指标 | 数量 |
|---|---:|
| 黄金款式总数 | 11 |
| 原文 exact match | 11 |
| 审计标准化 exact match | 0 |
| 未命中 | 0 |
| 多候选 | 0 |

事实：当前 11 行黄金款式结果都能在款式表中找到标准项。  
推断：款式表足以表达 Gate 2D 已固化的 11 行黄金款式结果。  
限制：本轮未重新运行真实业务规则匹配，未修改黄金预期。

## 9. 当前 49 条输出覆盖

来源：Gate 2D 已生成业务 JSON 与解析报告，只读统计。

| 字段 | 总记录 | 非空 | 空 | 原文 exact match | 标准化 exact match | 未命中 | 歧义 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 款式 | 49 | 36 | 13 | 36 | 0 | 0 | 0 |
| 面料 | 49 | 49 | 0 | 17 | 0 | 30 | 2 |
| 面料-涤棉成分 | 49 | 42 | 7 | 42 | 0 | 0 | 0 |

事实：款式和成分覆盖较好；面料字段存在明显粒度差异。  
推断：Gate 3A-B 的首要设计问题不是“能不能读款式表”，而是“面料标准值到底以聚合输出为准，还是以完整价格表条目为准”。  
建议：用户确认前，加载器不得直接改写现有面料输出。

## 10. 当前代码与字典冲突

| ID | 等级 | 字段 | 当前位置 | 字典位置 | 影响 |
|---|---|---|---|---|---|
| C001 | Medium | 物料名称/被套筛选 | `extraction/item_extractor.py: INCLUDE_KEYWORDS` | `PI单提取规则.xlsx / 被套 提取规则 / row 2` | 字典缺少部分代码补充词，直接替换会降低召回 |
| C002 | High | 被套筛选 | `extraction/item_extractor.py: STRONG_EXCLUDE_KEYWORDS` | `PI单提取规则.xlsx / 被套 提取规则` | 字典没有独立排除词列，可能误召回非被套 |
| C003 | Medium | 面料-涤棉成分 | `normalization/field_normalizer.py: normalize_component` | `面料类价格表 / 涤棉成份列` | 中文百分比与当前代码式标准值需要契约 |
| C004 | High | 款式 | `normalization/field_normalizer.py: normalize_style` | `款式表_structured.xlsx / Sheet1 / rows 2-106` | 字典更全但缺优先级和排除词，不能直接替换 |
| C005 | Medium | 颜色 | `normalize_color` | PI 规则表与面料表 | 默认漂白规则需用户确认 |
| C006 | Medium | 面料 | `normalize_fabric` | `面料类价格表` | 当前输出粒度比字典粗 |
| C007 | Low | 客户/业务员/币种 | `metadata_extractor.py` / `party_extractor.py` | PI 规则表 | 元数据结构识别不应由当前字典替换 |

统计：7 项代码-字典差异，其中 High 2、Medium 4、Low 1；需要用户确认 4 项。

## 11. 用户决策问题

| 问题 | 事实 | 推断/风险 | 建议 |
|---|---|---|---|
| 是否可以进入 Gate 3A-B？ | 核心文件版本明确，SHA 稳定，Critical 0 | 仍有 High 3 | 可以进入设计讨论，不能直接实现生产加载器 |
| 是否先生成中间规范文件？ | PI 规则 0 行 machine_ready，17 行需人工结构化 | 直接运行时加载风险高 | 是，先生成规范 JSON/CSV 草案 |
| 款式表是否可作为运行时字典？ | 105 行结构完整 | 缺主键/优先级/排除词 | 先用于校验/诊断，用户确认后再驱动解析 |
| 面料标准值用什么粒度？ | 当前 49 条面料仅 17 条命中字典标准 | 完整面料与聚合面料不一致 | Gate 3A-B 必须先定粒度 |
| 成分标准怎么写？ | 字典为中文百分比，当前输出为代码式 | 标准值/别名需映射 | 设计 `standard_value` + `aliases` |
| 排除词由哪里来？ | 字典没有独立排除词列，代码有强排除 | 直接字典化会误召回 | 保留代码强排除，另设用户确认清单 |
| 默认颜色是否都是漂白？ | 字典和代码均有默认趋势 | 并非所有 PI 都显式提供颜色 | 需要用户确认默认范围 |
| 缺款式字段怎么处理？ | 13 条当前输出为空，其中多为源未提供 | 字典不能凭空补全 | 继续空值 + 诊断说明 |
| 规则 ID 如何生成？ | 两个 Excel 均无稳定主键 | 依赖行号不利于版本变化 | 程序生成 `source_sha + sheet + row + normalized_key` 派生 ID |
| 字典变更如何处理？ | 本轮记录 SHA | 静默变化会破坏可复现性 | Gate 3A-B 至少警告；生产前应拒绝未知 SHA |
| 字典放仓库内吗？ | 当前真实 Excel 被 Git 忽略 | 提交真实资料有治理风险 | 继续外部/ignored；只提交契约、报告和测试 |
| 失败是否回退硬编码？ | Gate 2D 硬编码规则稳定 | 静默回退会掩盖字典质量问题 | 设计期允许显式 fallback，生产需报告 |

## 12. Gate 3A-B 建议架构与测试

建议架构方向：

- 先设计数据契约，不直接接入生产解析流程。
- 输出可审计中间规范文件，保留 `raw_value`、`normalized_for_audit`、`source_file_sha256`、`source_sheet`、`source_row`。
- 款式字典优先作为结构校验和诊断来源。
- PI 规则表先拆出包含词、排除词、默认值、标准值、别名、备注说明。
- 面料表拆成面料品类、完整面料、颜色、成分、密度，不进入物料编码匹配。

建议测试：

- 字典文件 SHA 不匹配时有明确失败/警告。
- 中间规范文件生成稳定、排序稳定。
- 款式表 105 行可读，11 行黄金款式 11/11 命中。
- 当前 49 条结果的款式、面料、成分覆盖统计可复现。
- 字典加载失败不得污染业务 JSON。

## 13. Gate 3A-B 不应实现的事项

- 不接入 LLM、OpenAI API、Embedding、FAISS 或 BGE-M3。
- 不做物料编码匹配，不生成真实相似分数。
- 不做 ERP 对比、API、前端、Agent、Docker。
- 不改真实 Excel，不提交真实字典或真实 PI。
- 不直接用字典替换 Gate 2D 的确定性规则。

## 14. Git 与保护检查

| 检查 | 结果 |
|---|---|
| 源 Excel 哈希前后一致 | 是 |
| 生产代码修改 | 无 |
| 测试修改 | 无 |
| 依赖修改 | 无 |
| `pyproject.toml` / `uv.lock` | 无修改 |
| Day01 文件修改 | 无 |
| 真实 Excel 提交 | 无 |
| 生成 JSON/Markdown 审计产物 | 位于 `data/output/gate3a_audit/`，被 Git 忽略 |

## 15. 交付物

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

## 16. 最终结论

Gate 3A-A 判定为 `CONDITIONAL PASS`。

事实：两个核心 Excel 均能稳定只读打开，版本明确，源文件 SHA 前后一致；款式表能覆盖 11 行黄金款式，当前 49 条输出中的 36 个非空款式全部原文命中。  
风险：PI 规则表无法直接机器运行，款式表缺少运行时必须的主键、优先级和排除词；面料输出粒度与面料表存在差异。  
建议：允许进入 Gate 3A-B 的数据契约和加载器设计讨论，但 Gate 3A-B 开始前必须确认面料粒度、排除词来源、默认颜色范围和字典 SHA 变更策略。
