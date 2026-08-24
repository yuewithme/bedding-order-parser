# Gate 4C-D2A 豆包真实返回格式兼容修复报告

生成时间：2026-08-01
项目目录：D:\AI-Learning\Projects\bedding-order-parser

## 1. D1实际Commit

- D1 HEAD：126e67e2e3a5d71f7793c8fe6ca6a514cc3d39dd
- D1短哈希：126e67e
- D1提交信息：feat: localize desktop ai advisory
- 启动检查结果：D1代码和 D1 报告已经提交。

## 2. 两次用户失败调用的可用脱敏证据

用户报告在正式桌面端手动点击两次“AI复核建议”，页面均显示“AI复核建议未生成 / 模型返回格式不符合要求”。本地持久化采用同一 source_record_id 的状态文件覆盖写入，因此只保留最后一次失败状态，未保留两份独立失败快照。

可用脱敏证据如下：

- Job：29c84b45dce04a1b92f4f158029f8fd9
- 记录：record_index 0
- source_record_id：sha256:bd194b4c9e5f312f226c6f6367327b8ae0eeb12d2ba7aa4c3e386cbb249b7a04
- 失败状态时间：2026-08-01T22:02:51+08:00
- operation：generate_chinese
- state：failed
- error.code：structured_output_error
- error.message：AI复核建议调用失败：模型返回格式不符合要求。请检查配置或稍后手动重试。
- attempt_count：1
- request_id：resp_0...9e00
- Sidecar：未生成
- 主 Job 状态：completed

旧状态文件未保存 schema_path、response_item_types、has_function_call、has_output_text、missing_keys、extra_keys、actual_type 等细粒度字段，因此无法从历史落盘数据还原第二次失败的完整响应形态或具体原始字段值。

## 3. 实际失败阶段

历史状态能确认失败不在 HTTP 层：已有 Provider request_id 且错误码为 structured_output_error。本轮将失败归类为本地 Provider 结构化输出提取、规范化或严格 Schema 校验阶段，而不是主 Job、路由、Sidecar 读写、中文检测或页面渲染阶段。

修复后同一 Job、同一 record_index、同一 source_record_id、同一模型通过正式业务路由真实调用成功，说明原始问题位于 Ark Responses API 真实等价响应与本地严格合同之间的兼容层。

## 4. 具体失败字段或Schema路径

历史失败状态没有保存具体 schema_path。本轮新增了安全诊断后，后续若再失败会记录：error_stage、schema_path、missing_keys、extra_keys、expected_type、actual_type、invalid_enum_value、source_record_id_match、response_item_types、has_function_call、has_output_text。

本轮最小兼容修复覆盖并测试的实际本地合同路径包括：

- $.output：Responses output 不是数组或没有可用 function_call / output_text 时定位到该路径。
- $.output[].arguments：function_call arguments 不是 JSON 对象文本或 JSON 对象时定位到该路径。
- $.output_text：顶层 output_text JSON 解析失败时定位到该路径。
- $.confidence：模型返回数字字符串时安全规范化为 number；非法字符串仍以 actual_type=string 拒绝。
- $.action：枚举错误仍拒绝。
- $.source_record_id：与请求记录不一致仍拒绝。
- $：缺失字段或额外字段仍拒绝。

## 5. 根本原因

根本原因是 Ark Responses API 的真实返回形态与本地实现之间存在兼容缺口，旧实现在失败时只把所有提取、JSON 解析、Schema 校验问题折叠为 structured_output_error，导致页面只能显示“模型返回格式不符合要求”。

本轮修复没有放宽业务合同，而是在 Provider 边界补齐等价响应解析、数字字符串的安全规范化和脱敏诊断。修复后同一记录真实调用成功生成严格中文 Sidecar。

## 6. 是否属于Provider解析、Schema或中文检测

- Provider 解析/规范化：是，本轮修复重点。
- 严格 Schema：是，保留并增强诊断。
- 中文检测：否。本次成功 Sidecar language_status=zh_cn，页面显示中文动态说明。
- HTTP 或鉴权：否。失败和成功调用均有 request_id，成功调用 status=succeeded。

