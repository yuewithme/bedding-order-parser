# Gate 4B-R8D 任务状态持久化报告

## 1. 任务目标

本轮只强化桌面任务状态持久化与重启恢复：

- 保持 `job.json` 原子写入；
- 为 Windows 瞬时文件占用增加有限、可观测重试；
- 让同一 Job 的读取、合并、终态判断和写入串行；
- 在桌面新会话接单前恢复无运行进程支撑的陈旧活动任务；
- 使用曾触发 WinError 5 的 11 记录 PI 执行一次真实桌面验收。

未修改解析器、字典验证、物料匹配、Embedding、FAISS、前端或 20 字段合同。

## 2. Git 基线

- 分支：`master`
- 开始 HEAD：`9c61fce9e95dfb1bfa26f61b97722c4ed27f450d`
- 开始短 HEAD：`9c61fce`
- 最新提交：`test: revalidate embedding worker with sufficient memory`
- 开始工作区：干净
- Git 作者：`小艾 <1746762028@qq.com>`

## 3. 原 job.json 写入调用链

实际调用链位于 `src/bedding_order_parser/web/services.py`：

1. `JobService.create_job()` 创建初始 `queued` 元数据并调用 `_write_job()`。
2. 单 Worker 执行线程通过 `_set_progress()` 写入 `processing` 进度。
3. 桌面主线程通过 `interrupt_active_jobs()` 写入 `interrupted`。
4. `_run_job()` 在业务成功时写入 `completed`，异常时写入 `failed`。
5. `_write_job()` 原先只在最终写入阶段取得单 Job 锁。
6. `_write_json_atomic()` 原先使用同目录唯一 UUID 临时文件、`Path.write_text()` 和 `os.replace()`。
7. `list_jobs()`、`get_job()`、前端轮询和下载通过 `Path.read_text()` / `_read_json()` 短暂读取，读取调用结束即关闭句柄。

原实现的临时文件与 `job.json` 位于同一目录，名称已包含 UUID，也已使用 `os.replace()`；但缺少显式 `flush()`、`os.fsync()` 和 Windows 瞬时占用重试。

## 4. WinError 5 根因分析

现有证据支持两个独立风险：

1. Windows 杀毒、索引或并发读取可能在很短时间内占用目标文件，使 `os.replace()` 抛出 WinError 5、32 或 33。原实现单次失败即终止，没有退避窗口。
2. 原单 Job 锁只包围最终写入。Worker 可以先读取旧 `processing` 快照，桌面线程随后写入 `interrupted`，Worker 再取得锁并把旧快照发布回 `processing`。这解释了终态倒退风险，但不等同于文件句柄占用。

真实验收中应用日志未出现 `WinError 5`、`Access is denied`、最终原子替换失败或重试告警，指定任务正常完成。

## 5. 原子写入重试策略

新增 `src/bedding_order_parser/web/job_persistence.py`：

- 临时文件与目标文件同目录；
- 文件名包含目标文件名、当前 PID、线程 ID 和随机 UUID；
- UTF-8 写入完整 JSON；
- 显式 `flush()`；
- 显式 `os.fsync()`；
- 文件句柄关闭后调用 `os.replace()`；
- 成功后不保留临时文件。

允许重试：

- `PermissionError`；
- WinError 5；
- WinError 32；
- WinError 33。

退避间隔为 `0.05 / 0.10 / 0.20 / 0.40 / 0.80` 秒，即首次尝试后最多重试 5 次，共最多 6 次替换尝试。非瞬时 `OSError` 立即向上抛出，不重试。

最终失败抛出 `AtomicJsonWriteError`，消息只包含目标文件名、尝试次数和异常类型/WinError 编号，不包含用户目录绝对路径。日志同样只记录文件名和脱敏摘要。

## 6. 并发写入保护

`JobService` 继续使用按 Job ID 建立的细粒度锁，没有增加阻塞全部任务的全局状态锁。

本轮把以下操作收进同一 Job 的短临界区：

- 读取当前 `job.json`；
- 判断当前状态是否已经为终态；
- 合并本次状态更新；
- 原子发布完整 JSON。

锁不覆盖 Excel 解析、BGE-M3 推理、FAISS 检索或结果生成全过程。

20 个并发进度更新的定向测试确认：

- 未出现 JSON 损坏；
- 未留下 `.job.json.*.tmp`；
- 没有线程异常；
- 后续终态不会被迟到进度覆盖。

## 7. 终态保护

正式终态集合：

- `completed`
- `failed`
- `interrupted`

`_write_job()` 和 `_update_job()` 均在锁内读取当前状态。当前状态已经是终态时，后续旧 `processing` 进度、完成或失败快照不会改变该终态。

定向测试分别确认 `completed`、`failed`、`interrupted` 均不能倒退到 `processing`。

## 8. 陈旧任务判定规则

活动状态集合：

- `queued`
- `running`
- `processing`

恢复仅在 `desktop_mode=True` 的 `JobService` 初始化阶段执行，且发生在：

1. 桌面单实例锁已经取得之后；
2. 本会话接受新任务之前；
3. Daemon Job Executor 创建之前。

