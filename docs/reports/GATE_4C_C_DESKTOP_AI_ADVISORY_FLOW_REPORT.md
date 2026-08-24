# Gate 4C-C 桌面端 AI 单记录建议流程报告

## 1. 任务目标

本轮将现有火山方舟豆包 Provider 接入桌面端的单记录、用户主动触发
流程。AI 结果以独立 sidecar 保存和展示，不修改正式 20 字段业务 JSON、
字典验证结果、物料匹配候选或匹配摘要。

## 2. Git 基线

- 初始 HEAD：`8d3dad8f818af4cd5261b9f0c65e726147f9ecb4`
- 初始短 HEAD：`8d3dad8`
- 最新提交：`test: validate volcengine ark real calls`
- 初始工作区：干净

## 3. 最终交互设计

1. 上传页 AI 选项改为“允许手动生成 AI 建议”。
2. 勾选选项只在 Job 元数据中记录许可，不调用模型。
3. 原 Job 必须先完成确定性解析、字典验证和物料匹配。
4. 仅对 `insufficient_evidence`、`ambiguous_tie`、`no_candidate` 和
   `ranked_candidates` 记录开放入口。
5. 用户在单条匹配详情中点击“生成AI建议”。
6. 页面再次确认将调用豆包、产生少量 Token 费用、结果仅供参考且不会
   自动写回。
7. 调用期间按钮不可重复点击，页面轮询该记录状态。
8. 成功后展示结构化建议；重启或重新进入页面时直接读取缓存。

## 4. Route 与状态机

正式接口如下：

- `POST /api/tasks/<job-id>/ai-enhance`
  - 只接收 Job 和记录身份；
  - 启动一条记录的 AI 建议；
  - 新任务返回 HTTP 202，缓存命中返回 HTTP 200。
- `GET /api/jobs/<job-id>/matches/<index>/ai-advisory`
  - 查询 `not_requested`、`running`、`completed`、`failed` 或
    `cached` 状态；
  - 成功时返回严格 sidecar；
  - 失败时只返回脱敏错误分类、消息、尝试次数和掩码 request ID。
- 现有匹配详情接口同时返回该记录的 AI 状态，供页面统一渲染。

主 Job 状态不承载 AI 子任务状态，因此 AI 失败不会把 completed Job 改成
failed。桌面关闭时，若 AI 正在运行，会显示包含结果中断和 Token 费用说明
的关闭确认。

## 5. 单记录定位与证据来源

稳定身份由以下值共同确定：

- 原 PI 文件名；
- Sheet；
- 订单行号；
- 同一三元组重复时追加记录索引。

最终 `source_record_id` 为上述规范字符串的 SHA-256。H Hotel 订单行 39
得到的 ID 与 Gate 4C-B 完全一致。

后端不使用前端传入的业务字段。它根据 Job 元数据重新读取并关联：

- 正式业务 JSON；
- parse report；
- dictionary validation；
- material match candidates。

发给 Provider 的内容限定为本条记录的原始产品证据、产品字段、字段诊断、
字典验证和前三个候选摘要。路径被限制在 Job 目录内，文件名只保留 basename。
产品文本进入请求前还会过滤电话、邮箱、地址和联系人标签；整份 PI、其他
记录、API Key、本机路径和客户联系信息不会进入请求。

## 6. Sidecar 结构与发布

成功结果保存到：

```text
<Job>/ai-advisory/sha256_<digest>.json
```

文件复用现有严格 `FINAL_ADVISORY_SCHEMA`，包含：

- schema version、provider、model、request ID；
- source record ID；
- action、confidence、suggested fields；
- material assessment、reasoning summary；
- warnings、evidence references；
- Token usage、latency、attempt count；
- 固定的 `advisory_only: true`。

只有在本地严格 Schema 和 source ID 校验通过后，才通过原子 JSON writer
发布。sidecar 不保存 Authorization、API Key、Provider 原始响应、日志或
私有思维链。

## 7. 幂等、缓存与费用保护

- 同一 Job 同一记录重复点击只返回同一个 running 状态；
- 已有 sidecar 时直接返回 completed/cached，不再提交 Provider；
- 不同记录通过全局单活动记录保护串行执行；
- AI 与解析任务复用现有单线程任务执行器，不与 BGE-M3/FAISS 并行；
- 本轮没有增加业务级自动重试；
- Provider 内既有有限重试规则保持不变；
- 应用重启后，真实 H Hotel 记录返回 `cached`，页面显示“已读取缓存”；
- 本轮真实 Provider 逻辑调用恰好一次。

## 8. AI 失败与主 Job 隔离

离线测试覆盖 Provider 失败：

- 主 Job 保持 completed；
- 正式业务、匹配候选和 ZIP 哈希保持不变；
- sidecar 不发布；
- 状态保存脱敏错误分类、通用中文消息、attempt count 和掩码 request ID；
- Provider 原始错误详情不会进入 API 响应。

配置 disabled、缺 Key、缺 model 的既有 LLM 配置合同继续由
`tests/llm` 覆盖；未 ready 时不会进入真实 Provider。

## 9. UI 变化

匹配详情新增独立“AI辅助建议”区域，保持原有黑白灰商务风格，展示：

- 建议动作和置信度；
- 建议字段表；
- 物料评估；
- 简明依据；
- 警告和证据引用；
- 模型、Token、耗时和尝试次数；
- “仅供参考，不会自动写回”。

页面支持未请求、运行、失败、完成和缓存状态。真实验收中按钮、费用提示、
完成结果及缓存结果均正常；页面无横向溢出。

## 10. ZIP 设计

没有 sidecar 时不重建 ZIP，原行为完全不变。

