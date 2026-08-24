# Gate 4D-D4A-3｜AI 整单完成页 Review Summary、AI/Python 对照与可读证据展示报告

## 1. 基线与提交

- 分支：`master`
- 起始完整 HEAD：`1cc7be557bcc2784bca52d7f6f356f261d402218`
- D4A-2 implementation commit：`0b879b7a9239143e7a84dfd42b7ff322a9592074`
- D4A-2 report commit：`1cc7be557bcc2784bca52d7f6f356f261d402218`
- 本 Gate implementation commit：`d8c8c6dbd566caa1298754953a0c68817e0b1d81`
- implementation 提交信息：`feat: show ai full-order review comparisons`

起始工作区无已跟踪修改；七份既有未跟踪交接/审计文档保持原样，未暂存、未覆盖、未删除。

## 2. 最终架构

本 Gate 没有复制 Job 状态中的决策数据，也没有改变 D4A-1/D4A-2 的字段选择与 technical-ready 合同。最终数据流为：

```text
V2 五类 Bundle 中的 parse_diagnostics
  -> 本地白名单 Review Adapter
  -> Job API 摘要 + /api/jobs/{job_id}/ai-review 详情
  -> AI Enhanced 完成页
```

选择 `parse_diagnostics` 作为单一事实来源有三点原因：

1. comparison、正式值、选择来源和 evidence ID 已随原子 Bundle 固化；
2. Job 元数据只暴露结果页需要的计数，不重复保存 17 字段明细；
3. Review 读取不会调用 Provider，也不会改变五类 Bundle、CURRENT 或正式结果。

新增 `web/ai_review.py` 作为窄适配边界。它只接受固定 V2 协议、固定 17 字段、固定 comparison/source/severity/technical 枚举，并输出 UI/API 白名单。

## 3. Job/API Review DTO

`public_job()` 新增 `ai_review_summary`：

```text
applicable
available
compatibility_message
technical_ready
review_required_count
high_review_count
has_unreviewed_differences
comparison_summary
python_fill_count
ai_only_count
content_issue_count
historical_attention_count
```

新增只读接口：

```text
GET /api/jobs/{job_id}/ai-review
```

详情 item 白名单：

```text
record_index
line_number
field_name
formal_value
ai_display_value
ai_normalized_value
python_display_value
python_normalized_value
comparison_status
selected_source
review_required
review_severity
content_issue
ai_supporting_quote
ai_evidence
python_evidence
```

API 不返回 evidence ID、reason code、candidate issue code、原始 Provider 响应、Prompt、请求正文、Authorization、API Key、本机路径、完整缓存身份或思维链。

## 4. Review Summary 数据来源

- 字段明细来自发布后的 `parse_diagnostics.ai_enhanced.field_decisions`。
- `technical_ready` 来自 `parse_diagnostics.ai_enhanced.technical_readiness`。
- summary 由白名单 item 本地确定性重算，不信任前端传入计数。
- 当前尚无 revision，因此 `has_unreviewed_differences` 确定性等于 `review_required_count > 0`。
- 旧 `isolated_field_count` 只用于历史兼容计数，不再作为新完成页主要用户语言。

## 5. Evidence ID 到人类可读位置

发布层只为字段决策实际引用的 evidence 建立 `evidence_display` 索引，不写入完整 workbook catalog。每项仅包含：

```text
sheet_id
sheet_name
cell_range
source_row
excerpt（最多 180 字符）
```

`source_row` 由本地已验证的 cell range 确定；excerpt 来自本地 evidence 原文，经空白压缩和长度限制。AI supporting quote 同样限制为 180 字符。Review Adapter 再按字段 evidence ID 做白名单映射，UI 最终展示例如：

```text
本地规则来源：PI · A2
来源内容：BUYER:
```

不会展示整张 Sheet、完整订单、内部 evidence ID 或本机文件路径。旧诊断没有该索引时只显示固定兼容提示或“暂无可展示的来源位置”，不会猜测坐标。

## 6. Completed + Review 页面状态

AI Enhanced 技术成功后继续使用正常 `completed` 结果页，标题为：

```text
AI整单解析完成
```

顶部与 Review 区明确显示：

- 待复核字段数；
- 高风险待复核数；
- 本地规则补全数；
- 五类结果完整；
- “正式结果已经生成，可以正常下载”。

