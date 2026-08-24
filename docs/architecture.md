# 架构说明

## 1. 架构目标

Bedding Order Parser 采用分层、模块化架构。目标是在真实 Excel PI 结构复杂、客户模板差异大的前提下，逐步构建可测试、可维护、可扩展的解析和匹配系统。

当前文档只定义目标架构和阶段边界，不表示所有目录和模块都已经实现。

## 2. 模块化原则

- 一个模块承担一种主要职责。
- 一个 Python 文件不同时承担入口、读取、解析、校验和输出。
- 不把所有功能堆进 `main.py` 或 `cli.py`。
- 不创建数千行 God File。
- 不创建同时负责所有功能的 God Class。
- Excel 读取与 Excel 分析分开。
- 数据模型与业务执行分开。
- JSON 序列化与字段提取分开。
- 解析与校验分开。
- LLM 调用与 Prompt 定义分开。
- 向量召回与硬条件过滤分开。
- ERP 对比与 Excel 读取分开。
- 日志、路径和配置集中管理。
- 不出现循环导入。
- 不为未来功能提前创建没有使用者的接口、类或空壳模块。

## 3. 分层说明

- 入口层：`__main__.py` 和 `cli.py`，只负责命令行参数、输入输出消息和退出码。
- 流程编排层：`pipeline/`，负责组织执行顺序，不实现底层细节。
- Excel 能力层：`excel/`，负责只读打开工作簿、结构侦察、合并单元格和工作表快照。
- 数据模型层：`models/`，只定义结构化数据对象。
- 序列化层：`serialization/`，负责把模型写成稳定 JSON。
- 校验层：`validation/`，负责 Schema 或业务约束校验。
- LLM 层：`llm/`，负责模型客户端、提示词和结构化抽取。
- 匹配层：`matching/`，负责向量索引、硬条件过滤和物料匹配。
- ERP 层：`erp/`，负责 ERP 文件对比和差异标记。
- API 层：`api/`，负责后续 HTTP 接口，不直接实现业务解析。
- 基础设施层：`infrastructure/`，负责路径、日志和配置。

## 4. 目标目录树

以下是长期目标结构，不要求在当前阶段全部创建：

```text
bedding-order-parser/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore
├── .gitattributes
├── data/
│   ├── input/
│   └── output/
├── docs/
│   ├── project_scope.md
│   ├── project_context.md
│   └── architecture.md
├── src/
│   └── bedding_order_parser/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── exceptions.py
│       ├── models/
│       │   ├── workbook.py
│       │   ├── order.py
│       │   └── material.py
│       ├── excel/
│       │   ├── workbook_reader.py
│       │   ├── workbook_inspector.py
│       │   ├── merged_cells.py
│       │   └── sheet_snapshot.py
│       ├── serialization/
│       │   └── json_writer.py
│       ├── validation/
│       │   └── schema_validator.py
│       ├── pipeline/
│       │   ├── workbook_inspection.py
│       │   └── order_extraction.py
│       ├── llm/
│       │   ├── client.py
│       │   ├── prompts.py
│       │   └── extractor.py
│       ├── matching/
│       │   ├── vector_index.py
│       │   ├── hard_filter.py
│       │   └── material_matcher.py
│       ├── erp/
│       │   └── comparator.py
│       ├── api/
│       │   ├── app.py
│       │   ├── routes.py
│       │   └── schemas.py
│       └── infrastructure/
│           ├── paths.py
│           └── logging.py
└── tests/
    ├── test_smoke.py
    ├── excel/
    ├── serialization/
    ├── validation/
    ├── pipeline/
    ├── llm/
    ├── matching/
    └── erp/
```

## 5. 目录和关键文件职责

