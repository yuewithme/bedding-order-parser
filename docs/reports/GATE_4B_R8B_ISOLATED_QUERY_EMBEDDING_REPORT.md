# Gate 4B-R8B 查询 Embedding 子进程隔离报告

## 1. 任务目标

本轮只把查询文本的 BGE-M3 向量生成移入单个短生命周期子进程，并在
worker 完全退出后才允许父业务进程加载全量候选、FAISS 索引和 mapping。
不修改模型、revision、向量空间、Top 300、`hybrid_score_v1`、字段权重、
硬冲突规则或 20 字段业务合同。

## 2. Git 基线

- 分支：`master`
- 初始 HEAD：`86cd25620f4733b0b8391f1201ad2ff42ef61b22`
- 初始短 HEAD：`86cd256`
- 最新基线提交：`docs: audit material matching memory growth`
- 初始工作区：干净

## 3. 原高内存调用链

原调用链为：

`match_orders -> load_all_material_candidates -> load FAISS/mapping ->`
`SentenceTransformerEmbeddingAdapter -> encode -> search/ranking`

父进程会在模型编码期间同时保留 BGE-M3、29,127 条候选、FAISS、
mapping 及派生字典；模型对象直到 `match_orders` 返回才失去局部引用。

## 4. 新调用链

新调用链为：

`match_orders -> _load_order_inputs -> build query texts ->`
`encode_queries_isolated -> worker exits -> load_all_material_candidates ->`
`lazy import/read FAISS and mapping -> Top 300 -> hybrid_score_v1`

`hybrid_matcher.py` 不再顶层导入 FAISS、`vector_index` 或
`SentenceTransformerEmbeddingAdapter`。查询向量先通过无 FAISS/SQLite
依赖的轻量合同校验，再进入既有检索和排名流程。

## 5. 实际修改文件

- `src/bedding_order_parser/materials/query_embedding_contract.py`
- `src/bedding_order_parser/materials/query_embedding_worker.py`
- `src/bedding_order_parser/materials/query_embedding_runner.py`
- `src/bedding_order_parser/materials/hybrid_matcher.py`
- `src/bedding_order_parser/web/services.py`
- `tests/materials/test_query_embedding_worker.py`
- `tests/materials/test_hybrid_matcher.py`
- `tests/web/test_services.py`
- `docs/reports/GATE_4B_R8B_ISOLATED_QUERY_EMBEDDING_REPORT.md`

未修改 parser、20 字段模型、匹配权重、字典、索引、物料主数据、前端、
桌面启动器、依赖文件或 Day01。

## 6. Worker 请求响应合同

请求固定校验：

- schema version：`1.0`
- model：`BAAI/bge-m3`
- revision：`5617a9f61b028005a4858fdac845db406aefb181`
- device：`cpu`
- dimension：`1024`
- normalize：`true`
- query ID 唯一且文本非空

worker 使用现有 `SentenceTransformerEmbeddingAdapter`，严格按
`batch_size=1` 和输入顺序逐条编码。输出是同一受控临时目录中的
`vectors.npy`，要求 `float32`、有限值、逐行归一化且 shape 为
`(record_count, 1024)`。响应记录 PID、query 顺序、shape、dtype、
开始/完成时间，并在每条 query 后原子更新完成条数和最后一个 query ID。

worker 不读取 PI、正式 JSON、SQLite、FAISS、mapping，不执行候选比较，
也不写正式业务结果。

## 7. PID、超时和取消机制

runner 使用当前虚拟环境解释器、`shell=False` 和 Windows
`CREATE_NO_WINDOW`。`pythonw.exe` 场景优先选用同目录 `python.exe`。

Windows 虚拟环境解释器可能表现为一个重定向启动器进程及其实际 CPython
子进程。runner 不再假设 `Popen.pid` 就是业务 worker PID，而是以受控
响应中的 `worker_pid` 为真实 PID。取消先写
`cancel.requested`，等待短暂协作退出；若 worker 正在模型加载或单次
encode 中无法响应，则只对回执中的精确 PID 调用终止，之后等待启动器
退出。启动超时、总超时、非零退出、输出缺失、shape/dtype/NaN/归一化
错误均失败关闭，不允许继续加载候选或 FAISS。