Review 不会改成失败文案，不会进入 `awaiting_user_decision`，也不会禁用五类预览和下载。

## 7. AI/Python 对照 UI

AI Enhanced 结果页新增“AI 与本地规则对照”，Standard 结果页不渲染此区域。

每个字段清楚展示：

- 记录序号与正式行号；
- 当前正式结果；
- 当前采用来源：AI / 本地规则补全 / 空值；
- AI 提取值；
- 本地规则值；
- comparison 的中文状态；
- 高风险提示；
- 可展开的 AI/本地来源位置。

默认筛选为“待复核”，并提供“高风险”“本地补全”“全部”。筛选和证据详情均使用语义化 `button`，支持鼠标、Enter 和 Space；事件不会修改 hash、创建 Job 或调用 Provider。

## 8. Comparison 中文文案

| 内部状态 | 用户文案 |
| --- | --- |
| `agree` | AI 与本地规则一致 |
| `equivalent_after_normalization` | 表达形式不同，含义一致 |
| `different` | AI 与本地规则不一致，建议核对原订单 |
| `ai_only` | 仅 AI 识别到此字段 |
| `python_fill` | AI 未识别，本字段由本地规则补全 |
| `both_missing` | AI 与本地规则均未识别到此字段 |
| content issue | AI 给出了候选值，但证据不足，未作为正式值 |

`different` 卡片仍明确显示“当前采用：AI”。`python_fill` 明确显示“当前采用：本地规则补全”。

## 9. High Review 与 Normalization

- 客户、币种、业务员、数量、计划发货日期只在实际需要 review 时显示“高风险 · 建议重点核对”。
- 高风险只影响排序和视觉提示，不显示“失败/危险/禁止发布”。
- AI display 与 normalized 相同时不重复展示。
- 两者不同且转换有效时显示“正式格式：normalized value”，业务员不需要理解内部 normalization 枚举。
- selected source 仍保持 AI；本地格式转换不会伪装成 Python 选择。

## 10. 五类结果与正式结果保护

Review 区没有修改五类角色：

```text
official_result
parse_diagnostics
dictionary_validation
material_candidates
material_summary
```

- 五类仍恰好五类；
- 五类预览/单文件下载在 review 存在时全部可用；
- `official_result` 仍严格为既有 20 字段，不包含 comparison、review、evidence、model 或 token；
- comparison 只进入 `parse_diagnostics` 和派生的只读 Review API；
- 没有新增第六类业务 JSON；
- 没有改变原子 Bundle/CURRENT 发布。

现有 Excel 导出按钮和聚合 ZIP 的既有产品状态未在本 Gate 扩展；本 Gate 验收的是五类正式文件预览与下载不受 review 影响。

## 11. Standard、V1 与历史兼容

- Standard：结果页保持原布局，不请求或展示整单 AI/Python 对照；主值、五类结果、TopK 与单记录 AI Sidecar 均未改变。
- Legacy V1：返回固定兼容提示，不把 V1 套入 V2 comparison。
- 旧 V2 无 comparison：返回固定兼容提示，不伪造字段对照。
- 旧 V2 有字段决策但无 evidence display：仍可展示安全字段对照；来源位置缺失时明确说明不可用。
- 历史 fallback Job：保持只读回退语义，显示固定兼容提示。
- 未完成或 technical failure Job：Review 不可用，仍进入原失败/等待决策路径，不误显示完成页。
- 旧 `isolated_field_count`：内部兼容读取；用户文案改为“历史任务关注字段”，新任务使用“待复核字段”。

## 12. 修改文件

生产代码：

```text
src/bedding_order_parser/ai_full_order/downstream.py
src/bedding_order_parser/web/ai_review.py
src/bedding_order_parser/web/routes.py
src/bedding_order_parser/web/services.py
src/bedding_order_parser/web/static/app.js
src/bedding_order_parser/web/static/styles.css
```

测试：

```text
tests/ai_full_order/test_v2_downstream.py
tests/web/test_ai_full_order_jobs.py
tests/web/test_ai_review.py
tests/web/test_ai_review_frontend.py
tests/web/test_d3b2d_ui_enablement.py
```

未修改 `field_policy.py`、`comparison.py`、`normalization.py`、`orchestration.py`、`reliability_v2.py`、Provider、Prompt、Standard parser、字典规则、MaterialMatcher、单记录 Sidecar 或模板。

