# Gate 4B-R5 本机桌面一键启动快捷方式报告

## 1. 任务目标

本轮只为当前电脑创建本机桌面快捷方式 订单解析助手.lnk，让用户可以双击启动现有桌面入口 edding_order_parser.desktop。本轮不进行 PyInstaller 打包，不构建 Onedir，不构建 Onefile，不运行真实 PI，不修改前端五页面和匹配算法。

## 2. Git 基线

- 项目路径：D:\AI-Learning\Projects\bedding-order-parser
- 开始前 HEAD：0b82111cc31f429e34ee64b764b04b2e5f7095d
- 开始前短 HEAD：0b8211
- 开始前最新提交：0b8211 feat: stabilize local desktop launcher
- 开始前工作区：干净
- 轻量导入检查：desktop import ok

## 3. 使用 pythonw.exe 的原因

快捷方式目标使用项目虚拟环境中的 pythonw.exe，用于在 Windows 桌面环境下启动 Python GUI 程序时避免显示控制台窗口。该方式继续复用当前项目 .venv 中已配置好的运行环境，不需要调用 uv run、cmd.exe、powershell.exe、VS Code 或任何 PyInstaller 产物，也避免重新打包 Torch、FAISS 等大型依赖。

## 4. 快捷方式创建脚本

- 新增脚本：packaging/create_local_desktop_shortcut.ps1
- 创建机制：Windows 内置 WScript.Shell
- 桌面路径来源：[Environment]::GetFolderPath("Desktop")
- 覆盖规则：只有快捷方式已存在且指向当前项目时，才允许通过 -Force 更新；若同名快捷方式指向其他程序，脚本停止并拒绝静默覆盖。
- 编码处理：脚本源码保持 ASCII，中文快捷方式名和描述通过 Unicode 码点生成，以兼容 Windows PowerShell 5.1。

## 5. 实际桌面路径

- 桌面路径：$DesktopPath
- 快捷方式路径：$ShortcutPath

## 6. 快捷方式 TargetPath

D:\AI-Learning\Projects\bedding-order-parser\.venv\Scripts\pythonw.exe

## 7. 快捷方式 Arguments

-m bedding_order_parser.desktop

## 8. WorkingDirectory

D:\AI-Learning\Projects\bedding-order-parser

## 9. 桌面双击启动结果

- 启动方式：通过桌面快捷方式启动一次，命令链来自 .lnk，不是直接执行 Python 命令。
- HTTP 健康检查：成功，/health 返回可用状态。
- 首页检查：成功，/ 返回订单解析助手页面内容。
- 窗口标题检查：成功，实际窗口进程标题为 订单解析助手。
- 说明：快捷方式启动时先由项目 .venv\Scripts\pythonw.exe 拉起实际带窗口的 pythonw.exe 子进程，窗口标题位于子进程上；本轮按该真实窗口进程完成正常关闭验收。

## 10. 是否出现控制台

未发现控制台启动链。快捷方式 TargetPath 为 pythonw.exe，不是 python.exe、uv、cmd.exe、powershell.exe 或 VS Code。启动期间相关进程均为 pythonw.exe，未出现相关 python.exe 或 uv.exe 进程。

## 11. 五页面是否正常

五页面入口检查正常。启动后读取本地前端脚本，确认以下入口仍存在：

- enderUpload
- enderProgress
- enderResult
- enderMatch
- enderHistory

本轮没有上传 Excel，没有点击开始解析，没有执行真实 PI。

## 12. 正常关闭结果

正常关闭成功。对实际带窗口标题的 pythonw.exe 进程执行 CloseMainWindow()，返回 True。

## 13. HTTP 服务、端口和进程退出情况

关闭后检查结果：

- edding_order_parser.desktop 相关进程：0
- edding_order_parser.web 相关进程：0
- 项目相关 pythonw.exe 残留：0
- 127.0.0.1:8000 监听：0
- desktop_runtime.json 残留：无

## 14. 是否加载 BGE-M3、Torch 和 FAISS

未加载。验收仅启动桌面窗口、访问本地 /health、首页和静态前端脚本，没有触发 parse_order、match_orders、BGE-M3、Torch 模型或 FAISS 读取。

## 15. 是否运行真实 PI

否。本轮未上传 Excel，未点击开始解析，未运行真实 PI，未读取真实业务数据用于解析或匹配。

## 16. 实际提交文件

本轮准备提交的文件只有：

- packaging/create_local_desktop_shortcut.ps1
- docs/reports/GATE_4B_R5_LOCAL_DESKTOP_SHORTCUT_REPORT.md

桌面实际 .lnk 文件属于本机文件，不提交到 Git。

## 17. 最终 Commit

本报告随提交 eat: add one-click desktop shortcut 一起提交。提交后的实际短哈希以最终回复和 git log -1 --oneline 为准。

## 18. 工作区状态

提交前允许变更范围仅包含本轮脚本和本报告。提交后要求工作区干净。

## 19. 当前本地桌面版是否达到演示条件

达到本机演示条件。当前电脑可以通过桌面快捷方式双击启动订单解析助手，无需 VS Code、无需输入终端命令，启动后可显示本地桌面窗口和五页面入口，关闭窗口后 HTTP 服务、8000 端口和后台 Python 进程均正常退出。

## 20. 后续构建 Onedir 条件

后续只有在需要分发到其他电脑时才构建 Onedir。本轮不构建 Onedir、Onefile 或 EXE 安装包。
