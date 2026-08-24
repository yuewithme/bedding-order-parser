# Gate 4B-R8A 物料匹配高内存根因静态审计

## 1. 任务目标

本轮只通过静态代码、配置、既有报告和既有产物元数据，追踪桌面任务进入物料匹配后的内存生命周期，解释 Gate 4B-R7 中工作集从约 4.713 GiB 继续增长到约 9.95 GiB 的最可能原因，并提出下一轮唯一、可受控验证的最小修复方向。

本轮没有修改生产代码、测试、配置、模型、索引、业务数据或 Day01；没有运行 Python 业务程序、pytest、桌面/Web 服务、真实 PI、BGE-M3、Torch、FAISS、SQLite 全表扫描、LLM、Playwright 或 PyInstaller。

## 2. Git 基线

| 项目 | 结果 |
| --- | --- |
| 仓库 | `D:\AI-Learning\Projects\bedding-order-parser` |
| 分支 | `master` |
| 初始 HEAD | `4879aaf29aeac574c3ddca299a156b0117a5ab06` |
| 初始短 HEAD | `4879aaf` |
| 最新提交 | `4879aaf test: record desktop regression across 12 pis` |
| 初始工作区 | 干净 |
| R7 权威证据 | 3 条记录的第 2 份 PI 在物料匹配阶段触发安全停止；安全触发时工作集约 4.713 GiB，关闭确认等待期间最高约 9.95 GiB，系统可用内存最低约 0.858 GiB |

基线检查只执行了 `git status --short`、`git log -5 --oneline --decorate`、`git rev-parse HEAD` 和 `git rev-parse --short HEAD`。未运行测试。

## 3. 审计文件清单

### 项目运行路径

- `src/bedding_order_parser/web/routes.py`
- `src/bedding_order_parser/web/services.py`
- `src/bedding_order_parser/desktop/launcher.py`
- `src/bedding_order_parser/desktop/server_controller.py`
- `src/bedding_order_parser/materials/__main__.py`
- `src/bedding_order_parser/materials/hybrid_matcher.py`
- `src/bedding_order_parser/materials/embedding_model.py`
- `src/bedding_order_parser/materials/candidate_filter.py`
- `src/bedding_order_parser/materials/field_comparator.py`
- `src/bedding_order_parser/materials/vector_search.py`
- `src/bedding_order_parser/materials/match_writer.py`

### 配置、索引与既有证据

- `pyproject.toml`
- `uv.lock`
- `data/output/material_vector_index/vector_index_manifest.json`
- `docs/reports/GATE_3B_A_MATERIAL_STORE_FOUNDATION_REPORT.md`
- `docs/reports/GATE_3B_B_VECTOR_INDEX_FOUNDATION_REPORT.md`
- `docs/reports/GATE_3B_C_HYBRID_MATCHING_PROTOTYPE_REPORT.md`
- `docs/reports/GATE_4B_R7_12_PI_DESKTOP_REGRESSION_REPORT.md`
- R7 已有 3 条局部业务 JSON，仅统计 Embedding 相关字段字符长度，不复制业务内容。

### 只读依赖与模型配置

- `.venv/Lib/site-packages/sentence_transformers/base/model.py`
- `.venv/Lib/site-packages/sentence_transformers/base/modules/transformer.py`
- `.venv/Lib/site-packages/sentence_transformers/sentence_transformer/model.py`
- `.venv/Lib/site-packages/transformers/modeling_utils.py`
- Hugging Face 本地 BGE-M3 snapshot 的 `config.json`、`sentence_bert_config.json`、`modules.json` 及文件大小。

## 4. 完整调用链

