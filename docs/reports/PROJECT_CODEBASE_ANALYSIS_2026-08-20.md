# Bedding Order Parser 项目代码分析报告

日期：2026-08-20  
审计模式：只读代码审计（仅新增本报告，不修改生产代码、测试、配置或业务数据）

## 1. 结论摘要

这是一套面向床品外贸订单的本地智能解析软件，核心目标是把客户提供的复杂 Excel PI（Proforma Invoice，形式发票）转换为固定 20 字段的结构化业务结果，并进一步完成字段诊断、字典验证和物料候选匹配。

从实际源码看，项目已经不是 README 所写的 Gate 2D 早期解析器，而是一套较完整的 Windows 本地应用，包含：

- Python 确定性标准解析；
- AI Enhanced 整单解析；
- 本地 Web 单页界面；
- pywebview Windows 桌面壳；
- 字典验证；
- SQLite 物料主数据；
- BGE-M3 向量、FAISS 检索和结构化硬条件混合匹配；
- AI 证据绑定、Python shadow 对照、人工 Review 和不可变 Revision；
- 本地任务持久化、断点/失败处理、ZIP 下载和 PyInstaller 打包；
- 大规模离线自动化测试。

项目的工程安全边界比较成熟，但文档入口严重滞后，当前目录又是去掉 `.git`、真实数据、模型和运行资源后的源码归档包，因此它“代码完整”，却不是解压后立即能跑完整业务流程的独立发布包。

## 2. 审计对象与基线

### 2.1 实际目录

- 当前实际目录：`D:\AI lianxi\床品Excel解析`
- `AGENTS.md` 固定声明的正式仓库：`D:\AI-Learning\Projects\bedding-order-parser`
- 本机检查结果：正式仓库路径不存在；当前目录存在完整源码，但没有 `.git/`。

因此，本次无法读取或独立验证实际分支、HEAD、作者、工作区修改和提交历史。

### 2.2 归档声明

`SOURCE_PACKAGE_MANIFEST.md` 声明：

- 分支：`master`
- 归档提交：`a5c9056dda6e96d18a31c81873ff753d8acfc1be`
- 打包日期：2026-08-19
- 基线测试：670 passed、0 skipped、0 failed

这些属于归档清单和既有最终验收报告中的声明；由于 `.git` 和原运行环境均未随包提供，本轮不能把它们当作重新验证得到的现场结果。

### 2.3 代码规模

| 范围 | 文件/规模 |
|---|---:|
| 生产 Python | 105 个文件，约 27,837 行 |
| 前端 | HTML 88 行、JavaScript 1,565 行、CSS 1,420 行 |
| 自动化测试 | 71 个 Python 文件，约 19,380 行 |
| 显式测试函数 | 549 个，参数化后既有报告称收集 670 项 |
| 文档 | 109 个文件，包含 Gate 报告、截图、架构图和 2 份 Word 交付物 |

生产代码最大的几个子系统是 `ai_full_order`、`materials`、`web` 和 `dictionaries`，说明当前系统的主要复杂度已经从基础 Excel 读取转向 AI 可靠性、物料匹配、桌面任务编排和业务规则审计。

## 3. 系统用来做什么

业务输入是客户提供的 `.xlsx` PI/订单文件。此类文件可能存在合并单元格、多行表头、多个 Sheet、隐藏行列、公式、非固定明细区域和多语言描述。

系统当前围绕“被套”类商品执行以下工作：

1. 读取并识别 Excel 中的订单区域；
2. 提取客户、币种、业务员、商品、规格、颜色、面料、款式、数量、日期等业务字段；
3. 把结果规范化为固定的 20 字段 JSON；
4. 为每个字段保留来源、状态、规则和人工复核提示；
5. 使用规则/款式字典做只读验证；
6. 从物料主数据中召回并排序候选；
7. 在本地界面中展示结果、证据、候选、历史任务和 AI/Python 差异；
8. 允许用户对 AI 结果选择“保留 AI”“使用本地规则”或“手动修改”，并生成新的不可变 Revision；
9. 导出五类 JSON；Standard 任务还能打包下载 ZIP。

