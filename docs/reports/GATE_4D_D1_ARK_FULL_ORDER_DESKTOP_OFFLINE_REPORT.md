# Gate 4D-D1 火山方舟整单 Provider 与桌面服务离线接入报告

## 1. 基线与工作区

- 开始分支：`master`
- 开始完整 HEAD：`16fea09bb245e64e575bb289cc55ec26e6126cfe`
- 开始提交：`feat: add ai enhanced parsing desktop ui`
- 开始时不存在未提交的生产代码；保留了两份恢复文档以及 C2 交接状态文档，均未纳入本 Gate。

## 2. 实现与复用

- 新增 `ai_full_order.volcengine_ark.VolcengineArkFullOrderProvider`，实现既有整单端口的 `resolve_structure()` 与 `extract()`。
- 复用单记录 Ark Provider 的 `LLMSettings`、可注入 `JSONTransport`、Authorization、超时、有限重试、HTTP 错误分类、密钥脱敏与 Responses API 请求发送。
- 对既有单记录 Provider 做了局部兼容性提取：`extract_structured_output()` 可按函数名读取 function call、嵌套 function call、消息 `output_text` 或顶层 `output_text`。单记录的原有函数名和严格校验未改变。
- 整单请求使用非流式 `/responses`、`store=false`、严格 function schema 和固定 tool choice。发送内容仅为既有结构识别区块或 B1 请求合同；结构识别的本地 `cache_key` 在发送前被剔除。
- Provider 对模型输出继续执行既有 `validate_full_order_request()` / `validate_full_order_output()`；Provider、模型、request ID、usage、延迟和尝试次数由本地 transport 事实覆盖，不信任模型生成的元数据。
- 没有复制或修改 17 个 AI 字段、证据、身份、scope、字段裁决、缓存身份或 B3 发布合同。

## 3. 桌面依赖与安全状态

- 新增 `build_ai_enhanced_dependencies()` 作为桌面服务的窄构造入口。
- 只有 Ark 设置为 `ready` 且字典验证、物料匹配两个既有端口均已提供时，才构造并注入正式整单 Provider；关闭、缺失或不完整配置保持既有未就绪预检行为。
- `JobService` 保留显式注入的 Fake 依赖，同时支持通过设置、Transport 和两个下游端口构造正式依赖。
- import、构造和 `ai_enhanced_preflight()` 都不调用 Transport；只有实际运行 `ai_enhanced` Job 才可能进入 Provider。
- AI 执行摘要新增安全 `request_id`，并记录累计 Token、HTTP 尝试次数；不持久化完整请求、原始响应、Authorization 或思维链。

## 4. 离线成功与失败链路

- 使用记录型 FakeTransport 的正式整单 Provider 完成一条桌面 `ai_enhanced` Job：预处理、提取、严格验证、字段裁决、B2B、Fake 字典、Fake 匹配与 B3 五类 Bundle 发布均成功。
- 成功 Job 可按既有五种角色读取产物，状态为 `completed`，安全摘要保存 Provider、模型、request ID、累计 Token 与 HTTP 尝试次数。
- 注入 HTTP 400 的受控失败会被分类为确定性失败，Job 进入 `awaiting_user_decision`；不会静默回退、不会产生完整五类结果或半发布。

## 5. 严格合同与兼容验证

- 验证 function call 与 `output_text` 两种 Ark 返回形态。
- 验证严格 function schema、`additionalProperties=false`、`store=false`、无 Excel 二进制、本机路径、Job ID 或密钥的请求边界。
- 模型注入额外 `物料编码` 字段仍被现有严格 Schema 拒绝。
- 验证歧义结构识别调用复用同一安全 Transport，且不会发送本地 cache identity。
- 验证 429 重试受设置上限约束，并正确累计 HTTP 尝试次数。

## 6. 测试与结果

执行的定向命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ai_full_order\test_volcengine_ark_full_order_provider.py tests\llm\test_volcengine_ark_provider.py tests\web\test_ai_full_order_jobs.py tests\web\test_gate4c2_routes.py tests\web\test_gate4c2_frontend.py tests\web\test_ai_advisory.py tests\web\test_services.py tests\web\test_routes.py tests\desktop\test_server_controller.py -q
```

实际结果：`112 passed in 13.46s`。

附加静态校验：

```powershell
git diff --check
.\.venv\Scripts\python.exe -m compileall -q src
```

均通过。未运行完整 pytest、BGE-M3、FAISS、真实物料匹配或真实 PI。

## 7. 调用计数与数据安全

- 真实网络调用：`0`
- 真实火山方舟 / 豆包 API 调用：`0`
- BGE-M3 调用：`0`
- FAISS 调用：`0`
- 成功桌面链路的 FakeTransport HTTP 请求：`1`
- 受控失败桌面链路的 FakeTransport HTTP 请求：`1`

所有测试显式注入测试 Ark 设置和 FakeTransport；不会读取或使用本机真实凭证。

## 8. 修改文件

- `src/bedding_order_parser/ai_full_order/volcengine_ark.py`
- `src/bedding_order_parser/llm/volcengine_ark.py`
- `src/bedding_order_parser/web/ai_full_order_dependencies.py`
- `src/bedding_order_parser/web/ai_full_order_service.py`
- `src/bedding_order_parser/web/services.py`
- `tests/ai_full_order/test_volcengine_ark_full_order_provider.py`
- `docs/reports/GATE_4D_D1_ARK_FULL_ORDER_DESKTOP_OFFLINE_REPORT.md`

## 9. 提交与工作区

实际提交信息：`feat: connect ark full-order desktop provider`。本报告与本 Gate 的代码、测试同属该最终提交；完整哈希以提交后的 Git 核验为准。

预期保留且不暂存的未跟踪文件：

- `CODEX_HANDOFF_AND_RECOVERY_2026-07-30.md`
- `CODEX_RECOVERY_AUDIT_ROUND_1_REPORT_2026-08-01.md`
- `docs/reports/GATE_4D_C2_EXECUTION_HANDOFF_STATUS_2026-08-02.md`

## 10. 下一步

下一步应仅在用户明确授权后进行真实火山方舟小样本验收：先做配置与脱敏审计，再对最小化脱敏证据执行受控调用，并验证真实响应形态不会放宽本 Gate 的严格整单合同。