| 层级 | 文件与位置 | 函数/对象 | 实际行为与生命周期 |
| --- | --- | --- | --- |
| HTTP 请求 | `web/routes.py:65` | `WebRequestHandler.do_POST` | 接收上传与启动请求，调用任务服务；不加载模型。 |
| 任务创建/提交 | `web/services.py:190-194` | `JobService.start_job` | 把同一 job 提交给单 worker 执行器；每个 PI 一次。 |
| 后台线程 | `web/services.py:60-102` | `DaemonJobExecutor` | 整个桌面生命周期一个 daemon worker，串行执行任务。 |
| 任务主体 | `web/services.py:371-500` | `JobService._run_job` | 在线程内延迟导入解析与匹配模块；每个 PI 一次。 |
| 正式解析 | `web/services.py:397-405` | `parse_order` | 生成正式业务 JSON、parse report 和字典验证；字典验证属于同一次 parse 调用。 |
| 中断检查 | `web/services.py:406` | `_ensure_job_active` | 解析完成后检查一次。 |
| 物料匹配 | `web/services.py:420-427` | `match_orders` | 对该 PI 产生的整批订单记录调用一次，不是逐记录调用。 |
| 输入构造 | `materials/hybrid_matcher.py:94-105,300-356` | `_load_order_inputs` | 读取该 job 的正式结果和报告，构造轻量 `OrderQuery`。 |
| 全量主数据 | `materials/hybrid_matcher.py:106` | `load_all_material_candidates` | 每个匹配任务读取一次 SQLite 全量候选。 |
| 向量运行时 | `materials/hybrid_matcher.py:107-110,359-394` | `_load_vector_runtime` | 每个任务依次加载 FAISS、mapping 和一个 BGE-M3 adapter。 |
| Embedding | `materials/hybrid_matcher.py:116-123` | `embedding.encode` | 将该 PI 的全部 query 文本一次送入，R7 三条记录的 batch size 为 3。 |
| FAISS 检索 | `materials/hybrid_matcher.py:124-129` | `index.search` | 整批 query 一次搜索 Top 300，并建立位置字典。 |
| SQLite 结构召回 | `materials/hybrid_matcher.py:135-146` | `retrieve_structured_candidate_codes` | 每条记录一次轻量 SQL，只返回编码。 |
| 候选比较/排序 | `materials/hybrid_matcher.py:147-186` | `compare_candidate` 等 | 每条记录创建候选评价，硬冲突对象不保留，幸存对象排序。 |
| 结果保留 | `materials/hybrid_matcher.py:187-207` | `records.append` | 每条仅保留 Top 10 的序列化候选、决策与统计。 |
| 匹配输出 | `web/services.py:428-454` | `write_match_outputs`、`_write_bundle` | `match_orders` 完成后才再次检查中断并写两份匹配 JSON 与 ZIP。 |

关键结论：Web/桌面路径没有另写一套匹配算法；它直接复用了 Gate 3B-C 的 `match_orders`。高内存主要发生在这个同步函数内部。

## 5. 模型实例化次数

1. **一次桌面生命周期：**每个进入物料匹配的 PI 任务都会新建一次 BGE-M3；若生命周期内执行 N 个匹配任务，则累计构造 N 次，但单 worker 正常情况下同一时刻最多一个。
2. **一次 PI 任务：**默认路径构造一次，位置是 `_load_vector_runtime()` 中的 `SentenceTransformerEmbeddingAdapter(...)`。
3. **一条订单记录：**不构造模型。
4. **三条订单记录：**共享同一个模型，不会创建三份模型。
5. **`match_orders()` 调用次数：**Web 对一个 PI 的整批记录调用一次。
6. **adapter 位置：**在订单记录循环外创建，循环开始前已完成全部 query 编码。
7. **长期引用：**adapter 是 `match_orders` 的局部变量，没有存入 job、历史记录或输出；但在函数返回前一直保持强引用。
8. **任务结束释放：**函数返回后没有项目级 Python 引用阻止析构；原生 allocator、mmap 页面和工作集是否立即归还操作系统，静态审计无法确认。
9. **第二个任务：**不会复用第一个任务的模型，会重新加载一个新实例。
10. **测试/查询/索引模型并存：**生产路径只有一个查询模型；FAISS 是预计算向量索引，不是另一个神经网络模型；没有测试模型实例。

