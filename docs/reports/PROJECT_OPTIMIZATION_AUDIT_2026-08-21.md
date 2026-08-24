# Bedding Order Parser 项目优化审计报告

- 日期：2026-08-21
- 模式：只读优化审计（仅新增本报告）
- 当前目录：`D:\AI lianxi\床品Excel解析`
- 结论：不建议重写架构；应优先处理发布链路、索引可恢复性、业务真值和批量性能

## 1. 审计边界

本轮读取源码、既有验收报告、当前物料清单和 SQLite 元数据，执行了不输出业务
值的 SQLite/JSONL 只读性能测量。没有修改生产代码、测试、配置、业务数据、模型、
FAISS 索引或固定 20 字段合同；没有运行真实 PI、BGE-M3 编码、FAISS 查询、LLM
API、ERP、pytest、PyInstaller 或外部网络。

当前目录没有 `.git`，无法核验现场 HEAD、分支、工作区差异或创建提交。
`SOURCE_PACKAGE_MANIFEST.md` 记录的历史 commit 只能作为来源说明，不能证明当前目录
在后续本地修改后仍与该 commit 一致。

## 2. 总体判断

当前技术路线适合本地床品订单系统：Python 确定性解析、SQLite、BGE-M3、FAISS、
标准库 HTTP 和 pywebview 都没有必须替换的架构性问题。29,085 条被套向量仍属于
`IndexFlatIP` 可以轻松处理的规模，当前瓶颈不是 FAISS 搜索算法。

主要问题集中在四处：

1. 打包 EXE 的 Embedding Worker 启动方式缺少真实端到端证明；
2. 29,127 条物料建库耗时约 16.19 小时，但没有向量分片或断点续建；
3. 匹配分数没有经业务真值标定，无法回答 Top-1/Top-10 实际准确率；
4. 每个 PI 都重新加载 BGE-M3，且每个任务重复展开全量候选和映射。

## 3. 当前量化基线

| 项目 | 当前事实 |
|---|---:|
| 物料记录 | 29,127 |
| 被套向量 | 29,085 x 1,024 float32 |
| BGE-M3 模型快照 | 约 2.29 GB |
| 正式索引构建耗时 | 58,269.584 秒（约 16.19 小时） |
| 当前机器一次单查询冷启动检索 | 约 59.6 秒（含模型加载） |
| 历史 Worker Private Bytes 峰值 | 约 3.56–3.78 GiB |
| 全量 MaterialCandidate 加载 | 0.659 秒，tracemalloc 峰值 40.719 MiB |
| 29,085 行 mapping JSONL 展开 | 0.649 秒，tracemalloc 峰值 62.407 MiB |
| 一次样本结构化 SQL | 43.16 ms，返回 3,981 个编码 |
| 生产 Python | 106 文件，约 24,938 行 |
| 测试 Python | 71 文件，约 16,529 行 |
| `web/services.py` | 2,064 行 |
| `shadow_matcher.py` | 1,474 行 |
| 前端 `app.js` | 1,476 行 |

历史 12 份 PI/49 条回归中：14 条 `unique_best_candidate`、3 条并列、26 条
证据不足、6 条无候选。该结果只证明工程一致性，不是业务准确率。

## 4. P0：继续开发和发布前先处理

### 4.1 验证并修正 PyInstaller Embedding Worker 启动链

`query_embedding_runner.py` 使用：

```text
sys.executable -m bedding_order_parser.materials.query_embedding_worker
```

源码快捷方式下 `sys.executable` 是 `.venv` 的 Python，因此可以工作；PyInstaller
环境下 `sys.executable` 通常是 `订单解析助手.exe`。当前 `packaging/desktop_entry.py`
无条件启动桌面程序，不解析 `-m`，也没有单独的 Worker EXE。发布校验脚本只检查
EXE 存在、大小和 SHA-256，没有运行一次打包后的完整物料匹配任务。

因此存在高置信度发布风险：打包版可能重新启动桌面入口或被单实例锁拦截，而不是
执行查询 Worker。当前源码快捷方式不受影响，但在向其他电脑分发 EXE 前应视为
release-blocker candidate。

建议：

- 优先生成独立的 `embedding_worker.exe`，由桌面程序通过绝对路径启动；或
- 给打包入口增加明确、不可与普通 UI 混淆的 `--embedding-worker` 分派；
- Onedir 和 Onefile 分别做一次合成订单端到端验收；
- 验证不依赖系统 Python、Worker PID 可追踪、退出后无残留、五类 JSON 完整。

### 4.2 恢复可验证的 Git/路径基线

当前 `AGENTS.md`、项目 skill 和部分当前交接文档仍固定指向不存在的旧目录，当前目录
又没有 `.git`。这会影响差异审查、回滚、报告可信度和后续自动化操作范围。

