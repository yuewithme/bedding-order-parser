# Gate 4D-D2D Ark 整单输出合同白名单差异诊断离线报告

## 1. 结论与基线

本 Gate 已离线完成 Ark 整单严格输出合同的白名单差异诊断加固。

- 开始分支：`master`
- 开始完整 HEAD：`9102c9c97f8d765416708fe4b21d15b4cbb747e3`
- 开始提交：`test: validate ark full-order real extraction`
- 开始工作区：仅有三份既有未跟踪交接/恢复文档；没有未知业务修改。
- 真实网络、真实 Ark API、BGE-M3、FAISS、真实物料库与真实 PI 调用：均为 `0`。

本轮没有重新解释 D2C 的真实响应，没有新增任何真实调用，也没有为猜测的返回形态增加兼容分支。

## 2. 新增安全诊断分类

`FullOrderContractError` 现在可携带经白名单清洗的 `contract_diagnostic`，Job 仅在 `ai_execution.contract_diagnostic` 保存该对象。允许字段仅为：阶段、类别、固定合同路径、预期/实际 JSON 类型、固定缺字段名、额外字段数量和固定禁止字段名。

阶段覆盖：`request_validation`、`output_schema`、`identity_validation`、`evidence_validation`、`forbidden_fields`、`provider_metadata`、`response_parsing`。

分类覆盖：

- 固定必填字段缺失、额外字段数量、类型不匹配、固定枚举/常量不匹配；
- 文件 SHA、记录数、记录身份和 scope 不匹配；
- evidence ID 不存在、跨 scope、原值或规范化值不可追溯、字段证据条件不满足；
- 固定禁止字段（`行号`、`物料编码`、`相似分数`）命中；
- Ark Provider 元数据/usage 合同错误，以及 Responses 输出解析失败。

未知模型字段名只会反映为 `extra_field_count`。摘要不会保留未知键名、模型生成值、evidence ID、evidence 文本、函数参数、完整请求、原始响应、Authorization、API Key 或思维链。即使内部异常被误记录，额外字段错误消息也不再包含模型生成的字段名。

## 3. Provider、Job 与摘要闭环

- `VolcengineArkFullOrderProvider` 在请求验证、Responses 解析、Ark 元数据/usage 校验和严格输出合同失败时，记录最后一个白名单诊断对象；仍维持既有严格拒绝行为。
- Provider 对 Ark `model` 和非空 `usage` 元数据做最小类型校验；usage 缺失和已有可兼容的数字字符串归一化行为不变。
- `JobService._pause_ai_job()` 将 Provider 诊断通过同一清洗器写入失败 Job；旧 Job、正常 Job 与标准模式保持空对象，不产生伪造诊断。
- D2B 的验收摘要从 Job 白名单字段读取该对象，并继续在 `finally`、临时目录清理之前形成摘要。

未改动 17 字段、正式行号、证据/身份/scope 验证规则、字段裁决、缓存身份、五类发布门、默认 ZIP、C2 UI、标准解析或单记录 AI Sidecar。

## 4. 离线故障矩阵

所有 Job 场景均使用 `VolcengineArkFullOrderProvider`、可计数 FakeTransport、FakeDictionaryValidator、FakeMaterialMatcher 和人工合成工作簿。每个失败场景均为 `awaiting_user_decision`，没有五类结果、没有字典/匹配调用，并在临时目录清理前形成摘要。

| 场景 | 白名单阶段 / 类别 | 下游与发布 |
| --- | --- | --- |
| 缺固定字段 | `output_schema / missing_required_fields` | 均未调用/未发布 |
| 未知额外字段 | `output_schema / extra_fields`，仅数量 | 均未调用/未发布 |
| 注入物料编码 | `forbidden_fields / extra_fields`，仅固定禁止字段名 | 均未调用/未发布 |
| 类型、枚举错误 | `output_schema / type_mismatch` 或 `enum_or_constant_mismatch` | 均未调用/未发布 |
| SHA、记录身份、scope 不一致 | `identity_validation` 对应固定类别 | 均未调用/未发布 |
| 缺失 evidence、不可追溯值 | `evidence_validation` 对应固定类别 | 均未调用/未发布 |
| 跨 scope evidence | 直接严格合同测试为 `evidence_validation / evidence_cross_scope`；编排层本地按 scope 分块，不伪造跨块请求 | 拒绝，不放宽 scope |
| 非对象 usage | `provider_metadata / provider_metadata_or_usage` | 均未调用/未发布 |
| 请求结构或 Responses 参数无法解析 | Provider 记录 `request_validation` 或 `response_parsing` | 不进入发布 |

成功路径仍完成五类结果。故障矩阵额外断言摘要序列化文本中不存在人工注入的未知字段名、生成值或 `arguments`。

## 5. 测试与离线证明

执行命令：

```powershell
$env:LLM_ENABLED='false'; $env:ARK_API_KEY=''; $env:LLM_MAX_RETRIES='0'
.\.venv\Scripts\python.exe -m pytest tests\ai_full_order\test_contracts.py tests\ai_full_order\test_acceptance_diagnostics.py tests\ai_full_order\test_volcengine_ark_full_order_provider.py tests\llm\test_volcengine_ark_provider.py tests\web\test_ai_full_order_jobs.py tests\web\test_gate4c2_routes.py tests\web\test_gate4c2_frontend.py tests\web\test_ai_advisory.py tests\web\test_services.py tests\web\test_routes.py tests\desktop\test_server_controller.py -q
.\.venv\Scripts\python.exe -m compileall -q src
git diff --check
```

实际结果：`148 passed in 17.57s`；编译和 diff 检查均通过。

`test_acceptance_diagnostics.py` 的 autouse fixture 将 `UrllibJSONTransport.send()` 置为立即失败；所有测试显式注入 FakeTransport，并且本轮环境显式禁用 LLM、清空 Ark Key、设置重试为零。因此误走真实网络会导致测试失败，实际网络/API 调用数为 `0`。

未运行完整 pytest，未加载 BGE-M3、FAISS、真实字典、真实物料库，也未解析真实 PI。

## 6. 修改文件与提交

- `src/bedding_order_parser/ai_full_order/contracts.py`
- `src/bedding_order_parser/ai_full_order/volcengine_ark.py`
- `src/bedding_order_parser/web/services.py`
- `tests/ai_full_order/test_contracts.py`
- `tests/ai_full_order/test_volcengine_ark_full_order_provider.py`
- `tests/ai_full_order/test_acceptance_diagnostics.py`
- `docs/reports/GATE_4D_D2D_FULL_ORDER_CONTRACT_DIAGNOSTICS_OFFLINE_REPORT.md`

提交信息：`fix: expose safe full-order contract diagnostics`。

本报告与上述修改将在同一 Gate 提交中；完整哈希、提交文件清单和最终工作区由提交后的 Git 核验给出。

## 7. 后续

后续真实验收若再次得到明确授权，可使用 D2B/D2D 的 `finally` 白名单摘要定位严格失败类别；在没有新的授权和安全证据前，不得追加真实 Ark 调用或放宽合同。
