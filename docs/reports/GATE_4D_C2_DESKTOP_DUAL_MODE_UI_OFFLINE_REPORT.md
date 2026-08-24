# Gate 4D-C2 桌面双模式 UI 离线联调报告

## 1. 实际开始基线与工作区

- 分支：`master`。
- 开始完整 HEAD：`257d50ed322c13c3f195800369bde39e560a34a7`。
- 开始短哈希：`257d50e`。
- 开始提交：`feat: integrate ai full-order desktop jobs`。
- 开始工作区继承三份未提交 C2 半成品：
  - `src/bedding_order_parser/web/services.py`
  - `src/bedding_order_parser/web/routes.py`
  - `src/bedding_order_parser/web/static/app.js`
- 保留且未暂存的既有恢复文件：`CODEX_HANDOFF_AND_RECOVERY_2026-07-30.md`、`CODEX_RECOVERY_AUDIT_ROUND_1_REPORT_2026-08-01.md`，以及本轮开始前已存在的 C2 执行交接文档。

## 2. 继承半成品审查结论

- `services.py` 的 `ai_enhanced_preflight()` 可保留：仅返回 UI 所需的就绪状态、中文原因、Provider、模型、逻辑调用上限和未知估算，不暴露密钥、请求、响应、缓存或思维链。
- `routes.py` 的 AI 操作路由可保留：复用 C1 的 `retry_missing_chunks`、`fallback_to_standard`、`keep_failed`，没有复制整单服务链。本轮补充了意外异常的通用中文错误响应。
- `app.js` 的双模式、确认、进度、五角色和历史骨架可保留；本轮补齐初始化预检、Escape 取消、坐标化数据而非 Excel 二进制的说明、路由一致性保护和完整样式。
- 未发现与 C1 Job 合同、标准解析、20 字段、五类结果或单记录 AI Sidecar 冲突的继承修改；没有需要删除的生产代码。

## 3. 本轮完成与 UI 状态流

- 首次加载同时读取 capabilities 与 `/api/ai-enhanced/preflight`；预检失败仅禁用 AI 模式并显示安全中文原因，标准解析不受影响。
- 上传页提供互斥 `standard` / `ai_enhanced`，默认标准解析；创建 Job 明确提交 `parse_mode`，未恢复 `allow_ai` 布尔设计。
- AI 模式确认框显示文件名、Provider/模型、仅发送必要坐标化订单数据且不发送 Excel 二进制、未知 Token/费用、失败不静默回退以及后续三种用户选择。取消、点击遮罩或 Escape 都不会创建 Job；确认复选框和提交状态防止重复提交。
- AI 阶段代码映射为中文，显示 chunk 进度、逻辑调用、HTTP 尝试、Token 占位、Provider/模型、五类结果状态和安全错误码。
- `awaiting_user_decision` 提供重试、二次确认回退和保留失败；未确认回退不发送 fallback 请求。回退后保留原始 `ai_enhanced`，有效模式变为 `standard`，不会混入部分 AI 产物。
- 结果页只按 `official_result`、`parse_diagnostics`、`dictionary_validation`、`material_candidates`、`material_summary` 五个统一角色渲染；不暴露物理文件名、缓存、staging、Sidecar 或第六类业务产物。
- 历史页显示解析模式、回退标签和方式筛选；缺少模式字段的旧 Job 继续以“标准解析（历史任务）”展示。
- 修复了异步历史页在路由切换后覆盖等待决策页的竞态：异步视图在请求返回时核验当前 hash，过期响应不再重绘新页面。

## 4. 新增与更新测试

- 新增 `tests/web/test_gate4c2_routes.py`：预检未就绪/注入 FakeProvider、安全字段、retry、keep-failed、未确认与确认 fallback、未知 action、缺失 Job 和安全错误。
- 新增 `tests/web/test_gate4c2_frontend.py`：预检初始化、默认模式、`parse_mode`、确认与二次确认、五角色、历史筛选、Sidecar 边界、旧 `allow_ai` 缺失和 CSS 选择器。
- 运行 C1 AI Job、标准 Web Job、旧 Job、路由、持久化、单记录 AI Sidecar 和既有前端静态回归。