以下记录不恢复：

- 已有终态；
- 当前会话 `_session_job_ids` 中的任务；
- `owner_session_id` 等于当前会话；
- `owner_pid` 对应进程仍存在；
- 缺少 PID 的旧 schema 任务创建时间不足 30 分钟。

普通 `python -m bedding_order_parser.web` 创建的非桌面 `JobService` 不自动恢复历史任务，避免误伤另一个仍运行的 Web 服务。

## 9. 会话与 PID 归属

每个新 `JobService` 生成：

- `session_id`
- 当前进程 `owner_pid`

每个新 Job 内部元数据记录：

- `owner_session_id`
- `owner_pid`

Windows 进程存活检查使用 `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`，不向目标进程发送信号。非 Windows 平台使用 `os.kill(pid, 0)` 的只读存在性语义。

这些内部字段未加入 `public_job()`，不会污染现有公开 API。

## 10. 恢复字段和兼容性

恢复后的内部元数据增加：

- `interruption_reason: application_restarted`
- `previous_status`
- `recovered_at`
- `recovery_session_id`

同时更新：

- `status: interrupted`
- `current_stage: 任务已中断`
- `completed_at`
- `error: 上次运行异常结束，任务已标记为中断，请重新提交。`

兼容旧 schema：

- 缺少 session 字段可以恢复；
- 缺少 owner PID 时采用 30 分钟保守陈旧阈值；
- 损坏 `job.json` 被单独跳过、写入脱敏 warning 和 `recovery_errors`，不会阻止整个服务启动；
- 不删除任务目录、输入、已有 JSON 或局部产物；
- 第二次恢复扫描看到 `interrupted` 后不再改写，保持幂等。

## 11. 实际修改文件

- `src/bedding_order_parser/web/job_persistence.py`
- `src/bedding_order_parser/web/services.py`
- `tests/web/test_job_persistence.py`
- `tests/web/test_services.py`
- `tests/web/test_gate4b_routes.py`
- `docs/reports/GATE_4B_R8D_JOB_STATE_PERSISTENCE_REPORT.md`

未修改 `routes.py`、桌面启动器、HTML、CSS、JavaScript、解析器或匹配模块。

## 12. 定向测试

