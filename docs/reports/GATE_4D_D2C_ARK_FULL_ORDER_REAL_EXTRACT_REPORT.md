# Gate 4D-D2C 火山方舟整单 extract 真实响应单次验收报告

## 1. 验收结论

本轮授权的单次真实调用、清理、离线回归、报告与提交已闭环，但 **Ark 整单 extract 未通过正式链路验收**。

- 唯一一次真实响应成功到达，并以现有已支持的 `function_call` 形态返回。
- 响应在 `VolcengineArkFullOrderProvider` 的严格输出合同边界被拒绝。
- Job 安全进入 `awaiting_user_decision`，没有静默回退、字段裁决、Fake 下游调用或五类发布。
- 没有保存原始响应，安全摘要只能把失败定位到“严格 Schema / 身份 / scope 合同校验层”，不足以证明某一种允许的等价响应格式差异。
- 未进行猜测性兼容修复，也没有第二次真实调用。

## 2. 基线与工作区

- 开始分支：`master`
- 开始完整 HEAD：`1ce7504979b79c0e3b5cea891a00b92038e9e538`
- 开始提交：`fix: preserve safe full-order failure diagnostics`
- 开始工作区只有三份既有未跟踪交接文档，无未知业务修改。

## 3. 调用前审计

- Ark 配置：`ready`
- Provider：`volcengine_ark`
- 模型：`doubao-seed-2-0-lite-260428`
- Base URL：`https://ark.cn-beijing.volces.com/api/v3`
- API Key：已配置，仅检查布尔状态，未输出值。
- 本机环境默认 `LLM_MAX_RETRIES` 为 `1`；真实调用进程显式覆盖并断言为 `0`。
- 请求使用 Ark Responses API、`store=false`；`stream` 未设置，采用 API 默认非流式行为。
- 仅允许 `FULL_ORDER_EXTRACTION_FUNCTION`，未调用 `resolve_structure()`。

### 合成数据与 fixture

- 使用与 D2B 等价的内存合成工作簿：单 Sheet `SYNTHETIC`，表头 `No.`、`Item`、`Specification`、`Qty`，单行数据 `1`、`Duvet Cover`、`White cotton`、`12`。
- D2C 调用前离线单测再次证明该 fixture 可通过正式 Provider 边界、字段裁决、Fake 字典、Fake 匹配和五类发布：`1 passed in 0.77s`。
- 不含真实 PI、客户、联系人、银行信息或真实物料主数据。
- Transport 发送前断言正文不含 API Key、Authorization、本机临时目录、Job ID 或 Excel 二进制。

### 调用前计数

- 预检：`ready=true`
- 预检阶段 Transport 尝试：`0`
- Job 创建阶段 Transport 尝试：`0`
- `structure_call_count`：`0`
- `extraction_call_count`：`0`

## 4. 唯一一次真实调用安全摘要

D2B 的 `_run_with_summary()` 在 `finally` 中、临时目录退出前形成白名单摘要；摘要输出后才执行完成态与正式产物断言。

### Job 与 Provider

- Job 状态：`awaiting_user_decision`
- AI 阶段：`awaiting_user_decision`
- 安全错误码：`AI_SCHEMA_OR_EVIDENCE_FAILED`
- 可展示消息：`AI增强整单解析未发布，请选择重试、回退或保留失败。`
- 回退状态：`not_requested`
- Provider：`volcengine_ark`
- 模型：`doubao-seed-2-0-lite-260428`
- 脱敏 request ID：`sha256:7eae097d5af7`
- 返回形态：`function_call`
- 安全解析阶段：`strict_schema`

### Usage 与预算

- input tokens：`4317`
- output tokens：`1348`
- total tokens：`5665`
- 延迟：`23281 ms`
- 结构识别逻辑调用：`0`
- 字段提取逻辑调用：`1`
- 总逻辑调用：`1`
- HTTP 尝试：`1`
- 重试：`0`

