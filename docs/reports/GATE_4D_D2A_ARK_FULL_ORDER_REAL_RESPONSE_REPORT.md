# Gate 4D-D2A 火山方舟 AI 整单真实响应小样本验收报告

## 1. 验收结论

本 Gate **未通过完整验收**。

- 第 1 次真实调用的结构识别严格通过。
- 第 2 次真实调用已按授权通过正式桌面 `ai_enhanced` Job 发起，但 Job 未进入 `completed`，因此不能证明字段提取、整批 ready 门和五类结果完整发布。
- 两次逻辑调用、两次 HTTP 尝试的预算已经全部耗尽，未重试、未切换模型、未增加预算。
- 第二次进程在本地完成态断言处终止，安全摘要尚未输出；临时 Job 随后自动清理，所以第二次返回形态、Token、延迟和具体安全错误码无法恢复。本报告不猜测这些数据。
- 没有足够证据证明是等价真实返回形态差异，故未做 Provider 兼容修复，也未放宽任何严格合同。

## 2. 调用前审计

- 分支：`master`
- 开始完整 HEAD：`0bf841fab4caf1144a21672c72f108f6985cd09e`
- 开始提交：`feat: connect ark full-order desktop provider`
- 开始工作区仅有三份已知未跟踪交接文档，无未知业务修改。
- Ark 配置状态：`ready`
- Provider：`volcengine_ark`
- 模型：`doubao-seed-2-0-lite-260428`
- Base URL：`https://ark.cn-beijing.volces.com/api/v3`
- API Key：已配置，仅检查布尔状态，未输出值。
- 本机环境原始 `LLM_MAX_RETRIES` 为 `1`；两个真实调用进程均显式覆盖为 `0`，并在调用前断言实际设置为 `0`。
- 请求均使用 Ark Responses API、`store=false`；`stream` 未设置，采用 API 默认非流式行为。
- 调用前逻辑调用数和 HTTP 尝试数均为 `0`。

合成数据审计：

- 第 1 次仅发送人工合成的区块清单，scope、chunk、block 和记录身份均为 `synthetic` 标识。
- 第 2 次使用内存生成的单 Sheet、单记录工作簿：表头为 `No.`、`Item`、`Specification`、`Qty`，数据为 `1`、`Duvet Cover`、`White cotton`、`12`。
- 不含真实客户、联系人、银行信息、真实物料主数据或真实 PI。
- Transport 在发送前断言正文不包含 API Key、Authorization、本机临时目录、桌面 Job ID 或 Excel 二进制。
- 完整请求、完整外发正文、原始响应和系统提示均未落盘或打印。

## 3. 第一次真实调用：结构识别

- 入口：`VolcengineArkFullOrderProvider.resolve_structure()`
- 数据：最小人工合成歧义结构区块。
- 结果：通过严格结构识别合同。
- 返回状态：`ambiguous`
- 返回形态：`function_call`
- Provider：`volcengine_ark`
- 模型：`doubao-seed-2-0-lite-260428`
- 脱敏 request ID：`sha256:fa62d04ab348`
- input tokens：`596`
- output tokens：`38`
- total tokens：`634`
- 延迟：`2704 ms`
- HTTP 尝试：`1`
- 本地 cache identity 未发送。
- 严格对象字段与状态枚举校验：通过。

## 4. 第二次真实调用：正式桌面 Job

- 入口：`JobService` 正式 `ai_enhanced` 路径。
- 工作簿结构：本地明确，仅应调用一次 `extract()`，不调用 `resolve_structure()`。
- 下游：`FakeDictionaryValidator` 与 `FakeMaterialMatcher`；未加载真实字典工作簿、BGE-M3、FAISS 或真实物料库。
- 预检：`ready=true`，且预检、Job 创建阶段 Transport 调用数保持 `0`。
- 真实逻辑调用：`1`
- HTTP 尝试：`1`
- 重试：`0`
- 最终本地断言：`completed["status"] == "completed"` 失败。
- 正式链路验收：未通过。
- 五类结果完整发布：未能证明；Job 未进入完成态。
- 返回形态：无法安全恢复。
- 脱敏 request ID：无法安全恢复。
- input/output/total tokens：无法安全恢复。
- 延迟：无法安全恢复。
- Schema、身份、scope、证据和禁止字段验证的具体失败环节：无法从已清理的临时状态安全恢复，不能据此实施兼容修复。

第二次脚本只在所有合同、五类产物、正式 20 字段和 Transport 元数据断言全部通过后才输出安全摘要。失败发生在 Job 完成态断言，因此后续断言没有执行。为遵守预算，没有再次调用真实 API。

## 5. 调用预算与安全计数

- 授权逻辑调用上限：`2`
- 实际逻辑调用：`2`
- 授权 HTTP 尝试上限：`2`
- 实际 HTTP 尝试：`2`
- 每次调用最大重试：`0`
- 额外重试：`0`
- 模型切换：`0`
- 真实 PI：`0`
- BGE-M3：`0`
- FAISS：`0`
- 真实物料匹配：`0`

## 6. 兼容修复

- 生产代码修复：`0`
- 脱敏真实响应 fixture：`0`
- 原因：第二次安全摘要没有形成，无法证明失败来自可接受的等价响应形态；在证据不足时修改 Provider 会有放宽合同或猜测兼容的风险。
- 17 字段、正式行号、证据验证、身份、scope、禁止字段、字段裁决、缓存身份、发布门、标准模式、C2 UI 和单记录 Sidecar 均未修改。

## 7. 离线回归

真实调用结束后，测试进程显式设置 `LLM_ENABLED=false`、清空 `ARK_API_KEY` 并保持 `LLM_MAX_RETRIES=0`，执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ai_full_order\test_volcengine_ark_full_order_provider.py tests\llm\test_volcengine_ark_provider.py tests\web\test_ai_full_order_jobs.py tests\web\test_gate4c2_routes.py tests\web\test_gate4c2_frontend.py tests\web\test_ai_advisory.py tests\web\test_services.py tests\web\test_routes.py tests\desktop\test_server_controller.py -q
```

结果：`112 passed in 13.16s`。

附加检查：

```powershell
git diff --check
.\.venv\Scripts\python.exe -m compileall -q src
```

均通过。标准模式、单记录 Ark Provider、C1/C2 预检与 UI 合同未出现离线回归。

## 8. 临时数据与敏感信息

- 两次真实响应仅在调用进程内存中由现有 Provider 解析，没有保存原始响应。
- 第二次合成工作簿、Job、reliability 状态和五类暂存目录位于 `TemporaryDirectory`，进程退出后已自动清理。
- 未保存或提交完整 HTTP 请求、原始响应、Authorization、API Key、完整外发正文、系统提示或私有思维链。
- 未生成真实 Sidecar、真实 Job、真实 PI 或额外分析文件。

## 9. 修改文件与提交

本轮只新增：

- `docs/reports/GATE_4D_D2A_ARK_FULL_ORDER_REAL_RESPONSE_REPORT.md`

未修改生产代码、测试、UI、标准解析或既有报告。

提交信息：`test: validate ark full-order real responses`

完整提交哈希以提交后 Git 核验及最终回复为准。

## 10. 最终状态与后续条件

本 Gate 不能声称完成，因为第二次正式桌面链路未通过且预算内无法取得可诊断的安全摘要。

如需继续，必须由用户另行授权新的真实调用预算。下一轮应先改进一次性验收脚本：无论 Job 成功或失败，都在清理前输出并仅输出安全 response shape、脱敏 request ID、usage、延迟、Job 安全错误码和 Provider 计数；不得改变整单合同或扩大数据范围。
