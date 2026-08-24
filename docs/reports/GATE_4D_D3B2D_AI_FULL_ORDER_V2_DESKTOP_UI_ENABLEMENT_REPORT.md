# Gate 4D-D3B-2D - AI 整单 Contract V2 桌面 UI 启用与离线端到端验收

日期：2026-08-05
分支：`master`
实现前 HEAD：`11b705258f7e1e6463d96ba8a0181930c05417c9`（D3B-2C 实现提交为 `e1196f278c04220eebf1275c71f082880e7a034c`）
实现提交：`e68761216c280cd932eb000633e57a87dffb60f3`（`feat: enable ai full-order v2 desktop ui`）

## 1. 真实禁用根因与 D3B-2C 缺口

### 根因一：前端混淆了“V2 产品能力”与“本机 Provider 可运行”

`src/bedding_order_parser/web/static/app.js` 的旧 `renderUpload()`（约 154-218 行）仅以 `state.aiPreflight.ready` 决定 AI 单选项能否点击：`ready !== true` 时强制把已选的 `ai_enhanced` 重置为 `standard`，同时给单选框添加 `disabled`，并拒绝 AI 模式切换。因此，只要运行时配置、下游端口或 Provider 未完整就绪，桌面页面就不能展示可选择的 AI 整单模式，更不能展示不就绪原因或确认语义。这是直接根因，不是 CSS、静态资源缓存、桌面快捷方式或常驻进程造成的；`styles.css` 的 `.mode-choice.disabled` 只反映了该前端判断。

### 根因二：默认桌面组装没有提供 V2 下游端口

`src/bedding_order_parser/desktop/server_controller.py`（约 35-42 行）以默认参数创建 `JobService`；`src/bedding_order_parser/web/ai_full_order_dependencies.py::build_ai_enhanced_dependencies()` 只有 Ark 配置就绪且字典验证器、物料匹配器均注入时才构造 V2 `AIEnhancedDependencies`。默认桌面组合没有注入这两个端口，所以即使 Ark 基本配置完备，也不能声明完整整单运行链路 ready。

这是真实运行前置条件，本轮用 Fake 下游完成离线验收，没有绕过它、加载真实字典、BGE-M3、FAISS 或物料库。

### D3B-2C 覆盖缺口

D3B-2C 已完成 V2 Job/服务合同和依赖注入链路，但测试主要直接注入 `AIEnhancedDependencies`，没有覆盖默认桌面组合下的上传页选择、当前静态资源是否被本地服务器提供、未就绪固定中文原因，以及“可选择”和“可提交运行”的分离，因而未发现硬禁用分支。

只读检查确认桌面快捷方式仍指向项目虚拟环境的 `pythonw -m bedding_order_parser.desktop`，没有相关运行进程；本轮没有修改快捷方式、打包脚本或桌面启动方式。

## 2. 实现内容

### 预检合同分层

`src/bedding_order_parser/web/services.py::JobService.ai_enhanced_preflight()` 现在分别返回：

- `v2_backend_available`：当前代码具备 Contract V2 UI 能力；
- `provider_configured`：本地配置或已注入依赖具备的配置事实；
- `provider_ready`：完整 V2 Provider、字典验证和匹配端口均可安全执行；
- `real_call_requires_user_confirmation`：固定为 `true`；
- `unavailable_reason_code`、`unavailable_reason_text`：固定、脱敏中文原因。

旧 `ready`、`reason` 保留为 C2 兼容字段。`capabilities()` 也返回相同安全的 `ai_full_order` 视图。`create_job()` 在服务端再次拒绝未 ready 的 `ai_enhanced` 请求，因此绕过页面直接 POST 也不会创建半成品 Job 或静默回退。

未就绪原因覆盖 API Key/模型缺失、Provider 禁用/不支持/配置错误，以及 Ark 配置可用但下游验证或匹配端口未就绪；不输出密钥、路径或 Provider 原始错误。

### 桌面页面与结果视图

`src/bedding_order_parser/web/static/app.js` 使用 `v2_backend_available` 控制“AI整单解析”是否可选择，使用 `provider_ready` 控制“开始解析”是否可提交。选择 AI 模式、访问预检、页面加载和展示确认对话均不调用 Provider。

配置未就绪时，用户仍能看见并选择该模式，页面显示固定中文原因，开始按钮不可提交；服务端同样阻止创建 AI Job，且不会回退到标准模式。配置就绪时保留既有确认对话；确认后才提交 `parse_mode=ai_enhanced`。

页面仅保留 `standard` 与 `ai_enhanced` 两种对外模式。V1/V2 是内部合同版本：V2 Job 在进度与完成页显示 `Contract V2`，不构成第三种业务模式。进度页新增 V2 阶段中文标签、隔离字段数和固定安全错误文本；结果页只按既有五角色提供预览/下载：

