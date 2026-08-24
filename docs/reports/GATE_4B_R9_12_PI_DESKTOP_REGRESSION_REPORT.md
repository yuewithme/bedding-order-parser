# Gate 4B-R9：12份PI桌面端串行全量回归与性能验收

## 1. 任务目标与执行边界

本轮通过桌面快捷方式启动一个桌面应用会话，按文件名不区分大小写升序，串行提交正式目录中的12份PI。每个任务均通过同一桌面实例的`/api/jobs`提交，没有并行、预排队或失败重试；任务终态后等待至少5秒再提交下一份。

本轮只执行真实桌面回归、输出校验、资源观察和报告。未修改生产代码、测试、解析规则、字典、物料主数据、Embedding隔离、BGE-M3、FAISS、mapping、Top 300、评分权重、硬冲突、20字段合同、前端或Day01；未运行pytest、Playwright、PyInstaller、Onedir、Onefile、LLM或外部API。

## 2. Git基线

- 仓库：`D:\AI-Learning\Projects\bedding-order-parser`
- 分支：`master`
- 初始HEAD：`d6a572d15a703d9fa4c02bb43dba9bcc0934d7db`
- 初始短HEAD：`d6a572d`
- 最新提交：`fix: harden job state persistence`
- 初始工作区：干净
- Day01 HEAD：`b6206bf28a9ce5499e317cee324b16ea98bf569d`
- Day01工作区：干净

## 3. 正式12份PI清单、大小和SHA

统计口径为运行前原始文件字节数和SHA-256；运行后重新计算，12份均完全一致。

| 序号 | 文件名 | 字节数 | SHA-256 |
| ---: | --- | ---: | --- |
| 1 | `20251231 被套 Proforma Invoice（11行）.xlsx` | 15,121 | `8e7f01815b9d5d4c1109bacc60b457ea8ea32a21fc377e091bfb4b2fee68adbe` |
| 2 | `3402505MR30022 Proforma Invoice of H Hotel JODC - Dun 20250507.xlsx` | 105,053 | `e005dc8f5f3b17e4e1175e902a1a1417883700c90173f3e9abb1fec9a33c9bab` |
| 3 | `3402510MG10094 Canasin Proforma Invoice-Blooming_Caption by Hyatt KABUTOCHO-Oct.26.2025 V2.xlsx` | 58,848 | `b009aa358c6d9b48cad4bf2d51b127dfeb93afe8375f560595ffc70e07d1de3d` |
| 4 | `3402510MG10095 Canasin Proforma Invoice-Annupuri Garden 2-Sep.23.2025 V4.xlsx` | 70,826 | `af9ba46a2f99d33ffdbc97b8feeb1874466450a31161a91369cc2dcd138a58a2` |
| 5 | `3402510MH40078  Proforma Invoice for Okura 20251020.xlsx` | 22,230 | `3136771697215e16a9631196c28a556533c179b1ce21296a80324e891b12dc3b` |
| 6 | `3402510MH40090 Proforma Invoice【Ease Hotel】- Canasin 20251023.xlsx` | 32,640 | `29cf074273436627c73c22a93a2e2064f02b905c913faba84662f1bf0ad93edf` |
| 7 | `3402510MH90180.xlsx` | 61,378 | `fbda2707b05ab1568bbf49df06afbdf95431ad128b7b3403fa83a9395a14ac34` |
| 8 | `3402510MR30051 Proforma Invoice of Double Tree Jeddah - 20251002.xlsx` | 102,129 | `1f7108bd387f1b99a48d5e2dbaa512cdeafaabc858db2a895859ec11aedfb599` |
| 9 | `3402511MG20056 Proforma Invoice - Welllife PO 1031.2025.xlsx` | 12,189,302 | `e91b6b38d107525b5c9efe426cd7cecd481275cb49d3932b981dfc0e0ba905f3` |
| 10 | `3402511MH30095.xlsx` | 3,988,910 | `6d2beb4bc7e36c07cd1202d07cae9414f1f1fdfdf056b506416a2c8451acd9b2` |
| 11 | `3402511MW30039 Canasin Invoice for MAK LLC Bayarsuren Natsagdorj Makotel project 20250915.xlsx` | 829,058 | `cbca657d309d039cde5a4a015e5fa585e2a0d4507590adbd248a2a3d5cbe74e9` |
| 12 | `3402511MW90145 DW PI-  Canasin 20251030.xlsx` | 1,694,576 | `eef3025c305dae55f7b5cac362b3e43dea75b3be51c87792735309507acc7985` |

