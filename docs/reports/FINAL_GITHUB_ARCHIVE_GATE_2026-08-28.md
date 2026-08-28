# GitHub 最终归档 Gate 报告

## Gate 目标

核实项目的可安全归档内容，将完整 Git 历史推送至用户明确要求的公开 GitHub 仓库，并验证本地与远端 HEAD 一致。

## 基线

- 分支：`master`
- 任务开始 HEAD：`4a04b78d225da4cf36eaaa95f32fcac2d71b181a`
- 作者：`yuewithme <430714704@qq.com>`
- 任务开始工作区：干净
- 任务开始远端：未配置

## 范围与边界

- 范围：Git 完整性、可复现文件、历史范围、敏感信息、离线测试、提交、推送和远端 HEAD 复核。
- 禁止：真实 PI、业务参考资料、本地 Job/Sidecar、物料库、向量索引、密钥和冻结目录。
- 本轮不修改生产代码、解析合同或匹配数据；仅修复最终验证发现的两处 Windows LF/CRLF 测试兼容性阻断。

## 本地唯一数据提示

以下内容受 `.gitignore` 和项目规则保护，不会上传 GitHub：

- 真实 PI 文件：13 个，约 19.2 MB。
- 本地参考/物料资料：8 个，约 6.0 MB。
- 本地物料库：3 个，约 42.0 MB。
- 本地向量索引：5 个，约 276.7 MB。

删除本地项目将丢失这些未上传的内容；不得将其解释为已由 GitHub 备份。

## 审计与验证

### Git 与历史

- `git fsck --full`：通过，无对象损坏。
- 任务开始时共 3 个可达提交、328 个已跟踪文件；最大已跟踪文件约 1.14 MB，无 GitHub 单文件体积阻断。
- 全历史路径检查未发现 `data/input`/`data/reference`/`data/golden`/`data/output` 中的业务文件曾被提交。
- 全历史未发现私钥、GitHub/OpenAI/AWS/Slack 常见真实凭证格式。旧 Provider 报告中的 `Authorization: Bearer` 仅为明确脱敏的文字说明。
- `.env` 不存在；`.env.example` 为已跟踪的无凭证示例。

### 依赖与测试

- `uv lock --check`：通过，87 个包解析成功。
- 默认 pytest 临时目录存在 Windows 权限异常；改用任务专用临时目录后测试可正常执行。
- 修复前完整离线套件：`682 passed, 2 failed`；两项失败均由测试辅助代码只匹配 LF，无法读取 Windows CRLF 检出的 `app.js` 引起。
- 最小修复：`tests/web/test_ai_progress_frontend.py` 和 `tests/web/test_ai_review_frontend.py` 的常量终止符同时接受 LF/CRLF；定向复验 `3 passed`。
- 修复后两次完整离线套件均为 `683 passed, 1 failed`，但失败项不同：一次为 FakeTransport 合同验收，一次为双进程 leader 竞争；两项紧接着单独复验均为 `1 passed`。
- 结论：684 项测试均有通过证据，但未取得单轮 `684 passed`；完整套件在当前 Windows 环境中存在偶发时序/状态抖动，不作隐瞒。

### 公开发布安全

- 用户已明确要求创建公开 GitHub 仓库。
- 实际要推送的 Git 历史不包含本地忽略的真实 PI、参考/物料数据、物料库、向量索引或密钥。

## 未执行事项

- 未调用真实 AI Provider 或其他真实 API。
- 未加载 BGE-M3 或 FAISS 真实索引。
- 未解析真实 PI。
- 未上传忽略的业务数据或本地生成物。
- 未执行本地删除。

## 提交、远端与最终工作区

- 归档准备提交：`214fddec6313933de64b0ccc16b1edd16abc9bf8`，5 个必要文件，提交后工作区干净。
- GitHub 仓库：`https://github.com/yuewithme/bedding-order-parser`，可见性 `PUBLIC`，默认分支 `master`。
- 首次 `git push -u origin master` 被 GitHub 服务端 `Internal Server Error` 拒绝，远端仍为空；第二次重试成功建立 `master`。
- 首次推送后核验：本地 HEAD、`origin/master`、`git ls-remote --heads origin master` 和 GitHub commits API 均为 `214fddec6313933de64b0ccc16b1edd16abc9bf8`，四方一致。
- 本报告的推送结果补记由本报告所在的闭环文档提交承载；该提交的最终远端 HEAD 和工作区状态在交付前再次以命令核验。
