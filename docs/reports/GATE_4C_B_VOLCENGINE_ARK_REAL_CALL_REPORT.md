# Gate 4C-B：火山方舟豆包首次真实调用报告

## 1. 任务目标

本轮在不接入桌面业务流程、不处理整份 PI 的前提下，通过项目真实
Provider 链路完成两次逻辑调用：

1. 一次最小非流式连通性调用；
2. 一次 H Hotel 单记录严格结构化 sidecar 建议调用。

## 2. Git 基线

- 初始 HEAD：`8cd90ed675854bc6e16986e93ef553180d8ea4fa`
- 初始短 HEAD：`8cd90ed`
- 最新提交：`feat: add volcengine ark llm provider`
- 初始工作区：干净

## 3. 配置 ready 检查

- `LLM_ENABLED`：符合 `true`
- `LLM_PROVIDER`：符合 `volcengine_ark`
- Base URL：符合火山方舟北京 Responses API 地址
- 模型：`doubao-seed-2-0-lite-260428`
- 超时：60 秒
- 最大重试：1
- `LLMSettings.configuration_status()`：`ready`

## 4. Key 安全检查

- API Key configured：`true`
- 长度：46
- 包含空白：`false`
- Key 原文、前缀、后缀、Authorization 值：均未输出或写入报告
- 当前 Git 差异中检出真实 Key：否

## 5. 最小连通性调用

- 状态：成功
- 调用方式：非流式 Responses API
- 工具：无
- 文件或订单数据：无
- `store`：`false`
- 输出上限：64 Token
- 返回文本符合“连接成功”：是

## 6. 实际 API 与模型

- Provider：`volcengine_ark`
- API：`POST /responses`
- 实际模型：`doubao-seed-2-0-lite-260428`
- Provider 状态：`completed`

## 7. 最小调用元数据

- request ID：`resp_0...d2cb`
- input tokens：46
- output tokens：36
- total tokens：82
- latency：3547 ms
- attempt count：1

## 8. 单记录来源与 source_record_id

- 来源：已有 H Hotel 三记录结果
- 选择依据：订单行 39 的物料匹配决策为 `insufficient_evidence`
- Sheet：`PI`
- 证据单元格：`PI!B52`、`PI!C52`、`PI!D52`
- source_record_id：
  `sha256:1675f3bf65c57b159d7d9eaf3a47983a4f5cacd1435c6f2edd07deb591f1e725`
- 输入输出 ID：完全一致

本轮只读取已有 JSON，不重新解析 Excel。

## 9. 发送的字段名称

仅发送以下字段类别，不在报告中保存完整值：

- `raw_evidence`：商品名称、规格、产品描述三个证据单元格
- `parsed_record`：物料品类、规格、颜色、面料、成分、款式、加标方式、
  尺寸类型、行备注、是否绣花
- `parse_diagnostics`：上述字段的状态、规则和来源单元格
- `dictionary_validation`：物料名称、规格、颜色验证状态
- `top_candidates`：一个候选的编码、分数、可比字段数和字段级状态
- `enhancement_reason`：`insufficient_evidence`

未发送联系人、电话、邮箱、地址、整份 PI、本机路径或其他订单记录。

## 10. 结构化调用结果

- 状态：成功
- request ID：`resp_0...73b6`
- 实际模型：`doubao-seed-2-0-lite-260428`
- Provider 状态：`completed`
- action：`insufficient_evidence`
- confidence：0.23
- suggested fields：0
- material assessment：`insufficient_evidence`
- suggested material code：空
- warnings：2
- evidence references：3
- latency：12171 ms
- attempt count：1

## 11. Schema 验证

- schema version：`1.0`
- 顶层 `additionalProperties: false`：保持
- 本地严格 Schema：通过
- source_record_id 一致性：通过
- action 枚举：通过
- confidence 范围：通过
- suggested_fields 结构：通过
- material_assessment 枚举和空编码约束：通过
- usage、latency、attempt_count：合法

## 12. Advisory 边界

- `advisory_only`：`true`
- confirmed 物料状态：不存在
- ERP 写回动作：不存在
- 确定性字段覆盖：不存在
- 自动确认物料编码：不存在
- 模型在证据不足时选择不建议字段和物料编码，符合边界。

## 13. Token 及费用数据

