# 床品订单智能解析与物料匹配系统

英文项目名称：`bedding-order-parser`

## 当前阶段

项目已经形成一套本地优先的床品订单处理流水线：读取 PI Excel、识别订单
结构和交易双方、生成固定 20 字段业务结果、执行字段级诊断与字典验证，
再通过 SQLite 结构化召回和 BGE-M3/FAISS 向量召回生成物料候选。

项目同时提供本地 Web 服务和 pywebview 桌面壳。`standard` 模式默认完全
离线；`ai_enhanced` 模式的代码已经接入，但只有在单独配置模型服务并明确
授权真实业务调用后才能使用。

## 环境

- Python：3.12
- 正式依赖：openpyxl、faiss-cpu、sentence-transformers、pywebview
- 开发与打包依赖：pytest、PyInstaller

同步环境：

```powershell
uv sync
```

运行测试：

```powershell
uv run pytest
```

## 数据目录

- `data/input/`：放置用户提供的真实 Excel PI 文件。
- `data/reference/`：放置本地解析规则、模板和字典资料。
- `data/golden/`：放置本地对照结果和验收参考资料。
- `data/output/`：保存后续阶段生成的结构快照和解析结果。

`data/input/`、`data/reference/`、`data/golden/` 中的真实企业资料和
`data/output/` 中生成的 JSON 默认不进入 Git。目录中的 `.gitkeep` 只用于
保留空目录结构。

### 导入自己的业务资料库

项目不再依赖旧电脑上的固定绝对路径。可以把包含 `material_info.csv`、
`PI单提取规则.xlsx`、`款式表_structured.xlsx` 和 PI 参考文件的 ZIP 安全导入
到当前项目的 `data/` 目录：

```powershell
.\packaging\import_business_library.ps1 -ArchivePath "你的业务资料.zip"
.\packaging\initialize_desktop_config.ps1
```

导入脚本只复制已知的规则、物料和参考订单文件，不会修改 ZIP 原件。默认映射：

- 规则、款式、物料 CSV 和模板：`data/reference/`；
- PI 样例：`data/input/pi/`；
- 已知对照结果：`data/golden/`；
- 本地说明资料：`data/reference/docs/`。

如需把业务库放在项目外部，可在两个脚本中显式传入相同的 `-DataDir`。
桌面配置保存到当前用户的 `%LOCALAPPDATA%\BeddingOrderParser\config\app_config.json`。
物料 SQLite 与 FAISS 索引仍需从导入后的 `material_info.csv` 生成；导入动作本身
不会下载模型、加载 BGE-M3 或构建 FAISS。

## 当前能力边界

当前已实现离线规则解析、交易双方识别、字段级诊断、字典验证、物料主数据
SQLite/JSONL 构建、BGE-M3/FAISS 向量索引、结构化与向量混合候选排序、
本地 HTTP 接口、浏览器界面和 Windows 桌面壳。

物料匹配目前定位为“候选推荐 + 人工复核”，不能把最高分候选直接视为 ERP
最终编码。整单 AI 增强需要外部模型服务配置；默认不联网、不调用真实 API。
ERP 写回、生产系统集成和无人值守自动确认不在当前已验收范围内。

运行解析：

```powershell
uv run python -m bedding_order_parser parse "data/input/pi/20251231 被套 Proforma Invoice（11行）.xlsx" --output "data/output/20251231_被套_解析结果.json"
```

每次解析默认生成两个文件：

- 业务结果：使用 `--output` 指定的路径，例如 `order_result.json`；
- 解析报告：与业务结果同目录，默认名为 `order_result_parse_report.json`。

命令无需增加参数。任一输出已存在时默认拒绝执行，只有显式使用
`--overwrite` 才会同时覆盖两份输出。

解析报告为最终 20 个字段逐项记录以下状态：

- `extracted`：从源 Excel 明确提取；
- `normalized`：有明确源证据并完成业务标准化；
- `derived`：由其他已确定字段生成；
- `defaulted`：使用已批准的固定业务默认值；
- `source_not_provided`：相关区域未提供足够信息；
- `unrecognized`：存在相关文本但当前规则无法稳定转换；
- `ambiguous`：候选冲突或证据不足，需要人工复核；
- `not_implemented`：属于后续阶段，本阶段尚未实现。

业务 JSON 与诊断报告严格分离。无法确定的业务字段保持空字符串，提示语、
状态和解释只写入解析报告，不得污染业务字段。物料编码仍为空字符串，
相似分数仍为浮点数 `0.0`。

## 项目文档

- [项目范围](docs/project_scope.md)
- [项目背景](docs/project_context.md)
- [架构说明](docs/architecture.md)
- [Codex 工程规则](AGENTS.md)

## 项目交接与报告

- [Gate 2D 最终报告](docs/reports/GATE_2D_FINAL_REPORT_2026-07-23.md)
- [Gate 3A-A 字典源只读审计报告](docs/reports/GATE_3A_A_DICTIONARY_AUDIT_2026-07-24.md)
- [当前 Codex 交接文档](docs/handoffs/CODEX_CURRENT_HANDOFF.md)
- [Codex 交付协议](docs/workflow/CODEX_DELIVERY_PROTOCOL.md)

历史 Gate 报告保留了各阶段的验收背景；当前实际能力请以本 README、项目规则
和最新 `docs/reports/` 报告为准。
