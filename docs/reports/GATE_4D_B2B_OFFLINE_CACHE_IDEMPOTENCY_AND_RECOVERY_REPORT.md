# Gate 4D-B2B｜离线缓存、幂等、Single-flight与中断恢复报告

## 1. 实际基线和提交

- 开始分支：master。
- 开始完整 HEAD：f5f73d8f7a59a4a95f054774bbca39cd9dc54cc9。
- 开始短哈希：f5f73d8。
- 开始提交：feat: add ai full-order orchestration and field resolution。
- 开始工作区仅有允许保留的未跟踪恢复文档：CODEX_HANDOFF_AND_RECOVERY_2026-07-30.md、CODEX_RECOVERY_AUDIT_ROUND_1_REPORT_2026-08-01.md。
- 本报告与本轮实现同一提交；提交信息为 feat: add ai full-order cache and recovery，实际哈希以提交后 Git 核验及最终交接为准。

## 2. 缓存键

- 新增 src/bedding_order_parser/ai_full_order/reliability.py。
- CacheIdentity 使用规范化 JSON（稳定字段排序与紧凑序列化）计算 SHA-256 缓存键。
- 缓存身份固定包含：source_file_sha256、provider、model、extraction_schema_version、prompt_version、preprocessor_version、normalization_rules_version、canonical_chunk_manifest_sha256。
- manifest 摘要按确定性 order 排序，因此输入字段顺序、调用进程和重启不改变键；任一版本字段变化均产生未命中。

## 3. 缓存分类

- validated：仅保存已重新通过严格 Schema、身份、scope、记录数和证据校验的结构化输出；恢复时再次校验，绝不把缓存直接当作正式结果。
- failed_deterministic：Schema、证据、身份、scope、记录数等确定性失败持久化为终态，默认不再调用 FakeProvider。
- 允许已获得 lease 的上层调用 force_deterministic_retry=True 对首次确定性失败显式重试一次；第二次强制请求保持隔离，不创建额外逻辑调用。
- failed_transient：只保存错误类别、尝试次数和有界 retry_after_ms，不伪装为成功，也不保存 Provider 原始响应；达到上限后隔离。
- pending、running 与 interrupted 都不被视为可复用成功。

## 4. 原子状态和状态转换

- 状态枚举：pending、running、succeeded、validated、failed_transient、failed_deterministic、interrupted。
- JSON 写入使用唯一临时文件、flush、os.fsync、os.replace；对模拟 Windows PermissionError 做有界重试。
- 状态转换按白名单校验。validated 与 failed_deterministic 不允许被普通旧写入覆盖。
- 唯一例外是由 lease leader 明确触发且仅限一次的确定性失败强制重试；该操作有单独方法和尝试次数约束。
- 损坏、未知版本、字段不完整、身份不匹配或 validated 缺少严格输出的状态文件均安全隔离，不会猜测为成功。

## 5. 幂等与Single-flight

- 客户端 idempotency_key、服务端业务键与缓存键共同生成稳定 execution_id。
- 同一客户端键复用到不同业务或合同版本会拒绝；相同请求重复提交返回相同执行身份。
- 已有全部 validated 缓存时直接返回 cached，不会再次调用 FakeProvider。
- single-flight 采用共享状态目录中的原子排他创建 lease 文件，不使用模块级线程锁。
- lease 含唯一 owner token 与心跳；健康锁不会被抢占。过期且内容未变化的锁才会被隔离后重新竞争。
- follower 可读取成功缓存、在有界时间内等待，或返回 in_progress；不会无限阻塞。
- 对恢复状态的判定只在拿到 lease 后进行，防止 follower 把健康 leader 的 running 状态错误标为中断。

## 6. 中断恢复

- 重启时，lease leader 将遗留 running 块单调转为 interrupted，之后仅恢复未验证块。
- validated 块由严格缓存恢复，保留 B2A 的行号、记录身份、scope 和 manifest 顺序，不重复调用 Provider。
- 确定性失败默认不重跑；瞬时失败受尝试上限控制。
- 部分块完成后返回 interrupted 与 B2A isolated 批次；只有全部预期块恢复、通过既有记录/身份/scope/高风险冲突检查后才为 ready_for_downstream。
- 本轮没有发布五类核心 JSON。

## 7. 并发及故障注入测试

执行命令：

~~~powershell
uv run pytest tests/ai_full_order tests/extraction/test_item_extractor.py tests/excel/test_table_parser.py -q
~~~

结果：75 passed in 3.37s。

- 版本化缓存键稳定性及任一合同版本失效。
- 同请求连续提交仅一次 FakeProvider 逻辑调用，且相同幂等键返回同一执行身份。
- 两个独立 spawn 进程、两个独立存储实例在同一状态目录竞争时，计数文件证明只有一个 leader 逻辑调用。
- 健康 lease 不抢占、过期 lease 可恢复、follower 等待有界。
- 第一个块完成后的模拟中断只恢复余下块，validated 块不重跑，部分结果不能绕过 B2A ready 门。
- 确定性失败不自动重试，显式重试仅一次；瞬时失败达到尝试上限后不再调用。
- 终态旧写入拒绝、模拟 Windows 占用后的原子写入恢复、损坏状态隔离。
- 现有 B2A 的 17 字段、正式行号、跨 scope/伪造证据、物料编码/相似分数禁止和零网络测试一并回归。

## 8. FakeProvider调用计数

- 成功重复提交：1 次逻辑提取调用。
- 两进程 single-flight：计数型 FakeProvider 文件记录为 1 次。
- 两块中断恢复：中断前 1 次，恢复实例仅 1 次剩余块调用。
- 确定性失败：默认只 1 次；单次显式强制重试后总计 2 次，第二次强制请求不新增调用。
- 瞬时失败：达到默认 2 次上限后不再调用。

## 9. 网络/API调用数

- 真实豆包/API 调用：0。
- 网络调用：0；测试使用 FakeProvider 计数与 socket 禁用断言。
- BGE-M3 调用：0；FAISS 调用：0。
- 未解析真实 PI，未安装依赖，未运行完整 pytest。

## 10. 修改文件、工作区和下一步

- src/bedding_order_parser/ai_full_order/reliability.py
- tests/ai_full_order/test_reliability.py
- docs/reports/GATE_4D_B2B_OFFLINE_CACHE_IDEMPOTENCY_AND_RECOVERY_REPORT.md
- 未修改标准解析、桌面 UI、正式 Job、五类 JSON 发布、字典、BGE-M3、FAISS 或物料匹配。
- 提交后工作区应仅保留两份恢复文档为未跟踪文件，不暂存、不删除。

下一步唯一建议：Gate 4D-B3：离线连接字段裁决结果、字典验证、物料匹配适配和五类JSON原子发布。
