# Codex 当前交接文档

本文件是新 Codex 会话进入 Bedding Order Parser 项目前必须先读的当前交接入口。新会话不要直接开发，先按本文末尾的只读检查确认仓库状态、阶段边界和用户目标。

## 1. 项目身份

- 中文项目名称：床品订单智能解析与物料匹配系统。
- 正式课题名称：基于LLM与向量检索的床品订单智能解析与物料匹配系统研发。
- 英文项目名称：Bedding Order Parser。
- Python 包名：`bedding_order_parser`。
- 项目目录：`D:\AI-Learning\Projects\bedding-order-parser`。
- 当前开发环境：Windows 11、VS Code、Python 3.12、uv、Git、pytest、openpyxl。

当前项目没有 GUI、Web 前端、API 服务、Agent、Docker、LLM 调用或向量检索运行时。

## 2. Day01 隔离

Day01 位于 `D:\AI-Learning\Projects\Day01`，是独立的企业文件整理助手项目。稳定 HEAD 为 `b6206bf28a9ce5499e317cee324b16ea98bf569d`，tag 为 `v2.7C`。Bedding Order Parser 不得写入 Day01，不得共享源码、虚拟环境、依赖锁文件或 Git 历史。除只读验证外，不要碰 Day01。

## 3. 当前 Git 基线

- 分支：`master`。
- Gate 2D 业务代码基线 HEAD：`24c6e6ea99a25312d92c0a4e284a3b2d25c3c103`。
- 对应提交：`feat: add party extraction and field diagnostics`。
- 本交接文档由后续 docs-only 收尾提交加入，不改变解析器代码。
- Git 作者必须保持：`小艾 <1746762028@qq.com>`。
- 本仓库当前不需要 remote，不创建 tag，不 push，除非用户明确授权。

## 4. Gate 历史

| Gate | 关键提交 | 内容 |
|---|---|---|
| Gate 0 | `260270b` | 初始化独立 Python 项目、Git、uv、目录和冒烟测试。 |
| Gate 0.1 | `0fa1a6a` | 建立 `AGENTS.md`、项目背景、范围和架构文档。 |
| Gate 1 | `18b5dbd` | 建立离线 PI 到最终 20 字段 JSON 基线解析器。 |
| Gate 2A/2B | `52f4bc0` | 多模板真实 PI 回归后改进解析规则。 |
| Gate 2C | `92e1248`、`65ac8f2` | 保留签名块买方抽取，处理复杂结构和黄金样本规则。 |
| Gate 2D | `24c6e6e` | 增加交易双方抽取、字段级诊断和双输出。 |

## 5. 当前模块结构

- `cli.py` / `__main__.py`：命令行入口，只处理参数、错误和用户可见摘要。
- `pipeline/order_parser.py`：读取、定位、解析、元数据、商品明细、诊断、SHA 校验和双输出编排。
- `excel/workbook_reader.py`：只读加载工作簿、计算 SHA-256。
- `excel/sheet_locator.py`：选择 PI / PI-update / 模糊 PI / 第一个工作表。
- `excel/table_parser.py`：合并单元格回填、表头定位、明细行连续性、前后区域拆分。
- `extraction/party_extractor.py`：买方组织、卖方联系人、买方联系人辅助证据。
- `extraction/metadata_extractor.py`：交易双方、币种、发货日期、包装、表头备注。
- `extraction/item_extractor.py`：被套筛选、强排除、相邻描述继承、最终记录和诊断。
- `normalization/field_normalizer.py`：规格、颜色、面料、成分、款式、行备注等标准化。
- `models/final_result.py`：最终 20 字段合同。
- `diagnostics/models.py`：状态、证据、字段诊断、记录诊断和报告模型。
- `diagnostics/report_builder.py`：保证报告字段顺序和值与业务 JSON 一致。
- `serialization/json_writer.py`：原业务 JSON 写入能力。
- `serialization/diagnostic_writer.py`：业务结果和解析报告成对安全写入。

## 6. 最终 20 字段合同

字段顺序固定为：

`客户`、`币种`、`业务员`、`表头备注`、`行号`、`物料编码`、`物料名称`、`规格`、`颜色`、`面料`、`面料-涤棉成分`、`款式`、`加标方式`、`尺寸类型`、`数量`、`行备注`、`计划发货日期`、`包装方式`、`是否绣花`、`相似分数`。

业务 JSON 中不得出现诊断状态、提示语、空值原因或人工复核文本。没有明确证据的字段保持空字符串。`相似分数` 为浮点数，当前固定 `0.0`。

## 7. 交易双方定义

- `客户` 是买方主体组织，来自 buyer / invoice to / bill to / sold to 等买方区域。
- `业务员` 是 Canasin 卖方区域联系人、业务或区域联系人。
- 买方联系人只作为辅助证据，不写入最终 20 字段。
- 不能把 Canasin 卖方公司当客户，也不能把买方联系人当业务员。

## 8. 字段状态

`extracted`、`normalized`、`derived`、`defaulted`、`source_not_provided`、`unrecognized`、`ambiguous`、`not_implemented` 是当前解析报告唯一允许的 8 类状态。

