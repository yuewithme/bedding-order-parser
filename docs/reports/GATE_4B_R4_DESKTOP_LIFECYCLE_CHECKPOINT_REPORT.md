# Gate 4B-R4 桌面生命周期检查点报告

## 1. 任务目标

本轮完成三项工作：

1. 精确停止 Gate 4B 中断后残留的旧 Web 服务；
2. 对修复后的桌面开发模式执行一次轻量真实启动和正常关闭验收；
3. 在全部保护条件通过后，为有价值的 Gate 4B 半成品建立 Git 安全检查点。

本轮没有执行 PyInstaller、真实 PI、BGE-M3、FAISS 索引读取或全量测试。

## 2. Git 基线

- 项目：`D:\AI-Learning\Projects\bedding-order-parser`
- 开始 HEAD：`2f3ec2de31640f017e61ea6aa052ecba2a2fdd18`
- 最新正式提交：`2f3ec2d feat: implement local frontend v1`
- 开始工作区：不干净，为 Gate 4B 中断后经 R2、R3 保留并审计的已知半成品
- 未执行 reset、restore、clean、stash、amend、tag 或 push

## 3. 残留 Web 服务的进程和端口

开始时确认以下父子进程链：

```text
uv.exe 30336
  -> python.exe 31120
     -> python.exe 33388
```

三者命令行均明确包含：

```text
python -m bedding_order_parser.web
```

其中 PID 31120 的解释器路径来自：

```text
D:\AI-Learning\Projects\bedding-order-parser\.venv\Scripts\python.exe
```

`127.0.0.1:8000` 的监听进程为 PID 33388。

## 4. 实际停止的精确 PID

按子进程到父进程顺序处理。实际执行 `Stop-Process -Id 33388 -Force` 后，PID 31120 和 PID 30336 随子进程退出而自行结束，因此没有对已经不存在的父进程重复发出停止命令。

停止后确认：

- PID 33388：不存在；
- PID 31120：不存在；
- PID 30336：不存在；
- 匹配 `bedding_order_parser.web` 的 uv/Python 进程：0；
- `127.0.0.1:8000` 监听：0。

## 5. 是否影响其他 Python 进程

否。进程筛选同时验证了名称、命令行、父子关系和目标仓库虚拟环境路径。没有使用按名称批量结束命令，没有终止其他 Python、VS Code、Codex 或系统服务。

## 6. 定向测试结果

只执行协议允许的两组测试：

```text
uv run pytest tests/desktop -q
20 passed in 4.07s

uv run pytest tests/web/test_gate4b_routes.py -q
2 passed in 1.53s
```

未运行全量 `uv run pytest`，未运行整个 `tests/web`。

## 7. 桌面实际启动结果

执行一次：

```text
uv run python -m bedding_order_parser.desktop
```

结果：

- 桌面窗口成功出现；
- 窗口标题为“订单解析助手”；
- 实际 URL 为 `http://127.0.0.1:8000`；
- `/health` 返回 `status=ok`；
- 首页 HTTP 状态为 200；
- 启动状态记录耗时 0.044 秒；
- 没有上传 Excel，没有点击开始解析。

## 8. 五页面切换情况

实际运行服务返回的前端脚本包含全部五个页面函数：

- `renderUpload`
- `renderProgress`
- `renderResult`
- `renderMatch`
- `renderHistory`

同时验证上传首页、进度任务、完成结果、匹配详情和历史记录所需的本地数据路由均可读取。五页面合同均正常，未执行新业务任务，也未修改现有任务状态。

## 9. 正常关闭结果

通过窗口正常关闭消息调用桌面关闭流程，`CloseMainWindow()` 返回 `True`。15 秒等待窗口内，本轮创建的 uv/Python 进程全部自然退出，没有使用强制结束冒充正常关闭。

## 10. HTTP 线程退出情况

桌面进程退出后：

- `bedding_order_parser.desktop` 命令行进程数为 0；
- 本轮 HTTP 服务所在 Python 进程不存在；
- 因服务进程已退出，`bedding-local-http` 线程不存在。