## 7. 修复方案

修复内容：

1. Ark Provider 支持顶层 output_text JSON、message.content output_text JSON、顶层 function_call，以及等价嵌套 function_call/function 工具包装。
2. function arguments 解析失败时记录 function_call_arguments_parse 或 output_text_json_parse 阶段。
3. 对 confidence 这类明确数字字符串进行安全 float 规范化；非法数字字符串仍失败。
4. usage token 的数字字符串规范化为非负整数。
5. SchemaValidationError 增加 path 和 diagnostic。
6. validate_json_schema 对缺字段、多余字段、类型错误、枚举错误、source_record_id 错位输出安全诊断。
7. AIAdvisoryManager 只持久化白名单诊断字段，不保存原始响应、请求体、订单正文或密钥。

## 8. 未放宽的安全约束

未放宽以下约束：

- 不接受任意字典。
- 不关闭严格 Schema。
- 不忽略额外字段。
- 不删除 source_record_id 校验。
- 不删除 advisory_only=true。
- 不允许 confirmed 物料状态。
- 不允许 ERP 写回。
- 不自动把英文建议伪装成中文。
- 不提交真实 Sidecar、真实 Job 数据或原始 Provider 响应。

## 9. 新增脱敏fixture

新增离线等价 fixture 覆盖：

- 顶层 output_text JSON。
- 嵌套 function_call/function 响应形态。
- confidence 数字字符串。
- usage token 数字字符串。
- 缺字段。
- 多余字段。
- 错误类型。
- 错误枚举。
- source_record_id 错位。
- output_text 非法 JSON。
- Web 状态只持久化安全诊断字段。

所有 fixture 均为人工构造的脱敏结构，没有提交真实原始 Provider 响应。

## 10. 定向测试命令与结果

执行命令：

    uv run pytest tests/llm/test_volcengine_ark_provider.py tests/web/test_ai_advisory.py tests/web/test_services.py -q

结果：78 passed in 3.29s

额外真实 Sidecar Schema 校验：sidecar_schema=passed

未运行完整 pytest，未运行 BGE-M3、FAISS 或重新解析 PI。

## 11. 真实调用次数

真实豆包逻辑调用次数：1

说明：历史证据不足以定位细粒度路径；用户显式授权后，通过正式业务路由对同一 Job、同一记录发起一次真实调用。修复后该调用直接成功，因此未执行第二次真实调用。

## 12. 最终复验结果

最终复验通过。

- 调用成功：是
- 返回动态说明为简体中文：是
- 页面能够正常展示：是
- 字段建议能够展示：是，6 条
- 整体建议能够展示：是
- 物料评估能够展示：是
- 技术详情默认折叠：是
- Sidecar严格Schema通过：是
- source_record_id一致：是
- advisory_only=true：是
- 再次查看读取缓存：是
- 再次查看不增加Provider调用：是，浏览器二次查看 ai-enhance POST 为 0
- 缓存启动接口返回 cached：是
- 主Job仍为 completed：是

## 13. 模型、Token、耗时、attempt count和脱敏request ID

- 模型：doubao-seed-2-0-lite-260428
- request ID：resp_0...13da
- input_tokens：2537
- output_tokens：927
- total_tokens：3464
- latency_ms：23641
- attempt_count：1
- provider：volcengine_ark
- finish_status：completed

## 14. 中文页面展示

Playwright + Edge 访问正式桌面服务 http://127.0.0.1:8000 的匹配详情页，结果：

- AI复核建议区域显示。
- 状态显示为“已读取缓存”。
- AI复核结论显示为“建议人工核查”。
- 主要依据为简体中文。
- 建议修改字段显示 6 行：物料名称、款式、加标方式、尺寸类型、包装方式、是否绣花。
- 物料评估说明显示。
- 风险提示显示。
- 技术详情 details 默认 closed。
- 1440px 桌面无页面横向溢出。
- 390px 移动视口无页面级横向溢出。
- 外部请求数：0。
- 页面二次查看 ai-enhance POST：0。

## 15. Sidecar与缓存

成功 Sidecar：