## 8. 父进程与 Worker 资源加载顺序

父进程在启动 worker 前只读取正式结果、解析报告和轻量 manifest，
并构造 query 文本。worker 退出并通过输出合同后，父进程才：

1. 加载全量 `MaterialCandidate`；
2. 延迟导入 FAISS 相关模块；
3. 校验并读取 FAISS 与 mapping；
4. 建立 `mapping_by_code`、`position_by_code`；
5. 执行既有召回、结构化过滤和排名。

取消检查点覆盖 worker 启动前、等待期间、worker 退出后、候选加载前、
FAISS/mapping 加载前、每条订单开始前和结果返回前。Web 服务把任务
状态检查传入该合同。

## 9. 定向测试命令和结果

未运行完整 pytest，也未在测试中加载真实 BGE-M3。

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests/materials/test_query_embedding_worker.py -q` | `12 passed in 3.32s` |
| `uv run pytest tests/materials/test_hybrid_matcher.py -q` | `6 passed in 0.75s` |
| `uv run pytest tests/web/test_services.py -q` | `8 passed in 0.72s` |

合计 `26 passed`。覆盖请求/响应、batch size 1、顺序、float32、归一化、
无 FAISS/SQLite worker 依赖、正常退出、启动/总超时、精确 PID 终止、
取消、非零退出、缺失/损坏输出、worker 先退出、父进程无模型/FAISS
顶层导入、原有排序及 Web 中断传播。

## 10. 单份 PI 实际运行结果

唯一提交文件：

`data/input/pi/3402505MR30022 Proforma Invoice of H Hotel JODC - Dun 20250507.xlsx`

- 提交方式：桌面快捷方式启动的同一实例，通过 `/api/jobs` 提交
- 提交次数：1；没有重试
- 任务 ID：`2fcc1d3c94044f8eb2a979b57a02c47c`
- 最终状态：`failed`
- 最终阶段：物料匹配，进度 70%
- 错误：`Embedding worker exited with an error.`
- 失败原因：外部验收监控把 Windows 虚拟环境重定向启动器 PID
  `39308` 和实际 CPython worker PID `39276` 误判为两个独立
  Embedding worker，触发 `second_embedding_worker` 安全停止。
- 实际处理：只终止实际 worker PID `39276`；启动器随后退出。

这是一个监控身份归类的假阳性，不是已确认的第二个模型实例，也不是内存
红线。按照“只提交一次、不重试”要求，本轮没有重新提交该 PI。

## 11. 业务 JSON 与 Gate 2D 一致性

任务在进入匹配前已生成正式业务 JSON、解析诊断 JSON 和字典验证 JSON。
三份文件均为合法 UTF-8 JSON。

- 业务记录：3
- 每条业务记录字段数：`20, 20, 20`
- 前 19 字段：字符串
- 第 20 字段：float
- `null`：0
- 与 Gate 2D 同名基线：3 条完整对象逐字段一致
- 源 PI SHA-256 前后：
  `e005dc8f5f3b17e4e1175e902a1a1417883700c90173f3e9abb1fec9a33c9bab`

由于任务未发布 artifacts 映射，这三份文件存在于任务目录，但没有作为
completed 任务提供下载。

## 12. 匹配结果一致性

本次 worker 在生成查询向量前被外部安全停止，未加载 FAISS/mapping，
未生成匹配候选、匹配摘要或 ZIP。因此以下项目均为**无法比较**：

- 3 条真实 query 顺序；
- Top 1 物料编码；
- Top 候选编码顺序；
- `hybrid_score_v1`；
- 决策状态；
- 候选数量和统计摘要。

未使用 fake 测试结果冒充真实匹配结果。

## 13. Worker 资源峰值

**未取得。** 验收监控在同一次 WMI 快照中发现重定向启动器和实际
CPython 后立即按“第二 worker”条件停止；该时点尚未完成 worker 身份
归并，因而没有产生可信的单一 worker Working Set、Private Working Set、
Private Bytes、Commit Size 或 CPU 峰值。

不能据此判断 worker 是否低于 4.0 GiB。

## 14. 父进程资源峰值

在安全停止前的有效样本中：

- 父进程 PID：`22816`
- Working Set 峰值：`147,464,192 B`，约 `140.63 MiB`
- Private Bytes 峰值：`610,279,424 B`，约 `582.01 MiB`
- 提交前 Working Set：`55,848,960 B`，约 `53.26 MiB`
- 提交前 Private Bytes：`542,416,896 B`，约 `517.29 MiB`

由于任务在模型加载早期停止，这些值不能代表完整匹配峰值。

## 15. 系统可用内存最低值

有效样本中：

- Available Physical Memory 最低：`6,673,707,008 B`，约 `6.21 GiB`
- Commit/Commit Limit 最高：约 `64.81%`
- D 盘最低剩余：约 `169.66 GiB`

没有触发 1.25 GiB 可用内存或 90% Commit 红线。

## 16. Worker 退出后的内存回收

实际 worker PID `39276` 和重定向启动器 PID `39308` 均已退出，但因
停止前没有取得可信 worker 基线和峰值，**无法量化 worker 退出后的模型
内存回收量**。桌面关闭后系统未留存该 worker。

## 17. FAISS 加载时 Worker 是否已退出

代码顺序和定向测试证明 FAISS 只能在 worker 成功退出后加载。本次真实
任务在 worker 阶段失败，未进入 FAISS/mapping 加载，因此真实结果应记为：

`not_reached`，不能写成真实验收“是”。

## 18. 安全停止是否触发

安全停止：**是**。

触发项为外部监控的 `second_embedding_worker` 假阳性。实际观测到的是
同一 `-m bedding_order_parser.materials.query_embedding_worker`
命令的虚拟环境重定向启动器和 CPython 子进程。未触发：

- worker Private Bytes 超 4.0 GiB 持续 10 秒；
- 系统可用内存低于 1.25 GiB；
- Commit 达到 90%；
- CPU 超 95% 持续 60 秒；
- worker 超 5 分钟。

验收期间未观察到电脑或桌面明显卡顿。

## 19. 桌面关闭和残留检查

外部安全停止后：

- 实际 worker PID `39276`：已退出；
- 重定向启动器 PID `39308`：已退出；
- 任务：`failed`；
- 桌面窗口：通过 `WM_CLOSE` 正常关闭；
- 桌面业务进程：已退出；
- `runtime.json`：已移除；
- 8000 端口：已释放；
- 相关 `pythonw.exe`：无；
- 相关 worker：无。

历史记录由 5 条增加为 6 条，但新增记录为 `failed`，不是成功标准要求的
`completed`。

## 20. 未处理的 WinError 5 与旧 Processing

本轮没有修改 `job.json` 原子写入、WinError 5 处理或旧
`processing` 恢复规则。真实验收也没有使用 R7 的第一份失败 PI。

## 21. 未执行事项

- 未运行 12 份 PI 回归；
- 未调用 LLM、外部 API、Embedding API；
- 未重建 FAISS；
- 未修改模型、revision、dtype 或索引；
- 未执行 PyInstaller、Onedir、Onefile；
- 未修改前端或桌面视觉；
- 未修改 Day01；
- 未运行完整 pytest；
- 未 push、tag 或 amend。

## 22. 最终 Commit

- 提交信息：`fix: isolate query embedding memory`
- Commit：本报告所在的提交；完整哈希以提交后的 `git rev-parse HEAD`
  为准。

## 23. 工作区与结论

代码实现和 26 项定向测试通过，源 PI 与 Gate 2D 确定性结果保持不变。
但唯一一次真实任务没有 completed，真实 worker 峰值、内存回收、FAISS
后续阶段和匹配基线均未完成验证。因此 Gate 4B-R8B 的**代码实现完成，
真实受控验收失败**，不得宣称内存隔离已经通过生产级验收。

由于实际结果既不满足“完整成功且内存安全”，也没有证明“worker 触发
内存红线”，提示词给出的 A/B 两个后续条件均未成立。唯一建议是下一轮
先把 Windows 虚拟环境重定向启动器与实际 CPython 归并为一个逻辑 worker
身份，再由用户明确批准一次新的单 PI 受控验收；不得在本轮重试，也不应
据此切换模型或重建索引。