直接证据：

- `embedding_model.py:41-58` 延迟导入并构造 `SentenceTransformer`。
- `hybrid_matcher.py:107-109,375-380` 每次 `match_orders` 都经 `_load_vector_runtime` 构造 adapter。
- `hybrid_matcher.py:116-123` 整批编码发生在 `for input_index, item in enumerate(inputs)` 之前。
- 项目没有 singleton、`lru_cache`、全局 adapter 或进程级 runtime cache。

## 6. FAISS 和 mapping 加载次数

1. FAISS 在 `_load_vector_runtime()` 中、query 编码前加载。
2. 每个 `match_orders`/PI 任务加载一次，不是每条记录加载。
3. 活跃任务只保留一个 duvet-cover 索引；项目目录另有全量索引产物，但此路径不读取它。
4. 没有把整个 FAISS 索引转换为 NumPy 矩阵；只对结构召回而向量 Top 300 未覆盖的候选调用 `index.reconstruct(position)`。
5. mapping JSONL 每任务完整展开为一个 29,085 行的 Python `list[dict]`。
6. mapping 不会逐记录重新读取。
7. 29,127 个 `MaterialCandidate` 每任务创建一次，不是逐记录重复创建。
8. Top 300 前不创建 29,085 个逐 query 候选评价；FAISS 直接返回 `records x 300` 的位置与分数。
9. 合并时每条记录创建结构编码列表、Top 300 字典、并集列表和 set；同时任务级创建 `mapping_by_code`、`position_by_code`。
10. 排序只保留当前记录幸存的 `CandidateEvaluation`；最终输出只保留 Top 10，不保留全量 Embedding 矩阵。

量化数据：

| 资源 | 规模 |
| --- | ---: |
| `material_master.sqlite3` | 25,260,032 B（24.090 MiB），29,127 条 |
| `duvet_cover.faiss` | 119,132,205 B（113.613 MiB），29,085 x 1,024 float32 |
| `duvet_cover_mapping.jsonl` | 19,129,463 B（18.243 MiB），29,085 行 |
| 单个 query 向量 | 1,024 x 4 B，约 4 KiB |
| R7 三条 query 矩阵 | 3 x 1,024 x 4 B，约 12 KiB |

这些资源是明确的内存放大项，但其文件规模本身不足以单独解释约 9.95 GiB。

## 7. 按记录循环行为

不存在 `for record: model/index/mapping/all_materials = ...` 模式。模型、索引、mapping、全量候选都在循环外创建。

循环内实际行为：

- 每条创建最多 300 个向量召回编码/分数。
- 每条通过 SQLite 返回结构召回编码。Gate 3B-C 的 49 条统计平均为 1,730.449。
- 两路并集平均 1,984.306；逐一创建比较对象，平均 1,976.265 个因硬冲突被丢弃，平均只剩 8.041 个。
- `evaluations`、当前记录的召回字典和并集列表在下一轮可失去引用，不由最终结果长期保留。
- `records` 只保留每条 Top 10 的普通字典。
- `reconstructed_vectors` 是任务级缓存，会跨记录累积结构召回独有候选的 1,024 维向量；它有界于索引规模，但可能达到约 113.6 MiB 量级并带来 Python 字典开销。
- 全量 `candidates`、`mappings`、`mapping_by_code`、`position_by_code`、FAISS 和模型在整个函数期间同时存活。

因此存在**任务级大型对象重叠与有界缓存累积**，不存在逐记录无限累积完整模型、完整索引或全部候选评价。

R7 三条既有正式记录的九个 Embedding 业务字段，字符长度合计分别为 85、85、84，单字段最大 37；`build_order_query()` 也只拼接 11 个标量字段。因此本次约 9.95 GiB 不能归因于真实 query 文本接近 8,192 token 上限。

