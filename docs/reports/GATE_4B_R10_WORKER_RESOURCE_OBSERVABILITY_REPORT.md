# Gate 4B-R10：Worker资源可观测性验收报告

## 1. 任务目标

本轮仅修正临时验收监控对桌面Job根目录的定位，并计划在同一个桌面会话内严格串行运行三份代表性PI，取得`response.json`声明的实际CPython Worker身份、资源峰值和阶段顺序。

本轮未修改生产代码或测试代码，未直接调用`parse_order`或`match_orders`。

## 2. Git基线

- 仓库：`D:\AI-Learning\Projects\bedding-order-parser`
- 分支：`master`
- 初始HEAD：`6a0cb905ae11a80e354e7940be1e70783a48f79b`
- 初始短HEAD：`6a0cb90`
- 最新提交：`test: complete desktop regression across 12 pis`
- 初始工作区：干净
- Day01 HEAD：`b6206bf28a9ce5499e317cee324b16ea98bf569d`
- Day01工作区：干净

运行前门槛最终复核：

- 可用物理内存：6,655 MiB，满足至少6 GiB。
- Commit：53%，低于75%。
- D盘剩余：约168.84 GiB。
- 旧桌面/Web/Embedding进程：0。
- 8000端口监听：0。
- `runtime.json`：不存在。

## 3. R9观测缺口

R9错误地在项目默认目录`data/output/web/jobs`中寻找桌面Worker的`response.json`。桌面模式实际使用LocalAppData任务目录，导致R9没有保留实际CPython Worker PID和峰值。

R10已修正该路径，成功取得两份已提交任务的实际Worker PID、启动器PID、父子关系、命令行、run目录、查询进度和资源峰值。

## 4. 正确桌面Job根目录

实际根目录由系统API计算，没有硬编码用户名：

```text
[Environment]::GetFolderPath("LocalApplicationData")
→ <LocalApplicationData>\BeddingOrderParser\tasks\jobs
```

本次实际值：

```text
C:\Users\alyar\AppData\Local\BeddingOrderParser\tasks\jobs
```

代码证据链：

1. `local_app_root()`从`LOCALAPPDATA`构造应用根目录；
2. `resolve_application_paths()`默认令`task_root = app_root / "tasks"`；
3. `ServerController`创建`JobService(root=paths.task_root)`；
4. `JobService`在其root下使用`jobs/<Job ID>`；
5. 桌面API返回的Job ID与实际目录中的`job.json.id`一致。

## 5. 监控脚本路径定位方法

临时监控脚本位于Windows TEMP，不进入Git。启动前PowerShell解析器结果：

- 语法错误：0。
- 禁用变量`$PID/$Pid/$pid`：0。
- TEMP复制前后SHA-256一致。

每次API提交后，脚本执行：

1. 读取API返回的唯一Job ID；
2. 组合`<desktop job root>\<Job ID>`；
3. 等待该目录及`job.json`实际出现；
4. 验证`job.json.id`与API Job ID一致；
5. 锁定`runtime\embedding\run-*`；
6. 读取该run目录中的`response.json`；
7. 以`response.worker_pid`作为实际Worker唯一权威身份；
8. 确认项目默认`data/output/web/jobs/<Job ID>`不存在。

## 6. 三份PI清单

固定计划顺序：

| 序号 | 用途 | 文件 | 预期记录 |
| ---: | --- | --- | ---: |
| 1 | 最大记录数 | `20251231 被套 Proforma Invoice（11行）.xlsx` | 11 |
| 2 | 已有Worker及匹配基线 | `3402505MR30022 Proforma Invoice of H Hotel JODC - Dun 20250507.xlsx` | 3 |
| 3 | 最大文件 | `3402511MG20056 Proforma Invoice - Welllife PO 1031.2025.xlsx` | 3 |

实际提交2份。第1份真实失败；第2份完成但监控触发安全停止；第3份按协议未提交。没有重试。

## 7. 三份任务结果

| 序号 | Job ID | 状态 | Job耗时 | Job记录 | 结果 |
| ---: | --- | --- | ---: | ---: | --- |
| 1 | `6a5eb6c87f2f44b4ab53174dff7013f0` | `failed` | 28.663秒 | 0 | Worker在0/11查询完成时异常退出，错误为`Embedding worker exited with an error.` |
| 2 | `9da8046d91674703b87a6d52383a3817` | `completed` | 15.885秒 | 3 | 三份核心JSON、匹配输出和ZIP完整 |
| 3 | 未创建 | 未执行 | N/O | N/O | 安全停止后未提交 |

第一份API提交至观察到失败终态为34.937秒。其确定性解析、诊断和字典验证已生成11条，但匹配候选、匹配摘要和ZIP未生成，因此不能算完成。

## 8. 三份阶段耗时