当前没有 ERP 逐行对比模块，也没有自动确认或写回物料编码。物料匹配合同仍是 `manual_review_only`：系统提供候选和解释，但正式业务结果中的 `物料编码`、`相似分数`不会因为 Top 1 候选而自动写回。

## 4. 实际架构

| 目录 | 主要职责 |
|---|---|
| `excel/` | 工作簿加载、Sheet 定位、合并单元格回填、表头和明细行识别 |
| `extraction/` | 买卖双方、订单元数据、被套商品和字段证据提取 |
| `normalization/` | 尺寸、颜色、面料、成分、款式、绣花等业务归一化 |
| `models/` | 固定 20 字段最终结果模型 |
| `diagnostics/` | 字段级状态、来源、警告和解析报告 |
| `serialization/` | UTF-8 JSON、成对输出和失败回滚 |
| `pipeline/` | Standard 解析流程编排 |
| `dictionaries/` | 规则/款式字典加载、shadow 对照、产品验证与集成预览 |
| `materials/` | 物料 CSV 清洗、SQLite store、BGE-M3、FAISS、硬条件比较、候选输出和人工审核工作簿 |
| `llm/` | LLM 配置、Provider 协议、HTTP transport、火山方舟 Responses 调用和单记录建议 |
| `ai_full_order/` | 整单 AI V1/V2 合同、本地预处理、结构裁决、证据绑定、Python shadow、字段政策、缓存、可靠性、发布和 Revision |
| `web/` | 本地 HTTP API、任务服务、持久化、AI Review 和浏览器 UI |
| `desktop/` | pywebview 桌面窗口、WebView2、本地服务生命周期、单实例锁、资源校验和保存文件桥接 |
| `packaging/` | PyInstaller onedir/onefile 构建、图标、快捷方式和发布校验 |

整体是“本地桌面壳 + 127.0.0.1 HTTP 服务 + Python 业务内核 + 原生 HTML/CSS/JavaScript”的架构。没有采用 FastAPI、Flask、React、Vue、Electron 或数据库服务端。

## 5. 两种解析模式

### 5.1 Standard

```text
上传 Excel
→ openpyxl 读取并计算输入 SHA-256
→ 定位 PI Sheet、合并单元格、表头和编号明细行
→ Python 规则提取与字段规范化
→ 固定 20 字段正式结果 + 字段级解析诊断
→ 字典验证
→ BGE-M3 查询向量 + FAISS 召回 + 结构化硬冲突过滤
→ 物料候选与匹配摘要
→ 五类 JSON + Standard ZIP
```

Standard 默认不调用 LLM。只有任务完成后，用户明确点击单条“AI 复核建议”才会进入 advisory sidecar；该建议不修改正式结果、五类 JSON 或 ERP。

Standard 解析具有几项重要防护：输入前后 SHA-256 一致性检查、固定字段顺序检查、诊断值与正式值一致性检查、输出临时文件与原子替换、已有输出默认拒绝覆盖。

### 5.2 AI Enhanced

```text
上传 Excel 并明确确认 AI 模式
→ 本地读取公式值/显示值、Sheet、使用区域、隐藏结构和合并单元格
→ 本地优先确定订单区块；仅在歧义时请求 Layout AI 选择本地候选 ID
→ 按本地记录身份生成单记录 extraction unit
→ AI 仅返回固定 17 个业务字段的稀疏候选
→ 本地绑定 Sheet/单元格/原文 quote 和 scope
→ Python shadow 独立解析
→ 字段级 AI/Python 比较与 canonical 决策
→ 字典验证、物料匹配
→ 五类 JSON 原子发布
→ UI Review / 不可变 Revision / CURRENT 指针
```

AI 不负责 `行号`、`物料编码`和`相似分数`。每个非空 AI 候选必须能绑定到同一订单 scope 内的已知证据；身份、范围、证据归属、合同形状或五类发布完整性失败时不会发布半套正式结果。

