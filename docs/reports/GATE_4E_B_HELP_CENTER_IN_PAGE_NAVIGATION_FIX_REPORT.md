# Gate 4E-B：帮助中心顶部卡片页内导航修复报告

## 起始基线

- 分支：`master`
- 起始完整 HEAD：`fb8586d685956620bfe6b6f0f2f068c0b760fdab`
- Gate 4E-A 实际提交：`fb8586d685956620bfe6b6f0f2f068c0b760fdab`（`feat: improve help center content`）。
- 开始时没有已跟踪文件修改；六份既有未跟踪交接/审计文档保持未修改、未暂存。

## 实际根因

根因位于 `src/bedding_order_parser/web/static/app.js`：

1. `renderHelp()` 原先在约第 276-278 行将三张顶部卡片渲染为 `href="#help-terms"`、`href="#help-usage"`、`href="#help-flow"` 的链接。
2. 点击链接会把 `window.location.hash` 从 `#help` 改为这些页内 ID。
3. 约第 1294 行的 `hashchange` 监听器调用 `route()`；约第 1258-1266 行的 `route()` 只将首段为 `help` 的 `#help` 识别为帮助页。
4. 三个 ID 都是未知顶层路由，最终落入 `return renderUpload()`，因此应用重新渲染订单解析首页。

卡片没有 `data-route`；问题不是节点丢失，而是锚点错误进入了应用级 hash 路由器。

## 修复后的页内导航

- 三张卡片改为原生 `<button type="button">`，使用稳定的 `data-help-target` 和 `aria-controls`：`help-terms`、`help-usage`、`help-flow`。
- 新增 `scrollToHelpSection(event)`：只读取目标 ID，查找目标节点，并执行 `target.scrollIntoView({ behavior: "smooth", block: "start" })`。
- 新增 `bindHelpEntryNavigation(root)`，仅在 `renderHelp()` 完成本地 DOM 渲染后绑定三张卡片。
- 处理函数不调用 `navigate()`、不写 `window.location.hash`、不调用 `api()`、不创建 Job。
- 目标缺失时安全返回，不抛错、不跳转首页。
- `.help-section` 增加 `scroll-margin-top: 22px`，让标题滚动到可见位置；原窄窗口单列布局保持不变。

## 三张卡片与可访问性

- 英文术语注释 → `help-terms`；软件使用方法 → `help-usage`；软件处理流程 → `help-flow`。
- 原生 button 支持鼠标、Tab 焦点、Enter 和 Space；既有 `.help-entry-link:focus-visible` 焦点样式未移除。
- 侧栏“帮助”继续通过 `data-route="help"` 进入 `#help`；刷新 `#help` 时现有 router 仍调用 `renderHelp()`。

## 真实行为测试方法

`tests/web/test_gate4e_help_center.py` 新增受控 Node 行为测试：从实际 `app.js` 提取 `scrollToHelpSection()` 和 `bindHelpEntryNavigation()`，提供最小 fake DOM、三个真实目标和一个缺失目标，执行绑定后的 click handler。

测试分别模拟每张按钮的鼠标 click 和原生 button 产生的键盘 click，并断言：

- 六次有效操作均调用正确目标的 `scrollIntoView({ behavior: "smooth", block: "start" })`；
- 缺失目标安全无操作；
- `window.location.hash` 始终为 `#help`；
- `api()` 调用数、`createJob()` 调用数均为 `0`。

这是执行后的事件行为验证，不是只检查 `scrollIntoView` 字符串。

## 测试命令与精确结果

- `node --check src\bedding_order_parser\web\static\app.js`：通过。
- `.\.venv\Scripts\python.exe -m pytest tests\web\test_gate4e_help_center.py tests\web\test_routes.py tests\web\test_gate4b_frontend.py tests\web\test_gate4c2_frontend.py tests\web\test_d3b2d_ui_enablement.py -q`：`27 passed in 5.76s`。
- `git diff --check`：通过。

未运行完整 pytest、真实 Ark、真实字典、真实物料、BGE-M3 或 FAISS。

## 修改文件与未修改范围

修改：

- `src/bedding_order_parser/web/static/app.js`
- `src/bedding_order_parser/web/static/styles.css`
- `tests/web/test_gate4e_help_center.py`

未修改：帮助三项正文、后端 route、JobService、标准解析、AI 整单解析、Provider、字典和物料规则、五类 JSON、API 配置及项目外文件。

## 调用计数与最终工作区

- Provider 调用：`0`
- API 调用：`0`
- 真实网络调用：`0`
- Job 创建：`0`

本报告生成后仅显式暂存本 Gate 的三个源/测试文件和本报告，以 `fix: keep help navigation within help page` 提交。既有六份未跟踪交接/审计文档继续保留且未修改。