| 调用 | 输入 Token | 输出 Token | 总 Token |
| --- | ---: | ---: | ---: |
| 最小连通性 | 46 | 36 | 82 |
| 单记录结构化 | 1608 | 424 | 2032 |
| 合计 | 1654 | 460 | 2114 |

API 响应未提供货币账单金额，本报告不推算费用。

## 14. 总逻辑调用次数

- 逻辑调用：2
- 连通性调用：1
- 单记录结构化调用：1
- Provider 重试：0
- 第三次调用：未执行

## 15. Provider 真实响应兼容性

实际 Responses API 返回被现有 JSON Transport 和严格结构化解析路径成功
接受。请求 ID、实际模型、状态、用量和延迟均成功取得；未降低 Schema，
未跳过 source_record_id 校验，也未把真实原始响应加入 Git。

## 16. 实际代码修改

生产代码：

- `src/bedding_order_parser/llm/__init__.py`
- `src/bedding_order_parser/llm/contracts.py`
- `src/bedding_order_parser/llm/diagnostics.py`
- `src/bedding_order_parser/llm/null_provider.py`
- `src/bedding_order_parser/llm/provider.py`
- `src/bedding_order_parser/llm/service.py`
- `src/bedding_order_parser/llm/volcengine_ark.py`

测试：

- `tests/llm/test_diagnostics.py`
- `tests/llm/test_volcengine_ark_provider.py`

实现内容为最小连通性合同、Provider/Service 入口、可复用诊断 CLI 和离线
测试。未修改 Web 路由、前端、解析器或匹配算法。

## 17. 定向测试命令和结果

调用前：

```powershell
uv run pytest tests/llm -q
```

结果：`52 passed in 0.66s`

最终复验：

```powershell
uv run pytest tests/llm tests/web/test_gate4b_routes.py -q
```

结果：`56 passed in 2.71s`

所有 pytest 均使用 FakeTransport，没有发送真实网络请求。未运行完整 pytest。

## 18. API Key 泄露扫描

- 当前差异包含 API Key 原文：否
- 当前差异包含本机用户绝对路径：否
- TEMP 请求或结果被 Git 跟踪：否
- 报告包含 Key、Authorization 值或完整请求/响应：否

## 19. 正式业务结果保护

以下文件调用前后 SHA-256 完全一致：

- 正式 20 字段 JSON：
  `6F53509593BBEC402466F5409702E02EB88E7B7BBB9858FAD7EB7BC9BA5E5CDD`
- parse report：
  `2CA868419D88031D81ECCA5A41B58C6437772146EBCBC65CBD6DFED555F6E616`
- dictionary validation：
  `4D26278DB9376E5BEE79D3ED66BA9ADB6E4B9EE0DF42A462E5D1A625C46BD472`
- material match candidates：
  `3B9266A9EAFB535910D38A7FF392C98103153EEFF6C3C8FBA5B20D141C41817E`

parser、字典验证和物料匹配算法均未修改。

## 20. 未接入桌面业务流程

- AI 开关：未修改
- `/ai-enhance` 正式业务路由：仍未接入任务流程
- 自动 Provider 调用：未启用
- AI sidecar：只存在于 Windows TEMP 验证结果

## 21. 未执行事项

- 真实 PI 解析：未执行
- 整份 PI 处理：未执行
- 12 份 PI：未执行
- BGE-M3：未运行
- Torch 模型：未加载
- FAISS：未运行
- Embedding：未生成
- PyInstaller/桌面打包：未执行
- LLM 工具、图片或联网搜索：未调用

## 22. 最终 Commit

- 提交信息：`test: validate volcengine ark real calls`
- 提交范围：本报告第 16 节列出的代码、测试及本报告
- push：否
- tag：否
- amend：否

本报告与代码位于同一提交；最终哈希以提交后 Git 输出为准。

## 23. 工作区

提交前变更仅限 Gate 4C-B 的 LLM 代码、定向测试和本报告。提交后要求工作区
干净。TEMP 中的真实请求和 sidecar 不进入 Git。

Day01：

- HEAD：`b6206bf28a9ce5499e317cee324b16ea98bf569d`
- 工作区：干净

## 24. 是否达到下一阶段条件

达到。两次真实调用成功，实际模型和 Responses API 可用，严格 Schema、
source_record_id、advisory_only 和业务文件保护全部通过。

## 25. 下一步唯一建议

**Gate 4C-C：将 AI 增强路由接入单记录 sidecar 流程，并连接桌面端用户主动
开关。**