成功 sidecar 生成后，使用临时 ZIP 和原子替换方式保留原五类 JSON，并新增：

```text
AI建议/<source-id-prefix>_AI建议.json
```

真实验收 ZIP 共 6 项：原五类 JSON 5 项、AI 建议 1 项。状态文件、日志、
API Key、原始 HTTP 响应和本机路径均未加入 ZIP。若 ZIP 更新失败，已通过
Schema 的 sidecar 仍保持成功，状态会记录 ZIP 未纳入，不反向破坏建议结果。

## 11. 修改文件

生产代码：

- `src/bedding_order_parser/desktop/launcher.py`
- `src/bedding_order_parser/llm/contracts.py`
- `src/bedding_order_parser/llm/diagnostics.py`
- `src/bedding_order_parser/web/ai_advisory.py`
- `src/bedding_order_parser/web/routes.py`
- `src/bedding_order_parser/web/services.py`
- `src/bedding_order_parser/web/static/app.js`
- `src/bedding_order_parser/web/static/styles.css`

测试：

- `tests/desktop/test_launcher.py`
- `tests/web/test_ai_advisory.py`
- `tests/web/test_gate4b_frontend.py`
- `tests/web/test_gate4b_routes.py`
- `tests/web/test_routes.py`
- `tests/web/test_services.py`

文档：

- `docs/reports/GATE_4C_C_DESKTOP_AI_ADVISORY_FLOW_REPORT.md`

未修改 parser、20 字段合同、字典验证、Embedding Worker、BGE-M3、FAISS、
SQLite、混合评分、Top 300、字段权重或硬冲突规则。

## 12. 定向测试

最终命令：

```powershell
uv run pytest tests/llm tests/web tests/desktop -q
```

结果：

```text
122 passed in 9.69s
```

覆盖 completed Job 限制、稳定身份、服务端证据重建、隐私过滤、原子 sidecar、
严格 Schema、状态机、重复点击、全局串行、缓存、重启读取、Provider 错误
脱敏、主 Job 隔离、ZIP、上传许可、API、UI 和桌面关闭确认。

所有 pytest 使用 Fake Provider/Transport，没有真实网络请求。未运行完整
pytest。

## 13. 一次真实 H Hotel 调用

- 来源：已有 completed H Hotel 桌面 Job；
- 记录：订单行 39，`insufficient_evidence`；
- 触发方式：桌面本地页面单条按钮，经正式 HTTP 业务路由；
- 逻辑调用次数：1；
- Provider 重试：0；
- 模型：`doubao-seed-2-0-lite-260428`；
- source record ID：
  `sha256:1675f3bf65c57b159d7d9eaf3a47983a4f5cacd1435c6f2edd07deb591f1e725`；
- action：`insufficient_evidence`；
- confidence：`0.3`；
- suggested fields：`0`；
- material assessment：`insufficient_evidence`；
- Token：`2598`；
- latency：`12750 ms`；
- attempt count：`1`；
- request ID：`resp_0...c3d6`。

没有重新解析 PI，没有运行 BGE-M3、FAISS 或完整物料匹配。

## 14. 正式结果保护

正式 20 字段业务 JSON 调用前后 SHA-256：

```text
6F53509593BBEC402466F5409702E02EB88E7B7BBB9858FAD7EB7BC9BA5E5CDD
```

物料匹配候选 JSON 调用前后 SHA-256：

```text
3B9266A9EAFB535910D38A7FF392C98103153EEFF6C3C8FBA5B20D141C41817E
```

两者均完全一致，主 Job 最终状态仍为 completed。ZIP 因加入 sidecar 按设计
发生变化，原五类内容仍保留。

## 15. 桌面关闭与缓存复验

首次真实调用完成后：

- 桌面正常关闭：成功；
- 8000 端口释放：是；
- `pythonw` 残留：0。

再次启动桌面后：

- 状态：`cached`；
- 页面显示“已读取缓存”；
- 没有第二次 Provider 调用；
- 再次正常关闭成功；
- 8000 端口再次释放；
- `pythonw` 残留：0。

## 16. API Key 泄露检查

- 当前配置状态：ready；
- Key configured：true；
- Key 长度：46；
- 包含空白：false；
- Git 差异包含 Key：否；
- sidecar/status 包含 Key：否；
- ZIP 包含 Key：否；
- sidecar 包含 Authorization：否；
- 报告包含 Key、前缀、后缀或请求头：否。

## 17. 未执行事项

- 第二次真实 AI 业务调用：未执行；
- 自动批量 AI：未实现；
- 新 PI 或整份 PI：未处理；
- BGE-M3、Torch、FAISS：未运行或加载；
- Embedding：未生成；
- PyInstaller、Onedir、Onefile：未执行；
- LLM 工具、图片、联网搜索、Agent 循环：未调用；
- Day01：未修改；
- push、tag、amend：未执行。

## 18. 最终提交

- 提交信息：`feat: connect desktop ai advisory flow`
- 提交范围：本报告第 11 节列出的实现、测试和本报告
- push：否
- tag：否
- amend：否

本报告与实现位于同一提交；最终提交哈希以提交后的 Git 输出为准。

## 19. 下一阶段条件

Gate 4C-C 已具备进入下一阶段的条件：单记录主动触发、严格 sidecar、缓存、
费用保护、正式结果隔离、ZIP、桌面展示和生命周期均已验证。

下一步唯一建议：

Gate 4C-D：从新上传一份 PI 开始，完成“确定性解析 → 物料匹配 → 用户手动
单记录 AI 建议 → Sidecar → 下载”的桌面端最终全流程验收。