AI V2 还实现了基于源文件、合同版本、Prompt 版本、结构清单和 extraction manifest 的缓存身份、幂等键、文件锁、失败隔离和有限重试。失败任务可以重试未完成部分、保留失败，或从可信原始上传创建一个新的独立 Standard Job；不会原地篡改原 AI Job 的模式。

## 6. 固定业务合同

最终结果严格包含以下 20 个字段，名称和顺序固定：

`客户`、`币种`、`业务员`、`表头备注`、`行号`、`物料编码`、`物料名称`、`规格`、`颜色`、`面料`、`面料-涤棉成分`、`款式`、`加标方式`、`尺寸类型`、`数量`、`行备注`、`计划发货日期`、`包装方式`、`是否绣花`、`相似分数`。

- 前 19 个字段统一序列化为字符串；
- `相似分数`必须是 JSON number；
- 正式结果不允许缺字段、额外字段或 `null`；
- 诊断状态和人工说明与正式业务 JSON 分离；
- AI 只允许提取其中 17 个业务字段；
- `行号`由本地源坐标确定；
- `物料编码`和`相似分数`只属于本地物料匹配边界。

完整产品任务的五类核心产物是：

1. `official_result`：正式业务 JSON；
2. `parse_diagnostics`：解析诊断 JSON；
3. `dictionary_validation`：字典验证 JSON；
4. `material_candidates`：物料候选 JSON；
5. `material_summary`：物料匹配摘要 JSON。

需要注意，裸 CLI 的 `parse` 子命令本质上仍是较低层的 Gate 2D parser，只生成正式结果、解析报告，并可选生成字典验证；五类产物由 Web/Desktop Job 编排补齐。CLI 和完整产品任务的语义边界应在文档中明确区分。

## 7. 技术栈

| 分类 | 实际技术 | 当前作用 |
|---|---|---|
| 语言与构建 | Python `>=3.12`、uv、uv_build | 包管理、锁定依赖、运行与构建 |
| Excel | openpyxl 3.1.5 | 读取 PI、公式/显示值、合并单元格、字典和人工审核工作簿 |
| 数据模型 | dataclasses、Enum、Protocol | 轻量强约束模型和可注入接口；未使用 Pydantic |
| 本地存储 | JSON、JSONL、SQLite | Job 状态、物料主数据、向量映射、诊断与结果 |
| 数值计算 | NumPy 2.5.1 | 向量校验、归一化、点积和 worker 数据交换 |
| 向量检索 | faiss-cpu 1.14.3 | `IndexFlatIP` 内积召回；归一化向量等价于余弦相似度排序 |
| Embedding | sentence-transformers 5.6.1、PyTorch 2.13.0、`BAAI/bge-m3` | CPU 生成 1024 维物料/查询向量；固定模型 revision |
| LLM | 火山引擎 Ark Responses 风格接口、urllib、自定义 strict function schema | 整单候选提取、歧义结构选择、单记录 advisory |
| Web 后端 | Python `ThreadingHTTPServer` / `BaseHTTPRequestHandler` | 仅监听本地回环地址的 JSON API 和静态资源服务 |
| Web 前端 | 原生 HTML、CSS、JavaScript | 单页路由、上传、进度、Review、Revision、历史、预览和帮助 |
| Windows 桌面 | pywebview 6.2.1、Edge WebView2、Win32 API | 原生窗口、单实例、保存文件、生命周期和本地服务托管 |
| 打包 | PyInstaller 6.21.0、PowerShell | onedir/onefile EXE、图标、快捷方式和发布哈希 |
| 测试 | pytest 9.1.1 | 单元、合同、离线集成、Web、Desktop、FakeProvider 和显式授权的真实验收入口 |

`.env.example` 中默认 `LLM_ENABLED=false`，Provider 为 `volcengine_ark`。源码没有内置真实 Key；API Key 只从 `ARK_API_KEY` 环境变量读取，配置对象的 `repr` 会遮罩 Key。

## 8. 主要运行入口

