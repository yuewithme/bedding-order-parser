# 订单解析助手源代码包说明

## 包身份

- 项目：订单解析助手（bedding-order-parser）
- 分支：`master`
- Git commit：`a5c9056dda6e96d18a31c81873ff753d8acfc1be`
- 打包日期：2026-08-19
- 打包原则：以该提交的全部 Git 已跟踪文件为准

## 主要内容

- `src/bedding_order_parser/`：完整生产源码
- `tests/`：完整自动化测试
- `pyproject.toml`：Python项目、依赖与测试配置
- `README.md`：项目说明
- `AGENTS.md` 与 `.codex/skills/bedding-gate/SKILL.md`：项目长期规则和Gate流程
- `docs/`：设计、验收、架构图、截图和最终文档
- `.env.example`：不含真实凭证的配置示例

## 明确排除

- `.git/`版本数据库
- `.env`及真实API Key、Authorization或本机秘密配置
- `.venv/`、缓存、`__pycache__/`、pytest缓存
- 本机Job、上传文件、运行时状态、真实订单和物料索引
- 未跟踪的恢复/交接文档和个人结题报告

## 运行提示

建议使用项目README和`pyproject.toml`配置Python环境。AI Provider、真实字典和物料资源均需由使用者在授权环境中单独配置；本包不附带任何真实凭证、客户订单或生产物料数据。

## 最终验收事实

该代码基线所属项目最终签署结果为670项测试全部通过（670 passed，0 skipped，0 failed）。本源代码包由Git提交直接归档，不从当前工作区临时拼接文件。
