# Gate 4B-R11：11记录PI Embedding Worker异常退出修复报告

## 1. 任务范围

本轮只诊断并修复 11 记录 PI 在查询 Embedding Worker 阶段异常退出后：

- 父进程只能得到通用错误；
- Worker 退出码、stderr、失败阶段和查询进度没有进入 Job 元数据；
- 临时运行目录在父进程完成诊断持久化前被删除；
- 瞬时的、首条查询前的不透明进程退出没有受控恢复路径。

本轮没有修改匹配算法、`hybrid_score_v1`、字段权重、硬冲突规则、FAISS
召回逻辑、正式 20 字段合同或解析规则。没有接入 LLM/API，没有执行
12 份 PI 回归，也没有执行 PyInstaller、Onedir 或 Onefile。

## 2. Git 与保护基线

- 项目：`D:\AI-Learning\Projects\bedding-order-parser`
- 分支：`master`
- 初始 HEAD：`389f64dfdee2e92284bf063039fd75b7bfdb0b72`
- 初始提交：`389f64d test: verify embedding worker resource isolation`
- 初始工作区：干净
- Day01 HEAD：`b6206bf28a9ce5499e317cee324b16ea98bf569d`
- Day01 工作区：干净

## 3. R10 失败证据

R10 的失败 Job 为：

`6a5eb6c87f2f44b4ab53174dff7013f0`

该任务在安全阈值内、`0/11` 查询完成时退出，Job 只保留：

`Embedding worker exited with an error.`

失败后没有保留 Worker 的退出码、stderr、失败响应或运行目录，因此无法从
既有产物恢复该次原生进程退出的精确外部原因。报告不得把杀毒软件、Torch、
分页、输入文本或 Windows 原生异常中的任意一项伪写成已证实根因。

可以确定的工程根因是：

1. Runner 在 `finally` 中删除运行目录，删除时机早于 Job 层持久化诊断；
2. 非零退出只传播通用错误，真实退出码和 stderr 丢失；
3. Worker 响应缺少稳定的阶段、活动 query 和已完成 query 进度；
4. Job 失败元数据不保存 Worker 诊断，也没有写入失败完成时间；
5. Windows 启动器与实际 CPython Worker 的身份、存活和终止处理不够明确。

## 4. 输入隔离诊断

使用与 11 记录 PI 完全相同的 11 条 query 构造，单独执行一次 Worker：

- query 数量：11
- query 文本长度范围：100 至 121 字符
- 启动器 PID：`17660`
- 实际 Worker PID：`32560`
- 退出码：`0`
- Windows 状态：`0x00000000`
- 完成进度：`11/11`
- 最后完成 query：`10`
- 向量文件：正常生成
- Worker 耗时：`15.093` 秒

同一请求不经桌面层可以成功，未发现确定性的输入、请求合同或 query 文本异常。
这将 R10 原失败归类为“无法恢复原始证据的不透明瞬时进程退出”，而不是
确定性输入错误。

## 5. 修复设计

### 5.1 Worker 进度与错误合同

Worker 响应新增并持续原子写入：

- `stage`
- `completed_query_count`
- `last_completed_query_id`
- `active_query_id`
- `error_type`
- `error_summary`
- `traceback_summary`

阶段覆盖模型加载、query 编码、向量写入、完成。失败响应继承此前已写入的
query 列表与进度，主入口捕获 `BaseException`，将脱敏错误摘要同时写入响应
和 stderr。

### 5.2 Runner 诊断

每次尝试记录：

- 启动器 PID 与实际 Worker PID；
- 进程返回码与 Windows 十六进制退出状态；
- Worker 是否已确认退出；
- 请求/响应合同版本；
- 失败阶段、已完成 query 数、活动 query；
- stderr/stdout 有界摘要；
- 错误类型、脱敏 traceback 摘要；
- 超时、取消和运行耗时。

Runner 先将诊断聚合并原子持久化到 Job runtime，再清理包含请求、向量和完整
日志的临时 run 目录。完整 stderr、原始向量和本机绝对路径不进入下载 ZIP。

### 5.3 有界重试

只允许以下条件同时成立时重试一次：

- 第一次尝试；
- 退出属于不透明非零退出或 Windows 异常终止；
- 未收到 Python `failed`/`cancelled` 响应；
- 没有错误类型；
- 完成进度为 `0`；
- 前一个实际 Worker 已确认完全退出；
- 不是超时或取消。

