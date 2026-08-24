# 项目计划优化实施报告

日期：2026-08-24

项目：`D:\AI lianxi\床品Excel解析`

分支：`master`

导入基线：`c311212a071841ea521803c3d52a7cfec4f80c5f`

实施提交：`228be22d188b36209ac21d5861538341620b87da`（`feat: harden local embedding and review workflows`）

作者：`yuewithme <430714704@qq.com>`

## 1. 结论

本轮按优化计划完成了四项可直接使用的改进：修复冻结桌面包无法作为 Embedding Worker 启动的问题；为长时间物料向量构建增加可验证断点续建；为人工审核表增加真值评估；将查询向量推理改为有界微批并补充阶段耗时。

本轮没有改动正式 20 字段、五类核心 JSON、ERP 边界或两种解析模式。没有调用真实 LLM API，没有发送真实业务数据，没有解析真实 PI，也没有自动写回物料编码。

## 2. 实施内容

### 2.1 冻结桌面包 Worker 分发

- 新增统一桌面入口 `desktop/entrypoint.py`。
- 普通启动仍进入 PyWebView 桌面应用。
- 冻结 EXE 收到 `--embedding-worker` 时，在同一 EXE 内进入隔离向量 Worker，而不再错误地把冻结 EXE 当成 Python 解释器执行 `-m`。
- 源码运行仍使用 `python -m bedding_order_parser.materials.query_embedding_worker`，两种运行时明确分流。
- PyInstaller 入口已改为统一分发器，相关入口和打包合同测试已覆盖。

### 2.2 向量索引断点续建

- 新增内容寻址的 Embedding 检查点目录；身份由源文件哈希、模型名、revision、设备、维度、批大小和编码窗口共同确定。
- 每个向量分块使用原子 `.npy` 写入，并在清单中记录 SHA-256、shape 和 dtype。
- 重跑时只复用哈希、shape、dtype 均验证通过的分块；损坏分块会重新编码。
- 检查点清单不保存订单文本或物料描述，只保存源哈希和运行合同。
- 最终 FAISS 索引原子发布成功后，自动删除本次检查点；失败时保留已完成分块供续跑。
- 显式禁止检查点目录与最终索引目录互相包含，避免路径配置错误造成覆盖冲突。
- CLI `build-index` 新增可选参数 `--checkpoint-dir`。

定向故障测试使用 33 条合成文档、32 条一个编码窗口：第一次在第二窗口故障后保留第一窗口；第二次只编码剩余 1 条并复用 1 个分块。损坏分块测试确认两个窗口都会重新编码。

### 2.3 人工审核真值评估

- 审核结论新增 `Top候选外编码正确`，用于记录真实正确编码不在 Top10 内的漏召回。
- 校验器要求该编码存在于当前 SQLite 物料库，但不得出现在该订单 Top10 候选中。
- 新增 `evaluate-review` CLI，从已校验审核表生成聚合指标 JSON：
  - 已审核、未审核、正真值、无物料真值和排除行数；
  - Top1、Top3、Top10 命中数与命中率；
  - Top10 外漏召回数；
  - 无对应物料时系统正确不推荐数、错误推荐数和正确不推荐率。
- 指标 JSON 只包含计数、比例、Schema 版本和审核工作簿 SHA-256，不包含客户、订单文本或物料编码。
- 输出使用原子写入，默认拒绝覆盖。
- 评估前后均校验工作簿哈希，并补充了“校验完成后文件被修改”的 TOCTOU 防护。

### 2.4 查询推理性能和可观测性

- Worker 从逐条 `encode(..., batch_size=1)` 改为最多 8 条一个微批。
- 一个匹配 Job 的多条订单仍只加载一次 BGE-M3，微批能减少模型调用和 Python 调度开销。
- 保留批间取消点和进度写入；完成计数只在整批验证通过后推进。
- Worker 响应和父进程诊断新增四项安全耗时：模型加载、编码、向量写入、总耗时。

当前源码工作树上的离线 BGE-M3 双查询验收结果：

| 项目 | 结果 |
|---|---:|
| 输入 | 2 条合成床品描述 |
| 网络/真实业务 | 本地模型、零网络、无真实业务数据 |
| 退出码 | 0 |
| 输出 | `2 × 1024`、`float32`、两行范数均为 `1.0` |
| 命令墙钟时间 | 15.889 秒 |
| Worker 总耗时 | 14.035669 秒 |
| 模型加载 | 13.637143 秒 |
| 两条合批编码 | 0.370916 秒 |
| 向量写入 | 0.003533 秒 |

结果表明本机当前主要耗时是短进程的模型加载，而不是两条文本的编码。微批已经降低单个 Job 内的重复调用成本；若未来要进一步降低跨 Job 延迟，需要评估常驻模型进程与当前短进程隔离安全之间的权衡。

### 2.5 路径和交接文档

- 根 `AGENTS.md` 和 `bedding-gate` 技能中的项目路径已改为当前实际目录。
- `docs/project_context.md` 不再错误声称项目没有 Web、桌面、LLM 或向量能力。
- 当前交接入口已压缩为低上下文版本，准确说明 standard/ai_enhanced、BGE-M3/FAISS、Web、桌面和安全边界。
- 归档报告中的旧绝对路径作为历史证据保留，没有批量改写。

