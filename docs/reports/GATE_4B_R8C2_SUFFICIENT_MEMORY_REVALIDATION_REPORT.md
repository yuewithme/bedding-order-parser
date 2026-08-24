# Gate 4B-R8C2 充足内存环境下重新验收隔离 Embedding Worker

## 1. 任务目标

本轮在不修改生产代码和测试代码的前提下，于满足 6 GiB 前置内存门槛的环境中，仅对指定的 3 记录 PI 执行一次桌面端完整受控验收。验收重点为 Windows 逻辑 Worker 身份、BGE-M3 资源峰值、Worker 退出后的内存恢复与 FAISS 加载顺序、业务及匹配结果、桌面关闭后的进程和端口状态。

指定输入：

`data/input/pi/3402505MR30022 Proforma Invoice of H Hotel JODC - Dun 20250507.xlsx`

## 2. Git 基线

- 分支：`master`
- 开始 HEAD：`b11bcdf27e9c9f4e76c2f0e5660e5f630a4d5b4b`
- 开始短 HEAD：`b11bcdf`
- 最新提交：`b11bcdf test: revalidate isolated embedding worker`
- 开始工作区：干净
- 本轮生产代码修改：无
- 本轮测试代码修改：无

## 3. 内存与磁盘前置条件

| 检查点 | 可用物理内存 | Commit 使用率 | D 盘可用空间 | 结论 |
| --- | ---: | ---: | ---: | --- |
| 本轮开始 | 6.138 GiB | 53.907% | 168.899 GiB | 达到 6 GiB 门槛 |
| 26 项定向测试后 | 6.398 GiB | 53.123% | 168 GiB 以上 | 允许真实验收 |
| 正式启动前复核 | 6.702 GiB | 53.098% | 168 GiB 以上 | 允许启动桌面 |

开始前及测试后均未发现项目相关桌面进程、`bedding_order_parser.web`、`query_embedding_worker`、残留项目 `pythonw` 或 8000 端口监听。

## 4. 逻辑 Worker 身份

Windows 虚拟环境启动器与其实际 CPython 子进程按父子关系、同一任务运行目录、同一 `query_embedding_worker` 调用和 `response.json.worker_pid` 合并为一个逻辑 Worker。

- 桌面父业务进程 PID：`30252`
- 虚拟环境启动器 PID：`36504`
- 实际 CPython Worker PID：`36840`
- 权威 Worker 身份来源：`response.json.worker_pid`
- 实际 Worker 的 Parent PID：`36504`
- 启动器与实际 Worker 父子关系：正常
- 逻辑 Worker 数量：`1`
- 真正第二 Worker：未发现

## 5. 定向测试

仅运行了任务允许的三组测试，未运行完整 pytest：

| 测试 | 结果 |
| --- | --- |
| `tests/materials/test_query_embedding_worker.py -q` | 12 passed |
| `tests/materials/test_hybrid_matcher.py -q` | 6 passed |
| `tests/web/test_services.py -q` | 8 passed |
| 合计 | 26 passed |

## 6. 单份 PI 最终状态

- Job ID：`341948288f9744aaab89d8692c393a81`
- 创建时间：`2026-07-29T14:07:50+08:00`
- 完成时间：`2026-07-29T14:08:06+08:00`
- 任务耗时：`16.411` 秒
- 最终状态：`completed`
- 最终进度：`100`
- 业务记录数：`3`
- 汇总：高匹配 2、部分匹配 1、冲突 0
- API 提交次数：1
- 其他 PI 提交次数：0

## 7. 阶段时间

| 阶段 | 时间 |
| --- | --- |
| 桌面启动 | 14:07:49.971 |
| 首页及健康检查完成 | 14:07:50.161 |
| 任务创建 | 14:07:50.314 |
| 文件读取、确定性解析、字典验证、物料匹配阶段进入 | 14:07:52.624 |
| Worker PID 声明 | 14:07:52.634 |
| 启动器识别 | 14:07:53.322 |
| 实际 Worker 最后存活采样 | 14:08:02.780 |
| 监控确认 Worker 与启动器退出 | 14:08:04.418 / 14:08:04.419 |
| FAISS 被父进程加载 | 14:08:04.929 |
| 结果生成及 completed 被观察 | 14:08:06.941 |
| Worker 退出后 3 秒采样 | 14:08:08.258 |
| 任务终态确认 | 14:08:08.307 |
| 任务完成后 3 秒采样 | 14:08:11.313 |

阶段名称来自 0.5 秒任务轮询和约 2 秒资源采样。文件读取、确定性解析、字典验证的细粒度内部完成时刻未由现有 API 单独暴露，因此记录为首次观察到物料匹配阶段的时刻，不伪造更细时间。

## 8. JSON 与 Gate 2D 一致性

三份 JSON 均可由 UTF-8 JSON 解析器正常读取：

- 业务 JSON：3 条记录。
- 解析诊断 JSON：3 条记录。
- 字典验证 JSON：3 条记录。