Python 异常、中途 query 失败、输出合同错误、超时和取消均不重试。最大尝试
次数为 2，不会同时保留两个实际模型 Worker。

### 5.4 Job 持久化

`JobService` 将聚合后的 `worker_diagnostics` 写入 `job.json` 和公开 Job
响应。失败 Job 同时写入 `completed_at`。字典、正式业务 JSON 和匹配结果
合同不读取该诊断字段。

## 6. 实际修改的 11 个核心文件及原因

以下按“项目交付文件 + 本轮核心诊断/验收脚本”口径列出 11 个实际文件。
其中前 7 项属于项目交付范围；后 4 项位于项目仓库外，只用于一次性取证，
提交前删除，不作为产品代码或构建输入。

| 序号 | 文件 | 修改或创建原因 |
|---:|---|---|
| 1 | `src/bedding_order_parser/materials/query_embedding_runner.py` | 保存退出码、Windows 状态、stderr、阶段和进度；精确收尾实际 Worker；实现一次有界重试 |
| 2 | `src/bedding_order_parser/materials/query_embedding_worker.py` | 增加阶段/query 进度、失败响应、脱敏 traceback 与 stderr 摘要 |
| 3 | `src/bedding_order_parser/materials/hybrid_matcher.py` | 只向 Runner 透传独立诊断文件路径，不改变匹配算法 |
| 4 | `src/bedding_order_parser/web/services.py` | 将 Worker 诊断和失败完成时间持久化到 Job |
| 5 | `tests/materials/test_query_embedding_worker.py` | 覆盖成功、Python 异常、非零退出、一次重试、中途失败、损坏输出、超时、取消和清理 |
| 6 | `tests/web/test_services.py` | 验证失败诊断进入 Job 元数据且错误正常传播 |
| 7 | `docs/reports/GATE_4B_R11_EMBEDDING_WORKER_RECOVERY_REPORT.md` | 保存本轮根因、修复、测试和真实验收证据 |
| 8 | `gate4b_r11_direct_diagnostic.py` | 构造同一 11-query 请求，隔离桌面层直接诊断 Worker |
| 9 | `gate4b_r11_authorized_validation.ps1` | 执行用户授权的一次 11 记录桌面补偿验收及资源监控 |
| 10 | `gate4b_r11_hotel_continuation.ps1` | 执行一次 H Hotel 控制回归及安全阈值监控 |
| 11 | `gate4b_r11_compare_outputs.py` | 使用 Python 标准库核对 JSON 类型及语义差异，排除 PowerShell 哈希/类型误报 |

另有临时 patch、staging 副本及一次失效监控草稿，仅承担补丁传递或过程恢复，
不属于核心实现，不进入 Git；全部在提交前清理。

## 7. 定向测试

测试全部使用 fake adapter，不加载真实 BGE-M3：

| 命令范围 | 结果 |
|---|---:|
| `tests/desktop` | `20 passed` |
| `test_query_embedding_worker.py`、`test_hybrid_matcher.py`、`test_services.py` | `43 passed` |
| 合计 | `63 passed` |

重点验证：

- 正常 Worker 完成；
- Python 异常与 stderr 传播；
- 不透明非零退出最多重试一次；
- 连续非零退出在第二次后明确失败；
- 中途 query 失败不重试；
- 缺失、损坏、shape、dtype、NaN 输出拒绝；
- 启动超时、总超时、取消和精确 PID 清理；
- 运行目录成功或失败后均受控清理；
- Job 保存完整失败诊断；
- 桌面生命周期既有测试不退化。

按任务协议没有运行完整 pytest。

## 8. 11记录PI桌面端验收

- 输入：`data/input/pi/20251231 被套 Proforma Invoice（11行）.xlsx`
- Job：`a5af0df8a02f466a8f3295e4d9b27eb3`
- 最终状态：`completed`
- 业务记录：11
- Job 耗时：`41.828` 秒
- 观察耗时：`42.130` 秒
- Worker 启动器 PID：`37832`
- 实际 Worker PID：`4840`
- 返回码：`0`
- Windows 退出状态：`0x00000000`
- 最终阶段：`completed`
- query 进度：`11/11`
- 最后完成 query：`10`
- 尝试次数：1
- 重试次数：0
- Worker 已确认退出：是
- 同时存活的实际 Worker 最大数量：1
- 安全停止：未触发

资源峰值：

