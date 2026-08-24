# 最终文档视觉素材索引

> All screenshots use synthetic/Fake data. No real customer/order/material data is included.

本目录服务于《订单解析助手项目设计与实现报告》和《订单解析助手技术解析与答辩学习手册》。截图由当前 `master` 的真实前端模板、JavaScript 与 CSS 渲染；API 状态来自临时内存 Fake 服务。所有业务名称、订单值、请求计数和物料编码均为人工合成。

## 截图

所有截图均为 PNG、`1440 x 900`，未打开开发者工具或测试框架界面。

| 文件名 | 来源 / Route | 展示功能 | 项目报告建议章节 | 技术手册建议章节 | Fake 数据 | 敏感检查 |
|---|---|---|---|---|---|---|
| `screenshots/01_首页_模式选择.png` | 当前前端 `#upload` | 上传、Standard/AI 双模式、开始解析 | 产品概览、用户流程 | UI 路由与模式合同 | 是 | 通过 |
| `screenshots/02_AI整单解析_授权确认.png` | `#upload` 真实弹窗 | Provider/模型、发送范围、Token 提示与确认 | AI 功能与安全边界 | AI 预检及授权 | 是 | 通过 |
| `screenshots/03_AI整单解析_结构确认进度.png` | `#job/ai-structure/progress` | 12% 结构确认、五阶段同步 | AI 处理流程 | Job 阶段映射 | 是 | 通过 |
| `screenshots/04_AI整单解析_字段提取进度.png` | `#job/ai-extract/progress` | AI 字段提取、区块、调用、Token | AI 处理流程 | V2 telemetry | 是 | 通过 |
| `screenshots/05_AI整单解析_完成页.png` | `#job/ai-completed/result` | 完成、记录数、Review 汇总、当前 Revision | 核心成果、结果展示 | AI-first 完成合同 | 是 | 通过 |
| `screenshots/06_AI_Python对照.png` | 同上，点击“全部” | agree/different/ai_only/python_fill/both_missing | AI-first 设计 | comparison 与 field policy | 是 | 通过 |
| `screenshots/07_Evidence来源展开.png` | 同上，点击“查看来源位置” | Sheet、单元格、短 excerpt | 可解释性设计 | provenance binder | 是 | 通过 |
| `screenshots/08_Revision_使用本地规则.png` | 同上，执行 Revision | 用户选择本地规则后的正式值与来源 | 人工复核工作流 | immutable revision | 是 | 通过 |
| `screenshots/09_Revision_手动修改.png` | 同上，保存“珍珠白” | 手工修订后的值、来源和状态 | 人工复核工作流 | 本地下游重发布 | 是 | 通过 |
| `screenshots/10_AI技术失败页.png` | `#job/ai-awaiting/progress` | 安全错误、重试、独立 Standard 重处理 | 失败处理 | hard technical gate | 是 | 通过 |
| `screenshots/11_Standard重新处理.png` | 从失败页实际点击重处理 | 新 Standard Job 的独立进度 | 双模式边界 | Job lineage | 是 | 通过 |
| `screenshots/12_Standard进度页.png` | `#job/standard-progress/progress` | 68% 物料匹配与五阶段 | Standard 流程 | Standard 状态映射 | 是 | 通过 |
| `screenshots/13_Standard完成与ZIP.png` | `#job/standard-completed/result` | 五类结果、匹配统计、ZIP；Excel 显示当前入口 | Standard 成果 | 五类发布与导出 | 是 | 通过 |
| `screenshots/14_物料匹配详情.png` | `#job/standard-completed/match/0` | Fake 编码、参考分数、字段对比与 Top 5 | 物料匹配设计 | hybrid matcher | 是 | 通过 |
| `screenshots/15_历史任务.png` | `#history` | 搜索、日期、状态、模式、任务查看 | 桌面产品功能 | 历史 API/UI | 是 | 通过 |
| `screenshots/16_Help中心.png` | `#help` | 术语、使用方法、处理流程顶部入口 | 可用性与交付 | 五类术语与产品边界 | 否（静态帮助内容） | 通过 |

## 架构图

每张图同时提供 SVG（Word 高质量插图）和 `1600 x 1000` PNG（兼容版本），均采用黑、白、灰配色。

| 文件名 | 内容 | 项目报告建议章节 | 技术手册建议章节 | Fake 数据 | 敏感检查 |
|---|---|---|---|---|---|
| `diagrams/diagram_01_系统总体架构.svg/.png` | Desktop UI、JobService、双模式、共享下游、五类发布 | 系统总体设计 | 系统分层与模块职责 | 不适用 | 通过 |
| `diagrams/diagram_02_双模式业务流程.svg/.png` | Standard 与 AI Enhanced 泳道、共同汇合点 | 业务流程设计 | 双模式合同 | 不适用 | 通过 |
| `diagrams/diagram_03_AI证据与字段决策.svg/.png` | Evidence、hard validation、AI/Python 对照、AI-first 决策 | AI-first 架构 | Contract V2 / provenance / comparison | 不适用 | 通过 |
| `diagrams/diagram_04_物料向量与混合匹配.svg/.png` | BGE-M3、FAISS、SQLite、混合召回和 Top candidates | 物料匹配架构 | 向量建库与混合检索 | 不适用 | 通过 |

## 安全与使用说明

- Synthetic 客户：`示例家居有限公司`；Synthetic 物料编码：`MAT-DEMO-001` 等。
- 截图中的 Ark 调用、HTTP 尝试与 Token 全部来自 Fake Job 状态；真实调用均为 0。
- 未写入 API Key、Authorization、真实请求/响应、本机路径、真实 PI 或真实物料主数据。
- `13_Standard完成与ZIP.png` 保留当前真实 UI 状态：ZIP 可见，Excel 仍显示现有产品入口，不把未来能力伪装为已交付。
- 图示中的 FAISS 被准确描述为向量近邻索引，不是数据库；系统也未被描述成完整 RAG。
- AI 只提取 17 个业务字段；正式行号由本地生成，ERP 物料编码与参考分数由 MaterialMatcher 产生。
