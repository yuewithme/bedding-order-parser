# Gate 4E-A：帮助中心三项内容完善与前端验收报告

## 1. 起始基线

- 分支：`master`
- 起始完整 HEAD：`767e9ea3edabd2c47ad55fba520df13b7234abb6`
- 起始提交：`docs: report ai v2 structure path fix`
- 开始时工作区没有已跟踪文件修改；保留了既有的六份未跟踪交接/审计文档，未读取、修改、删除或暂存它们。

## 2. 帮助页组织方式

原侧栏“帮助”仅显示一条提示。本 Gate 将其改为本地 hash 路由 `#help`，默认直接展示三个清晰入口和三个完整内容区：

1. **英文术语注释**：按正式业务结果、解析诊断、字典验证、物料候选、物料匹配摘要、常见模式/状态/安全提示分组。
2. **软件使用方法**：覆盖上传 Excel、选择解析方式、确认提示、开始处理、查看进度和五类结果、预览/下载、导出 Excel/ZIP、历史记录。
3. **软件处理流程**：分别展示标准解析和 AI增强整单解析的业务员可读流程。

页面为纯本地渲染；`renderHelp()` 不调用 `api()`，不创建任务、不访问 Provider，也不改变任何任务或解析逻辑。

## 3. 英文术语的数据来源

术语仅取自现有用户可见角色、序列化字段和前端标签：

- 五类角色来自 `src/bedding_order_parser/web/services.py` 的 `ARTIFACT_ROLES`：`official_result`、`parse_diagnostics`、`dictionary_validation`、`material_candidates`、`material_summary`。
- 角色中文说明复用 `src/bedding_order_parser/web/static/app.js` 的既有 `artifactCopy` 语义。
- `material_code`、`similarity_score` 等字段来自既有前端 `AI_FIELD_LABELS` 和物料匹配输出边界。
- `validation_only`、`records`、`candidates`、`accuracy_statement` 等词来自现有字典、候选和摘要 JSON 结构。
- `standard`、`ai_enhanced`、`completed`、`awaiting_user_decision`、`interrupted` 来自现有 Job/UI 状态合同。

没有将 API Key、Authorization、缓存身份、本机路径、原始异常正文或开发专用字段放入帮助页。相似分数明确说明为参考分数，不代表绝对准确率或正确概率。

## 4. 实际修改文件

- `src/bedding_order_parser/web/templates/index.html`
  - 将侧栏“帮助”从 toast 改为 `data-route="help"`。
- `src/bedding_order_parser/web/static/app.js`
  - 新增业务员可读帮助数据、`renderHelp()`、`#help` 路由和帮助导航激活状态。
  - 帮助页只生成本地 HTML，不调用后端 API。
- `src/bedding_order_parser/web/static/styles.css`
  - 增加帮助页三区、术语分组、步骤、流程和窄窗口单列布局样式；复用现有颜色、边框和间距体系。
- `tests/web/test_gate4e_help_center.py`
  - 新增帮助路由、三项入口、真实角色/术语、两种模式说明、流程、无 API 调用和窄窗口规则断言。

## 5. UI 验收结果

- 桌面布局：三个入口采用三列导航，术语采用两列分组，使用方法和流程采用两列对照。
- 窄窗口布局：`max-width: 600px` 下入口、术语、模式说明和流程全部收为单列；术语行从三列改为单列，避免英文键名和中文说明挤压重叠。
- 已通过 JavaScript 语法检查和 CSS 结构断言。
- 本机 Playwright 命令未返回可用版本信息；本轮没有安装浏览器或任何额外依赖。UI 验收因此由现有本地 HTTP 服务测试、页面结构测试和窄窗口 CSS 断言完成。

## 6. 测试命令与结果

```powershell
.\.venv\Scripts\python.exe -m pytest tests\web\test_gate4e_help_center.py tests\web\test_routes.py tests\web\test_gate4b_frontend.py tests\web\test_gate4c2_frontend.py tests\web\test_d3b2d_ui_enablement.py -q
```

结果：`26 passed in 6.15s`

```powershell
node --check src\bedding_order_parser\web\static\app.js
.\.venv\Scripts\python.exe -m pytest tests\web\test_gate4e_help_center.py tests\web\test_d3b2d_ui_enablement.py::test_current_local_server_serves_v2_ui_assets_without_provider_calls tests\web\test_routes.py::test_home_and_static_assets_are_served -q
git diff --check
```

结果：JavaScript 语法检查通过；定向本地服务回归 `6 passed in 2.01s`；`git diff --check` 通过。

## 7. Provider/网络调用

- 真实 Provider 调用：`0`
- 真实网络调用：`0`
- Ark、BGE-M3、FAISS、真实字典和真实物料匹配调用：`0`
- 本地服务回归明确断言 FakeProvider 的 extraction、structure 和 network 计数均为 `0`。

## 8. 未修改的后端范围

未修改 AI 整单合同、Prompt、Provider、字段政策、标准解析、字典规则、物料匹配算法、Job 状态机、五类 JSON Schema、任务创建/发布、默认 ZIP 或 API 配置。

## 9. 提交与最终工作区

- 本报告生成后，显式暂存本 Gate 的三项前端文件、一个测试文件和本报告，并以 `feat: improve help center content` 提交。
- 既有六份未跟踪交接/审计文档保持未跟踪且未修改。
