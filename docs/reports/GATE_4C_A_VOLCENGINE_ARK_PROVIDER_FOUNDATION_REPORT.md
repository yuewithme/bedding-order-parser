# Gate 4C-A：火山方舟豆包 Provider 基础层报告

## 1. 任务目标

本轮建立供应商可扩展、默认关闭、仅提供 sidecar 建议的 LLM Provider
基础层，并完成火山方舟豆包 Provider 的离线合同测试。Provider 不进入
确定性解析、字典验证、物料匹配或正式 20 字段业务 JSON。

## 2. Git 基线

- 项目：`D:\AI-Learning\Projects\bedding-order-parser`
- 分支：`master`
- 初始 HEAD：`3cc9d36d45030eb4c2cdcba776b80333250638b4`
- 初始提交：`3cc9d36 fix: harden embedding worker recovery`
- 初始工作区：干净
- Day01 HEAD：`b6206bf28a9ce5499e317cee324b16ea98bf569d`
- Day01 工作区：干净

仓库长期文档仍保留早期 Gate 描述；本轮以用户明确批准的 Gate 4C-A
指令为当前阶段授权，不修改旧交接、README 或架构文档。

## 3. 现有 LLM 架构审计

Gate 4B 已预留：

- `LLMProvider` Protocol；
- `NullLLMProvider`；
- `LLMSettings` 环境变量设置；
- `LLMService`；
- `/api/capabilities`；
- 尚未接入业务的 `/api/tasks/<id>/ai-enhance`；
- 前端只读取 `llm.configured` 决定 AI 开关状态。

主要缺口：

1. 旧设置读取 `LLM_API_KEY`，未采用火山方舟要求的 `ARK_API_KEY`；
2. 没有超时、重试、错误分类、请求 ID 和 Token 合同；
3. 原响应结构允许任意字典，不能执行严格 Schema 校验；
4. 没有真实可运行但可离线替换 Transport 的 Provider；
5. capabilities 不能区分关闭、缺 Key、缺模型、Provider 不支持和就绪；
6. Null Provider 合同没有版本化的 source record 对齐约束。

## 4. Provider 设计

依赖方向：

```text
LLMService
-> provider factory
-> LLMProvider Protocol
-> NullLLMProvider / VolcengineArkProvider
-> JSONTransport Protocol
-> UrllibJSONTransport
```

关键边界：

- `LLMService` 在配置不是 `ready` 时先失败关闭；
- `build_provider()` 根据 `LLM_PROVIDER` 创建 Provider；
- Provider 只接收单条 `LLMEnhancementRequest`；
- 请求与响应必须携带同一 `source_record_id`；
- Provider 返回 `LLMEnhancementResponse` sidecar，不接触正式结果；
- Transport 可注入，所有测试使用 FakeTransport；
- import、服务初始化、health check 和 capabilities 均不发网络请求。

## 5. SDK/HTTP 方案选择及原因

选择：**Python 标准库 `urllib` + 可注入 JSON Transport**。

未选择官方 SDK 或 OpenAI SDK，原因：

- 当前仓库没有通用 HTTP/LLM SDK；
- 本轮只需非流式 Responses API；
- 标准库可以明确控制超时、HTTPError、URLError 和响应字节；
- FakeTransport 可以覆盖所有错误，不需要 monkeypatch SDK 内部实现；
- 不增加桌面打包体积和 PyInstaller hidden imports；
- API Key 不进入 URL、repr 或异常；
- 下一轮若 SDK 能提供明确收益，可以在 Provider 后方替换 Transport，
  不改变业务合同。

官方协议依据：