| 阶段 | 11记录PI | H Hotel | Welllife |
| --- | ---: | ---: | ---: |
| API提交至Job终态 | 34.937秒（外部观察） | 15.885秒（Job内部） | N/O |
| Worker声明至退出 | 17.558秒 | 13.491秒 | N/O |
| Worker内部报告 | 未生成completed响应 | 11.468102秒 | N/O |
| Worker退出至FAISS加载 | N/O | N/O | N/O |
| FAISS及匹配 | 未进入 | N/O | N/O |
| 结果发布 | 未进入 | N/O | N/O |

H Hotel的匹配和发布均实际完成，但监控在安全事件处停止了细分采样，因此不猜测耗时。

## 9. 三份启动器与实际Worker PID

| PI | 桌面父PID | 启动器PID | 实际Worker PID | run目录 |
| --- | ---: | ---: | ---: | --- |
| 11记录PI | 38152 | 25552 | 29136 | `...\6a5eb6c87f2f44b4ab53174dff7013f0\runtime\embedding\run-5rcqdhsq` |
| H Hotel | 38152 | 39212 | 4748 | `...\9da8046d91674703b87a6d52383a3817\runtime\embedding\run-tr4m383n` |
| Welllife | N/O | N/O | N/O | 未提交 |

两个实际Worker PID均来自对应`response.json`，不是根据进程名猜测。

## 10. Worker父子关系

两次均确认：

```text
桌面业务进程
→ .venv\Scripts\python.exe 启动器
→ Python312\python.exe 实际Worker
```

- Worker的Parent PID等于记录的启动器PID：是。
- 启动器的Parent PID等于桌面业务PID：是。
- 启动器与Worker命令行均引用同一Job ID和同一run目录：是。
- 第二个独立Worker：未发现。

启动器和实际CPython是一个逻辑Worker，没有因两个`python.exe`误判为并发Worker。

## 11. 三份Worker资源峰值

| 指标 | 11记录Worker | H Hotel Worker | Welllife Worker |
| --- | ---: | ---: | ---: |
| Working Set峰值 | 1,633,353,728 bytes | 1,632,841,728 bytes | N/O |
| Private Working Set峰值 | 536,100,864 bytes | 709,787,648 bytes | N/O |
| Private Bytes峰值 | 4,060,016,640 bytes（3.781 GiB） | 3,825,352,704 bytes（3.563 GiB） | N/O |
| Commit Size峰值 | 4,060,016,640 bytes（3.781 GiB） | 3,825,352,704 bytes（3.563 GiB） | N/O |
| CPU时间峰值 | 21.734375秒 | 10.40625秒 | N/O |
| 实际Worker资源样本 | 6 | 6 | 0 |

两次已观测峰值均低于4.0 GiB Private Bytes和4.5 GiB Commit安全线。第一份仍在首次查询完成前异常退出，说明本次失败不能由已采样到的安全阈值超线直接解释。

## 12. 父进程资源变化

| 指标 | 11记录PI | H Hotel |
| --- | ---: | ---: |
| 任务前Private Bytes | 656,011,264 bytes | 2,886,287,360 bytes |
| 任务期间已采样峰值 | 1,892,098,048 bytes | 至少6,260,473,856 bytes |
| Worker退出附近 | 1,890,725,888 bytes | 6,254,714,880 bytes |
| 稳定值 | 1,890,590,720 bytes | 6,260,473,856 bytes（5.830 GiB） |
| 稳定Working Set | 1,394,683,904 bytes | 1,594,986,496 bytes |
| CPU增量 | 41.156秒 | 4.016秒 |

H Hotel后父进程稳定Private Bytes低于6 GiB阻断线，但仅余约174 MiB裕量。由于第三份未运行，本轮不能验证继续处理最大文件时的父进程安全裕量。

## 13. 系统资源最低/峰值

| 指标 | 11记录PI | H Hotel | 全轮 |
| --- | ---: | ---: | ---: |
| 最低可用物理内存 | 3,390 MiB | 3,529 MiB | 3,390 MiB |
| Commit峰值 | 73% | 74% | 74% |
| CPU峰值 | 68% | 23% | 68% |
| D盘最低剩余 | 168.832 GiB | 168.837 GiB | 168.832 GiB |

系统没有低于1.25 GiB，没有达到90% Commit，也没有出现95% CPU持续60秒。

WebView2按桌面进程子树独立统计，不计入Worker。两份任务的WebView2 Private Bytes峰值分别为191,688,704和191,315,968 bytes。

## 14. Worker退出和FAISS加载顺序

11记录PI在Embedding Worker阶段失败，没有进入FAISS。

H Hotel的`response.json`在16:38:30.969 UTC写出completed，监控在16:38:31.848观察到completed响应、启动器退出和FAISS模块。实际Worker PID在本轮轮询的下一周期16:38:33.608才被确认不可枚举，因此脚本触发“FAISS早于Worker退出”安全停止。

该事件不能直接判为产品顺序违规：

