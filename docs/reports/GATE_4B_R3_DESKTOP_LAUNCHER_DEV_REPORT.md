# Gate 4B-R3 桌面启动器开发模式报告

## 1. 本轮任务目标

本轮只复核并稳定以下开发模式流程：

```text
uv run python -m bedding_order_parser.desktop
-> 启动现有 Python 标准库 HTTP 服务
-> 等待 /health 成功
-> 打开 pywebview 窗口
-> 用户关闭窗口
-> 停止 HTTP 服务并释放桌面会话资源
```

未执行 PyInstaller、Onedir、Onefile、真实 PI、真实 FAISS、BGE-M3 或外部 API。

## 2. Git 基线

- 项目：`D:\AI-Learning\Projects\bedding-order-parser`
- HEAD：`2f3ec2de31640f017e61ea6aa052ecba2a2fdd18`
- 最新提交：`2f3ec2d feat: implement local frontend v1`
- 开始状态：不干净，为 Gate 4B 中断后经 R2 保留的已知半成品
- 本轮提交：无

## 3. 复核的 desktop 文件

- `src/bedding_order_parser/desktop/__init__.py`
- `src/bedding_order_parser/desktop/__main__.py`
- `src/bedding_order_parser/desktop/launcher.py`
- `src/bedding_order_parser/desktop/server_controller.py`
- `src/bedding_order_parser/desktop/resource_paths.py`
- `src/bedding_order_parser/desktop/instance_lock.py`
- `src/bedding_order_parser/desktop/app_logging.py`
- `src/bedding_order_parser/desktop/desktop_api.py`

模块职责仍分离为入口编排、服务生命周期、资源路径、单实例、日志和桌面下载桥接；未合并为 God 文件。

## 4. 实际修改文件

本轮修改：

- `src/bedding_order_parser/desktop/__init__.py`
- `src/bedding_order_parser/desktop/launcher.py`
- `src/bedding_order_parser/desktop/resource_paths.py`
- `src/bedding_order_parser/desktop/server_controller.py`
- `src/bedding_order_parser/web/app.py`
- `src/bedding_order_parser/web/services.py`
- `tests/desktop/test_resource_paths.py`
- `tests/desktop/test_server_controller.py`
- `tests/desktop/test_launcher.py`
- `docs/reports/GATE_4B_R3_DESKTOP_LAUNCHER_DEV_REPORT.md`

未修改匹配算法、权重、20 字段合同、LLM 合同、前端页面结构或 Day01。

## 5. 启动阶段重资源检查

修复前发现两条启动期风险：

1. `validate_application_paths()` 在打开窗口前完整计算 SQLite、FAISS 和 mapping 的 SHA-256，并扫描 BGE-M3 revision 目录。
2. `web/services.py` 顶层导入 `hybrid_matcher`，进而在启动期导入 FAISS 原生模块。

修复后：

- 启动只检查资源路径是否存在；
- 不读取 SQLite 内容；
- 不读取 FAISS 索引；
- 不计算大文件 SHA-256；
- 不遍历模型缓存；
- 不导入 FAISS、Torch 或 SentenceTransformer；
- `tests/desktop` 中的导入期断言通过。

## 6. 延迟加载调整

新增 `validate_startup_paths()`，仅执行 `is_file()` / `is_dir()` 级检查。原完整验证函数保留，未改变匹配算法；现有匹配任务仍在用户实际启动任务后通过原匹配流程读取并校验向量资源。

`parse_order`、`match_orders` 和 `write_match_outputs` 改为在 `_run_job()` 开始后局部导入。调用参数、执行顺序和业务结果合同均未改变。

## 7. HTTP 服务启动和停止机制

- 复用 `bedding_order_parser.web` 的 `ThreadingHTTPServer`；
- 服务线程名称为 `bedding-local-http`，可通过 `shutdown()`、`server_close()` 和有限时长 `join()` 停止；
- 停止时先停止接收新任务，再关闭服务和会话资源；
- `ServerController.stop()` 增加幂等保护；
- `DesktopApplication.run()` 的 `finally` 始终停止服务并释放单实例锁；
- pywebview 失败时不再打开带地址栏的系统浏览器，而是显示中文错误并清理退出。

## 8. 动态端口和健康检查

- 明确只绑定 `127.0.0.1`；
- 默认优先端口为 8000；
- 健康检查上限由 30 秒收紧为 15 秒；
- 轮询间隔 0.1 秒，无无限轮询；
- `/health` 实际返回 `status=ok`、`accepting_jobs=true`。

