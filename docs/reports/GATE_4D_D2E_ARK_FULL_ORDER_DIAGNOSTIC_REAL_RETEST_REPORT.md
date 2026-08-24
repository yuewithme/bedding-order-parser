# Gate 4D-D2E Ark 整单 extract 白名单诊断真实复验报告

## 1. 结论

本 Gate 授权的一次真实 Ark extract 调用、白名单诊断、临时数据清理、离线回归、报告与提交已闭环，但 **Ark 整单真实协议验收仍未通过**。

- Ark 返回形态为现有已支持的 `function_call`，不是新的 Responses 包装兼容问题。
- 严格合同在 `evidence_validation / field_evidence_requirements` 拒绝模型输出。
- Job 安全进入 `awaiting_user_decision`；没有静默回退、字段裁决完成态、下游调用或五类发布。
- 诊断证明模型字段没有满足冻结的“有值、原值和证据引用必须同时成立”要求，不属于可做等价兼容的 Provider 边界差异。
- 未修改生产代码或测试，未放宽 Schema、类型、枚举、身份、scope、证据、禁止字段或发布门。

## 2. 基线与调用前审计

- 开始分支：`master`
- 开始完整 HEAD：`3f6249fdbbe829b0e0f5bb3d20c97f8e7088d4af`
- 开始提交：`fix: expose safe full-order contract diagnostics`
- 开始工作区：仅有三份既有未跟踪交接/恢复文档，无未知业务修改。
- Ark 配置状态：`ready`
- Provider：`volcengine_ark`
- 模型：`doubao-seed-2-0-lite-260428`
- Base URL：`https://ark.cn-beijing.volces.com/api/v3`
- API Key：仅确认已配置，未输出值。
- 本次进程强制 `LLM_MAX_RETRIES=0`；实际设置读取值为 `0`。
- 请求合同：`store=false`、非流式、严格函数 Schema、固定函数 `submit_bedding_order_full_order`。

正式调用前先运行等价人工合成 fixture 的离线 Provider/Job/发布验证，结果为 `29 passed in 2.17s`。人工合成工作簿仍为单 Sheet、单记录、英文产品描述与数量，不含真实 PI、客户、联系人、银行或物料主数据。

预检和 Job 创建阶段均断言 Transport 尝试数为 `0`；调用前 `structure_call_count=0`、`extraction_call_count=0`。发送前仅在内存中检查请求使用批准模型、正式 Base URL、`store=false`、非流式和严格函数合同，且正文不含 API Key、本机路径、Job ID 或 Excel 二进制；请求正文没有打印或保存。

## 3. 唯一一次真实调用安全摘要

验收脚本在 `finally` 中、临时目录清理前形成摘要，然后才执行调用预算和完成态判定。

### Job 与 Provider

- Job 状态：`awaiting_user_decision`
- AI 阶段：`awaiting_user_decision`
- 安全错误码：`AI_SCHEMA_OR_EVIDENCE_FAILED`
- 回退状态：`not_requested`
- Provider：`volcengine_ark`
- 模型：`doubao-seed-2-0-lite-260428`
- 脱敏 request ID：`sha256:b4f22cafa38a`
- 返回形态：`function_call`
- 安全失败阶段：`evidence_validation`
- 合同失败类别：`field_evidence_requirements`

### 固定路径与白名单差异

D2D 诊断返回了字段路径，但本次验收的二次固定 17 字段核对未能证明该路径后缀属于允许集合。因此本报告不复述该路径文本，也不把它作为业务字段事实；允许保留的有效诊断仅为固定阶段和固定类别。

这暴露出 D2D 路径清洗器的残余缺口：当前实现对 `$.records[]` 后缀的检查仍不够严格。该问题不影响严格合同拒绝、Job 隔离或发布门，但未来再次真实验收前，应单独离线把路径限制为从冻结 Schema 推导出的固定路径集合。D2E 只授权在等价 Provider 响应兼容成立时修改生产代码；本次模型输出未满足证据合同，因此未借本轮扩大修改范围。

