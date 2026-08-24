# Gate 4D-D3B-2E - 真实桌面快捷方式运行身份与 V2 默认依赖组装离线验收

日期：2026-08-05
分支：`master`
起始 HEAD：`ac5e11dbaf0f6c3de9bbb1af84bf8dc345a780ff`
起始短哈希：`ac5e11d`
D3B-2D 实现/报告提交：`e68761216c280cd932eb000633e57a87dffb60f3` / `ac5e11dbaf0f6c3de9bbb1af84bf8dc345a780ff`
实现提交：`80aa08a500e120441578f96a014b0775dd9fe48f`（`fix: align desktop shortcut runtime with ai v2`）

## 1. 快捷方式只读审计与真实运行身份

发现一个与项目生成逻辑一致的桌面快捷方式：

| 项目 | 实际值 |
| --- | --- |
| 快捷方式 | `C:\Users\alyar\Desktop\订单解析助手.lnk` |
| TargetPath | `D:\AI-Learning\Projects\bedding-order-parser\.venv\Scripts\pythonw.exe` |
| Arguments | `-m bedding_order_parser.desktop` |
| WorkingDirectory | `D:\AI-Learning\Projects\bedding-order-parser` |
| IconLocation | `D:\AI-Learning\Projects\bedding-order-parser\src\bedding_order_parser\desktop\resources\app.ico,0` |
| 最后修改时间（UTC） | `2026-07-28T16:01:53.8119304Z` |

仓库内 `packaging/create_local_desktop_shortcut.ps1` 生成同样的 TargetPath、Arguments、WorkingDirectory 和图标路径；生成逻辑正确。没有修改项目目录外的 `.lnk`，也不需要用户重新生成快捷方式。

启动前未发现订单助手 Python/Pythonw 进程。使用上述 TargetPath、Arguments 和 WorkingDirectory 进行快捷方式等价启动后，实际观察到：

- 初始启动进程：项目 `.venv\Scripts\pythonw.exe`；
- Windows 进程树中的运行服务子进程：Python 3.12 基解释器 `pythonw.exe`；
- 两个进程均以 `-m bedding_order_parser.desktop` 运行，子进程继承当前项目工作目录；
- 子进程由当前仓库代码生成的运行身份为实现提交 `80aa08a500e1`；
- 由真实 HTTP 服务提供的 `app.js` SHA-256 为 `ddb59b6f5d04f57687a8bca525106f56c58a1f2657fe877768cfebf766ae8b6b`，与仓库当前文件完全一致；
- 页面 `GET /` 为 200，Capability 和预检也均来自该同一实例；
- 审计结束后仅关闭本次自己启动的两个项目进程，剩余订单助手进程为 0。

Windows/pywebview 进程树显示基解释器子进程这一事实不等于旧安装：运行身份和静态 SHA 同时证明该服务加载的是当前仓库版本，而非 site-packages 旧副本或旧静态资源。D3B-2D 未覆盖此入口，因为其离线端到端测试使用 `create_server()`，没有经过 `.lnk`、`pythonw`、WebView 生命周期和默认 `ServerController` Composition。

## 2. 受控运行身份

新增 `desktop/runtime_identity.py`，由 `ServerController` 在启动时生成并仅通过 `GET /api/capabilities` 与本地 `runtime.json` 提供以下白名单字段：

```json
{
  "application_version": "0.1.0",
  "build_commit_short": "80aa08a500e1",
  "ui_asset_version": "v2-ui-2026-08-05",
  "ui_asset_sha256_short": "ddb59b6f5d04",
  "ai_contract_version": "2.0"
}
```

没有暴露绝对路径、机器信息、分支脏状态、配置、密钥、请求或原始响应。页面加载和 Capability 查询均不调用 Provider。V1/V2 仍是内部合同版本，不构成第三个用户解析模式。

## 3. 默认 V2 下游 Composition

新增 `desktop/ai_full_order_composition.py`，并在 `ServerController` 默认创建 `JobService` 时注入 `DesktopV2DownstreamFactory`：

- 工厂只检查既有 SQLite、FAISS、向量清单、字典工作簿和模型缓存路径是否存在；启动、预检、页面加载和模式选择不读取工作簿，不导入 FAISS，不加载 BGE-M3，不发起网络调用。
- Provider 配置与下游资源齐备时，`provider_ready` 才为真；资源缺失时保留 V2 capability 和可选择 UI，但返回 `AI_DOWNSTREAM_NOT_READY` 并阻止提交，不静默回退。
- 每个确认后的 V2 Job 才绑定独立的 `DesktopDictionaryValidator` 与 `DesktopMaterialMatcher`。
- 字典适配器在字典验证阶段调用既有 `build_product_validation_report()`；物料适配器在物料匹配阶段以短生命周期中间 JSON 调用既有 `match_orders()`，不复制字典规则、匹配权重、阈值或 FAISS/BGE 算法。
- 现有物料匹配合同是 `manual_review_only`，因此适配器保留候选和摘要，并让正式 `物料编码` 为 `""`、`相似分数` 为 `0.0`，不把候选自动写回正式结果。