建议把当前可运行状态纳入一个新的正式 Git 仓库，保留原归档 manifest 作为来源证据，
再更新当前规则和交接入口中的正式路径。真实 PI、模型、SQLite、FAISS 和本机配置继续
保持 Git 忽略，不纳入提交。

## 5. P1：业务收益最高的优化

### 5.1 建立物料匹配业务真值集

当前 `hybrid_score_v1` 是 75% 结构化 + 25% 向量的工程基线，没有批准的正确物料
编码真值，无法判断权重、Top-300、硬冲突和 Top-10 是否合理。项目已经有人工审核
工作簿和校验器，可以直接复用来采集真值。

建议先由业务人员复核一批分层样本：常规订单、不同语言、缺字段、容易并列、无物料、
历史解析错误。至少输出以下指标：

- Top-1、Top-3、Top-10 命中率；
- 正确编码未进入 Top-300 的召回失败率；
- 硬冲突误杀率；
- 无候选判定准确率；
- 按尺寸、颜色、面料、成分、款式分组的错误分布。

在得到真值前，不应调整 75/25 权重，也不应自动写回 ERP。

### 5.2 让 16 小时索引构建可断点续建

当前 `vector_index.py` 每次从头编码，向量只存在内存和临时 FAISS 中。第一次构建已经
实际发生过“全部编码完成、最终写文件失败、只能重新编码”的情况。

建议增加本地分片缓存：

- 每 256/512 条保存一个规范化 float32 向量分片；
- 分片身份包含源 JSONL SHA-256、模型名、revision、维度、归一化和文本范围；
- 每个分片原子写入并记录完成 manifest；
- 重启时只计算缺失或校验失败分片；
- 全部分片完成后再合并并原子发布 FAISS/映射；
- 源文件、模型 revision 或文本顺序改变时必须整体失效。

29,127 x 1,024 x 4 字节的原始向量约 113.8 MiB，保存可恢复分片的成本远低于再次
等待 16 小时。可另加 GPU 构建入口，但 CPU 路径仍应支持恢复。

### 5.3 优化日常订单吞吐，而不是让模型永久常驻

当前一个 PI 启动一个短生命周期 Worker，Worker 加载一次 BGE-M3，然后逐条执行
`adapter.encode(..., batch_size=1)`。这种隔离解决了 Windows 内存和强制终止问题，
不能简单改成永久常驻模型；永久保持约 3.5–3.8 GiB Commit 对当前机器风险较高。

建议按顺序推进：

1. 先记录 `model_load`、`query_encode`、`candidate_load`、`mapping_load`、`faiss_load`、
   `search`、`compare` 和 `publish` 的独立耗时/内存；
2. Worker 内将订单行按 4–8 条微批编码，在批次之间保留取消检查；
3. 支持用户一次选择多份 PI，由一个受控 Worker 编码这一批任务后退出，以摊薄模型
   冷启动成本；
4. 只有实测内存允许时，才增加很短的空闲 TTL，并保持单 Worker、串行请求、内存上限
   和强制终止；
5. 后续评估 ONNX Runtime/INT8 等 CPU 后端，但必须重建向量索引并用真值集验证，不能
   直接替换现有 BGE-M3 输出。

### 5.4 减少每任务全量 Python 对象

当前每次匹配都会：

- 把 29,127 条 SQLite 记录全部转换为 dataclass 字典；
- 把 29,085 行、约 19 MB mapping 全部转换为 Python `list[dict]`；
- 再建立 `mapping_by_code` 和 `position_by_code`。

只读测量显示这两步约 1.31 秒、tracemalloc 峰值合计约 103 MiB。它不是模型冷启动
的最大瓶颈，但优化风险较低。

建议：

- mapping 只保留 `position -> material_code` 等必要字段，详细元数据统一从 SQLite 取；
- 先合并结构化与向量编码，再批量 `SELECT ... WHERE material_code IN (...)` 只加载候选；
- 对多订单任务汇总 union code 后一次批量读取；
- 运行时缓存必须以 manifest/hash 为 key，并在资源变化时失效；
- 不应在未完成内存测量前把模型、FAISS、mapping、全量候选同时永久常驻。

### 5.5 本地 HTTP 安全和任务数据生命周期

服务只监听 `127.0.0.1`，上传限制为 25 MB，路径解析也有边界检查，这是好的基础。
但当前未发现 Host/Origin 校验、会话 CSRF token 或自定义应用请求头。恶意网页理论上
可能向本机端口发起跨站表单请求；若 AI Provider 已启用，后端创建 `ai_enhanced`
Job 时没有独立于前端对话框的服务器确认令牌。

建议：