## 4. 运行前环境

- 可用物理内存：6,688 MiB（6.531 GiB），满足最低6 GiB。
- Commit：53%，低于75%启动门槛。
- D盘剩余：约168.85 GiB，超过10 GiB。
- 旧桌面/Web/Embedding相关进程：0。
- 8000端口监听：0。
- `runtime.json`：不存在。
- 启动前Torch、BGE-M3、FAISS：未加载。

受保护物料资产运行前后SHA-256一致：

| 资产 | SHA-256 |
| --- | --- |
| `material_master.sqlite3` | `bc590bd08b617588677c9c79db33c5feb03ce5f3ffd11c8b904c1ffb51374e20` |
| `duvet_cover.faiss` | `098a35725b90a3ddc5d762715714cc221e7ed476756f4c516c91df5a384b9ab6` |
| `duvet_cover_mapping.jsonl` | `ee31d7b09c67a2724fbe2c1f433a385b1a63865d47eaa73281dcbef18965a3c1` |
| `vector_index_manifest.json` | `d2e2ef9a4e5af792fc2ce285f7c301924c7a7af4c4bff2d987c1157056f73662` |

## 5. 桌面启动结果

- 启动方式：桌面快捷方式`订单解析助手.lnk`。
- 桌面冷启动到健康且窗口可见：2.846秒。
- 应用内部报告启动：0.049秒。
- URL：`http://127.0.0.1:8000`。
- 桌面业务PID：`39576`。
- 启动器PID：`37596`。
- 启动后父进程Private Bytes：590,372,864 bytes。
- 启动后模块检查：Torch=false，FAISS=false。
- mapping与全量MaterialCandidate没有可直接由模块列表观测的标识；生产调用顺序仍只在进入匹配后加载。

## 6. 12份PI逐项结果表

`总耗时`为API提交到观察到终态的外部耗时。`N/O`表示当前API或本轮监控未能可靠分离，未写成0。第2份观察到确定性解析及字典验证组合阶段1.662秒；第3至12份首次processing采样已到70%，不能安全拆分。Worker、Worker退出至FAISS、FAISS与匹配、发布阶段因第19节所述监控路径问题均未取得逐份可靠值。