## 8. 桌面父子进程分析

- `desktop/launcher.py:52-66` 在实际 Python 应用进程中启动本地 HTTP 控制器和 pywebview。
- `server_controller.py:72-77` 只额外建立一个 daemon HTTP 线程。
- `web/services.py:66-71` 只额外建立一个 daemon job worker 线程。
- 项目运行路径没有 `multiprocessing`、`ProcessPoolExecutor` 或为匹配创建 Python 子进程。
- Windows 快捷方式可出现一个很小的虚拟环境 `pythonw.exe` 启动器父进程和实际 CPython 子进程；静态源码没有让父启动器导入业务模块。
- WebView2 会有浏览器渲染进程，但没有项目代码让它们加载 Torch/BGE-M3。

结论：只有实际 CPython 进程执行 Python 业务代码。WMI 把父子 Working Set 相加时，共享页可能被重复计入，但父启动器很小；更重要的是 R7 同时观测到系统可用物理内存降至约 0.858 GiB，因此不能把高内存解释为纯统计假象。

下一轮应分别采集：

- `Working Set`：当前驻留物理页，包含共享/文件映射页。
- `Private Working Set`：当前驻留且仅该进程持有的页。
- `Private Bytes`：该进程已提交的私有虚拟内存。
- `Commit Size`：进程提交量，并同步记录系统 committed/limit 与 available memory。
- 每个 PID 的父子关系和上述指标，不只求和 Working Set。

## 9. 安全中断路径

当前路径为：

`安全阈值触发（外部验收） -> 请求关闭窗口 -> 等待确认对话框 -> interrupt_active_jobs() -> job.json 标为 interrupted -> ServerController.stop() -> JobService.close() -> executor.shutdown(wait=False) -> Python 进程退出`

逐项结论：

1. 安全停止只能阻止后续阶段，不能停止正在执行的匹配函数。
2. worker 没有 `Event`、cancel token 或可查询回调。
3. 当前 `SentenceTransformer.encode` 是同步阻塞调用，项目没有向其提供可中断机制。
4. 关闭确认框等待期间尚未调用 `interrupt_active_jobs()`；即使已标记，`match_orders` 内也没有检查点，所以内存继续增长。
5. job worker 和 HTTP 线程都是 daemon。
6. HTTP 关闭只等待 HTTP 线程最多 5 秒；`JobService.close()` 对 worker 使用 `wait=False`，不等待当前任务完成。
7. 当前实现要立即释放正在使用的模型，只能结束实际 Python 进程；标记 job 不会释放。
8. 最安全的强制取消策略是把高资源匹配隔离到可识别 PID 的受控子进程，先协作取消，超时后终止该子进程；但这不是本轮实现内容。
9. 若仍采用进程内匹配，应至少在模型加载后、编码批次之间、FAISS 后和逐记录循环之间检查取消；这仍不能可靠中断一个正在执行的单次 Torch forward。
10. 若要同时实现资源上限和可靠强制终止，独立子进程最终更稳妥。

当前任务的安全取消能力判定为**部分**：可以拒绝新任务、取消队列并在整段匹配返回后阻止后续发布，但不能中断当前高内存计算。

## 10. 与 Gate 3B-C 原型比较

| 对比项 | Gate 3B-C 原型 | 当前 Web/桌面路径 |
| --- | --- | --- |
| 入口 | `materials/__main__.py:123-134` | `web/services.py:420-430` |
| 核心函数 | 同一 `match_orders` | 同一 `match_orders` |
| 模型 | 一次调用构造一次 | 每个 PI 任务构造一次 |
| FAISS/mapping | 一次调用加载一次 | 每个 PI 任务加载一次 |
| 输入批次 | 12 份结果、49 条在一次调用中 | 每份 PI 独立调用；R7 目标为 3 条 |
| 逐记录算法 | 同一结构召回、硬过滤、排序 | 相同 |
| 输出 | 同一 `write_match_outputs` | 同一输出后再组 ZIP |
| 模型生命周期 | 49 条共享一个模型 | 一个 PI 内共享；下一 PI 重载 |