1. 同一监控循环先采Worker、后采启动器和模块，存在约1.76秒非原子观察窗口；
2. 生产代码要求`encode_queries_isolated()`返回后才调用`load_all_material_candidates()`和FAISS加载；
3. `encode_queries_isolated()`又要求其Popen启动器已经退出；
4. H Hotel最终匹配输出完整且基线一致。

结论：H Hotel的严格“实际PID消失早于FAISS”外部时间顺序为`N/O`，本次安全事件属于监控竞态假阳性；报告不把负间隔作为产品问题，也不伪造通过。

## 15. JSON与20字段

11记录PI虽然Job失败，但确定性阶段留下：

- 业务JSON：11条；
- 解析诊断JSON：11条；
- 字典验证JSON：11条；
- 严格20字段：通过；
- 前19字段字符串：通过；
- 相似分数float：通过；
- `null`：0。

H Hotel：

- 三份核心JSON：各3条；
- 严格20字段：通过；
- `null`：0；
- 匹配候选和匹配摘要：合法。

全轮任务结果仍不完整，因为第一份没有匹配产物和ZIP，第三份未执行。

## 16. Gate 2D差异

对两份已产生业务JSON的14条记录比较18个确定性字段：

- 可比较记录：14。
- 差异记录：0。
- 字段差异：0。

## 17. H Hotel匹配基线差异

可靠基线：

`data/output/web/jobs/07042764e463498b866ad90adfc205c5/match-output`

比较Top 1、完整候选顺序、`prototype_match_score`、决策状态、候选数量和摘要：

- 可比较记录：3。
- 差异：0。
- 最大浮点差：0。
- 匹配摘要：完全一致。

一致性不代表业务准确率。

## 18. ZIP与历史记录

- H Hotel ZIP：存在，5份JSON，无坏条目。
- 11记录PI ZIP：未生成。
- Welllife ZIP：未执行。
- 初始历史Job：22。
- 最终历史Job：24。
- 新增Job：2，恰好对应两次提交。
- 新增活动状态残留：0。
- 11记录Job：`failed`。
- H Hotel Job：`completed`。
- 未删除历史任务。

三份输入文件和SQLite、FAISS、mapping、manifest的SHA-256前后一致。

## 19. 安全停止和电脑响应

- Worker Private Bytes持续超4.0 GiB：否。
- Worker Commit超4.5 GiB：否。
- 父进程Private Bytes超6 GiB：否。
- 系统可用内存低于1.25 GiB：否。
- Commit达到90%：否。
- CPU达到持续阈值：否。
- Worker超5分钟：否。
- 任务超10分钟：否。
- 真正第二Worker：否。
- 电脑明显卡顿：未观察到。
- 桌面失去响应：未观察到。
- 监控安全停止：是，原因是H Hotel的FAISS/实际PID非原子观察竞态。
- 第三份提交：否。

第一份真实失败发生在安全阈值内，是本轮需要后续处理的唯一产品问题。

## 20. 桌面关闭与残留

- 桌面会话启动次数：1。
- 正常关闭请求：成功。
- 桌面业务进程：已退出。
- `runtime.json`：已清理。
- 8000端口：已释放。
- 残留Embedding Worker：无。
- 残留启动器：无。
- 残留pythonw：无。
- 新增running/processing：0。

## 21. 是否达到LLM接入前稳定条件

**未达到。**

三份PI只提交2份，仅1份completed；11记录PI的实际Worker在0/11查询完成时异常退出；第三份未执行；三次Worker峰值、三次正常退出和三次FAISS顺序均未满足成功条件。

## 22. 未执行事项

- 生产代码修改：否
- 测试代码修改：否
- pytest：否
- Playwright：否
- LLM/API：否
- PyInstaller：否
- Onedir：否
- Onefile：否
- 匹配算法修改：否
- 权重/Top 300/硬冲突修改：否
- Day01修改：否
- 失败PI重试：否
- 第三份PI提交：否

## 23. Git提交

本轮只提交：

`docs/reports/GATE_4B_R10_WORKER_RESOURCE_OBSERVABILITY_REPORT.md`

提交信息：

`test: verify embedding worker resource isolation`

临时监控脚本、原始采样、分析JSON、日志和Job数据不提交。

## 24. 工作区

提交前后将核对`git diff --check`、变更范围和最终工作区。生产代码、测试、依赖文件和Day01均保持不变。

## 25. 下一步唯一建议

**Gate 4B-R11：只修复11记录PI的短生命周期Embedding Worker异常退出问题。**

处理边界：

- 复现并保留该Worker的真实退出码、stderr和失败响应；
- 找到0/11查询阶段退出的具体根因；
- 只修复这一项Worker可靠性问题；
- 不修改解析、字典、FAISS、匹配算法、权重、Top 300或20字段合同；
- 不把本轮FAISS监控竞态误判为产品顺序问题。