| # | PI文件 | 大小 | 记录 | 总耗时(s) | 确定性组合 | Worker | Worker→FAISS | FAISS/匹配 | 发布 | 状态 | 推荐 | 无候选 | Worker峰值 | 父进程后Private | 最低可用内存 | 输出字节 | 备注 |
| ---: | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- | ---: | --- |
| 1 | `20251231 被套 Proforma Invoice（11行）.xlsx` | 15,121 | 11 | 20.588 | N/O | N/O | N/O | N/O | N/O | completed | 3 | 1 | N/O | 4.468 GiB | N/O | 365,151 | 终态后监控器因SQLite占用读取中断；Job与5秒稳定等待已完成 |
| 2 | `3402505MR30022 Proforma Invoice of H Hotel JODC - Dun 20250507.xlsx` | 105,053 | 3 | 18.228 | 1.662s | N/O | N/O | N/O | N/O | completed | 2 | 0 | N/O | 4.469 GiB | 5,502 MiB | 228,345 | 同会话续跑 |
| 3 | `3402510MG10094 Canasin Proforma Invoice-Blooming_Caption by Hyatt KABUTOCHO-Oct.26.2025 V2.xlsx` | 58,848 | 3 | 15.161 | 未分离 | N/O | N/O | N/O | N/O | completed | 0 | 0 | N/O | 4.469 GiB | 4,655 MiB | 132,950 | 正常 |
| 4 | `3402510MG10095 Canasin Proforma Invoice-Annupuri Garden 2-Sep.23.2025 V4.xlsx` | 70,826 | 2 | 16.528 | 未分离 | N/O | N/O | N/O | N/O | completed | 2 | 0 | N/O | 4.480 GiB | 5,832 MiB | 187,185 | 正常 |
| 5 | `3402510MH40078  Proforma Invoice for Okura 20251020.xlsx` | 22,230 | 2 | 15.748 | 未分离 | N/O | N/O | N/O | N/O | completed | 0 | 1 | N/O | 4.479 GiB | 4,667 MiB | 116,425 | 另有1条候选并列 |
| 6 | `3402510MH40090 Proforma Invoice【Ease Hotel】- Canasin 20251023.xlsx` | 32,640 | 2 | 16.020 | 未分离 | N/O | N/O | N/O | N/O | completed | 2 | 0 | N/O | 4.483 GiB | 5,820 MiB | 122,354 | 正常 |
| 7 | `3402510MH90180.xlsx` | 61,378 | 4 | 16.657 | 未分离 | N/O | N/O | N/O | N/O | completed | 0 | 4 | N/O | 4.479 GiB | 4,617 MiB | 137,635 | 4条均无候选 |
| 8 | `3402510MR30051 Proforma Invoice of Double Tree Jeddah - 20251002.xlsx` | 102,129 | 3 | 20.065 | 未分离 | N/O | N/O | N/O | N/O | completed | 2 | 0 | N/O | 4.494 GiB | 5,092 MiB | 255,716 | 正常 |
| 9 | `3402511MG20056 Proforma Invoice - Welllife PO 1031.2025.xlsx` | 12,189,302 | 3 | 18.047 | 未分离 | N/O | N/O | N/O | N/O | completed | 2 | 0 | N/O | 4.502 GiB | 5,155 MiB | 12,332,512 | 另有1条候选并列 |
| 10 | `3402511MH30095.xlsx` | 3,988,910 | 5 | 18.419 | 未分离 | N/O | N/O | N/O | N/O | completed | 0 | 0 | N/O | 4.496 GiB | 4,939 MiB | 4,091,341 | 5条证据不足 |
| 11 | `3402511MW30039 Canasin Invoice for MAK LLC Bayarsuren Natsagdorj Makotel project 20250915.xlsx` | 829,058 | 9 | 20.006 | 未分离 | N/O | N/O | N/O | N/O | completed | 0 | 0 | N/O | 4.497 GiB | 4,570 MiB | 1,015,985 | 9条证据不足 |
| 12 | `3402511MW90145 DW PI-  Canasin 20251030.xlsx` | 1,694,576 | 2 | 16.451 | 未分离 | N/O | N/O | N/O | N/O | completed | 1 | 0 | N/O | 4.506 GiB | 5,775 MiB | 1,757,796 | 正常 |

## 7. 应用冷启动与重复Worker加载分析

桌面应用只冷启动一次，12份PI均在PID `39576`的同一会话中处理。启动时未加载Torch或FAISS。

每份PI均由生产代码创建新的短生命周期查询Embedding Worker，不是模型常驻热复用。第2至12份识别到各自独立的虚拟环境启动器PID；第11份静态现场检查明确看到启动器`38820`与其子CPython `39552`，两者命令行指向同一个Job和同一个`run-*`目录，属于一个逻辑Worker，不是第二Worker。后续任务可能受Windows文件缓存影响，但本报告不称为模型热复用。

## 8. 12份总体耗时统计

- API提交到终态外部耗时合计：211.918秒。
- 平均：17.660秒。
- 中位数：17.352秒。
- 最快：第3份，15.161秒。
- 最慢：第1份，20.588秒。
- JobService内部`elapsed_seconds`合计：189.508秒。
- 桌面应用冷启动：2.846秒。
- 第1份Worker耗时：未取得。
- 第2至12份Worker平均耗时：未取得。

