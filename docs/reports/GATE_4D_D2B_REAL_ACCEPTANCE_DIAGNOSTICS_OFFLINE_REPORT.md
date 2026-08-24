# Gate 4D-D2B Ark 整单真实验收安全诊断离线报告

## 1. 结论

本 Gate 已完成。D2A 暴露的“失败后临时目录清理，安全证据未输出”缺口已通过最小生产诊断回填与离线验收辅助器闭环。

- 未调用真实网络或真实 Ark。
- 未修改 17 字段、正式行号、证据/身份/scope、字段裁决、缓存身份、五类发布、默认 ZIP、C2 UI、标准模式或单记录 Sidecar。
- 合成 fixture 在正式整单 Provider 与 Fake 下游组合下可完成字段裁决与五类发布；它不是 D2A 第二次验收失败的固有阻断因素。

## 2. 基线与工作区

- 开始分支：`master`
- 开始完整 HEAD：`12e0442cafbbd12c89090496a2e6ae6c308da072`
- 开始提交：`test: validate ark full-order real responses`
- 开始工作区只有三份既有未跟踪交接文档，无未知业务修改。

## 3. D2A 证据丢失原因

D2A 的第二次真实验收脚本仅在所有成功断言之后输出安全摘要。正式 Job 未进入 `completed` 时，完成态断言立即抛出，控制流直接退出 `TemporaryDirectory`，从而删除了合成工作簿、Job、reliability 状态和 Bundle；摘要代码没有执行。

这不是允许保存原始响应的理由。根因是验收脚本的摘要时机错误，以及暂停 Job 没有把已经存在的安全 Provider 元数据完整回填到 `ai_execution`。

## 4. 诊断闭环

新增测试侧 `_run_with_summary()`：无论 Job 正常返回、进入 `awaiting_user_decision`，还是后续断言抛出，均在 `finally` 中调用 `_safe_summary()`，并在 `TemporaryDirectory` 退出前形成仅含白名单字段的内存摘要。

摘要包含：

- Job 状态、AI 阶段、安全错误码、可展示消息、回退状态；
- Provider、模型、SHA-256 截断后的 request ID、逻辑调用数、HTTP 尝试、usage、延迟；
- 已完成/总 chunk 与未验证 chunk 数；
- `ready_for_downstream`、五角色完整性；
- FakeTransport 分类得到的返回形态和安全解析阶段；
- Schema、证据、下游/发布门失败标志，以及仅类名形式的验收断言异常。

摘要不会读取或保留请求正文、原始响应、Authorization、API Key、完整外发正文或思维链。FakeTransport 在内存中完成返回形态分类后立即丢弃请求/响应字节。

## 5. 最小生产诊断修复

### Provider 安全失败元数据

`VolcengineArkFullOrderProvider` 在既有 `LLMProviderError` 路径中仅记录 Provider、模型、来自 Transport 的 request ID、尝试次数和零 usage/延迟占位；随后仍按原有瞬时/确定性分类抛出。它不保存错误正文、请求或响应。

### 暂停 Job 元数据

`JobService._pause_ai_job()` 现在将已有 Provider 名称、模型、脱敏来源 request ID、累计 Token 和 HTTP 尝试次数回填到既有 `ai_execution` 白名单字段。标准结果、字段裁决、发布门和失败策略未改变。

## 6. 合成 fixture 与离线摘要结果

所有场景均使用：单 Sheet、单行合成工作簿（`No.`、`Item`、`Specification`、`Qty` / `1`、`Duvet Cover`、`White cotton`、`12`）、`VolcengineArkFullOrderProvider`、FakeTransport、FakeDictionaryValidator 和 FakeMaterialMatcher。

| 场景 | Job / 门 | 安全诊断事实 |
| --- | --- | --- |
| 成功 | `completed`；ready 与五角色均为真 | `function_call`；1 逻辑调用、1 HTTP 尝试、usage `11/7/18`；Provider/模型已记录，request ID 为 `sha256:d193af157149`。Fake 字典和匹配各调用一次，正式 20 字段及 float 相似分数通过。 |
| HTTP 400 | `awaiting_user_decision`；五角色为假 | 安全错误码 `AI_SCHEMA_OR_EVIDENCE_FAILED`；解析阶段 `http_status`；1 次 HTTP 尝试；Provider/模型与 `sha256:a59cd5187456` 在清理前形成，usage 为 `0/0/0`。下游均未调用。 |
| 严格 Schema | `awaiting_user_decision`；五角色为假 | 模型注入 `物料编码` 字段，既有额外字段拒绝保持有效；返回形态 `function_call`，阶段 `strict_schema`，usage `11/7/18`，下游未调用。 |
| 伪造证据 | `awaiting_user_decision`；五角色为假 | 不存在 evidence ID 继续被拒绝；阶段 `evidence_reference`，证据失败标志为真，下游未调用。 |
| 断言异常 | Job 已完成 | 验收器在注入 `AssertionError` 后仍先形成安全摘要：异常只记录类名，五角色为真。 |
| 失败/中断 | `failed` / `interrupted` | 对已有 Job 使用同一白名单快照，状态、阶段和回退字段均可安全读取。 |

所有 `TemporaryDirectory` 场景均在摘要断言后退出，并验证根目录不存在；因此 Job、缓存、工作簿、staging Bundle 和日志不会遗留。

## 7. 测试与离线边界

执行：

```powershell
$env:LLM_ENABLED='false'; $env:ARK_API_KEY=''; $env:LLM_MAX_RETRIES='0'
.\.venv\Scripts\python.exe -m pytest tests\ai_full_order\test_acceptance_diagnostics.py tests\ai_full_order\test_volcengine_ark_full_order_provider.py tests\llm\test_volcengine_ark_provider.py tests\web\test_ai_full_order_jobs.py tests\web\test_gate4c2_routes.py tests\web\test_gate4c2_frontend.py tests\web\test_ai_advisory.py tests\web\test_services.py tests\web\test_routes.py tests\desktop\test_server_controller.py -q
```

结果：`117 passed in 14.96s`。

另执行：

```powershell
git diff --check
.\.venv\Scripts\python.exe -m compileall -q src
```

均通过。新增诊断测试以 autouse fixture 替换 `UrllibJSONTransport.send()` 为立即失败的断言，任何误走真实网络路径都会失败。

- 真实网络/API：`0`
- 真实 Ark：`0`
- BGE-M3：`0`
- FAISS：`0`
- 真实物料库：`0`
- 真实 PI：`0`

未运行完整 pytest，也未安装依赖。

## 8. 修改文件

- `src/bedding_order_parser/ai_full_order/volcengine_ark.py`
- `src/bedding_order_parser/web/services.py`
- `tests/ai_full_order/test_acceptance_diagnostics.py`
- `docs/reports/GATE_4D_D2B_REAL_ACCEPTANCE_DIAGNOSTICS_OFFLINE_REPORT.md`

提交信息：`fix: preserve safe full-order failure diagnostics`

完整提交哈希以提交后的 Git 核验和最终回复为准。

## 9. 最终状态

诊断闭环已准备好供未来经授权的真实验收脚本使用：脚本必须在临时目录退出前、在 `finally` 内输出此白名单摘要。D2A 的真实第二次响应不被重新解释，也未因本 Gate 新增真实调用。