`AIEnhancedDependencies` 新增按 Job 绑定下游端口的窄接口；V1/直接注入 Fake 依赖保持原行为。只有运行到 V2 下游阶段才可能加载真实下游资源。本 Gate 的测试全部使用 Fake 或 monkeypatch，未加载真实资源。

## 4. 真实快捷方式实例验收

快捷方式等价实例的受控结果：

| 检查 | 结果 |
| --- | --- |
| 当前项目 `.venv` 为快捷方式初始目标 | 通过 |
| 当前仓库模块/资源身份 | 通过（`build_commit_short=80aa08a500e1`） |
| 当前 `app.js` | 通过（HTTP SHA 与仓库 SHA 相同） |
| V2 backend capability | `true` |
| 本机完整 Provider readiness | `true` |
| `ui_asset_version` | `v2-ui-2026-08-05` |
| `ai_contract_version` | `2.0` |
| 页面、Capability、预检期间 Provider 调用 | `0` |

未创建 V2 Job，因此没有 Ark HTTP 尝试、Token、真实 Provider 调用、BGE-M3、FAISS、真实字典、真实物料库或真实 PI 调用。

## 5. 离线 Fake V2 完整流程

新增的 Controller 级 HTTP 测试通过真实 `ServerController` 启动动态端口，注入 Fake V2 Provider、Fake 字典验证器和 Fake 物料匹配器后完成：

1. 请求实际上传页面与能力 API；
2. 通过上传 API 确认创建 `ai_enhanced` Job；
3. Job 固定 `ai_contract_version=2.0`；
4. V2 Fake 提取调用 1 次，V1 提取、结构识别和 Fake 网络调用均为 0；
5. 字典与匹配 Fake 各调用 1 次；
6. 正式 20 字段和五类角色完整发布，并可按统一角色 API 预览；
7. Controller 正常关闭。

同时覆盖资源缺失时 `AI_DOWNSTREAM_NOT_READY`、运行身份白名单、快捷方式生成合同、动态端口、健康检查、Controller 关闭、标准模式、legacy V1 Job、单记录 AI Sidecar、V1/V2 缓存隔离、五类发布和默认 ZIP 的直接相关回归。

## 6. 测试与安全边界

执行的最终定向命令（未运行完整 `pytest`）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/desktop/test_d3b2e_runtime_and_composition.py tests/desktop/test_server_controller.py tests/desktop/test_launcher.py tests/desktop/test_resource_paths.py tests/web/test_d3b2d_ui_enablement.py tests/web/test_gate4c2_frontend.py tests/web/test_gate4c2_routes.py tests/web/test_gate4b_frontend.py tests/web/test_gate4b_routes.py tests/web/test_routes.py tests/web/test_services.py tests/web/test_ai_full_order_jobs.py tests/web/test_ai_advisory.py tests/ai_full_order/test_v2_offline_resolution.py tests/ai_full_order/test_v2_reliability.py tests/ai_full_order/test_v2_downstream.py tests/ai_full_order/test_volcengine_ark_full_order_provider.py tests/ai_full_order/test_acceptance_diagnostics.py tests/pipeline/test_order_parser.py tests/serialization/test_json_writer.py tests/serialization/test_diagnostic_writer.py tests/llm/test_advisory_schema.py tests/llm/test_llm_contracts.py tests/llm/test_volcengine_ark_provider.py -q
```

结果：`233 passed in 32.08s`。

真实外部网络/API、Ark、BGE-M3、FAISS、真实字典、真实物料库、真实 PI 调用均为 **0**。实际快捷方式实例只请求本地 loopback 页面、Capability 与预检，Provider 调用为 **0**；Fake 完整 Job 的 V2 提取为 1 次，Fake 网络为 0。

## 7. 修改文件与未改变的边界

- `src/bedding_order_parser/desktop/ai_full_order_composition.py`
- `src/bedding_order_parser/desktop/runtime_identity.py`
- `src/bedding_order_parser/desktop/launcher.py`
- `src/bedding_order_parser/desktop/server_controller.py`
- `src/bedding_order_parser/web/ai_full_order_dependencies.py`
- `src/bedding_order_parser/web/ai_full_order_service.py`
- `src/bedding_order_parser/web/services.py`
- `src/bedding_order_parser/web/app.py`
- `src/bedding_order_parser/web/routes.py`
- `tests/desktop/test_d3b2e_runtime_and_composition.py`

未修改 Contract V2、17 字段、正式行号、provenance、字段政策、可靠性/缓存身份、字典规则、物料匹配算法/权重/阈值、标准解析、默认 ZIP、C2 UI、单记录 AI Sidecar 或项目外用户文件。

## 8. 进入真实 Ark 验收前的状态

默认桌面 Composition、可验证运行身份、V2 预检与离线 Fake 发布链均已具备。真实 Ark 验收仍需独立的明确用户授权、最小人工合成数据、调用预算和零重试约束；本 Gate 未发起也未模拟真实 Provider 网络请求。