执行命令：

```powershell
node --check src/bedding_order_parser/web/static/app.js
.\.venv\Scripts\python.exe -m pytest -q tests/web/test_gate4c2_routes.py tests/web/test_gate4c2_frontend.py tests/web/test_gate4b_frontend.py tests/web/test_routes.py tests/web/test_services.py tests/web/test_job_persistence.py tests/web/test_ai_full_order_jobs.py tests/web/test_ai_advisory.py tests/web/test_gate4b_routes.py
git diff --check
```

结果：JavaScript 语法检查通过；`81 passed in 12.41s`；`git diff --check` 通过（仅有 Git 的 CRLF 提示，无空白错误）。

## 5. 1440px / 390px 离线浏览器验收

使用本机 `127.0.0.1` 服务、FakeProvider、FakeDictionaryValidator、FakeMaterialMatcher、合成双 Sheet Excel 和本机 Edge 执行联调；未使用真实 PI。

| 视口 | 检查页面/路径 | 结果 |
| --- | --- | --- |
| 1440px | AI 就绪上传、确认弹窗、取消确认、确认后完整五角色结果 | 通过 |
| 1440px | 历史页模式列与筛选、等待决策、重试、回退二次确认、保留失败 | 通过 |
| 390px | AI 模式上传页和确认弹窗 | 通过；弹窗可滚动、按钮可见可操作、长文件名与 Provider/模型未发生关键横向溢出 |
| 390px | 标准模式创建 Job | 通过；创建请求的模式为 `standard` |

- 取消 AI 确认前后 Job 数均为 `9`，证明取消创建 Job 数为 `0`。
- 浏览器记录的 20 个请求均为 `127.0.0.1`；未出现外部请求。
- 回退取消后任务仍是 `awaiting_user_decision` / `ai_enhanced`；明确确认后最终为原始 `ai_enhanced`、有效 `standard`、`fallback.status=confirmed` 且有确认时间。
- 临时截图数量：6。检查过桌面确认、结果、历史、等待决策及窄屏上传/确认；未发现本 Gate 范围内的遮挡、关键溢出或无法操作问题。
- 初次浏览器运行器使用过于简化的临时 Fake 字典输出，正确触发 B3 隔离门；将临时运行器改为 C1 测试同等 Fake 合同后，五角色结果路径通过。该问题未涉及生产代码。
- 联调结束后已关闭本地服务，并删除临时运行器、6 张截图、合成工作簿、临时 Job、缓存、日志和运行目录；未提交这些产物。

## 6. 标准模式与正式结果保护

- 标准模式创建/执行、旧 Job 只读兼容、统一五角色角色映射、默认 ZIP 相关回归和单记录 AI Sidecar 回归均通过。
- AI 增强整单模式不会自动触发单记录 AI 复核；标准模式仍只能由用户主动触发该只读 Sidecar。
- 未修改标准解析算法、固定 20 字段、字典规则、物料匹配算法/权重/阈值、默认 ZIP 或 C1 整单编排合同。

## 7. 调用计数与安全边界

- 外部网络调用：`0`。
- 真实 API 调用：`0`。
- 真实豆包调用：`0`。
- BGE-M3 调用：`0`。
- FAISS 调用：`0`。
- 未安装依赖、未运行完整 pytest、未使用真实 PI。

## 8. 修改文件、提交与下一步

本轮提交文件：

- `src/bedding_order_parser/web/services.py`
- `src/bedding_order_parser/web/routes.py`
- `src/bedding_order_parser/web/static/app.js`
- `src/bedding_order_parser/web/static/styles.css`
- `tests/web/test_gate4c2_routes.py`
- `tests/web/test_gate4c2_frontend.py`
- `docs/reports/GATE_4D_C2_DESKTOP_DUAL_MODE_UI_OFFLINE_REPORT.md`

提交信息：`feat: add ai enhanced parsing desktop ui`。

提交哈希和最终工作区以提交后核验结果为准。

下一步唯一建议：Gate 4D-D1：实现火山方舟 AI 整单 Provider 适配与正式桌面服务注入，先完成全离线 Transport、严格 Schema 和请求构造测试，不调用真实 API。