## 13. 测试与真实前端行为

### 核心定向矩阵

```powershell
.venv\Scripts\python.exe -m pytest tests/web/test_ai_review.py tests/web/test_ai_review_frontend.py tests/ai_full_order/test_v2_downstream.py tests/web/test_ai_full_order_jobs.py tests/web/test_d3b2d_ui_enablement.py -q
```

结果：`46 passed in 7.44s`

覆盖 high/ordinary difference、AI only、python fill、both missing、content issue、白名单 API、safe evidence、hard failure、V1/fallback/Standard、五类下载与 route。

### 相邻 Web 与 Sidecar 回归

```powershell
.venv\Scripts\python.exe -m pytest tests/web/test_services.py tests/web/test_routes.py tests/web/test_job_persistence.py tests/web/test_gate4b_frontend.py tests/web/test_gate4b_routes.py tests/web/test_gate4c2_frontend.py tests/web/test_gate4c2_routes.py tests/web/test_ai_advisory.py tests/web/test_gate4e_help_center.py -q
```

结果：`78 passed in 8.83s`

### 最终合并定向回归

上述 14 个直接相关测试文件一次运行：`124 passed in 15.77s`。

附加检查：

```powershell
node --check src/bedding_order_parser/web/static/app.js
git diff --check
```

结果：均通过。

### 真实浏览器验收

使用 `FakeV2CandidateProvider`、人工合成 Excel、FakeDictionaryValidator、FakeMaterialMatcher 和本地 loopback 服务生成 completed-with-review Job，并在实际桌面浏览器中验证：

- 页面标题为“AI整单解析完成”；
- Review 计数、高风险计数、正式值、AI/Python 值和采用来源可见；
- Enter 激活“高风险”筛选后只显示 5 个高风险字段；
- 展开证据后显示 `PI · A2/A3` 与短来源内容；
- 筛选和展开后 URL 始终保持结果 route；
- 五类预览/下载入口可见；
- 390×844 窄窗口无横向溢出，字段三方值和证据区切为单列；
- 无控制台阻断错误。

没有保留含业务内容的浏览器截图或临时 Job；临时服务已关闭。

## 14. 调用计数与安全边界

```text
真实 Ark：0
外部 HTTP：0
真实 PI：0
真实字典：0
真实物料库：0
BGE-M3：0
FAISS：0
```

测试仅包含本机 loopback HTTP 与计数型 FakeProvider 逻辑调用。页面加载、筛选、展开证据、预览和下载不会触发 Ark/Provider 调用。

## 15. 核心政策是否变化

没有修改：

- AI-first 字段选择；
- Python fallback 规则；
- technical-ready；
- provenance/identity/scope/evidence ownership hard boundary；
- reliability/cache；
- 五类原子发布；
- Standard 主解析语义。

本 Gate 只增加展示所需的受控诊断索引、白名单 API 适配和结果页 UI。

## 16. 留给 D4A-4

D4A-4 应单独实现不可变 revision，而不是在本页面直接改写当前 Bundle：

```text
保留 AI
改用 Python
手动输入
parent revision
受影响下游重跑
新 revision 原子发布
CURRENT revision switch
并发与审计
```

本 Gate 没有显示无功能的修订按钮，也没有修改同 Job fallback 或 standard reprocess。

## 17. 真实订单首次验收前风险

1. 真实订单记录较多且 review 密集时页面可能很长；当前默认“待复核”和筛选可控制信息量，后续可依据真实样本决定是否需要分页或按记录折叠。
2. 多行 cell range 的 `source_row` 当前展示首个本地可证明行号，完整范围仍通过 `cell_range` 展示；真实合并区域需要重点观察文案是否足够清楚。
3. 历史 V2 Bundle 没有本 Gate 新增的 `evidence_display` 时不能恢复短来源内容，系统会安全降级而不猜测。
4. Review 尚不可修改；用户当前只能看见、理解、定位和下载，修订能力必须由 D4A-4 建立版本化发布合同。
5. 本 Gate 未扩大现有 Excel/ZIP 导出能力；真实产品验收时应按既定路线单独确认该能力的当前交付状态。

## 18. 最终工作区

implementation 提交后仅保留起始时已经存在的七份未跟踪交接/审计文档。报告将独立提交；报告提交后预期仍只保留这七份既有未跟踪文档，无本 Gate 已跟踪修改残留。