- `AGENTS.md`：后续 Codex 任务的规则入口。
- `README.md`：项目概览、环境和文档入口。
- `docs/project_scope.md`：阶段范围和明确不做的内容。
- `docs/project_context.md`：业务背景、工程基线、阶段路线和 Day01 隔离关系。
- `docs/architecture.md`：长期架构、分层、依赖方向和数据流。
- `data/input/`：用户提供的真实 Excel PI 输入目录，输入文件只读。
- `data/output/`：后续生成结构快照、解析结果和导出文件的默认目录。
- `src/bedding_order_parser/__main__.py`：后续命令行模块入口，只调用 `cli.py`。
- `src/bedding_order_parser/cli.py`：后续 CLI 参数解析和用户可见返回信息。
- `src/bedding_order_parser/config.py`：后续集中配置。
- `src/bedding_order_parser/exceptions.py`：后续项目级明确异常类型。
- `models/workbook.py`：Workbook Inspection 阶段的数据模型。
- `models/order.py`：后续订单结果模型。
- `models/material.py`：后续物料匹配模型。
- `excel/workbook_reader.py`：只读打开和读取 Excel 工作簿。
- `excel/workbook_inspector.py`：分析工作簿和工作表结构。
- `excel/merged_cells.py`：处理合并单元格范围信息。
- `excel/sheet_snapshot.py`：生成单个工作表结构快照。
- `serialization/json_writer.py`：UTF-8 JSON 序列化和输出写入。
- `validation/schema_validator.py`：后续结构和业务校验。
- `pipeline/workbook_inspection.py`：Workbook Inspection 流程编排。
- `pipeline/order_extraction.py`：后续订单字段抽取流程编排。
- `llm/client.py`：后续 LLM 服务调用封装。
- `llm/prompts.py`：后续 Prompt 定义。
- `llm/extractor.py`：后续 LLM 结构化抽取。
- `matching/vector_index.py`：后续 FAISS 与 embedding 召回。
- `matching/hard_filter.py`：后续规格、尺寸、密度等硬条件过滤。
- `matching/material_matcher.py`：后续物料编码匹配编排。
- `erp/comparator.py`：后续 ERP 逐行差异对比。
- `api/app.py`、`api/routes.py`、`api/schemas.py`：后续 FastAPI 服务入口、路由和接口 Schema。
- `infrastructure/paths.py`：路径解析和输入输出目录策略。
- `infrastructure/logging.py`：日志配置和脱敏策略。
- `tests/`：自动测试目录，结构尽量对应 `src/` 模块。

## 6. 依赖方向

长期依赖方向：

```text
入口层
-> 流程编排层
-> Excel能力、校验、序列化、匹配、ERP能力
-> 数据模型和基础设施
```

具体规则：

- `__main__.py` 只调用 `cli.py`。
- `cli.py` 只处理参数和返回信息。
- `pipeline/` 负责组织执行顺序。
- `excel/` 只处理 Excel 结构。
- `models/` 只定义数据。
- `serialization/` 只负责输出格式。
- `validation/` 只负责校验。
- `llm/` 只负责模型服务、提示词和抽取封装。
- `matching/` 只负责物料匹配。
- `erp/` 只负责 ERP 差异。
- `api/` 只负责 HTTP 接口。
- `infrastructure/` 负责路径、日志和配置。

## 7. 禁止依赖方向

禁止：

- 数据模型导入 CLI；
- Excel 读取模块调用前端或 API；
- JSON 写入模块直接调用 LLM；
- Agent 直接解析 Excel；
- API 路由直接实现业务解析；
- 一个模块反向依赖上层界面；
- 模块之间循环导入；
- 使用不必要的全局变量；
- 隐式修改输入文件。

## 8. Gate 1 基线解析器数据流

Gate 1 阶段用于离线读取真实 PI Excel、筛选被套商品，并输出最终 20 字段 JSON。当前实现不接入 LLM、向量检索、物料编码匹配、ERP 对比、API、前端或 Agent。

当前数据流：

```text
CLI输入文件路径
-> 路径和扩展名检查
-> 计算输入文件SHA-256
-> 非破坏性打开Excel
-> 定位PI-update/PI/模糊PI/第一个工作表
-> 合并单元格回填
-> 清洗前20列内的二维行数据
-> 定位表头与编号明细行
-> 提取客户、币种、业务员、计划发货日期等元数据
-> 筛选被套行并排除非被套品类
-> 规范化规格、颜色、成分、尺寸类型、款式、绣花等字段
-> 组装最终20字段结果
-> UTF-8 JSON原子写入data/output
-> 再次计算输入文件SHA-256并确认未变化
-> 返回执行摘要
```

Gate 2D 在该数据流中增加交易双方提取层、字段诊断层和成对输出提交。

## 9. 输入只读与输出隔离策略

