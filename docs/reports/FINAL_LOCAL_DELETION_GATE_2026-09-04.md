# 本地项目最终删除 Gate 报告

## Gate 目标

在 GitHub 与核心业务资料加密备份均可恢复的前提下，将本地项目目录和项目专属 AppData 移入 Windows 回收站，同时保留 GitHub、加密备份和冻结边界。

## 基线

- 分支：`master`
- 任务开始 HEAD：`bbc3b6427745986bef1c08b55db6e42b5d8295d6`
- 任务开始工作区：干净，与 `origin/master` 同步。
- GitHub：公开仓库 `yuewithme/bedding-order-parser`。
- 删除方式：Windows 回收站，不永久删除。

## 删除目标

- 项目根目录：当前 Bedding Order Parser Git 工作区。
- 项目专属 AppData：`%LOCALAPPDATA%\BeddingOrderParser`。

## 明确保留

- `%USERPROFILE%\Documents\BeddingOrderParser-Backup`：AES-256-GCM 加密核心业务资料备份。
- GitHub 公开仓库及其 `master` 完整历史。
- 项目边界外的冻结 `Day01` 路径；该路径及其上级路径在删除前已不存在，本任务不创建、不修改它。
- 非本项目专属的模型缓存、Python 安装、GitHub CLI 凭证和其他用户数据。

## 删除前验证

- 备份目录只包含加密包、SHA-256 文件、恢复脚本和恢复说明，共 4 个文件。
- 加密包 SHA-256：`218f61a3436e8758ff52720ea307df445cb8f644060a67ca1bc21fd084f3e92a`，与创建时一致。
- 使用交付恢复脚本和恢复口令实际恢复：24 个文件的路径、大小和 SHA-256 全部一致。
- 验证后明文目录已清理，无临时明文遗留。
- 本地 HEAD、远端 `master` 和 GitHub commits API 均为 `bbc3b6427745986bef1c08b55db6e42b5d8295d6`。
- 冻结 `Day01` 边界及其上级路径在本轮删除前已不存在；本轮尚未执行删除，该事实不是本任务造成。

## 提交、推送与删除结果

删除前检查点待提交。实际回收站删除与删除后边界验证将在推送该检查点后执行，并由临时闭环克隆补记。

## 未执行事项

- 未解析真实 PI。
- 未调用真实 AI Provider 或其他真实 API。
- 未加载 BGE-M3 或 FAISS 索引。
- 未上传业务资料。
- 未永久删除任何文件；回收站移动待执行。