Gate 3B-C 报告没有采集内存，因此“49 条曾完成”不能证明当前机器在 R7 时的可用内存条件下安全。Web 集成没有复制模型或改成逐记录加载，但把原型的一次 49 条调用改成了每 PI 一次重资源初始化；这是跨任务重复加载的生命周期差异。

R7 的高峰发生在该桌面生命周期第一次真正进入 `match_orders` 的任务，故不能归因于多个已完成 Web 任务的模型同时累积。pywebview 增加启动基线，但不是 BGE-M3 重复实例来源。

## 11. 依赖和模型配置

| 项目 | 实际值 |
| --- | --- |
| Python | `>=3.12` |
| torch | `2.13.0` |
| sentence-transformers | `5.6.1` |
| transformers | `5.14.1` |
| faiss-cpu | `1.14.3` |
| numpy | `2.5.1` |
| pywebview | `6.2.1` |
| 模型 | `BAAI/bge-m3` revision `5617a9f61b028005a4858fdac845db406aefb181` |
| device | `cpu` |
| dtype | 模型配置 `float32`；项目未覆盖 |
| 维度 | 1,024 |
| query batch | `min(16, record_count)`；R7 为 3 |
| 多进程编码 | 否，device 是单个字符串且未传 pool |
| 输出 | 默认 sentence embedding；`convert_to_numpy=True`、归一化；不请求 token embeddings 或全部 hidden states |
| 模型最大长度 | 8,192；项目未设更小上限 |

BGE-M3 本地 `pytorch_model.bin` 为 2,271,145,830 B（2,165.933 MiB），模型为 24 层、hidden size 1,024、intermediate size 4,096、16 heads、词表 250,002。

当前 Transformers 5.14.1 的静态实现补充说明：

- `from_pretrained` 默认 dtype 为 `"auto"`，最终采用模型 `float32` 配置。
- 普通模型在 meta device 上构造，避免先初始化一整份随机参数。
- `.bin` zip checkpoint 通过 `torch.load(..., mmap=True)` 读取，再装载进模型。
- 因而“必然同时复制两份完整 2.166 GiB 权重”不能列为已确认事实；mapped checkpoint 页、最终参数页、Torch/原生库与临时工作区对 Working Set/Private Bytes 的具体贡献必须动态分解。
- `SentenceTransformer.encode` 使用 `torch.inference_mode()`，未建立反向图。

## 12. 已确认根因

| 编号 | 证据文件/函数 | 代码行为 | 内存机制与预期级别 | 修复复杂度 | 修改风险 |
| --- | --- | --- | --- | --- | --- |
| A-01 | `embedding_model.py:53-58`；`hybrid_matcher.py:359-380`；BGE-M3 config | 每个 PI 任务在 CPU/float32 下构造完整 BGE-M3，单权重文件 2.166 GiB | 单模型即 GiB 级常驻与加载压力，是首要大头 | 中 | 改 dtype/后端会影响向量合同，不能盲改 |
| A-02 | `hybrid_matcher.py:106-130,135-238` | 加载顺序先创建全量 candidates、FAISS、mapping，再创建模型；模型编码后仍被局部变量引用到函数返回 | 模型与约 132 MiB 磁盘规模的索引/mapping、29k Python 候选、字典及逐记录对象全程重叠；数百 MiB 至 GiB 级放大 | 低至中 | 调整生命周期需保持 manifest 校验和输出不变 |
| A-03 | `launcher.py:126-137`；`services.py:213-233,420-428,502-504` | 关闭确认前不标记中断；标记只写元数据；`match_orders` 内无检查，worker shutdown 不等待/不中止当前函数 | 本身不创建模型，但确认解释安全触发后内存为何继续增长，直到计算返回或进程退出 | 中 | 强制终止必须隔离进程，避免破坏主服务数据 |