| 指标 | 实际值 | 阈值 | 结果 |
|---|---:|---:|---|
| Worker Private Bytes | `4,095,090,688` bytes | `4 GiB` | 通过 |
| Worker Working Set | `1,984,700,416` bytes | 记录项 | 通过 |
| 父进程 Private Bytes | `5,071,245,312` bytes | `6 GiB` | 通过 |
| 最低可用物理内存 | `4,337 MiB` | `2,048 MiB` | 通过 |
| 系统 Commit 峰值 | `70.6%` | `88%` | 通过 |

产物检查：

- 正式业务 JSON：11 条，逐条严格 20 字段；
- 前 19 字段：全部为字符串；
- 相似分数：全部为 JSON float；
- null：0；
- 业务 JSON：与可靠基线逐值、逐类型完全一致；
- 字典验证：SHA-256 与可靠基线一致；
- 匹配摘要：SHA-256 与可靠基线一致；
- ZIP：5 个条目，损坏条目 0；
- 原始 PI 与受保护资产哈希：前后一致。

验收监控最初把 PowerShell 反序列化后的 `0.0` 类型判定为非 float；使用
Python 标准库读取原始 JSON 后，11 条相似分数均确认是 float。

候选 JSON 与可靠基线有 17 个 `vector_score` 的 float32 末位抖动，最大绝对
差为 `1.1920928955078125e-7`；不存在字符串、结构、候选顺序或非浮点差异，
正式业务 JSON 完全一致。解析诊断只在两个输出绝对路径字段上不同。

## 9. H Hotel 控制回归

- 输入：`3402505MR30022 Proforma Invoice of H Hotel JODC - Dun 20250507.xlsx`
- Job：`e2286871a7c74b9f9094077143632e3f`
- 最终状态：`completed`
- 业务记录：3
- Job 耗时：`16.091` 秒
- Worker 启动器 PID：`17404`
- 实际 Worker PID：`32728`
- 返回码：`0`
- Windows 退出状态：`0x00000000`
- query 进度：`3/3`
- 尝试次数：1
- 重试次数：0
- Worker 已确认退出：是

H Hotel 的正式业务 JSON、候选 JSON 和匹配摘要与可靠基线完全一致；解析
诊断仅输出绝对路径不同。

控制监控脚本沿用了旧的命令行进程计数，把同一逻辑 Worker 的虚拟环境启动器
与实际 CPython 计成 2，记录了 `multiple_embedding_workers`。权威身份由
`response.json.worker_pid` 和父子关系确认，实际只有一个 Worker。取消文件
到达检查点前 Worker 已完成 3/3，Job 最终正常完成。该监控误报不属于产品
Runner；没有因此追加第二次 H Hotel。

11 记录补偿验收结束后桌面已正常关闭。H Hotel 因监控误报在另一桌面快捷方式
会话执行，因此没有满足原始截断提示词中“最终两项同一桌面服务”的偏好，但
满足用户后续授权中“11 条成功后只执行一次 H Hotel”的限制。

## 10. 桌面关闭与残留检查

H Hotel 完成后对标题为“订单解析助手”的窗口发送标准 `WM_CLOSE`，应用走
自身关闭流程：

- 相关 Python/Pythonw 进程：0
- 8000 端口监听：0
- `runtime.json`：已删除
- 残留实际 Worker：无
- 额外 H Hotel 重试：无

## 11. 未修改与未执行事项

- 匹配算法修改：否
- `hybrid_score_v1` 修改：否
- 字段权重修改：否
- FAISS 索引重建：否
- Embedding 模型重建：否
- 正式 20 字段合同修改：否
- 正式解析规则修改：否
- LLM/API 调用：否
- 12 份 PI 回归：否
- 其他 PI：否
- PyInstaller/Onedir/Onefile：否
- 依赖修改：否
- Day01 修改：否
- push/tag/amend：否

## 12. 结论

**Gate 4B-R11：PASS，带一项验收过程偏差说明。**

11 记录 PI 已在当前修复版本中一次完成，Worker 退出码、stderr、失败阶段和
query 进度具备持久化能力，资源未越线，正式结果与可靠基线一致。H Hotel
控制回归也一次完成并与可靠基线一致。原 R10 那次进程异常的精确外部原因因
旧实现已删除证据而保持“未确定”；本轮没有用未经证实的推测替代根因。

唯一偏差是两项最终验收没有处于同一桌面进程会话，原因是补偿监控在 11 条
成功后关闭了桌面，H Hotel 随后通过桌面快捷方式单独启动。该偏差不影响两项
业务结果、Worker 合同或资源结论。