禁止并未运行完整 pytest。

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests/web/test_job_persistence.py -q` | 6 passed |
| `uv run pytest tests/web/test_services.py -q` | 20 passed |
| `uv run pytest tests/web/test_gate4b_routes.py -q` | 3 passed |
| `uv run pytest tests/web/test_routes.py -q` | 4 passed |
| `uv run pytest tests/desktop/test_server_controller.py -q` | 6 passed |
| 合计 | 39 passed |

覆盖 WinError 5、32、33、有限重试耗尽、非瞬时错误、完整 JSON、旧正式文件保护、临时文件清理、清理异常不掩盖原异常、并发写入、三种终态保护、三种活动状态恢复、三种终态保持、旧 schema、当前会话、活跃 PID、幂等、局部产物、损坏 JSON、历史接口、新任务和桌面服务生命周期。

## 13. 旧 processing 真实恢复结果

- Job ID：`250c6faabfba4925a73c06bc9ea68de3`
- 原状态：`processing`
- 原创建时间：`2026-07-28T17:10:54+08:00`
- 恢复后状态：`interrupted`
- 恢复原因：`application_restarted`
- `previous_status`：`processing`
- 恢复时间：`2026-07-29T14:48:30+08:00`
- 中文摘要：正确
- 历史接口：可读取
- 非元数据局部文件：4 个，仍全部存在
- 任务目录总文件数：恢复前 5 个，恢复后 5 个

第一次恢复后 `job.json` SHA-256：

`6a5d186a14ea5bf4a2cb5193eb06b948a6349ef0c3ab0b2f5327997a2de33be1`

第二次桌面启动后 SHA-256 完全相同，状态仍为 `interrupted`，幂等检查通过。

## 14. 11 记录 PI 真实运行结果

输入：

`data/input/pi/20251231 被套 Proforma Invoice（11行）.xlsx`

- 提交方式：桌面快捷方式启动的同一 HTTP 服务 `/api/jobs`
- 提交次数：1
- 其他 PI：未提交
- Job ID：`d5593dde276847b39a625392f038fc1a`
- 创建时间：`2026-07-29T14:48:30+08:00`
- 完成时间：`2026-07-29T14:48:51+08:00`
- 耗时：`21.325` 秒
- 最终状态：`completed`
- 业务记录：11
- 汇总：高匹配 3、部分匹配 6、冲突 2
- Job error：空
- WinError 5：未出现
- 历史数量：8 增至 9
- 新增活动状态残留：0

## 15. JSON 和 20 字段结果

- 正式业务 JSON：合法，11 条。
- 解析诊断 JSON：合法，11 条。
- 字典验证 JSON：合法，11 条。
- 每条业务记录：严格 20 字段。
- 前 19 字段：全部为字符串。
- 第 20 字段：全部为浮点数。
- `null`：0。

## 16. 与 Gate 2D 一致性

对照基线：

`data/output/gate2d_validation/all_results/20251231 被套 Proforma Invoice（11行）_gate2d.json`

11 条业务记录逐字段、逐类型完全一致，差异为 0。

## 17. 匹配和 ZIP 结果

- `material_match_candidates.json`：合法，`record_count = 11`，records 为 11 条。
- `material_match_summary.json`：合法，`order_records = 11`。
- ZIP：成功生成。
- ZIP 完整性：无坏条目。
- ZIP 内容：正式业务、解析诊断、字典验证、匹配候选、匹配摘要，共 5 个 JSON。

## 18. 内存安全结果

真实运行前：

- 可用物理内存：`6.771 GiB`
- Commit：`53.651%`
- D 盘可用空间：`168.876 GiB`
- 旧桌面/Web/Embedding 进程：无
- 8000 端口监听：无

受控轮询每约 1 秒检查 Worker Private Bytes、系统可用物理内存、Commit 和第二 Worker。任务已完成并进入正常关闭步骤，期间没有触发：

- Worker Private Bytes 超过 4.0 GiB 持续 10 秒；
- Worker Commit/Private Bytes 超过 4.5 GiB；
- 系统可用内存低于 1.25 GiB；
- Commit 达到 90%；
- 第二独立 Worker；
- 电脑明显卡死。

验收辅助脚本在任务完成后的第一次关窗调用中使用了参数名 `$Pid`，与 PowerShell 只读内置变量 `$PID` 冲突，因此未把内存采样列表写入 metrics JSON，精确峰值不可复核。本报告不伪造资源峰值。该错误发生在产品 Job 已 `completed` 之后，不是应用 WinError 5，也未导致重复提交；随后使用实际桌面 PID 完成正常关闭。

## 19. 桌面关闭和残留

第一次桌面：

- 实际业务进程 PID：`268`
- 启动器 PID：`23128`
- `CloseMainWindow()`：成功
- 实际业务进程退出：是
- 启动器退出：是
- 8000 端口释放：是

第二次仅用于幂等检查的桌面：

- 实际业务进程 PID：`38268`
- 未提交 PI
- 首次关闭调用发生在窗口句柄出现前，返回 `False`
- 等待窗口句柄就绪后再次 `CloseMainWindow()`：成功
- 相关进程残留：0
- 8000 端口监听：0
- Worker 残留：无
- `pythonw` 残留：无

## 20. 受保护资产 SHA

输入 PI 当前 SHA-256 与 Job 在解析前记录的 `input_sha256` 完全一致：

`8e7f01815b9d5d4c1109bacc60b457ea8ea32a21fc377e091bfb4b2fee68adbe`

| 资产 | SHA-256 |
| --- | --- |
| `material_master.sqlite3` | `bc590bd08b617588677c9c79db33c5feb03ce5f3ffd11c8b904c1ffb51374e20` |
| `duvet_cover.faiss` | `098a35725b90a3ddc5d762715714cc221e7ed476756f4c516c91df5a384b9ab6` |
| `duvet_cover_mapping.jsonl` | `ee31d7b09c67a2724fbe2c1f433a385b1a63865d47eaa73281dcbef18965a3c1` |
| `vector_index_manifest.json` | `d2e2ef9a4e5af792fc2ce285f7c301924c7a7af4c4bff2d987c1157056f73662` |

以上四项与 Gate 4B-R8C2 前后保护基线一致。

Day01：

- HEAD：`b6206bf28a9ce5499e317cee324b16ea98bf569d`
- 工作区：干净
- 本轮修改：无

## 21. 明确未做事项

- 12 份 PI 串行回归：未运行。
- 完整 pytest：未运行。
- LLM 或外部 API：未调用。
- PyInstaller、Onedir、Onefile：未执行。
- BGE-M3、FAISS、mapping、物料库：未修改或重建。
- 匹配权重、Top 300、硬冲突：未修改。
- parser 业务规则和 20 字段合同：未修改。
- 前端 UI：未修改。
- Day01：未修改。
- amend、tag、push：未执行。

## 22. 最终 Commit

- 计划提交信息：`fix: harden job state persistence`
- 暂存方式：只显式添加本轮生产代码、定向测试和本报告。
- 最终提交哈希：由本报告提交对象确定，并在最终回复中记录。

## 23. 工作区

提交前只允许以下文件：

- `src/bedding_order_parser/web/job_persistence.py`
- `src/bedding_order_parser/web/services.py`
- `tests/web/test_job_persistence.py`
- `tests/web/test_services.py`
- `tests/web/test_gate4b_routes.py`
- `docs/reports/GATE_4B_R8D_JOB_STATE_PERSISTENCE_REPORT.md`

不提交真实任务输出、Job 运行数据、日志、监控脚本、采样文件、API Key 或绝对用户数据路径。

## 24. 下一步唯一建议

真实 11 记录 PI 已成功完成，没有出现 WinError 5；旧 `processing` 已正确且幂等地恢复为 `interrupted`。下一步进入：

**Gate 4B-R9：重新执行 12 份 PI 桌面端串行全量回归。**