`source_not_provided` 代表源文件没有足够信息；`unrecognized` 代表源文件存在信号但规则无法稳定转换；`ambiguous` 代表候选冲突；`not_implemented` 代表后续阶段功能，例如物料编码和相似度。

## 9. 双输出规则

每次解析默认写出两份文件：

- 业务 JSON：用户指定的 `--output` 路径。
- 解析报告 JSON：同目录，默认名为 `*_parse_report.json`。

两份文件必须作为一组处理。未传 `--overwrite` 时任一目标存在都拒绝写入。覆盖模式下任一步失败都要回滚旧文件或清理半成品。

## 10. 12 个真实 PI 回归关注点

| 文件/样本 | 回归关注点 |
|---|---|
| `20251231 被套 Proforma Invoice（11行）` | 11 行黄金样本款式顺序保持正确。 |
| `3402505MR30022 H Hotel JODC` | 非连续行号和 Ms Sunny 卖方联系人可稳定抽取。 |
| `3402510MG10094 Blooming` | 三个规格为 `270*180cm`、`270*210cm`、`270*250cm`，不会把 `+1cm` 错并入规格。 |
| `3402510MG10095 Annupuri` | 币种无证据时留空；共享描述可产出 `贡缎/T400/100C`、`100C` 和标准款式。 |
| `3402510MH40078 Okura` | 买方分支名 `Asset World Wex Co., Ltd. (Branch 00004)` 保留。 |
| `3402510MH40090 Ease Hotel` | 客户为 `Bridgeway Company Limited`，业务员为 `Sophia Zhao`，CNY 标准化为人民币。 |
| `3402510MH90180` | 客户为 `Hann Philippines, Inc.`，业务员为 `Michael`，4 条记录连续输出。 |
| `3402510MR30051 Double Tree Jeddah` | 3 条被套记录、美元、Ms Sunny，局部无法识别字段进入警告。 |
| `3402511MG20056 Welllife` | 客户为 `Welllife Company Limited`，业务员为 `Tinny Tian`，3 条 PO 明细稳定。 |
| `3402511MH30095` | 客户为 `OC International Furniture`，业务员组合字符串保留，缺款式有解释。 |
| `3402511MW30039 MAK/Makotel` | 文件名不决定客户；以表内买方证据输出 `HAI HA HANDICRAFT CO., LTD`。 |
| `3402511MW90145` | 客户为 `Amin Construction Pvt Ltd`，业务员为 `Vincy Lu`，不可稳定识别字段进入报告。 |

## 11. 当前 Gate 2D 结果

- 唯一 PI：12。
- 成功：12。
- 失败：0。
- 0 记录文件：0。
- 总业务记录：49。
- 业务 schema：12/12。
- 报告 schema：12/12。
- 缺客户文件：0。
- 缺币种文件：1，仅 Annupuri。
- 缺业务员文件：0。
- 缺款式文件：4。
- 输入 SHA 未变化：12/12。
- 空字段：185，全部有状态解释。
- 状态汇总：`extracted 192`、`normalized 301`、`derived 82`、`defaulted 171`、`source_not_provided 127`、`unrecognized 9`、`ambiguous 0`、`not_implemented 98`。

## 12. 当前没有实现

LLM 抽取、OpenAI API、FAISS、BGE-M3 embedding、物料库召回、物料编码匹配、ERP 对比、FastAPI、前端、Agent、Docker 都没有实现。不要提前创建空壳模块，也不要把 `物料编码` 或 `相似分数` 伪造成真实匹配结果。

## 13. 禁止踩的坑

- 不要修改真实企业 Excel。
- 不要把真实企业 Excel 或生成的业务 JSON 提交到 Git。
- 不要把诊断文字写入业务 JSON。
- 不要为了“看起来完整”新增未来阶段空壳。
- 不要改 `pyproject.toml`、`uv.lock` 或 Python 版本，除非用户明确批准。
- 不要 push、加 remote、建 tag。
- 不要修改 Day01。
- 不要在新会话里跳过 `AGENTS.md` 和本交接文档直接开发。

## 14. 下一阶段建议

先用更多真实 PI 做 Gate 2E 式回归审计，聚焦缺款式和 `unrecognized` 字段。随后再决定是否进入 LLM 辅助抽取或物料库整理。进入物料匹配前必须先确认字段合同、空值策略、人工复核策略和样本验收标准。

## 15. 新会话第一批只读检查

在任何开发前先执行：

```powershell
cd D:\AI-Learning\Projects\bedding-order-parser
git status --short
git rev-parse HEAD
git log --oneline --decorate -5
git config --get user.name
git config --get user.email
uv run pytest
Test-Path docs\handoffs\CODEX_CURRENT_HANDOFF.md
Test-Path data\output\gate2d_validation\gate2d_comparison.json
```

如需确认 Day01 隔离，只读执行：

```powershell
cd D:\AI-Learning\Projects\Day01
git status --short
git rev-parse HEAD
git tag -n
```

## 16. 新会话不要直接开发

新会话必须先读 `AGENTS.md`、`README.md`、`docs/project_scope.md`、`docs/project_context.md`、`docs/architecture.md` 和本文件，确认用户要求属于当前 Gate 边界，再提出或执行下一步。若用户要求进入 LLM、物料匹配、ERP、API、前端或 Agent，应先明确这是新 Gate，并先做只读状态确认。