## 11. 端口释放情况

- 本轮实际使用端口：8000；
- 关闭后实际端口监听数：0；
- 关闭后 `127.0.0.1:8000` 监听数：0；
- 未遗留动态端口监听。

## 12. 残留进程情况

本轮启动进程链为：

```text
uv.exe 33328
python.exe 36624
python.exe 36060
```

关闭后以上 PID 均不存在，匹配 `bedding_order_parser.desktop` 的进程数为 0。`runtime.json` 不存在，启动前后任务状态集合完全一致，没有本轮产生的 running 或 processing 任务。

## 13. 启动内存和 CPU 采样

短时轻量采样结果：

- 工作集最小值：120.0 MB；
- 工作集最大值：125.9 MB；
- 约 2.25 秒 CPU 增量：0.391 秒；
- 进程读取增量：0 MB；
- 进程写入增量：0 MB。

未观察到持续 CPU 增长、持续内存增长或磁盘异常。

## 14. BGE-M3、Torch、FAISS 是否加载

- BGE-M3：未加载；
- Torch：未加载；
- FAISS：未加载；
- SentenceTransformer：未加载；
- SQLite 内容：未扫描。

依据包括桌面导入期定向测试、静态局部导入检查以及实际窗口进程模块采样。匹配相关模块只在用户真正启动任务后延迟导入。

## 15. app.js 文件尾修复

仅删除 `src/bedding_order_parser/web/static/app.js` 最后一行多余空行。未修改 JavaScript 逻辑、前端布局、样式或五页面结构。修复后 `git diff --check` 无错误。

## 16. 实际提交文件

安全检查点显式包含以下允许范围：

- `.gitignore`
- `pyproject.toml`
- `uv.lock`
- `.env.example`
- `src/bedding_order_parser/web/` 的 Gate 4B 修改
- `src/bedding_order_parser/desktop/`
- `src/bedding_order_parser/llm/`
- `tests/web/` 的 Gate 4B 测试
- `tests/desktop/`
- `tests/llm/`
- `packaging/` 的源码、spec、配置示例和 PowerShell 脚本
- `docs/reports/GATE_4B_R2_SAFE_CLEANUP_REPORT.md`
- `docs/reports/GATE_4B_R3_DESKTOP_LAUNCHER_DEV_REPORT.md`
- `docs/reports/GATE_4B_R4_DESKTOP_LIFECYCLE_CHECKPOINT_REPORT.md`

暂存使用显式路径，没有使用 `git add .`。

## 17. 敏感信息检查

检查结果：

- 未发现真实 API Key、密码、Token 或个人敏感信息；
- `.env.example` 仅包含 `replace_with_secure_runtime_value` 占位符；
- 测试中的 `secret` 和 `never-expose-this` 为不可用假值；
- LLM 设置对象只输出掩码；
- 未提交本机 `app_config.json`、日志或 `runtime.json`；
- 未在源码、测试和 packaging 配置中发现本机绝对路径；
- 未提交 EXE、DLL、模型缓存、SQLite 或 FAISS 文件；
- 未提交 build、dist、dist-onefile 或 release。

## 18. 未执行事项

- PyInstaller：未执行；
- Onedir：未构建；
- Onefile：未构建；
- 真实 PI：未处理；
- BGE-M3 / Torch / FAISS：未加载；
- 外部 LLM / API：未调用；
- 全量测试：未执行；
- Day01：未修改；
- tag / push：未执行。

## 19. 最终 Commit

提交信息：

```text
feat: stabilize local desktop launcher
```

本报告与安全检查点位于同一个提交中，因此提交哈希不能自引用写入提交内容；实际完整哈希和短哈希以提交后的 `git rev-parse` 与最终聊天回复为准。

## 20. 工作区状态

提交后要求 `git status --short` 无输出。若存在任何剩余内容，以提交后实际检查为准，不得声称干净。

## 21. 下一步唯一建议

Gate 4B-R5：仅构建并验收Onedir稳定版，不构建Onefile，不处理真实PI。