## 13. 高概率原因

| 编号 | 证据文件/函数 | 代码行为 | 内存机制与预期级别 | 修复复杂度 | 修改风险 |
| --- | --- | --- | --- | --- | --- |
| B-01 | `transformers/modeling_utils.py:337-384,4408-4456,4562-4600` | 2.166 GiB `.bin` 以 mmap/state-dict 路径装载到 float32 模型 | mapped 权重页、最终参数、Torch DLL/allocator 和加载临时页很可能使 Working Set 明显高于文件大小；预计数 GiB | 高（若改模型格式/后端） | 可能改变数值、索引兼容性或引入新依赖 |
| B-02 | `candidate_filter.py:102-127`；`vector_search.py:149-171`；`hybrid_matcher.py:110,126-130` | 29k SQLite 行转 dataclass，29k JSONL 转 dict，并建立两个索引字典和跨记录重建向量缓存 | Python 对象开销高于磁盘文本大小，预计数百 MiB；会与模型峰值重叠 | 中 | 流式化/瘦对象可能触及候选合同 |
| B-03 | R7 报告 4、14 节 | 任务启动前系统仅约 4.41 GiB 可用，安全触发时只剩约 0.858 GiB | 同一模型成本在低可用内存环境下更易造成分页、工作集抖动和持续增长 | 低（验收前置条件） | 只能降低风险，不能替代代码修复 |

## 14. 可能原因

| 编号 | 证据文件/函数 | 代码行为 | 内存机制与预期级别 | 修复复杂度 | 修改风险 |
| --- | --- | --- | --- | --- | --- |
| C-01 | Torch CPU 推理路径；项目未配置线程数 | CPU kernel、oneDNN/OpenMP 线程池可能保留 workspace/线程栈 | 静态无法定量，可能为数十至数百 MiB，极端实现下更高 | 中 | 限线程可能显著降低性能 |
| C-02 | `hybrid_matcher.py:130,156-162` | `reconstructed_vectors` 跨 3 条记录增长 | 最坏接近索引向量体量约 113.6 MiB，通常小于该上限 | 低 | 改缓存可能增加重建时间 |

## 15. 已排除原因

| 编号 | 排除项 | 证据与结论 | 预期内存 | 修复复杂度/风险 |
| --- | --- | --- | --- | --- |
| D-01 | 每条记录创建一份 BGE-M3 | 模型在记录循环外创建；3 条共享一个实例 | 0 份额外模型 | 无需修复 |
| D-02 | 每条记录读取一份 FAISS | `faiss.read_index` 仅在 `_load_vector_runtime` 调用一次 | 0 份额外索引 | 无需修复 |
| D-03 | 每条记录重新展开 mapping | `_read_mapping` 在循环外一次执行 | 0 份额外 mapping | 无需修复 |
| D-04 | Top 300 前为每条创建 29,085 个候选评价 | FAISS 直接返回 Top 300；仅两路并集进入 comparator | 不成立 | 无需修复 |
| D-05 | 把整个 FAISS 复制为 NumPy | 只保留 query 矩阵和按需单向量 reconstruct | 不成立 | 无需修复 |
| D-06 | SentenceTransformer 多进程编码 | 传入单一 `cpu` device，没有 pool 或 device list | 无额外模型进程 | 无需修复 |
| D-07 | R7 三条 query 达到 8,192 token | 既有结果字段长度合计仅 84-85 字符，单字段最大 37 | 激活不可能由 8k 长文本触发 | 无需修复 |
| D-08 | Web/pywebview 复制 Gate 3B-C 模型 | Web 直接调用同一个 `match_orders`；WebView2 不执行 Python 模型代码 | 不成立 | 无需迁移 Web 框架 |

