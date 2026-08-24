# Gate 4B-R8C Worker 身份重新验收报告

## 1. 任务目标

本轮计划在不修改生产匹配逻辑的前提下，将 Windows 虚拟环境
`python.exe` 重定向启动器与其实际 CPython 子进程归并为一个逻辑
Embedding worker，并重新执行一次指定的 3 记录 PI 受控验收。

开始前环境检查发现系统可用物理内存低于协议要求的 6 GiB，因此本轮按
安全规则停止在真实模型启动前。没有启动桌面，没有提交 PI，没有加载
BGE-M3、Torch、FAISS、mapping 或全量候选。

## 2. Git 基线

- 仓库：`D:\AI-Learning\Projects\bedding-order-parser`
- 分支：`master`
- 初始 HEAD：`28240b7edcb2ea16598912aaab4e7a32ba70276d`
- 初始短 HEAD：`28240b7`
- 最新提交：`fix: isolate query embedding memory`
- 初始工作区：干净

## 3. R8B 失败原因

R8B 的外部验收监控以命令行匹配进程数量判断 worker 数量，把同一逻辑
worker 的虚拟环境重定向启动器 PID `39308` 与实际 CPython PID `39276`
误判为两个独立 worker，触发 `second_embedding_worker` 假阳性。

该结果没有证明 BGE-M3 内存超限，也没有完成向量、FAISS、匹配和 ZIP
验收。

## 4. 修正后的逻辑 Worker 身份规则

后续受控验收必须采用以下身份顺序：

1. 从当前任务唯一的 `response.json` 读取 `worker_pid`；
2. 该 PID 是唯一权威的实际 CPython worker；
3. 向上检查其父进程是否为同一任务命令、同一虚拟环境
   `Scripts\python.exe` 启动器；
4. 将“一个启动器 PID + 一个响应声明的实际 PID”归并为一个逻辑
   worker；
5. 只有出现第二个响应声明 PID、不同任务目录、不同父子链或无法归组的
   第三个业务进程时，才能判定真正第二 worker；
6. 同名进程数、Python 进程数或命令行匹配数不得单独触发安全停止。

## 5. 启动器 PID

本轮真实验收未执行，启动器 PID：`not_created`。

## 6. 实际 worker_pid

本轮未创建 worker 响应文件，实际 `worker_pid`：`not_created`。

## 7. 两者父子关系

本轮没有进程链可供动态验证：`not_observed`。

身份归并规则已按第 4 节明确，但不能用 R8B 的旧 PID 代替本轮动态证据。

## 8. 是否存在真正第二 Worker

开始前相关 `query_embedding_worker` 进程数为 0。本轮未启动 worker，
因此不存在真正第二 worker。

## 9. 定向测试结果