## 3. 冻结包真实验收

在统一 Worker 分发修复完成后的工作树上，实际运行了 PyInstaller onedir 和 onefile 构建，并运行发布核验脚本。该构建发生在后续真值评估和微批改动之前，因此它证明的是冻结入口和实际本地 BGE-M3 推理链可用；最终微批代码没有再次全量打包。

| 产物 | 结果 |
|---|---|
| onedir 主 EXE | 69,034,929 bytes；SHA-256 `1c277944ec9bfe78938484e043c10caef9217bc99975ec328606dbcf18a16913` |
| onedir 完整目录 | 6,326 个文件；717,711,174 bytes |
| onefile EXE | 257,156,658 bytes；SHA-256 `2b8037558c618cb9dbea3d7fd31818c03c5c9ed3fa2de31d5e02f72d2f3328b1` |
| 发布核验 | onedir、onefile 均通过 |
| onedir Worker | 退出码 0；`1 × 1024 float32`；范数 1.0；墙钟 46.476 秒；Worker 44.025529 秒 |
| onefile Worker | 退出码 0；`1 × 1024 float32`；范数 1.0；墙钟 54.708 秒；Worker 16.557850 秒 |

验收只使用合成床品描述和已下载的本地 BGE-M3，不包含真实 PI、客户或物料主数据。PyInstaller 的非阻断警告涉及未使用的 tensorboard/nvcuda、pycparser 表和 scipy `_cdflib`，未影响构建、发布核验或 Worker 推理。

## 4. 验证证据

### 4.1 测试驱动过程

- 冻结入口：新增测试先因 `desktop.entrypoint` 不存在而失败，实现后通过。
- 断点续建：新增测试先因 `checkpoint_dir` 参数不存在而失败，实施后通过。
- 真值评估：新增测试先因 `review_metrics` 模块不存在而失败，实施后通过。
- Worker 微批：原实现产生 10 次单条调用，新增期望 `[8, 2]` 后先失败，实施后通过。
- 校验后修改防护：测试先证明工作簿在校验后被修改仍会继续评估，补充哈希衔接检查后通过。
- 检查点路径重叠：测试先落到晚期输出冲突，补充前置拒绝后通过。

### 4.2 最终回归

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m pytest tests/materials tests/desktop -q -p no:cacheprovider --basetemp=data/output/pytest-temp-release-regression
```

结果：`116 passed in 19.58s`。

其他验证：

- Python AST：181 个 `src/` 与 `tests/` 文件全部解析通过。
- PowerShell AST：`packaging/` 下 6 个脚本全部解析通过。
- `git diff --check`：通过。
- 暂存范围：不包含 `data/input`、`data/reference`、`data/golden`、`data/output`、`build`、`dist` 或 `dist-onefile`。
- 新增行敏感信息扫描：无密钥、Bearer Token 或 Authorization 值候选。

## 5. 清理结果

验收完成后已删除：

- `build/`：约 555.59 MiB；
- `dist/`：约 684.46 MiB；
- `dist-onefile/`：约 245.24 MiB；
- 冻结 Worker 和源码 Worker 的请求、响应、临时向量；
- 本轮全部 `pytest-temp-*` 目录；
- 项目 `.pytest_cache` 和 `.venv` 之外的源码 `__pycache__`。

三类打包目录合计约 1,485.29 MiB（约 1.45 GiB）。本机没有发现 `%LOCALAPPDATA%\pyinstaller` 缓存。保留了仍有用途的 `.venv`、本地 BGE-M3 模型、物料库、索引、真实输入和既有业务输出；未触碰 Day01。

## 6. 未执行和剩余优化

- 未运行完整项目 pytest；本轮运行与改动直接相关的 materials + desktop 116 项。
- 未运行真实 PI 回归、真实 LLM API、ERP 写回或真实业务外发。
- 未执行完整物料库的 BGE-M3/FAISS 重建；断点续建使用合成向量测试验证。
- 微批完成后的最终代码没有再次执行 PyInstaller 全量构建；下一次正式发版应重新构建并重复 onedir/onefile Worker 验收。
- onefile 约 245 MiB、onedir 约 684 MiB，发布体积仍大。后续可单独审计 PyInstaller 隐式依赖并做可复现瘦身，不能为了体积删除 BGE-M3/torch/FAISS 的实际运行依赖。
- 模型加载占本机双查询 Worker 总耗时约 97%。若日常高频跨 Job 匹配仍慢，下一阶段应设计受控常驻 Worker、空闲回收、内存上限和进程身份校验，再比较吞吐与隔离风险。

## 7. 最终边界确认

- 固定 20 字段和字段类型未变。
- standard 与 ai_enhanced 的五类核心 JSON 发布边界未变。
- 未让 AI 生成或覆盖物料编码和相似分数。
- 真值评估只读取人工审核表并输出聚合指标，不改正式结果、核心 JSON、SQLite 或 ERP。
- 实施提交后工作区为干净状态；本报告将作为独立文档提交。