C:\Users\alyar\AppData\Local\BeddingOrderParser\tasks\jobs\29c84b45dce04a1b92f4f158029f8fd9\ai-advisory\sha256_bd194b4c9e5f312f226c6f6367327b8ae0eeb12d2ba7aa4c3e386cbb249b7a04.json

状态文件：

C:\Users\alyar\AppData\Local\BeddingOrderParser\tasks\jobs\29c84b45dce04a1b92f4f158029f8fd9\ai-advisory\sha256_bd194b4c9e5f312f226c6f6367327b8ae0eeb12d2ba7aa4c3e386cbb249b7a04.status.json

状态：completed，operation=generate_chinese，zip_included=false，core_zip_refreshed=true。

缓存验证：再次通过正式 ai-enhance 路由提交同一身份，返回 state=cached，状态文件 mtime 未变化，request_id 仍为 resp_0...13da，未产生新 Provider 调用。

## 16. 五类JSON和ZIP保护

主 Job：completed

核心产物 SHA：

- 正式业务 JSON：6f53509593bbec402466f5409702e02eb88e7b7bbb9858fad7eb7bc9ba5e5cdd
- 解析诊断 JSON：0efe40eccbb1815d7e93ae68d759ae0213d71d230e4150e53afb6af0783eabf7
- 字典验证 JSON：4d26278db9376e5bee79d3ed66ba9adb6e4b9ee0df42a462e5d1a625c46bd472
- 匹配候选 JSON：3b9266a9eafb535910d38a7ff392c98103153eeff6c3c8fba5b20d141c41817e
- 匹配摘要 JSON：3056c70faa48e7ed12c26f50a030983e8b7071e5c678018b84f64d02f26333ca

默认 ZIP 条目仍只有五类核心 JSON：

- 正式业务.json
- 解析诊断.json
- 字典验证.json
- 匹配候选.json
- 匹配摘要.json

ZIP 不包含 AI建议目录或 Sidecar。

## 17. API Key泄露检查

检查结果：无泄露。

执行 diff 扫描未发现 ARK_API_KEY、Authorization、Bearer、api_key 明文赋值或 PRIVATE KEY。真实调用命令和报告均未输出 API Key、Authorization、完整请求体、完整 Provider 原始响应、完整订单内容、联系人信息或本机私有思维链。

## 18. 桌面关闭、端口和残留进程

当前用户正式桌面服务仍在运行：runtime.json 显示 http://127.0.0.1:8000，pid=50632。本轮没有关闭用户桌面进程。

本轮脚本内临时启动的本地 HTTP server 均已 server.shutdown、server_close，并 join 线程；未留下额外长期监听端口。

## 19. 最终Commit

提交信息：fix: handle real ark advisory responses

说明：报告文件在同一个提交中，Git 提交哈希存在自引用问题，无法在提交前写入自身最终哈希。最终短哈希以提交后的 git log -1 输出和本轮最终回复为准。

## 20. 工作区

提交前修改范围：

- src/bedding_order_parser/llm/advisory_schema.py
- src/bedding_order_parser/llm/errors.py
- src/bedding_order_parser/llm/volcengine_ark.py
- src/bedding_order_parser/web/ai_advisory.py
- tests/llm/test_volcengine_ark_provider.py
- tests/web/test_ai_advisory.py
- docs/reports/GATE_4C_D2A_REAL_RESPONSE_COMPATIBILITY_FIX_REPORT.md

不提交两份既有未跟踪恢复文档：

- CODEX_HANDOFF_AND_RECOVERY_2026-07-30.md
- CODEX_RECOVERY_AUDIT_ROUND_1_REPORT_2026-08-01.md

## 21. 标准解析模式是否可以冻结

可以冻结。

标准解析模式保持确定性：AI 仍只在用户手动确认单记录复核时调用；AI 结果只写独立 Sidecar，不修改正式 20 字段 JSON、物料候选 JSON、解析诊断、字典验证或默认 ZIP 的五类核心 JSON。

## 22. 下一步唯一建议

Gate 4D-A：设计AI增强整单解析模式的严格合同。