只运行 R8B 直接相关的既有 fake 测试，未运行完整 pytest，未修改测试：

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests/materials/test_query_embedding_worker.py -q` | `12 passed in 3.49s` |
| `uv run pytest tests/materials/test_hybrid_matcher.py -q` | `6 passed in 0.89s` |
| `uv run pytest tests/web/test_services.py -q` | `8 passed in 0.74s` |

合计：`26 passed`。

## 10. 单份 PI 最终状态

指定文件未提交：

`data/input/pi/3402505MR30022 Proforma Invoice of H Hotel JODC - Dun 20250507.xlsx`

最终状态：`not_run_environment_blocked`。

阻断证据：

- 第一次开始前检查：可用物理内存 `5.635 GiB`；
- 定向测试后复核：可用物理内存 `5.600 GiB`；
- 协议最低运行条件：`6 GiB`。

两次独立读数均低于门槛，因此没有通过等待瞬时波动或关闭用户程序规避
安全条件。

## 11. 任务各阶段耗时

没有创建任务，以下阶段均为 `not_run`：

- 文件读取；
- 确定性解析；
- 字典验证；
- worker 启动和模型加载；
- query 1、2、3；
- 候选、FAISS、mapping；
- Top 300 和 hybrid 排名；
- 结果与 ZIP 生成。

## 12. 业务 JSON 和 Gate 2D 一致性

本轮没有生成新的业务 JSON，无法产生本轮一致性证据：`not_run`。

没有修改既有 Gate 2D 业务基线。

## 13. 查询向量合同

本轮没有生成查询向量，shape、dtype 和归一化动态证据均为 `not_run`。

R8B 既有 fake 测试继续验证 `3 x 1024` 合同所依赖的 runner/worker
机制，但测试结果不冒充真实模型证据。

## 14. 匹配结果和基线一致性

没有生成匹配候选、Top 5、匹配摘要或 ZIP，因此与既有同 PI 匹配基线：
`not_compared`。

## 15. 启动器资源峰值

启动器未创建，资源峰值：`not_available`。

## 16. 实际 Worker 资源峰值

实际 worker 未创建，Working Set、Private Working Set、Private Bytes、
Commit Size 和 CPU 峰值均为 `not_available`。

## 17. 父业务进程资源峰值

桌面父业务进程未启动，资源峰值：`not_available`。

## 18. 系统可用内存最低值

本轮两次记录中的最低值为 `5.600 GiB`。

该值低于 6 GiB 前置门槛，但高于运行中 1.25 GiB 紧急停止红线。由于
真实运行未开始，1.25 GiB 红线不适用。

## 19. Commit 百分比峰值

真实验收未运行，没有采集连续 Commit 序列：`not_available`。

## 20. Worker 退出后的内存恢复

worker 未启动，无法测量退出后 3 秒的内存恢复：`not_available`。

## 21. FAISS 加载是否发生在 Worker 退出后

FAISS 未加载：`not_reached`。

不能把 R8B 的代码顺序测试替代为本轮动态“是”。

## 22. 安全停止情况

没有触发运行中 worker 安全停止。真实运行被**开始前环境门槛**阻止：

`available_physical_memory_below_6_gib`

因此没有协作取消、精确 PID 终止或任务重试。

## 23. 电脑卡顿情况

未观察到电脑或桌面卡顿。没有启动真实模型。

## 24. 桌面关闭和残留

开始前与结束前均确认：

- `bedding_order_parser.desktop`：0；
- `bedding_order_parser.web`：0；
- `query_embedding_worker`：0；
- 8000 端口监听：无；
- `runtime.json`：无。

发现两个历史任务的 `runtime\embedding` 空根目录，两个目录的
`ChildCount` 均为 0；不存在 `run-*`、request、response、向量或日志
残留。空根目录不是运行中的 worker 临时目录，本轮没有删除历史任务目录。

## 25. 未修复的 WinError 5

本轮没有修改或验证 `job.json` 瞬时 WinError 5。

## 26. 未处理的旧 Processing

本轮没有修改旧 `processing` 恢复规则，也没有清理历史任务。

## 27. 未运行的 12 份回归、LLM 和打包

- 12 份 PI 回归：未运行；
- LLM/API：未调用；
- PyInstaller：未执行；
- Onedir/Onefile：未构建；
- FAISS：未重建；
- Day01：未修改；
- 生产代码和测试代码：未修改。

## 28. Git 提交

- 允许提交文件仅为本报告；
- 提交信息：`test: revalidate isolated embedding worker`；
- Commit：本报告所在提交，完整哈希以提交后 `git rev-parse HEAD`
  为准。

## 29. 工作区

提交前工作区只允许新增：

`docs/reports/GATE_4B_R8C_WORKER_IDENTITY_REVALIDATION_REPORT.md`

最终状态以提交后 Git 检查为准。

## 30. 下一步唯一建议

本轮未满足 A（完整成功且内存安全）、B（实际 worker 触发红线）或
C（发现生产代码阻断）的任何条件；阻断发生在真实运行前的主机资源门槛。

唯一建议：不要进入 Gate 4B-R8D。先在系统可用物理内存稳定达到
`>= 6 GiB` 后，重新执行 Gate 4B-R8C 的同一份 PI 单次受控验收，并使用
第 4 节逻辑 worker 身份规则。不得因本报告切换模型、重建索引或修复
无关代码。