## 16. 最小修复方案

### 修复方案 1：最小且最有证据

**拆开 `_load_vector_runtime` 的重资源生命周期：先从轻量 manifest 构造一次 query encoder，按 batch size 1 生成 query vectors，立即删除 adapter 并执行受控释放；确认模型对象不再被引用后，再加载全量 candidates、FAISS 和 mapping，执行现有 Top 300 与 hybrid score。**

理由：

- 不修改 BGE-M3、1024 维、归一化、FAISS、Top 300、字段权重、硬冲突或评分合同。
- 直接消除 A-02 已确认的“模型与全量检索运行时长期重叠”。
- batch size 1 不改变每条 embedding 的业务语义，并降低推理临时张量的同时峰值。
- R8B 必须采集加载前、模型加载后、每次 encode 后、模型释放后、FAISS/mapping/candidates 加载后、每条比较后和函数返回后的 Working Set、Private Working Set、Private Bytes、Commit Size。
- 若模型加载阶段自身仍越过红线，方案 1 判定不足，不得继续 12 份回归。

### 修复方案 2：若方案 1 不足

把 query embedding 或完整 `match_orders` 放入单一受控子进程，严格串行，返回轻量向量/JSON；为子进程设置资源监控、取消事件和超时，必要时只终止该 PID。父进程不得同时预加载同一 BGE-M3。此方案能保证任务完成/取消后释放模型，并为硬取消提供边界，但改动和测试面更大。

进程级 singleton 不作为首选：R7 高峰发生在第一次真正匹配，singleton 不能降低首次加载峰值，反而会让 2 GiB 以上模型在整个桌面生命周期常驻。

## 17. 不建议方案

- **只降低 Top K：**Top 10 是输出保留量，不是模型加载大头，也不减少 FAISS Top 300 前的模型成本。
- **盲目换小模型或改 float16/bfloat16：**现有 FAISS 用固定 BGE-M3 revision 和向量空间构建；变化会破坏索引合同，CPU 支持和召回影响未经验证。
- **只调大虚拟内存：**只能把失败变慢，不能减少 Private Bytes/Commit 或改善取消。
- **关闭安全阈值：**会移除最后一道保护，不能修复内存。
- **直接全局缓存模型：**不能解决首次峰值，且会长期占用内存。
- **马上继续 12 份：**R7 已证明风险，必须先单份 3 记录受控验证。
- **接入 LLM、迁移 Web 框架或执行 PyInstaller：**与根因无关，会扩大变量和资源压力。

## 18. 下一 Gate 唯一目标

**Gate 4B-R8B：实施一个有证据的最小内存修复，并用单份 3 记录 PI 受控验证。**

R8B 只验证方案 1：重排重资源生命周期、batch size 1、阶段化 Windows 内存指标与现有结果一致性。不得同时处理 WinError 5、旧 processing 记录、12 份全量回归、LLM 或 PyInstaller。

## 19. 未执行事项

- 未运行 pytest。
- 未运行 Python 业务程序或导入 Torch。
- 未启动 Web、桌面窗口或快捷方式。
- 未上传、解析或重新匹配真实 PI。
- 未实例化或加载 BGE-M3。
- 未执行 `faiss.read_index`。
- 未打开 SQLite 做内容扫描。
- 未调用 LLM/API。
- 未运行 Playwright、PyInstaller、Onedir 或 Onefile。
- 未修改或删除生产文件。

## 20. Git 提交与工作区

本轮唯一交付文件为：

`docs/reports/GATE_4B_R8A_MATERIAL_MATCH_MEMORY_ROOT_CAUSE_AUDIT.md`

提交信息：

`docs: audit material matching memory growth`

提交前后通过 `git diff --check`、`git status --short` 和 `git diff --name-status` 确认变更范围。最终 commit 与工作区状态以提交后的命令输出为准。
