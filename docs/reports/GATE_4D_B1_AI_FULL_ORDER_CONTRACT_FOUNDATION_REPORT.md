# Gate 4D-B1｜AI增强整单解析离线合同基础报告

## 1. 基线

- 开始基线：`d55f60cdecca7040ec6f33a935358c23a0e7df0c`（`chore: add project instructions and gate skill`）。
- 开始工作区仅有两份允许保留的未跟踪恢复文档：`CODEX_HANDOFF_AND_RECOVERY_2026-07-30.md` 与 `CODEX_RECOVERY_AUDIT_ROUND_1_REPORT_2026-08-01.md`。
- 本轮遵守 `AGENTS.md`、`.codex/skills/bedding-gate/SKILL.md` 与 Gate 4D-A 设计报告；对于旧设计中18字段且由AI生成行号的表述，按最新稳定规则采用17个AI业务字段和本地行号。

## 2. 新增合同和模块

- 新增 `src/bedding_order_parser/ai_full_order/contracts.py`：解析模式、严格请求/响应 Schema、17字段合同、禁止字段、请求与响应验证器。
- 新增 `src/bedding_order_parser/ai_full_order/preprocessing.py`：双视图 Excel 读取、稀疏结构、证据目录、本地订单区块识别与请求构造。
- 新增 `src/bedding_order_parser/ai_full_order/fake_provider.py`：完全离线的 FakeProvider，覆盖正常结果和合同破坏场景。
- 新增 `src/bedding_order_parser/ai_full_order/__init__.py` 与 `tests/ai_full_order/` 定向单元测试。
- 未改动既有标准解析、桌面 UI、正式 Job、五类 JSON 发布、字典、向量检索或物料匹配代码。

## 3. 17字段与本地行号

- `parse_mode` 仅允许 `standard` 和 `ai_enhanced`；不存在 `allow_ai` 布尔开关。
- AI响应只包含17个业务字段：`客户`、`币种`、`业务员`、`表头备注`、`物料名称`、`规格`、`颜色`、`面料`、`面料-涤棉成分`、`款式`、`加标方式`、`尺寸类型`、`数量`、`行备注`、`计划发货日期`、`包装方式`、`是否绣花`。
- 行号由本地 `sheet_id:source_row` 确定性生成（测试值为 `s1:4`），不在 AI 输入或输出字段中。
- `物料编码` 与 `相似分数` 被严格禁止出现在模型输出；后续仅可由匹配层生成。输入证据中的既有物料编码文本可保留为只读证据，不会写入正式解析结果。

## 4. Excel证据结构

- 预处理以 `data_only=False` 和 `data_only=True` 双视图读取工作簿，并在读取前后计算源文件 SHA-256，防止构建证据期间源文件发生变化。
- 稀疏单元格保留 Sheet、坐标、公式显示文本、计算视图值、类型、数字格式及合并锚点；空单元格不进入证据目录。
- 实际使用区域依据有值单元格重算，合并子单元格引用锚点而不重复文本，多层表头和表头证据随订单区块一并纳入 scope。
- 默认排除隐藏行、隐藏列和隐藏 Sheet 的内容；隐藏 Sheet 不保留可外发的稀疏单元格。
- 本地按表头和连续编号行识别明确订单区块；仅当结构为 `ambiguous` 时才调用结构解析器。明确结构测试验证解析器调用次数为零。

## 5. 严格Schema

- 请求和响应对象均要求完整字段、固定类型、固定枚举，并禁止额外字段与 `null`。
- 响应记录必须与请求的文件 SHA、记录数、源记录 ID 和 scope 对齐；所有证据 ID 必须真实存在且属于该记录 scope。
- 非空 `extracted`/`normalized` 字段必须同时给出值、原始值和有效证据引用；原始值及输出值必须可由被引用证据的文本追溯。
- 跨 scope 引用、伪造单元格、缺字段、额外字段、错误类型、错误枚举以及物料编码/相似分数注入均被拒绝。

## 6. 测试命令和结果

```powershell
uv run pytest tests/ai_full_order tests/excel/test_merged_cells.py tests/excel/test_table_parser.py -q
```

- 结果：`20 passed in 1.19s`。
- 覆盖：17字段完整性、本地行号、禁止字段注入、证据可追溯性、跨订单 scope 拒绝、伪造单元格、空值、非空字段缺证据、合并锚点、隐藏内容排除、本地明确区块不触发结构解析，以及零网络 FakeProvider。
- 未运行完整 `pytest`。

## 7. 网络/API调用数

- 真实豆包/API 调用：0。
- 网络调用：0。FakeProvider 的 `network_call_count` 始终为0，测试同时替换 `socket.create_connection` 为失败函数以证明其不发起套接字请求。
- BGE-M3 调用：0；FAISS 调用：0；未解析真实 PI；未安装依赖。

## 8. 修改文件

- `src/bedding_order_parser/ai_full_order/__init__.py`
- `src/bedding_order_parser/ai_full_order/contracts.py`
- `src/bedding_order_parser/ai_full_order/preprocessing.py`
- `src/bedding_order_parser/ai_full_order/fake_provider.py`
- `tests/ai_full_order/test_preprocessing.py`
- `tests/ai_full_order/test_contracts.py`
- `docs/reports/GATE_4D_B1_AI_FULL_ORDER_CONTRACT_FOUNDATION_REPORT.md`

## 9. Commit和工作区

- 提交信息：`feat: add ai full-order contract foundation`。
- 本报告与上述7个实现/测试文件属于同一提交；提交完成后工作区应只保留两份恢复文档为未跟踪文件，不暂存、不删除它们。
- 已完成暂存前 diff 空白检查；未包含密钥、真实 API 响应、真实 Job 数据或 Sidecar 内容。

## 10. 下一步

Gate 4D-B2：实现AI整单离线分块编排、Python shadow字段决策、缓存、幂等和中断恢复。