- 启动时生成随机会话 token，只通过桌面载入页面注入；
- 所有变更状态的 API 要求 token，并校验 Host、Origin/Referer；
- 拒绝跨站表单直接创建任务；
- 对 XLSX ZIP 做 entry 数、解压总量、单项大小、压缩比和 XML 尺寸预检，防止压缩炸弹；
- 为 `%LOCALAPPDATA%/.../tasks` 增加可见的保留策略和手动删除功能；原始上传、结果、
  AI Sidecar 和 Revision 不应无限期静默累积。

## 6. P2：维护性和产品体验

### 6.1 拆分大模块

- `web/services.py` 同时承担 Job repository、Standard runner、AI runner、恢复、
  Artifact、Review 和 public view，已达 2,064 行；
- `shadow_matcher.py` 同时承担多字段解析、字典匹配和报告汇总，约 1,474 行；
- `app.js` 同时承担路由、上传、状态轮询、Review、历史和帮助，约 1,476 行。

建议先按现有合同拆文件，不改变行为：`JobRepository`、`StandardJobRunner`、
`AIJobRunner`、`ArtifactService`、`PublicViewAssembler`；Shadow 按尺寸/面料/款式分域；
前端按 upload/job/review/history/help 拆 ES modules。不要为了拆分引入 React 或 FastAPI。

### 6.2 改进发布和工程工具

- `pyproject.toml` description 仍是 `Add your description here`；
- 应用版本在 pyproject 和 `runtime_identity.py` 重复硬编码为 `0.1.0`；
- 当前无 Git 时 runtime commit 会显示 `unavailable`；
- `verify_release.ps1` 只验证文件存在、大小和哈希；
- 未发现 Ruff、类型检查、覆盖率阈值和 CI 配置。

建议让版本只有一个来源，构建时注入 commit/归档 identity；发布校验增加启动、健康检查、
合成 XLSX Standard Job、Worker、五类产物和正常关闭。再逐步加入 Ruff、关键模块类型检查、
依赖审计和可重复构建清单，不必一次强制全项目类型化。

### 6.3 产品功能顺序

推荐顺序：

1. 真实 Excel 导出；
2. AI Enhanced 五类结果 ZIP；
3. 任务删除/留存策略；
4. Revision timeline；
5. ERP 对比；
6. 经业务审批后的编码确认/写回。

ERP 自动写回必须晚于业务真值、权限、审计日志、冲突处理和回滚设计。

## 7. 当前不建议投入的优化

- 不需要改成 RAG 或引入云向量数据库；
- 不需要为 29,085 条向量把 `IndexFlatIP` 改成 IVF/HNSW；
- 不需要为了“技术栈现代化”重写为 FastAPI、React 或 Electron；
- 不要在没有真值集时调整 75/25 权重或自动选择 Top-1；
- 不要直接换小模型；模型变更会改变向量空间，必须重建索引并重新验收；
- 两套 all/duvet 索引存在约 138 MB 重复空间，但相对 2.29 GB 模型和业务风险较小，
  目前不是优先项。

## 8. 推荐实施顺序与验收

### 阶段 A：可交付基线

- 建立正式 Git 仓库并修正当前路径合同；
- 修复/验证 PyInstaller Worker 分派；
- Onedir、Onefile 各完成一次离线合成 E2E；
- 验收：无需系统 Python、五类结果完整、Worker/端口无残留。

### 阶段 B：可恢复建库

- 实现向量分片和断点续建；
- 在中途强制终止后恢复；
- 验收：已完成分片不重算，最终条目/维度/哈希合同完整，源或模型变化必失效。

### 阶段 C：业务真值与准确率

- 收集人工审核结果并形成版本化真值；
- 输出 Top-K、召回、硬冲突和无候选指标；
- 验收阈值由业务方批准，不使用工程分数冒充准确率。

### 阶段 D：批量性能与资源

- 增加分阶段计时/内存；
- 实现微批查询和受控多 PI Worker；
- 验收：结果与当前基线逐字段/逐候选一致，Worker Private Bytes 不突破既有 4.0 GiB
  安全线，退出后无模型进程残留，并量化冷启动与批量总耗时改善。

### 阶段 E：安全、留存和模块拆分

- 会话 token、Origin/Host、XLSX ZIP 预检、任务留存；
- 拆分三处大文件并保持合同测试全绿；
- 完善发布 smoke、lint 和版本来源。

## 9. 最终建议

如果只选择一个技术优化，优先做“索引断点续建”；它能直接避免再次损失 16 小时。
如果只选择一个业务优化，优先做“人工物料真值集”；它决定系统能否从候选工具走向
可信的编码助手。如果准备分发给其他电脑，则 PyInstaller Worker 端到端验收必须先于
上述两项，属于发布前置条件。

本轮唯一新增文件为本报告。生产代码、测试、配置和业务资源均未修改。