### Usage、调用与门状态

- input tokens：`4312`
- output tokens：`1354`
- total tokens：`5666`
- Provider 延迟：`26313 ms`
- 结构识别逻辑调用：`0`
- 字段提取逻辑调用：`1`
- 总逻辑调用：`1`
- HTTP 尝试：`1`
- 重试：`0`
- 已验证 chunk：`0`
- 总 chunk：`1`
- `ready_for_downstream`：`false`
- FakeDictionaryValidator 调用：`0`
- FakeMaterialMatcher 调用：`0`
- 五类角色完整：`false`

调用预算已耗尽；没有第二次调用、模型切换、追加请求或 `resolve_structure()` 调用。

## 4. 失败判断与生产修改

失败发生在已支持的函数参数成功解析之后。固定类别 `field_evidence_requirements` 表明至少一个冻结业务字段的值、原值和证据引用组合不满足现有证据合同。这是模型输出内容未满足合同，不是可安全归一化的 Ark 元数据、usage、函数调用包装或 JSON 等价格式差异。

- 生产代码修改：`0`
- 测试代码修改：`0`
- 人工脱敏真实响应 fixture：`0`
- 猜测性兼容分支：`0`
- 合同放宽：`0`

完整函数参数、模型业务值、evidence ID/文本和原始响应均未持久化或提交，因此没有足够且合规的证据做任何字段级修复。

## 5. 离线回归

真实调用结束后显式设置 `LLM_ENABLED=false`、清空 `ARK_API_KEY` 并保持 `LLM_MAX_RETRIES=0`，执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ai_full_order\test_contracts.py tests\ai_full_order\test_acceptance_diagnostics.py tests\ai_full_order\test_volcengine_ark_full_order_provider.py tests\llm\test_volcengine_ark_provider.py tests\web\test_ai_full_order_jobs.py tests\web\test_gate4c2_routes.py tests\web\test_gate4c2_frontend.py tests\web\test_ai_advisory.py tests\web\test_services.py tests\web\test_routes.py tests\desktop\test_server_controller.py -q
.\.venv\Scripts\python.exe -m compileall -q src
git diff --check
```

实际结果：`148 passed in 17.67s`；编译和 diff 检查通过。标准模式、单记录 AI Sidecar、C1/C2 合同、整单 Provider、诊断器与桌面 Job 均未出现离线回归。未运行完整 pytest。

## 6. 安全、资源与清理

- 实际真实 Ark 逻辑调用：`1`
- 实际 HTTP 尝试：`1`
- 真实 PI、真实字典、真实物料库、BGE-M3、FAISS：均为 `0`
- 完整请求、函数参数、业务字段值、evidence 文本、原始响应、Authorization、API Key、系统提示和思维链：均未保存或提交。
- 合成工作簿、Job、可靠性状态、缓存和 Bundle 均位于 `TemporaryDirectory`。
- 调用后确认 `bedding-d2e-synthetic-*` 临时目录不存在。

运行时摘要曾包含一段未通过二次固定字段核对的路径后缀；该文本只存在于本地即时标准输出，没有保存或提交，本报告和最终交付均不复述。此事实作为 D2D 白名单残余风险如实记录。

## 7. 修改、提交与工作区

本轮只新增：

- `docs/reports/GATE_4D_D2E_ARK_FULL_ORDER_DIAGNOSTIC_REAL_RETEST_REPORT.md`

提交信息：`test: diagnose ark full-order real extraction`。

本报告将在该 Gate 提交中提交；完整哈希和最终工作区由提交后的 Git 核验与最终回复给出。三份既有未跟踪恢复/交接文档继续保留，不暂存、不清理。

## 8. 最终状态

Gate 4D-D2E 的受控真实复验已执行完成；Ark 整单真实协议验收未通过。下一步应先进行纯离线诊断路径白名单收紧，再由任务方决定是否需要新的、独立授权的真实验收；本轮不得追加真实调用。