第一份提交至最后一份终态的墙钟跨度包含验收监控器修正和同会话恢复时间，不作为产品性能指标。

## 9. 三份JSON完整性

12份任务均生成：

1. 正式业务JSON；
2. 解析诊断JSON；
3. 字典验证JSON。

共36份核心JSON均存在、UTF-8可解析且记录数与对应Job一致。候选JSON和匹配摘要JSON也均合法，五类JSON的每份记录数均与Job记录数一致。

## 10. 20字段合同

- 49条业务记录全部恰好20字段。
- 字段名称和顺序全部符合既有合同。
- 前19字段全部为字符串。
- `相似分数`全部为float。
- `null`数量：0。
- 额外字段：0。
- 缺失字段：0。

结论：通过。

## 11. 总记录数

各PI记录数依次为：11、3、3、2、2、2、4、3、3、5、9、2。

合计49条，与预期一致。

## 12. 确定性Gate 2D回归

以`data/output/gate2d_validation/all_results`中的同名业务JSON为基线，按文件和行号对应，比较除`物料编码`、`相似分数`之外的18个确定性字段。

- 可比较记录：49。
- 差异记录：0。
- 字段差异：0。
- 类型差异：0。

结论：确定性解析没有回归。

## 13. 匹配结果与基线

仅使用已有报告明确验收的两份可靠基线：

- 11行PI：旧Job `d5593dde276847b39a625392f038fc1a`。
- H Hotel 3行PI：`data/output/web/jobs/07042764e463498b866ad90adfc205c5/match-output`。

对14条记录比较Top 1、完整候选编码顺序、`prototype_match_score`、决策状态、候选数量和摘要：

- 可比较记录：14。
- 差异记录：0。
- 最大分数差：0，满足`abs(diff) <= 1e-6`。
- 其余10份：`baseline_unavailable`，未伪造比较结论。

匹配一致性只证明本次结果与既有可靠基线一致，不代表业务准确率。

## 14. 匹配状态与Top候选分布

49条汇总：

| 状态 | 数量 |
| --- | ---: |
| 推荐明确 `unique_best_candidate` | 14 |
| 存在候选 `ranked_candidates` | 0 |
| 候选并列 `ambiguous_tie` | 3 |
| 证据不足 `insufficient_evidence` | 26 |
| 无候选 `no_candidate` | 6 |
| 其他 | 0 |

- 有候选/推荐编码：43。
- 无候选编码：6。
- Top候选数最小/最大/平均：0 / 10 / 3.367。
- Top 1原型分数最小/中位数/最大：0.765010 / 0.769634 / 0.982044。
- 所有候选物料编码均存在于只读SQLite物料库。

原型分数未经业务真值校准，不是准确率，不据此调整权重或阈值。

## 15. Worker资源分布

本轮没有取得可复核的实际CPython Worker峰值，不能用启动器约0.001 GiB的Private Bytes替代。

根因是验收监控器按项目默认Web根目录寻找`response.json`，而桌面模式实际Job根目录为：

`%LOCALAPPDATA%\BeddingOrderParser\tasks\jobs`

因此实际Worker的`response.worker_pid`和峰值采样没有保留下来。第2至12份均识别到独立启动器，第11份现场确认启动器和实际CPython父子链，所有任务终态后未发现Worker残留，但这些证据不能补算逐份峰值。

这是验收可观测性阻断项，不是生产匹配失败；报告以“未取得”记录，不写成0。

## 16. 父进程长期内存趋势

任务后稳定Private Bytes：

`4.468, 4.469, 4.469, 4.480, 4.479, 4.483, 4.479, 4.494, 4.502, 4.496, 4.497, 4.506 GiB`

- 首份后：4.468 GiB。
- 第12份后：4.506 GiB。
- 总增长：38.91 MiB。
- 最大：4.506 GiB，低于6 GiB阻断线。
- 第1、3、6、9、12份后未形成连续3份单向上升。
- 相比首份增长远低于1 GiB。

判定：父进程没有可疑累积，也没有阻断泄漏。