业务 JSON 每条均为严格 20 字段；前 19 字段均为字符串，第 20 字段为浮点数；无 `null`。与以下 Gate 2D 基线逐字段、逐类型比较完全一致，无差异：

`data/output/gate2d_validation/all_results/3402505MR30022 Proforma Invoice of H Hotel JODC - Dun 20250507_gate2d.json`

## 9. 查询向量合同

运行成功路径对查询向量合同执行了强制校验：

- 预期 shape：`3 x 1024`
- 预期 dtype：`float32`
- 预期归一化：是
- 查询 ID：`0, 1, 2`

`query_embedding_runner.py` 在接受 Worker 结果前要求 `response.json` 状态为 `completed`，并逐项校验 Worker PID、查询 ID、shape、dtype、normalized 和向量文件名；随后以 `allow_pickle=False` 读取向量，并再次校验 `float32`、3 行、1024 维及归一化。任一条件不满足都会抛出 `QueryEmbeddingProcessError`，不会进入 FAISS 检索和结果生成。本次 3 条匹配全部完成并与可靠基线完全一致，因此运行时合同校验通过。

证据边界：外部监控脚本最后复制到的 `response.json` 快照仍处于 `running`，记录了 3 个 query ID 和已完成 2 个 query；最终 `completed` 响应及 `vectors.npy` 在受控运行目录清理前未被文件监视器另存，故没有独立保留向量二进制副本，`vector_contract` 外部采集字段为 `null`。本报告不把该外部采集缺口描述成直接读取到向量文件；合同结论来自生产 Runner 的强制校验路径、任务成功终态和三条匹配基线完全一致三项证据。

## 10. 匹配结果与基线

可靠基线：

`data/output/web/jobs/07042764e463498b866ad90adfc205c5/match-output/`

按 `source_file + sheet + 行号` 对齐后：

| 行号 | 决策 | 候选数 | Top 1 | Top 5 / 可用候选顺序 | 最大分数差 |
| --- | --- | ---: | --- | --- | ---: |
| 22 | `unique_best_candidate` | 2 | `F0903009985` | `F0903009985`, `F0903000771` | 0 |
| 32 | `unique_best_candidate` | 10 | `F0903011753` | `F0903011753`, `F0903028756`, `F0903025644`, `F0903016680`, `F0903028266` | 0 |
| 39 | `insufficient_evidence` | 1 | `F0903000771` | `F0903000771` | 0 |

全部候选编码顺序、`prototype_match_score`、决策状态、候选数量和匹配摘要均与基线一致；浮点差值为 0，满足 `abs(diff) <= 1e-6`。

## 11. ZIP 与历史记录

- ZIP：成功生成，大小 11,800 bytes。
- ZIP 完整性：`ZipFile.testzip()` 无坏条目。
- ZIP 内容：正式业务、解析诊断、字典验证、匹配候选、匹配摘要，共 5 个 JSON。
- 历史记录：由 7 条增至 8 条。
- 本轮新增记录：1 条 `completed`。
- 当前仍有 1 条更早的旧 `processing`：Job `250c6faabfba4925a73c06bc9ea68de3`，创建于 `2026-07-28T17:10:54+08:00`。
- 本轮没有新增 `running` 或 `processing` 残留，也没有修改旧 `processing`。

## 12. 资源峰值

### 启动器

| 指标 | 峰值 |
| --- | ---: |
| Working Set | 4,190,208 bytes / 4.00 MiB |
| Private Working Set | 483,328 bytes / 0.46 MiB |
| Private Bytes | 819,200 bytes / 0.78 MiB |
| Commit Size | 819,200 bytes / 0.78 MiB |

### 实际 CPython Worker

| 指标 | 峰值 |
| --- | ---: |
| Working Set | 1,640,828,928 bytes / 1.528 GiB |
| Private Working Set | 708,448,256 bytes / 675.63 MiB |
| Private Bytes | 4,079,747,072 bytes / 3.800 GiB |
| Commit Size | 4,044,066,816 bytes / 3.766 GiB |
| CPU 时间 | 20.156 秒 |

Worker Private Bytes 未超过 4.0 GiB，Commit Size 未超过 4.5 GiB。

### 桌面父业务进程

| 指标 | 峰值 |
| --- | ---: |
| Working Set | 402,530,304 bytes / 383.88 MiB |
| Private Working Set | 332,173,312 bytes / 316.79 MiB |
| Private Bytes | 5,025,140,736 bytes / 4.680 GiB |
| Commit Size | 4,807,806,976 bytes / 4.478 GiB |
| CPU 时间 | 6.234 秒 |

父进程峰值出现在 Worker 退出后的候选、mapping 与 FAISS 阶段，不能计入 BGE-M3 Worker 峰值。WebView2 单独采样，未计入 Worker 内存。

### 系统

- 运行期间最低可用物理内存：5,289,017,344 bytes / 4.926 GiB。
- 运行期间最高 Commit 使用率：70.503%。
- 最低可用内存高于 1.25 GiB 安全线。
- Commit 使用率低于 90% 安全线。

## 13. Worker 退出与内存恢复