- 输入 Excel 一律以只读方式打开。
- 不得原地保存、重命名、移动或删除用户输入文件。
- 不得覆盖已有输出文件。
- 输出默认写入 `data/output/`。
- 后续写入输出时应使用临时文件加原子替换策略，但不得覆盖同名已有结果。
- 后续应记录输入文件 SHA-256，便于审计和复现。
- 真实企业 Excel 不得提交到 Git。

## 9.1 Gate 2D 交易双方与诊断分层

- `extraction/party_extractor.py`：识别买方/卖方区域、提取买方主体、
  卖方联系人和买方联系人辅助证据，并负责候选优先级与冲突判定。
- `extraction/metadata_extractor.py`：编排交易双方、币种和日期等订单级
  元数据，不重复堆积买卖方区域正则。
- `diagnostics/models.py`：定义证据、字段诊断、记录诊断和解析报告模型。
- `diagnostics/report_builder.py`：校验诊断字段顺序和值与业务结果一致，
  汇总状态和警告。
- `serialization/diagnostic_writer.py`：把业务结果与解析报告序列化到临时
  文件，并作为一对输出提交；失败时恢复原文件或清理半成品。

业务结果与诊断报告采用分离模型：

```text
源Excel证据
-> extracted / normalized / derived / defaulted
-> 最终20字段业务值
-> 字段诊断（值、状态、坐标、区域、规则、说明）
-> 业务JSON + 解析报告JSON
```

无法确定的字段按证据情况流转为 `source_not_provided`、`unrecognized`
或 `ambiguous`，业务值保持空字符串。物料编码和相似分数在当前阶段标记
为 `not_implemented`。诊断文本不得写回业务字段。

双输出安全流程：

```text
检查两份目标是否允许写入
-> 分别序列化到目标目录临时文件
-> 覆盖模式下暂存两份旧文件
-> 原子替换业务结果和解析报告
-> 任一步失败则回滚两份旧文件并清理临时文件
```

## 10. 错误处理策略

- 输入文件不存在、扩展名不支持、Excel 无法打开或结构无法分析时，应抛出明确异常并给出可理解错误。
- 不使用裸 `except`。
- 不吞掉异常。
- 不把失败静默当作空结果。
- 业务错误使用项目级明确异常类型。
- CLI 最终负责把异常转换为用户可见消息和退出码。

## 11. 日志策略

- 日志配置集中在 `infrastructure/logging.py`。
- 正式代码不使用 `print` 替代日志体系，CLI 最终展示除外。
- 日志不得输出敏感业务内容或完整企业订单数据。
- 结构诊断可以记录摘要、文件哈希、工作表名称、坐标范围和错误类型。
- 测试不得写入真实日志目录。

## 12. 测试结构

- 当前测试命令：`uv run pytest`。
- 新模块应在 `tests/` 下建立对应测试。
- 测试不得修改真实输入。
- 测试不得污染 `data/input/` 或 `data/output/`。
- 测试使用临时目录。
- 测试不得依赖互联网。
- 测试结果必须可重复。
- 不得因为终端显示成功就宣布人工验收通过。

## 13. 后续能力位置

- LLM：放在 `llm/`，Prompt 与模型客户端分开。
- 向量检索：放在 `matching/vector_index.py`，计划使用 FAISS 和 BGE-M3 embedding。
- 硬条件过滤：放在 `matching/hard_filter.py`，处理规格、尺寸、密度等确定条件。
- 物料匹配编排：放在 `matching/material_matcher.py`。
- ERP 对比：放在 `erp/comparator.py`。
- FastAPI：放在 `api/`，路由不直接实现业务解析。
- 前端：后续另行设计，不在当前阶段创建。
- Agent：只能在解析、校验、匹配和对比工具成熟后作为调度层加入。

## 14. Agent 原则

Agent 不能承载底层业务逻辑，不能直接解析 Excel，不能绕过校验、匹配或 ERP 对比模块。Agent 只能调度已经稳定、可测试的工具，并应保留人工复核和错误回退机制。

## 15. 空壳模块原则

目标架构用于指导长期演进。除非某个阶段确实需要对应模块并配套测试，否则不得为了“看起来完整”提前创建无意义空文件、空类、空接口或未被调用的抽象。