- [火山方舟 Responses API 快速开始](https://www.volcengine.com/docs/82379/1795150)
- [火山方舟 Responses API 工具调用](https://www.volcengine.com/docs/82379/1958524?lang=zh)

## 6. 新增依赖或无新增依赖说明

- 新增正式依赖：无
- 新增开发依赖：无
- `pyproject.toml`：未修改
- `uv.lock`：未修改
- SDK/依赖体积增加：0

## 7. 火山方舟请求协议

- Provider 标识：`volcengine_ark`
- 默认 Base URL：`https://ark.cn-beijing.volces.com/api/v3`
- 请求路径：`POST <base_url>/responses`
- 认证：`Authorization: Bearer <ARK_API_KEY>`
- API Key：仅请求头，不进入 URL
- 模型：来自 `LLM_MODEL`
- 调用方式：Responses API，非流式
- `store`：`false`
- 输入：
  - developer 指令；
  - 单条记录 JSON 用户输入；
- 结构化输出：Function Calling
  - 函数名：`submit_bedding_order_advisory`
  - `strict: true`
  - 参数为严格 JSON Schema
  - `tool_choice` 固定为该建议函数

Provider 同时支持从 Responses API 的 `output_text` 中解析严格 JSON，作为
兼容性回退；两条路径都必须通过同一套本地 Schema 校验。

## 8. 安全配置

支持：

```text
LLM_ENABLED
LLM_PROVIDER
LLM_BASE_URL
LLM_MODEL
LLM_TIMEOUT_SECONDS
LLM_MAX_RETRIES
ARK_API_KEY
```

安全规则：

- 默认 `LLM_ENABLED=false`；
- 旧 `LLM_API_KEY` 不再作为火山方舟凭证来源；
- API Key 只在运行时设置对象和 Authorization 请求头中存在；
- `LLMSettings.__repr__` 只显示 `***`；
- capabilities 只返回 `api_key_configured: true/false`；
- Provider 错误类型会替换可能回显的 Key；
- HTTP 请求 repr 只显示 header 名称，不显示值或 body；
- Base URL 禁止用户名、密码、query 和 fragment；
- 远程 Base URL 必须使用 HTTPS，本地测试地址可使用 localhost；
- `.env` 与 `.env.*` 已被 Git 忽略，只有无秘密 `.env.example` 被跟踪；
- 不在 import 阶段读取并验证真实凭证。

配置状态：

```text
disabled
configuration_error
provider_not_configured
unsupported_provider
api_key_missing
model_missing
ready
```

## 9. 结构化 AI 建议 Schema

最终 sidecar 顶层固定为：

```text
schema_version
provider
model
request_id
source_record_id
status
finish_status
action
confidence
suggested_fields
material_assessment
reasoning_summary
warnings
evidence_references
usage
latency_ms
attempt_count
advisory_only
```

所有对象均 `additionalProperties: false`。

字段建议必须包含：

```text
field_name
original_value
suggested_value
reason
evidence_references
```

物料评估状态只允许：

```text
no_suggestion
suggested
insufficient_evidence
```

不存在 `confirmed`。状态不是 `suggested` 时，物料编码必须为空。输出没有
ERP 写回动作。`action=insufficient_evidence` 是合法结果。模型输入和输出的
`source_record_id` 不一致时，整条响应拒绝。

本地实现了本任务 Schema 所需的 object、array、string、number、integer、
boolean、required、enum、const、additionalProperties 和数值范围校验，
无需增加 `jsonschema` 依赖。

## 10. 错误分类

`LLMErrorCode` 完整区分：

```text
disabled
configuration_error
authentication_error
permission_error
model_not_found
rate_limited
timeout
connection_error
invalid_request
invalid_response
structured_output_error
provider_server_error
cancelled
unknown_provider_error
```

`LLMProviderError` 保存：

- 安全摘要；
- 是否可重试；
- HTTP 状态码；
- Provider 原始错误类型的脱敏摘要；
- request ID；
- 尝试次数；
- 有界 Retry-After。

不保存请求体、API Key 或完整 Provider 原始错误正文。

## 11. 重试策略

`LLM_MAX_RETRIES` 表示首次调用之后的最大重试次数，允许范围为 0 至 5。

允许重试：

- Transport timeout；
- connection error；
- HTTP 408；
- HTTP 429；
- HTTP 500、502、503、504。

禁止重试：

- 400；
- 401；
- 403；
- 404；
- 本地配置错误；
- 非 JSON 成功响应；
- Function arguments 非 JSON；
- JSON Schema 失败；
- `source_record_id` 错位；
- cancelled。

退避默认从 0.25 秒开始指数增长，最大 2 秒；Provider `Retry-After`
最大采纳 5 秒。sleep 可注入，离线测试不真实等待。每个成功响应记录
`attempt_count`，失败异常记录 `attempts`。

## 12. Token 和请求元数据

成功响应保存：

- Provider response `id`，或响应头 request ID；
- 实际响应模型名；
- Provider finish/status；
- input tokens；
- output tokens；
- total tokens；
- 总响应耗时 `latency_ms`；
- 尝试次数。

Provider 没有提供 total tokens 时，使用 input + output 计算；缺失用量不会
伪造收费数字，默认记录 0。

## 13. capabilities 变化

`/api/capabilities` 的 `llm` 对象现在安全返回：

```text
enabled
configured
status
provider
provider_supported
model
model_configured
api_key_configured
real_call_allowed
business_integration
mode
```

不返回 Key、环境变量原值或敏感路径。`business_integration` 固定为 `false`，
`mode` 为 `provider_foundation_only`。现有前端仍只使用 `configured`，页面
结构和交互未修改。

即使配置达到 `ready`，现有 `ai-enhance` 路由仍返回 501，测试确认 Provider
调用次数为 0。

## 14. 实际修改文件

生产与配置：

- `.env.example`
- `src/bedding_order_parser/llm/__init__.py`
- `src/bedding_order_parser/llm/advisory_schema.py`
- `src/bedding_order_parser/llm/contracts.py`
- `src/bedding_order_parser/llm/errors.py`
- `src/bedding_order_parser/llm/factory.py`
- `src/bedding_order_parser/llm/null_provider.py`
- `src/bedding_order_parser/llm/provider.py`
- `src/bedding_order_parser/llm/service.py`
- `src/bedding_order_parser/llm/settings.py`
- `src/bedding_order_parser/llm/transport.py`
- `src/bedding_order_parser/llm/volcengine_ark.py`

测试：

- `tests/llm/test_advisory_schema.py`
- `tests/llm/test_llm_contracts.py`
- `tests/llm/test_settings.py`
- `tests/llm/test_volcengine_ark_provider.py`
- `tests/web/test_gate4b_routes.py`

报告：

- `docs/reports/GATE_4C_A_VOLCENGINE_ARK_PROVIDER_FOUNDATION_REPORT.md`

## 15. 定向测试命令和结果

最终命令：

```powershell
uv run pytest tests/llm tests/web tests/desktop/test_packaging_contract.py -q
```

结果：

```text
90 passed in 5.88s
```

覆盖：

- 配置状态与 Provider factory；
- 默认关闭与缺 Key/缺模型不调用；
- Function Calling 和 output_text 结构化解析；
- Token、request ID、latency 和 attempt count；
- timeout、connection、429、500 的有限重试；
- 连续 429 失败；
- 400、401、403、404 不重试；
- 非 JSON 响应；
- 非 JSON function arguments；
- 多余字段；
- source record 错位；
- 合法的证据不足响应；
- API Key 脱敏；
- capabilities；
- Null Provider；
- Web、上传、历史、下载和前端静态合同；
- Provider ready 时业务路由仍不调用；
- 桌面打包资源合同。

所有 Provider 测试使用 FakeTransport。未运行完整 pytest。

## 16. API Key 泄露检查

检查结果：

- 扫描本轮 17 个代码/测试/配置文件；
- 异常控制字符：0；
- 本机绝对路径：0；
- 真实 `.env` 跟踪：0；
- 真实 API Key：0；
- `pyproject.toml` / `uv.lock` 差异：0；
- Provider 异常、repr、capabilities 和测试快照中的 Key：0。

测试中的 `ark-test-secret-never-log` 和 `test-secret` 均为显式假值；
`.env.example` 中的 `ARK_API_KEY` 保持为空。

## 17. 真实 API 调用次数

`0`

没有执行真实 HTTP 请求，没有启动用户本机凭证验证。

## 18. 真实 Token 消耗

`0`

测试中的 Token 数字来自本地 FakeTransport 响应，不产生费用。

## 19. 未接入业务流程的边界

- AI 开关不触发 Provider；
- Job 不保存 AI 请求或结果；
- 不生成 AI sidecar 文件；
- 不自动选择歧义记录；
- 不修改 Python 确定性值；
- 不覆盖字段；
- 不确认物料编码；
- 不写 ERP；
- 不执行 Agent 或工具；
- 不处理真实 PI。

## 20. 未修改的解析、匹配和 20 字段合同

- parser 规则：未修改
- 固定 20 字段合同：未修改
- 字典规则：未修改
- BGE-M3：未修改、未加载
- FAISS：未修改、未加载
- SQLite 物料库：未修改
- `hybrid_score_v1`：未修改
- Top 300：未修改
- 字段权重：未修改
- 硬冲突规则：未修改
- Worker 隔离：未修改
- 现有正式业务 JSON：未修改
- 前端页面与 JavaScript：未修改
- Day01：未修改

## 21. 最终 Commit

- 提交信息：`feat: add volcengine ark llm provider`
- 完整 commit：提交完成后以 Git 输出为准
- push：否
- tag：否
- amend：否

## 22. 工作区

提交前仅包含本报告列出的代码、测试、无秘密环境示例和报告。提交后必须
再次确认工作区干净。

## 23. 下一步唯一建议

**Gate 4C-B：使用用户本机配置的火山方舟凭证，完成一次最小文本调用和
一条订单记录结构化调用。**

Gate 4C-B 应继续保持 sidecar 建议边界，并在调用前由用户明确配置和授权真实
凭证、网络请求与 Token 费用。