### Chunk、合同与发布门

- 已验证 chunk：`0`
- 总 chunk：`1`
- 失败或未验证 chunk：`1`
- Provider 输出合同通过：`false`
- `ready_for_downstream`：`false`
- 字段裁决：未执行到可发布完成态
- FakeDictionaryValidator 调用：`0`
- FakeMaterialMatcher 调用：`0`
- 下游门通过：`false`
- 发布门通过：`false`
- 五类角色完整：`false`

严格 Provider 输出没有完成，因此 Schema、身份、scope、证据和禁止字段不能分别标记为“已通过”。安全诊断能准确确认失败发生在这些校验共同构成的 Provider 输出合同边界，但不能在不保存原始响应的条件下进一步确定具体字段路径。本报告不把未验证项误报为单独失败项。

## 5. 兼容修复判断

- 真实返回形态是现有已支持的 `function_call`，不是新的等价 Responses 包装形态。
- 安全摘要没有包含原始函数参数或具体 Schema 路径，这是有意的安全边界。
- 当前证据不足以证明只需增加一种等价形态解析；若修改 Provider，只能依靠猜测模型参数内容，可能放宽额外字段、身份、scope、证据或禁止字段合同。
- 因此生产兼容修复：`0`。
- 人工脱敏真实响应 fixture：`0`。
- 本轮未修改生产代码或测试。

## 6. 离线回归

真实调用后显式设置 `LLM_ENABLED=false`、清空 `ARK_API_KEY` 并保持 `LLM_MAX_RETRIES=0`，执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ai_full_order\test_acceptance_diagnostics.py tests\ai_full_order\test_volcengine_ark_full_order_provider.py tests\llm\test_volcengine_ark_provider.py tests\web\test_ai_full_order_jobs.py tests\web\test_gate4c2_routes.py tests\web\test_gate4c2_frontend.py tests\web\test_ai_advisory.py tests\web\test_services.py tests\web\test_routes.py tests\desktop\test_server_controller.py -q
```

结果：`117 passed in 14.57s`。

附加检查：

```powershell
git diff --check
.\.venv\Scripts\python.exe -m compileall -q src
```

均通过。标准模式、单记录 Ark Provider、诊断器、桌面 Job、C1/C2 预检和 UI 合同未出现离线回归。未运行完整 pytest。

## 7. 调用与资源计数

- 授权真实逻辑调用：最多 `1`
- 实际真实逻辑调用：`1`
- 授权 HTTP 尝试：最多 `1`
- 实际 HTTP 尝试：`1`
- 追加调用：`0`
- `resolve_structure()`：`0`
- 模型切换：`0`
- 真实 PI：`0`
- 真实字典：`0`
- 真实物料库：`0`
- BGE-M3：`0`
- FAISS：`0`

## 8. 安全与清理

- 白名单摘要在成功断言之前输出。
- 完整 HTTP 请求、原始响应、Authorization、API Key、系统提示、完整外发正文和思维链均未打印、保存或提交。
- 合成工作簿、Job、reliability 状态、缓存和 Bundle 位于 `TemporaryDirectory`。
- 调用结束后检查未发现 `bedding-d2c-synthetic-*` 临时目录残留。

## 9. 修改与提交

本轮只新增：

- `docs/reports/GATE_4D_D2C_ARK_FULL_ORDER_REAL_EXTRACT_REPORT.md`

提交信息：`test: validate ark full-order real extraction`

完整提交哈希以提交后的 Git 核验和最终回复为准。

## 10. 最终状态

D2C 验收执行已闭环，但当前 Ark 模型的真实整单 extract 输出仍未通过冻结合同，不能声称 AI 整单正式链路已完成真实验收。后续若要诊断具体字段差异，需要新的明确授权与一个能够在不提交原始响应的前提下输出白名单 Schema 路径/差异类别的验收能力；不得直接增加真实调用或放宽合同。
