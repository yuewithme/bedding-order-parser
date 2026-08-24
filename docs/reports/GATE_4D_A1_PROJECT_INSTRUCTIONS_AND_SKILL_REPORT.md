# Gate 4D-A1 项目级 AGENTS.md 与 Codex Skill 报告

生成日期：2026-08-01
项目目录：`D:\AI-Learning\Projects\bedding-order-parser`

## 1. 本轮目标

本轮只建立长期项目规则和可复用 Gate 工作流，不进行业务开发。目标文件为：

1. 项目根目录 `AGENTS.md`；
2. `.codex/skills/bedding-gate/SKILL.md`；
3. 本报告：`docs/reports/GATE_4D_A1_PROJECT_INSTRUCTIONS_AND_SKILL_REPORT.md`。

不得修改生产代码、测试、前端、解析器、字典、物料匹配、数据、Day01 或既有报告；不得调用真实 API、BGE-M3 或 FAISS；不得提交两份恢复文档。

## 2. Git基线与开始前核对

- 分支：`master`
- 初始完整 HEAD：`5da46f3b9a5cf8c3fbeb40ab7a17042cd4bbb515`
- 初始短 HEAD：`5da46f3`
- 最近提交：`5da46f3 docs: design ai enhanced order parsing`
- 初始工作区：只有以下两份既有未跟踪恢复文档：
  - `CODEX_HANDOFF_AND_RECOVERY_2026-07-30.md`
  - `CODEX_RECOVERY_AUDIT_ROUND_1_REPORT_2026-08-01.md`
- Git 作者：`小艾 <1746762028@qq.com>`。

根目录原有 `AGENTS.md` 是早期 Gate 规则，仍写着项目未接入 LLM、API、前端和向量能力，与当前 D1、D2A、4D-A 实际状态冲突。本轮对它做了整体收敛，只保留长期稳定规则；没有修改任何既有报告。

## 3. 阅读依据与当前事实

本轮读取：

- `docs/reports/GATE_4D_A_AI_FULL_ORDER_PARSE_CONTRACT_DESIGN_REPORT.md`
- `docs/reports/GATE_4C_D1_STANDARD_MODE_AI_REVIEW_OFFLINE_REPORT.md`
- `docs/reports/GATE_4C_D2A_REAL_RESPONSE_COMPATIBILITY_FIX_REPORT.md`
- `src/bedding_order_parser/models/final_result.py`
- `src/bedding_order_parser/llm/contracts.py`
- 本轮原有 `AGENTS.md`

当前代码事实：

- 固定正式结果为 20 字段；前 19 个字段为字符串，`相似分数`为浮点数。
- 五类核心 JSON 是正式业务、解析诊断、字典验证、物料候选、物料匹配摘要。
- D1/D2A 的标准模式 AI 是用户确认后针对单条已完成记录的只读 Sidecar，不写正式结果。
- 4D-A 的整单模式是独立的 `parse_mode` 架构，必须经过证据和本地校验。

## 4. 两个长期文件的设计结果

### 4.1 `AGENTS.md`

新规则控制在 47 行，内容只覆盖长期边界：

- 项目目录与 Day01 冻结边界；
- 20 字段名称、顺序和类型；
- 五类核心 JSON；
- `standard` 与 `ai_enhanced` 的责任边界；
- 标准模式用户确认后的单记录 Sidecar；
- 整单 AI 的证据、Python shadow、字典与本地校验；
- 本地优先结构识别，歧义时才调用 AI；
- 17 个 AI 业务字段；
- `行号`由本地 Sheet/行坐标确定性生成；
- 物料编码和相似分数只由匹配层生成；输入证据中已有的物料编码文本只能引用，不能写回；
- API Key、真实 PI、Job、Sidecar、Provider 原始响应和外发范围安全规则；
- Git、定向测试和每 Gate 唯一报告规则。

### 4.2 `bedding-gate/SKILL.md`

Skill 控制在 78 行，包含合法 frontmatter、Gate 通用步骤、合同锚点、五种工作模式和停止条件：

- 只读审计；
- 纯设计；
- 离线实现；
- UI 任务；
- 经授权的真实 API 验收。

通用流程覆盖 Git 基线、阅读合同、声明范围、最小修改、定向测试、正式产物与安全验证、唯一报告、显式暂存、提交和最终哈希/工作区/报告交付。停止条件覆盖未知未提交代码、合同冲突、真实调用未授权、测试或正式校验失败、密钥/真实数据泄露风险、Day01或受保护匹配边界被触及。

## 5. 17字段与本地行号的冲突消解

当前最终 20 字段中，排除 `物料编码`和`相似分数`后有 18 个字段；其中 `行号`不是模型业务抽取字段，而是由本地确定性源坐标生成。因此本轮两个长期文件统一规定：

- 模型实际只提取 17 个业务字段；
- `行号`由本地生成并校验；
- `物料编码`和`相似分数`由后续物料匹配层生成。

这保留了最终 20 字段合同，也避免把稳定的源行身份交给模型。既有 4D-A 设计报告没有被修改；本报告记录该实现级解释，后续离线实现应以这两份项目规则为执行入口。

## 6. 一致性与过时规则检查

重新读取两份目标文件后：

- `AGENTS.md`：47 行，低于约 120 行限制；
- `SKILL.md`：78 行，低于约 140 行限制；
- 两份文件都使用相同的 `standard`、`ai_enhanced`、17 个 AI 字段、本地行号、物料匹配唯一生产权和五类 JSON 边界；
- 两份文件都明确区分标准模式单记录 Sidecar与整单 AI 解析；
- 两份文件没有过时的旧布尔开关设计；
- 两份文件没有旧模型任务分配内容；
- Skill 目录只保留用户要求的 `SKILL.md`，没有模板附属文件；
- 项目内未生成临时报告源文件或额外资源目录。

## 7. Skill验证与测试边界

已按 `skill-creator` 要求运行初始化脚本，并尝试运行 `quick_validate.py`。验证脚本未能启动，原因是当前 bundled Python 缺少 `yaml` 模块：

```text
ModuleNotFoundError: No module named 'yaml'
```

本轮没有安装依赖、修改环境或扩大项目依赖。已用重新读取、frontmatter 目视检查、文件行数检查、关键术语扫描、目录清单和 `git diff --check` 完成人工等价检查。

本轮未运行 pytest、真实 PI、真实 API、BGE-M3 或 FAISS，因为本轮只创建规则与 Skill，且任务明确禁止这些业务验证动作。

## 8. 文件与安全检查

本轮目标文件：

- `AGENTS.md`：更新项目级长期规则；
- `.codex/skills/bedding-gate/SKILL.md`：新增复用工作流；
- 本报告：唯一 Gate 报告。

未修改：

- `src/`、`tests/`、前端、解析器、字典、物料匹配和数据；
- 三份既有 Gate 报告；
- Day01；
- 两份恢复文档。

未调用真实 API，未读取或发送真实 PI 业务内容，未生成或提交真实 Job、Sidecar、原始 Provider 响应或密钥。`git diff --check` 通过。

## 9. 提交计划与下一步

只显式暂存三个目标文件，提交信息为：

```text
chore: add project instructions and gate skill
```

提交后重新核对完整 HEAD、提交文件清单、工作区和报告绝对路径。下一轮可直接读取 `AGENTS.md` 与 `$bedding-gate` Skill，再按指定 Gate 合同执行，不必重复解释稳定项目边界。
