# Codex 交付协议

本协议适用于 Bedding Order Parser 后续每个 Gate 的收尾。目标是让用户不用猜文件在哪里，也让新 Codex 会话能从稳定交接点继续。

## 1. 每个 Gate 必须交付

1. 生成一份最终 Markdown 报告，放在 `docs/reports/`。
2. 更新 `docs/handoffs/CODEX_CURRENT_HANDOFF.md`。
3. 创建一份版本化归档交接，放在 `docs/handoffs/archive/`。
4. 最终聊天回复列出本轮用户需要查看的文件。
5. 最终聊天和报告中的关键文件必须使用可点击链接。

如果某个文件按任务要求未生成，必须明确写 `未生成`，不能让用户猜。

## 2. 报告必须包含

- 初始仓库路径、分支、HEAD、Git 作者和工作区状态。
- 本轮 Gate 目标。
- 当前边界和明确不做的范围。
- 关键模块职责。
- 业务字段合同或接口合同。
- 真实样本验证结果。
- 测试命令和结果。
- Git 操作记录。
- 输入保护、输出保护和 Day01 隔离确认。
- 已知限制、风险和未实现功能。
- 下一步建议。
- 交付文件清单。

## 3. 链接规则

- 报告内的本地项目文件使用相对 Markdown 链接，并同时写出绝对 Windows 路径。
- 最终聊天回复使用绝对路径 Markdown 链接，格式类似 `[文件名](<D:/path/with spaces/file.md>)`。
- 文件名或路径含空格、中文、括号时，链接目标使用尖括号包裹。
- 写入最终回复前必须对每个链接目标执行 `Test-Path`。
- 不存在的文件不能列为可点击链接。
- 缺失文件必须写 `未生成`。

## 4. 防猜测规则

- 不用“在输出目录里找一下”这类模糊说法。
- 不只给目录，必须给具体文件。
- 同一类结果有多个代表样本时，明确文件名和用途。
- 报告里的本地引用必须能从该报告所在目录正确跳转。
- 用户要求“给 GPT 查看”时，优先给代表性 JSON 的具体文件链接和简短说明。

## 5. 最终聊天格式

最终聊天只保留高信号摘要和链接：

- 本 Gate 是否完成。
- 关键报告和交接文件链接。
- 代表性验证文件链接。
- 测试结果。
- commit 短哈希和信息。
- 工作区是否 clean。
- tag、remote、push 状态。

不要在最终聊天重复整份报告。详细内容进入 Markdown 报告。

## 6. 提交前检查

提交前至少执行：

```powershell
uv run pytest
git diff --check
git status --short
git diff --stat
git diff --name-status
```

只 stage 本轮允许提交的文件。提交前再执行：

```powershell
git diff --cached --check
git diff --cached --stat
git diff --cached --name-status
```

禁止把 `src/`、`tests/`、`pyproject.toml`、`uv.lock`、真实 Excel、既有业务 JSON 或 Day01 改动混入纯文档收尾提交。

## 7. Gate 结束检查

提交后执行：

```powershell
git status --short
git log --oneline --decorate -3
uv run pytest
git tag -n
git remote -v
```

如任务要求 Day01 隔离确认，额外只读执行：

```powershell
cd D:\AI-Learning\Projects\Day01
git status --short
git rev-parse HEAD
git tag -n
```

任何检查失败都必须在最终回复中说明，不得用成功语气带过。