实际启动时发现启动前已有 Web 服务监听 8000，但新桌面服务仍绑定 8000。根因是 `WebServer.allow_reuse_address=True` 在 Windows 上允许地址共享。已改为 `False`，并新增“同类 WebServer 占用首选端口时必须改用动态端口”的回归测试，测试通过。

## 9. pywebview 窗口结果

- 实际窗口标题：`订单解析助手`
- 实际窗口：成功出现
- 实际 URL：`http://127.0.0.1:8000`（端口独占修复前的一次实启记录）
- 实际启动耗时：0.053 秒
- 目标尺寸测试：1440 x 900
- 最小尺寸测试：1180 x 720
- GUI：Edge Chromium
- debug：关闭
- 未打开浏览器地址栏或开发者工具

## 10. 单实例结果

Windows named mutex 测试通过：第二个锁实例会收到中文“已经在运行”错误，释放第一个锁后可重新获得。未采用高频轮询。

本轮没有再启动第二个真实桌面实例。

## 11. 定向测试命令和实际结果

```text
uv run pytest tests/desktop -q
20 passed in 3.23s

uv run pytest tests/web/test_gate4b_routes.py -q
2 passed in 1.51s
```

未运行全量 `pytest`，未运行整个 `tests/web`。

## 12. 开发模式实际启动结果

执行了一次：

```text
uv run python -m bedding_order_parser.desktop
```

窗口、运行状态文件、HTTP 健康检查和前端 JavaScript 均成功。验收期间未上传文件、未点击开始解析。

正常关闭请求被启动前已存在的一条 `processing` 任务元数据触发的确认流程阻挡；等待 15 秒后，本轮创建的精确 uv/Python PID 被终止，遗留 `runtime.json` 在确认 PID 已不存在后删除。按照“一次轻量真实启动”限制，修复后未进行第二次真实启动。

随后已将 `active_jobs()` 和关闭中断范围限定为当前 `JobService` 会话创建的任务，旧崩溃状态不会再阻挡新窗口关闭；对应定向测试通过。修复后的真实窗口关闭仍需在下一轮提交前做一次人工确认。

## 13. 五页面状态

实际 HTTP 服务成功返回前端脚本，确认以下五个页面函数全部存在：

- `renderUpload`
- `renderProgress`
- `renderResult`
- `renderMatch`
- `renderHistory`

未修改五页面 HTML、CSS 或 JavaScript 结构。由于本轮禁止上传和处理真实 PI，进度、结果和匹配详情没有用新业务任务填充；未使用 Playwright 或开发者工具。

## 14. 真实 PI

- 上传真实 PI：否
- 处理真实 PI：否
- 调用 `parse_order`：否
- 调用 `match_orders`：否

## 15. 关闭后端口和进程检查

首次实启的正常关闭被启动前旧 `processing` 状态阻挡，因此该次检查在 15 秒时仍观察到端口和 R3 进程；随后仅终止本轮精确 PID，端口和 R3 新增进程已清理。

系统中仍有启动前已存在的以下 Web 服务进程，本轮没有终止或修改：

```text
uv.exe 30336 -> python.exe 31120 -> python.exe 33388
命令：python -m bedding_order_parser.web
监听：127.0.0.1:8000
```

关闭逻辑的会话隔离、服务线程退出和端口回退已由定向测试覆盖；修复后的真实关闭未二次执行。

## 16. CPU、内存和磁盘

R3 实际窗口采样：

- 工作集：112.5 MB 至 121.6 MB
- 约 2.25 秒 CPU 增量：0.359 秒
- 未观察到 R3 窗口持续异常增长
- 未产生 build、dist、dist-onefile 或 release

启动前已有的 `python -m bedding_order_parser.web` 进程工作集约 2 GB，不属于 R3 新进程，本轮未终止。该旧进程是环境风险，应由用户确认后另行停止。

## 17. 未执行的打包事项

- PyInstaller：未执行
- `packaging/build_desktop.ps1`：未执行
- Onedir：未构建
- Onefile：未构建
- Playwright：未执行
- BGE-M3 / Torch / FAISS 索引：未加载
- 外部 API / LLM：未调用

## 18. 当前工作区状态

工作区仍不干净，原因是 Gate 4B 中断后保留的半成品、R2 报告和本轮 R3 修改。未执行 Git 清理、恢复、暂存或提交。

`git diff --check` 仍报告 `web/static/app.js` 的既有文件尾空行；该文件属于保留的前端半成品，本轮遵守“不修改现有五页面”边界，没有处理。

构建目录 `build`、`dist`、`dist-onefile`、`release` 和 `.playwright-cli` 均不存在。

## 19. 下一步唯一建议

Gate 4B-R4：整理并提交桌面启动器相关源码，不执行打包、不处理真实PI。
