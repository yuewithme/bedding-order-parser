# 本地项目最终退役 Gate 报告

## Gate 目标

在不上传真实业务数据的前提下，对不可从 GitHub 恢复的核心业务资料建立并验证加密备份，记录退役证据，并在恢复口令安全交付后退役本地项目。

## 基线

- 分支：`master`
- 任务开始 HEAD：`0fac5c2c5c0d7cb6915aaa465ff6b30f47cc8871`
- 任务开始工作区：干净，与 `origin/master` 同步。
- GitHub：公开仓库 `yuewithme/bedding-order-parser`。

## 备份合同

- 保留 `data/input/pi`、`data/reference`、`data/golden`。
- 使用随机高强度口令、PBKDF2-SHA256 和 AES-256-GCM。
- 备份内包含逐文件相对路径、大小和 SHA-256 清单。
- 必须实际解密和解包，并与源文件逐项匹配后才能视为可恢复。
- 恢复口令不写入项目、Git、备份目录或本报告。

## 禁止范围

- 不上传或公开真实 PI、物料主数据、字典、golden 对照或密钥。
- 不备份 `.venv`、物料 SQLite、FAISS 索引、缓存或其他可重建生成物。
- 不触碰冻结的 `Day01` 目录、GitHub 远端或非项目专属模型缓存。

## 备份、验证与恢复

- 备份位置：`%USERPROFILE%\Documents\BeddingOrderParser-Backup`，位于待退役项目外。
- 加密包：`BeddingOrderParser-CoreData-2026-08-28.bopbak`，25,236,026 字节。
- 加密包 SHA-256：`218f61a3436e8758ff52720ea307df445cb8f644060a67ca1bc21fd084f3e92a`。
- 源资料：24 个文件，共 25,199,631 字节。
- 加密参数：AES-256-GCM；PBKDF2-SHA256，600,000 次迭代；随机 16 字节 salt 和 12 字节 nonce。
- 内部解密验证：解密 tar SHA-256 与加密前一致；24 个文件的相对路径、大小和 SHA-256 全部一致。
- 交付脚本验证：实际运行 `Restore-BeddingOrderParserBackup.ps1`，成功恢复并再次验证 24 个文件；PowerShell 语法检查 0 错误。
- 明文清理：两次验证生成的 tar、staging 和恢复目录均已删除；备份目录只保留加密包、SHA-256 文件、恢复脚本和说明。
- 恢复口令：仅保存于当前会话待交付，未写入磁盘、项目、Git 或报告。

## 提交、推送与删除状态

- 备份与验证记录提交：`e8a4b42afd2e4c50a01bea402faad48bdc7936b1`。
- 该提交已推送 GitHub；本地 HEAD、`origin/master`、`git ls-remote --heads origin master` 和 GitHub commits API 四方一致。
- 本报告的推送补记由本报告所在的闭环文档提交承载，其最终远端 HEAD 在交付前再次核对。
- 本地删除：未执行；等待用户明确确认已保存恢复口令。

## 未执行事项

- 未解析真实 PI。
- 未调用真实 AI Provider 或其他真实 API。
- 未加载 BGE-M3 或 FAISS 索引。
- 未上传业务资料。
- 未在用户确认已保存恢复口令前删除本地项目。