1. `official_result`
2. `parse_diagnostics`
3. `dictionary_validation`
4. `material_candidates`
5. `material_summary`

未向页面暴露 staging、缓存、Provider 原始内容或额外业务产物。

## 3. 离线端到端验收

新增 `tests/web/test_d3b2d_ui_enablement.py`，使用当前 `create_server()` 启动短生命周期本地 loopback HTTP 服务，验证实际静态模板和 `app.js` 被服务，不依赖浏览器缓存或手工源码判断。测试结束后关闭服务和 JobService。

### 成功链路

人工合成 `.xlsx` 经真实 `JobService`、Contract V2、`FakeV2CandidateProvider`、`FakeDictionaryValidator`、`FakeMaterialMatcher` 和 B3 发布边界执行：

- Job 为 `completed`，`parse_mode=ai_enhanced`，内部合同为 `2.0`；
- 本地明确结构，结构识别调用为 0；
- V2 字段提取逻辑调用为 1；V1 提取调用为 0；Fake Provider 网络调用计数为 0；
- Fake 字典验证与 Fake 匹配各调用 1 次；
- 20 字段顺序等于 `FINAL_FIELD_NAMES`；
- 五角色完整，可从统一角色 API 读取；历史摘要保留 AI 模式。

### 未就绪与失败链路

- 使用启用 Ark、指定模型但空 API Key 的本地设置：V2 仍可选择，预检返回 `AI_API_KEY_MISSING` 和固定中文原因；提交 API 返回同一安全原因，未创建 Job，Provider 调用为 0。
- Fake Provider 返回未知 evidence：Job 为 `awaiting_user_decision`，安全码为 `AI_V2_CONTRACT_FAILED`，五角色不完整，字典/匹配调用均为 0。
- Fake Provider 产生普通字段问题：字段级隔离为 1，Job 仍可 `completed` 并完成下游与五类发布。

同时回归既有发布失败无半套结果、标准解析、单记录 AI Sidecar、C1/C2 服务接口和桌面服务器测试。

## 4. 定向测试与调用计数

执行命令（未运行完整 `pytest`）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/web/test_d3b2d_ui_enablement.py tests/web/test_gate4c2_frontend.py tests/web/test_gate4c2_routes.py tests/web/test_gate4b_frontend.py tests/web/test_gate4b_routes.py tests/web/test_routes.py tests/web/test_services.py tests/web/test_ai_full_order_jobs.py tests/web/test_ai_advisory.py tests/desktop/test_server_controller.py tests/desktop/test_launcher.py tests/desktop/test_resource_paths.py tests/ai_full_order/test_v2_offline_resolution.py tests/ai_full_order/test_v2_reliability.py tests/ai_full_order/test_v2_downstream.py tests/ai_full_order/test_volcengine_ark_full_order_provider.py tests/ai_full_order/test_acceptance_diagnostics.py tests/pipeline/test_order_parser.py tests/serialization/test_json_writer.py tests/serialization/test_diagnostic_writer.py tests/llm/test_advisory_schema.py tests/llm/test_llm_contracts.py tests/llm/test_volcengine_ark_provider.py -q
```

结果：`227 passed in 30.69s`。

真实外部网络/API、Ark、BGE-M3、FAISS、真实字典/物料库、真实 PI 调用均为 **0**。本地 loopback HTTP 仅用于桌面 Web 服务离线验收。页面加载、预检和模式选择的 Provider 调用为 **0**；成功提交 V2 Job 后只有 1 次 Fake V2 逻辑提取，Fake Provider 网络调用仍为 **0**。

## 5. 修改文件

- `src/bedding_order_parser/web/services.py`
- `src/bedding_order_parser/web/static/app.js`
- `tests/web/test_d3b2d_ui_enablement.py`
- `tests/web/test_ai_full_order_jobs.py`
- `tests/web/test_gate4b_routes.py`
- `tests/web/test_gate4c2_routes.py`

未修改标准解析、C2 UI 布局/CSS、17 字段、正式行号、字段裁决、缓存身份、发布门、默认 ZIP、单记录 AI Sidecar、字典规则或物料匹配算法。

## 6. 真实 Ark V2 验收前仍存在的阻塞

桌面 UI 与 V2 离线链路现已可用，但默认 `ServerController` 尚未组装真实运行所需的字典验证与物料匹配端口。因此生产配置在这些端口缺失时会安全显示 `AI_DOWNSTREAM_NOT_READY`，不能创建 AI Job；这避免将只有 Ark 配置的半链路误标为 ready。

进行真实 Ark V2 验收前，应以独立、受控 Gate 明确默认桌面如何提供两个既有下游端口，并以 Fake/离线测试证明不改变标准模式、不加载未授权模型后，再检查批准的 Ark 配置和用户确认。