Worker 最后存活采样时系统可用物理内存为 5,289,017,344 bytes。Worker 退出后 3 秒采样为 6,849,564,672 bytes，恢复 1,560,547,328 bytes，约 1.453 GiB。实际 Worker 和启动器均正常退出。

## 14. FAISS 加载顺序

- Worker 存活期间父进程未加载 Torch/BGE-M3。
- Worker 存活期间未观察到父进程加载 FAISS。
- Worker 最后存活采样：14:08:02.780。
- FAISS 首次观察：14:08:04.929。
- 监控事件记录 FAISS 位于 Worker 退出后约 2.149 秒。
- FAISS、mapping、候选检索、hybrid 排名和结果输出均成功。

结论：FAISS 在实际 Worker 退出后由父进程加载，未与 BGE-M3 Worker 峰值叠加。

## 15. 安全停止与电脑响应

- 安全停止触发：否。
- Worker Private Bytes 超线：否。
- Worker Commit Size 超线：否。
- 系统低内存超线：否。
- Commit 超线：否。
- 第二 Worker：否。
- 父进程提前加载 FAISS：否。
- 父进程重复加载 BGE-M3：否。
- 电脑明显卡顿：未观察到。
- 桌面失去响应：未观察到。

## 16. 桌面关闭与残留

- 通过桌面快捷方式启动。
- 本地 URL：`http://127.0.0.1:8000`。
- `/health` 与首页可访问。
- 启动阶段重模块：未发现 BGE-M3、Torch、FAISS、mapping 或全量候选加载。
- 桌面关闭请求：成功。
- 桌面父进程退出：成功。
- 8000 端口释放：是。
- 残留实际 Worker：无。
- 残留启动器：无。
- 残留项目 `pythonw`：无。
- 本次任务 `runtime/embedding` 目录为空，无临时响应、向量或日志文件。

窗口标题在启动后的脚本采样中返回空字符串，因此没有可复核的标题文本证据；这不影响首页、健康检查、任务执行和窗口生命周期结论。

## 17. 文件保护

原 PI SHA-256 前后一致：

`e005dc8f5f3b17e4e1175e902a1a1417883700c90173f3e9abb1fec9a33c9bab`

受保护物料资产 SHA-256 前后一致：

| 资产 | SHA-256 |
| --- | --- |
| `material_master.sqlite3` | `bc590bd08b617588677c9c79db33c5feb03ce5f3ffd11c8b904c1ffb51374e20` |
| `duvet_cover.faiss` | `098a35725b90a3ddc5d762715714cc221e7ed476756f4c516c91df5a384b9ab6` |
| `duvet_cover_mapping.jsonl` | `ee31d7b09c67a2724fbe2c1f433a385b1a63865d47eaa73281dcbef18965a3c1` |
| `vector_index_manifest.json` | `d2e2ef9a4e5af792fc2ce285f7c301924c7a7af4c4bff2d987c1157056f73662` |

Day01 HEAD 前后均为 `b6206bf28a9ce5499e317cee324b16ea98bf569d`，工作区前后均干净。

## 18. 明确未做事项

- WinError 5：未修复。
- 旧 `processing` 恢复规则：未修复。
- 12 份 PI 回归：未运行。
- LLM 或外部 API：未调用。
- PyInstaller、Onedir、Onefile：未执行。
- FAISS、Embedding、mapping、manifest：未重建。
- 权重、Top 300、硬冲突、模型 revision、dtype：未修改。
- Day01：未修改。
- Push、tag、amend：未执行。

## 19. Git 提交与工作区

- 本轮唯一交付文件：`docs/reports/GATE_4B_R8C2_SUFFICIENT_MEMORY_REVALIDATION_REPORT.md`
- 计划提交信息：`test: revalidate embedding worker with sufficient memory`
- 提交方式：仅显式暂存本报告；不使用 `git add .`
- 最终提交哈希：由本报告提交对象确定，并在最终回复中记录。

## 20. 结论

本次指定 3 记录 PI 在充足内存环境下完成一次且仅一次桌面端受控验收。逻辑 Worker 身份明确，实际 Worker 的 Private Bytes 和 Commit Size 均未触发安全红线；Worker 退出后系统可用内存恢复约 1.453 GiB，FAISS 随后才由父进程加载。业务 JSON、匹配候选及摘要与可靠基线完全一致，ZIP 和历史记录均生成，桌面关闭后无进程或端口残留。

外部监控未在临时运行目录清理前保留最终向量文件副本，这是本次证据采集限制；生产 Runner 的强制合同校验、成功终态和三条匹配基线一致共同证明运行时向量合同通过。该限制不要求修改生产代码，可在后续专门监控审计中通过更可靠的完成事件捕获改善。

## 21. 下一步唯一建议

进入 **Gate 4B-R8D：修复 `job.json` 瞬时 WinError 5 和旧 `processing` 恢复规则**。本次隔离 Worker 的单份真实 PI 验收已通过且资源安全，当前明确遗留的生产问题是旧 `processing` 状态恢复与瞬时文件访问异常。