## 17. 系统CPU、内存、Commit和磁盘

- 任务期最低可用物理内存：4,570 MiB（4.463 GiB），高于1.25 GiB阻断线。
- Commit峰值：82%，低于90%阻断线。
- CPU峰值：62%，未达到95%持续60秒条件。
- D盘最低剩余：168.780 GiB。
- 父进程Private Bytes峰值：4.506 GiB。
- 电脑明显卡顿：未观察到。
- 桌面失去响应：未观察到。
- 安全停止触发：0。

由于Worker峰值缺失，不能完成Worker 4.0 GiB/4.5 GiB两项阈值的本轮独立复核。

## 18. 历史记录

- 运行前历史Job：10。
- 运行后历史Job：22。
- 本轮新增：12个不同Job ID。
- 新增文件名：12个且与正式PI一一对应。
- 新增状态：12个`completed`。
- 新增queued/running/processing残留：0。
- 重复提交：0。
- 旧任务`250c6faabfba4925a73c06bc9ea68de3`仍为`interrupted`，`previous_status=processing`。
- 本轮未删除历史任务。

初版监控器曾从项目默认Web根目录读取初始目录集合；最终历史结论以桌面API的运行前10条快照、桌面实际LocalAppData目录22条终态和本轮12个Job ID交叉核对。

## 19. 桌面关闭与残留

- 关闭方式：对实际桌面窗口调用正常关闭。
- `CloseMainWindow()`：成功。
- 桌面业务进程：已退出。
- 启动器/pythonw：无残留。
- Web服务：已退出。
- 8000端口：已释放。
- `runtime.json`：已清理。
- Embedding Worker：无残留。
- 新增活动Job：0。

关闭后的唯一短暂命令行匹配项是本轮创建的PowerShell补充采样器，不是业务进程；已按精确PID结束，最终无验收会话残留。

## 20. 发现的问题分类

### 阻断问题

1. **Worker性能证据缺失**：验收脚本使用了错误的桌面Job根路径，未保留12份实际CPython Worker的峰值Private Bytes、Commit和阶段耗时，因此无法完成R9要求的Worker资源分布与安全阈值独立复核。

### 明确应修问题

无生产代码问题。

### 性能问题

未发现父进程累计泄漏、系统低内存、Commit阻断、CPU阻断或任务超时。

### UI或历史问题

未发现。12个新Job均可重新读取，旧`interrupted`状态保持。

### 无真值无法判断

43条有候选和6条无候选的业务正确性仍需人工真值；本轮只验证一致性，不声称准确率。

### 已知限制

10份PI没有经项目报告明确接受的匹配基线，标记为`baseline_unavailable`。

## 21. 是否达到接入LLM前的稳定条件

**因阻断问题无法判断。**

功能层面已完成12/12、49条、JSON/ZIP/20字段/Gate 2D回归/两份可靠匹配基线/历史与关闭验收，父进程和系统资源没有异常。但R9明确要求的实际Worker峰值和阶段资源证据未取得，不能据此正式放行Gate 4C-A。

## 22. 未执行事项

- 代码修改：否
- 测试代码修改：否
- pytest：否
- Playwright：否
- LLM/API：否
- PyInstaller：否
- Onedir：否
- Onefile：否
- Day01修改：否
- 失败PI重试：否

## 23. Git提交和工作区

本报告是唯一允许进入Git的文件：

`docs/reports/GATE_4B_R9_12_PI_DESKTOP_REGRESSION_REPORT.md`

提交前将执行`git diff --check`、`git status --short`和`git diff --name-status`，显式暂存本报告，提交信息为：

`test: complete desktop regression across 12 pis`

任务输出、Job数据、日志、临时脚本、采样文件、PI、向量和API Key均不提交。

## 24. 下一步唯一建议

**Gate 4B-R10：只修复R9验收监控的桌面Job根路径与实际Worker PID采样，并重新取得12份Worker峰值和阶段资源证据。**

不得在该步修改匹配算法、解析规则、权重或业务结果；取得完整性能证据后再判断是否进入Gate 4C-A。