- CLI：`python -m bedding_order_parser parse ...` 或安装后的 `bedding-order-parser parse ...`
- 本地 Web：`python -m bedding_order_parser.web --port 8000`
- Windows Desktop：`python -m bedding_order_parser.desktop`
- 打包入口：`packaging/desktop_entry.py`
- 构建脚本：`packaging/build_desktop.ps1`

桌面应用启动时会校验外部业务资源：SQLite 物料库、FAISS 索引与映射、向量 manifest、两份 Excel 字典和 BGE-M3 本地模型缓存。任务、日志、缓存和状态默认写到当前 Windows 用户的 `%LOCALAPPDATA%\BeddingOrderParser`，而不写回安装目录。

## 9. 物料匹配机制

物料匹配不是单纯的向量 Top 1：

1. 先从 SQLite 按结构化字段召回；
2. 再从被套专用 FAISS 索引召回；
3. 合并候选集合；
4. 对品类、规格、颜色、面料、成分、密度执行硬冲突过滤；
5. 对款式、加标方式、尺寸类型等做可解释字段比较；
6. 结构化得分占 75%，归一化向量得分占 25%；
7. 证据不足、重复物料文本、并列候选或硬冲突都会进入人工复核；
8. 当前没有批准自动写回阈值。

这种设计适合企业物料编码场景：优先防止“语义看起来相近、但尺寸或成分明确冲突”的错误匹配。

## 10. UI 与桌面能力

当前界面已经包含：

- 拖拽/选择 Excel；
- Standard 与 AI Enhanced 模式选择；
- AI 数据发送和 Token 费用确认；
- 五阶段进度、逻辑调用次数、HTTP 尝试、Token 和安全错误码；
- 五类 JSON 预览与下载；
- 物料候选明细和字段级比较；
- Standard 单记录 AI 建议；
- AI/Python 对照、来源单元格展开、Review 筛选；
- “保留 AI”“使用本地规则”“手动修改” Revision；
- AI 技术失败后的独立 Standard 重新处理；
- 历史任务、帮助中心和本地任务恢复；
- 桌面 Save As、覆盖确认、单实例和关闭前任务确认。

仍未实现的可见功能：

- “导出 Excel”按钮当前只提示“下一阶段开放”；
- AI 任务没有完整 ZIP 导出；
- 没有 ERP 对比页面或模块；
- 没有 Revision timeline / rollback UI。

## 11. 测试与本轮验证

测试重点分布：

| 子系统 | 显式测试函数 |
|---|---:|
| AI 整单解析 | 151 |
| Web | 107 |
| 字典 | 88 |
| 物料匹配 | 69 |
| LLM | 42 |
| 提取 | 31 |
| Desktop | 27 |
| 其余基础模块 | 34 |

本轮实际执行：

- 对 `src/` 和 `tests/` 共 176 个 Python 文件执行 AST 语法解析：PASS；
- 对 `src/bedding_order_parser/web/static/app.js` 执行 `node --check`：PASS；
- 扫描密钥相关引用：仅发现空的 `.env.example` 配置、生产代码中的预期 Authorization 构造和离线测试占位值，未发现随包提供的真实凭证；
- 外部网络、真实 Ark、真实 PI、真实字典、真实物料库、BGE-M3 加载和生产 FAISS 调用：均为 0。

本轮没有运行 pytest。原因是当前是无 `.git`、无 `.venv`、无真实业务资源的源码归档包；执行 `uv run` 会创建新环境并改变当前只读审计边界。既有最终签署报告记录的 670/670 结果未在本轮重跑。

## 12. 工程优点

