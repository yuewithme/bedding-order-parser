# Final Documentation Visual Assets 执行报告

## 1. 基线

- 分支：`master`
- 起始完整 HEAD：`38fc646ef19cba15a394206258c69cbfe92ba9a8`
- 起始短 HEAD：`38fc646`
- 起始已跟踪工作区：干净
- 起始既有未跟踪文档：7 份，均未读取、覆盖、清理或暂存
- Release 基线：`CORE IMPLEMENTATION COMPLETE`、`READY TO CLOSE`、`RELEASE BLOCKERS = 0`

## 2. 采集方法与真实性

- 使用当前 `master` 的真实 `index.html`、`app.js` 和 `styles.css` 渲染 UI。
- 使用 Microsoft Edge + Playwright CLI，统一 viewport `1440 x 900`。
- 临时 Python loopback harness 仅提供内存 Fake API；未重新制作或仿制 UI。
- 覆盖真实点击路径：AI 授权弹窗、Review“全部”、Evidence 展开、使用本地规则、手动修改并保存、AI 失败后的独立 Standard 重处理。
- 视觉数据均为人工合成，包括客户、业务值、Job、模型显示、调用计数和 `MAT-DEMO-*` 物料编码。

## 3. 截图结果

- 计划：16 张
- 实际：16 张
- PASS：16 张
- 缺失：0 张
- 尺寸：全部 `1440 x 900`
- 格式：全部 PNG

状态覆盖：上传双模式、AI 授权、结构确认、字段提取、AI 完成、五类 Review 状态、Evidence、两种 Revision、技术失败、独立 Standard 重处理、Standard 进度/完成、物料 Top 5、历史与 Help。

## 4. 架构图结果

- 计划：4 张图，每张 SVG + PNG
- 实际：4 张 SVG + 4 张 PNG
- PNG 尺寸：全部 `1600 x 1000`
- 视觉：黑白灰、A4 黑白打印可读、无渐变/发光/3D/营销式 AI 图形

图示内容：

1. 系统总体架构：Desktop UI、JobService、双模式、共享下游、固定 20 字段与恰好五类结果。
2. 双模式业务流程：Standard 与 AI Enhanced 独有节点及共同汇合点。
3. AI 证据与字段决策：Evidence Catalog、hard technical validation、Python Shadow、AI-first field policy 与 Review。
4. 物料向量与混合匹配：CSV 建库、BGE-M3、FAISS、SQLite、混合召回、Top candidates 与正式编码责任边界。

## 5. Synthetic / Fake 边界

| 项目 | 实际次数 |
|---|---:|
| 真实 Ark | 0 |
| external HTTP | 0 |
| 真实 PI | 0 |
| 真实字典 | 0 |
| 真实物料库 | 0 |
| BGE-M3 | 0 |
| 生产 FAISS | 0 |

仅使用 loopback HTTP 访问当前前端和临时 Fake API/静态 SVG；该流量不属于 external HTTP。

## 6. 质量与安全检查

- 逐组使用图像查看工具目视检查 16 张截图和 4 张图。
- 检查文字可读、关键控件未被遮挡、无开发者工具、console、Playwright 调试 UI 或错误 toast。
- 文本扫描未发现 `API Key`、`Authorization`、`Bearer`、本机用户路径或项目绝对路径。
- 未发现真实姓名、真实客户、真实订单、真实 PI 或真实物料编码。
- 相似分数在 UI 中明确为“参考分数，不代表准确率或正确概率”。
- 架构图未把 Transformer 写成自研、未把 FAISS 写成数据库、未把项目写成完整 RAG、未把 AI 写成物料编码来源。

## 7. 清理结果

- 临时 synthetic workbook：已删除。
- 临时 Fake Job/API harness：已删除并停止。
- 临时 SVG 静态服务：已停止。
- Playwright 浏览器会话：已关闭。
- Playwright snapshots / console log：已删除。
- trace / video：未生成。
- 端口 `8768`、`8770`：无监听。

## 8. 生产代码与项目状态

- 生产代码修改：否。
- 产品合同修改：否。
- 测试修改：否。
- 仅新增 `docs/documentation_assets/**` 和本报告。
- Release 结论保持：`READY TO CLOSE`。

## 9. 发现的 UI 问题

- 新发现产品 UI 问题：0。
- 采集过程中遇到 2 个仅属于截图工具状态的问题：授权弹窗跨 hash 保留、`file://` SVG 被浏览器限制。均通过刷新独立路由或 loopback 静态服务解决，未修改产品。
- 当前 Excel 导出入口保持现有真实状态；报告素材未将其描述成已正式开放能力。

## 10. 素材目录

- 截图：`docs/documentation_assets/screenshots/`
- 图示：`docs/documentation_assets/diagrams/`
- 索引：`docs/documentation_assets/README.md`
- 本报告：`docs/reports/FINAL_DOCUMENTATION_VISUAL_ASSETS_REPORT.md`

结论：视觉素材已满足最终生成《订单解析助手项目设计与实现报告》和《订单解析助手技术解析与答辩学习手册》的条件。