1. **业务合同清晰**：20 字段、17 个 AI 字段、五类产物、两种模式和写回边界都在代码中显式校验。
2. **AI 不是黑盒直通**：模型输出必须经过严格 Schema、身份、scope、证据和本地规范化验证。
3. **本地优先**：能用 Python 确定的结构不调用 Layout AI；Standard 默认完全离线。
4. **失败安全**：缓存、幂等、有限重试、Job 状态、原子写入和五类 Bundle 完整性处理较扎实。
5. **人工控制完善**：AI 结果可 Review、Revision，失败可保留或创建独立 Standard Job，不会静默回退。
6. **匹配可解释**：每个候选都有字段状态、硬冲突原因、结构化分数和向量分数。
7. **测试密度高**：测试代码约为生产 Python 行数的 70%，并覆盖大量异常与安全边界。
8. **桌面资源延迟加载**：BGE-M3 和 FAISS 不在应用启动/import 时加载，降低启动成本和测试污染。

## 13. 主要问题与风险

### 高优先级

1. **入口文档严重过时**：`README.md`、`docs/project_scope.md`、`docs/project_context.md`、`docs/architecture.md` 和当前 handoff 仍称没有 LLM、向量、前端或桌面端，与源码和最终 Gate 报告明显冲突。这会直接误导部署、维护和答辩。
2. **当前包缺少可验证的 Git 身份**：`AGENTS.md` 的固定路径不存在，当前目录没有 `.git`。只能相信 manifest 的 commit 声明，不能核验归档是否被二次修改。
3. **不是开箱即用发布包**：真实字典、SQLite 物料库、FAISS 索引、BGE-M3 缓存和应用配置均被有意排除；桌面启动要求这些资源存在。

### 中优先级

4. **部分模块过大**：`web/services.py` 约 2,174 行、`dictionaries/shadow_matcher.py` 约 1,617 行，已经偏离架构文档“不创建数千行 God File”的原则，后续修改的耦合和回归风险较高。
5. **CLI 与完整应用合同不同**：裸 CLI 不生成完整五类结果；Web/Desktop 才是完整产品主入口，README 目前没有解释这一点。
6. **产品功能仍有明确边界**：ERP 对比、Excel 导出、AI ZIP、物料编码自动确认/写回都未完成。
7. **输入格式存在入口差异**：底层 workbook reader 支持 `.xlsx` 和 `.xlsm`，Web 上传仅允许 `.xlsx`；用户文档应明确以哪个入口为准。

### 低优先级

8. `pyproject.toml` 的 description 仍是 `Add your description here`。
9. 早期 architecture 文档描述了 FastAPI、ERP 等“目标目录”，实际实现改为标准库 HTTP + pywebview；应重写为现状架构而不是继续叠加补丁。
10. 前端 JavaScript 和 CSS 均已超过 1,400 行，功能继续增加前宜按页面/领域拆分并建立更清晰的资源构建或模块边界。

## 14. 建议的下一步

1. 先做一次“文档基线纠偏”，更新 README、scope、context、architecture 和 handoff，使其以最终签署源码为准。
2. 为源码包增加可验证的归档机制，例如 manifest 文件哈希清单或签名；正式开发仍回到带 `.git` 的固定仓库。
3. 增加一份从源码到桌面运行的部署说明，明确业务资源、模型缓存、`app_config.json` 和环境变量的准备步骤。
4. 将 `web/services.py` 优先拆成 Job repository、Standard runner、AI runner、artifact service 和 public view assembler。
5. 明确 CLI 的产品定位：要么标注为“底层解析调试入口”，要么让它也通过统一 Job orchestration 生成五类产物。
6. 只有在业务方批准写回规则、阈值和审计流程后，再考虑自动填充物料编码；当前人工复核优先的边界是合理的。
7. 后续新功能可按真实业务价值排序：Excel 导出、AI ZIP、ERP 对比、Revision timeline；不建议仅为“技术栈更现代”替换当前本地 HTTP/前端架构。

## 15. 本轮工作区与未执行项

- 新增文件：仅本报告 `docs/reports/PROJECT_CODEBASE_ANALYSIS_2026-08-20.md`
- 生产代码、测试、配置、业务数据：未修改
- Git 分支、HEAD、status、diff、author：当前源码包无 `.git`，无法执行或核验
- Commit：未创建，用户未授权提交且当前目录无 Git 元数据
- pytest：未运行
- 真实 API / 真实 PI / BGE-M3 / 生产 FAISS：未调用

