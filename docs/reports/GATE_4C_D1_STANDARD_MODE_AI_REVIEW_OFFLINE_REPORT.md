# Gate 4C-D1 标准解析模式中文 AI 复核离线报告

- 项目：bedding-order-parser
- 项目目录：D:\AI-Learning\Projects\bedding-order-parser
- 执行日期：2026-08-01
- 执行性质：中断恢复后的正式离线收口
- 交接对象：GPT / 下一轮 Codex

## 1. 任务目标

本轮唯一目标是完成标准解析模式下的单记录中文 AI 复核离线收口。标准 Python
解析流程保持纯确定性，不自动调用 AI；只有用户在某一条已完成订单记录上点击
“AI复核建议”并通过确认弹窗后，系统才启动该记录的一次 Provider 调用。

AI 结果继续作为只读 Sidecar 保存，用于缓存、重启读取和重复费用保护，不修改
正式 20 字段 JSON，不修改物料候选 JSON，也不进入默认业务 ZIP。

## 2. Git 基线

开始前实际 Git 输出：

- 分支：master
- 完整 HEAD：4d6b008e2c78e265bea7dec43f03503b938d3d5c
- 短 HEAD：4d6b008
- 基线提交：feat: connect desktop ai advisory flow
- 暂存区：为空
- 半完成修改：11 个已跟踪文件
- 既有未跟踪文档：CODEX_HANDOFF_AND_RECOVERY_2026-07-30.md
- 既有未跟踪文档：CODEX_RECOVERY_AUDIT_ROUND_1_REPORT_2026-08-01.md

本轮没有执行 reset、clean、stash、覆盖式 checkout、amend、tag 或 push。

## 3. 恢复的半完成文件

本轮以恢复审计确认的 11 个半完成文件为基础继续，没有覆盖或丢弃既有实现：

1. src/bedding_order_parser/llm/volcengine_ark.py
2. src/bedding_order_parser/web/ai_advisory.py
3. src/bedding_order_parser/web/routes.py
4. src/bedding_order_parser/web/services.py
5. src/bedding_order_parser/web/static/app.js
6. src/bedding_order_parser/web/static/styles.css
7. tests/llm/test_volcengine_ark_provider.py
8. tests/web/test_ai_advisory.py
9. tests/web/test_gate4b_frontend.py
10. tests/web/test_routes.py
11. tests/web/test_services.py

保留的核心方向包括：所有 completed 记录可手动复核、用户确认后调用、单记录
串行保护、Sidecar 原子保存、缓存命中不重调、历史英文结果显式再生成、固定标签
中文化、技术证据默认折叠、默认 ZIP 只含五类核心 JSON。

## 4. 中文 Provider 指令

Provider 开发者指令已明确：

- 定位为床品订单单记录复核助手；
- 只能使用请求内证据；
- 不补造缺失值；
- 不自动确认物料编码；
- 不写 ERP；
- 不覆盖确定性解析结果；
- 不输出私有思维链；
- reasoning_summary、suggested_fields.reason、warnings、
  material_assessment.reason 和人工核查建议必须使用简体中文；
- PI 英文证据、客户原名、产品描述、物料编码、型号和专有名词允许保留原文；
- Schema 字段名和枚举值保持合同规定；
- prototype_match_score 只是未经业务真值标定的参考匹配分数，不是准确率或
  正确概率，不能仅凭该分数判断候选正确与否。

Provider 函数描述也已改为“为当前单条订单记录返回严格 Schema 的简体中文复核
建议”。

## 5. 20 字段映射

页面已为正式 20 字段提供显式中文映射，不会把以下已知字段显示为“其他字段”：

客户、币种、业务员、表头备注、行号、物料编码、物料名称、规格、颜色、面料、
面料-涤棉成分、款式、加标方式、尺寸类型、数量、行备注、计划发货日期、
包装方式、是否绣花、相似分数。

同时补充 salesperson、sales_person、header_note、line_number、
fabric_composition、quantity、planned_ship_date、similarity_score 和
prototype_match_score 等英文别名。composition 的中文显示已从“面料成分”
收敛为正式字段名“面料-涤棉成分”。

## 6. 中文检测策略

旧逻辑按整份动态文本的中英文数量做比例判断，并限制每段英文词数量。这会让
“中文业务解释 + 较长英文产品描述/型号/证据”的合格结果被误判为历史英文。

新逻辑改为：

- 只检查业务动态字段，不检查 PI 原始证据、证据引用、客户名、编码和型号；
- 收集 reasoning_summary、物料评估原因、每条字段修改原因和每条风险提示；
- 空动态内容判定为不合格；
- 每一条非空业务动态说明必须包含有意义的中文短语；
- 英文证据、产品描述、编码、型号和专有名词的长度不再反向扣分。

新增参数化测试覆盖：

- 中文正文加少量英文证据：通过；
- 中文正文加较长英文产品描述：通过；
- 全英文动态建议：拒绝；
- 空动态内容：拒绝；
- 中英文混合但业务解释主要为中文：通过。

该检测用于防止明显的全英文历史结果被当作新中文结果；简体中文的最终约束仍由
Provider 指令和结构化结果验收共同承担。

## 7. 用户确认与被动调用

标准解析和页面加载不会自动启动 Provider。单记录复核入口覆盖以下 completed
匹配状态：

- unique_best_candidate
- ranked_candidates
- ambiguous_tie
- insufficient_evidence
- no_candidate

确认弹窗明确显示：本次只复核当前记录、会调用豆包、可能产生少量 Token 费用、
不会修改正式订单。

浏览器实测：

- 打开确认弹窗后取消：POST /ai-enhance 次数为 0；
- 历史英文重新生成弹窗取消：POST /ai-enhance 次数为 0；
- 用户确认生成：只发送 1 次当前记录请求；
- 同一记录重复点击由后端幂等保护；
- 另一记录在已有调用运行时由全局串行保护拒绝。

## 8. 页面结构

普通用户在 AI 复核完成态首先看到：

- AI 复核结论；
- 置信度；
- 物料评估；
- 主要依据；
- 建议操作；
- 建议修改字段；
- 原值；
- 建议值；
- 修改原因；
- 物料评估说明；
- 风险提示；
- “仅供参考，不会自动写回”。

中文枚举和固定标签由前端映射，历史英文 Sidecar 的旧动态内容保持原样，避免
伪装成新中文结果。

## 9. 技术证据折叠

技术证据使用未设置 open 的原生 details，默认折叠。折叠内容包括：

- PI 文件、工作表、订单行；
- 来源单元格和原始 PI 文本；
- 字段解析诊断；
- 候选物料字段比较；
- 证据引用；
- 模型、Token 用量、响应耗时和尝试次数。

普通首屏不直接展开内部英文技术路径。浏览器实测
technical_details_default_open=false。

## 10. 历史英文 Sidecar 兼容

已验证：

- 中文 Sidecar 重启后直接读取缓存；
- 历史英文 Sidecar 标记为 historical_english；
- 页面显示“历史英文建议”和“重新生成中文建议”；
- 读取历史英文缓存不会自动调用 Provider；
- 不带 regenerate_chinese=true 的启动请求仍直接返回缓存；
- 只有用户明确点击并确认重新生成后才允许调用；
- 重新生成失败时旧英文 Sidecar 保留，失败信息作为附加状态返回；
- 旧 status 缺少 status_version、operation、core_zip_refreshed 等新字段时
  不崩溃，仍可读取已有中文 Sidecar 缓存。

浏览器实测历史英文自动重新生成 POST 次数为 0，取消后的 POST 次数仍为 0。

## 11. Sidecar 缓存

Sidecar 继续保存到 Job 内部 ai-advisory 目录，采用原子写入。缓存命中时：

- 重启后状态为 cached；
- 不产生第二次 Provider 请求；
- 重复点击直接返回已有结果；
- 失败状态不污染主 Job 的 completed 状态；
- 不残留临时写入文件。

Sidecar 和状态文件属于内部费用保护与恢复机制，不作为正式业务结果。

## 12. 默认五类 JSON 与 ZIP

默认业务结果保持五类核心 JSON：

1. 正式业务 JSON
2. 解析诊断 JSON
3. 字典验证 JSON
4. 匹配候选 JSON
5. 匹配摘要 JSON

AI 完成后刷新 ZIP 时仍只写入这五类文件。定向测试检查 ZIP 条目数量为 5，且
不存在 AI 建议条目。内部 Sidecar 不进入默认 ZIP。

## 13. API 兼容命名说明

当前单记录接口继续使用：

    /api/tasks/{job_id}/ai-enhance

本轮为避免恢复阶段的大规模重构，保留该路径用于兼容。未来“AI 增强整单解析”
必须采用不同且语义明确的接口和 parse_mode；单记录人工复核与整单 AI 解析
不能共用相同业务语义，也不应恢复旧的 allow_ai 上传勾选作为模式设计。

## 14. 修改文件

本轮提交范围包含 6 个生产文件、5 个测试文件和本报告：

- src/bedding_order_parser/llm/volcengine_ark.py
- src/bedding_order_parser/web/ai_advisory.py
- src/bedding_order_parser/web/routes.py
- src/bedding_order_parser/web/services.py
- src/bedding_order_parser/web/static/app.js
- src/bedding_order_parser/web/static/styles.css
- tests/llm/test_volcengine_ark_provider.py
- tests/web/test_ai_advisory.py
- tests/web/test_gate4b_frontend.py
- tests/web/test_routes.py
- tests/web/test_services.py
- docs/reports/GATE_4C_D1_STANDARD_MODE_AI_REVIEW_OFFLINE_REPORT.md

交接文档和上一轮恢复审计报告不属于本轮功能提交。

## 15. 定向测试命令与结果

执行命令：

    uv run pytest tests/llm/test_volcengine_ark_provider.py tests/web/test_ai_advisory.py tests/web/test_gate4b_frontend.py tests/web/test_routes.py tests/web/test_services.py -q

实际结果：

    81 passed in 5.76s

没有运行完整 pytest。

## 16. 离线 UI 验证

验证环境：

- 本地回环地址：127.0.0.1:8765
- 数据：临时目录内离线测试 Job
- Provider：FakeLLMService
- 浏览器：系统 Microsoft Edge，由本地捆绑 Playwright 驱动
- 网络策略：仅允许 127.0.0.1:8765，其他请求全部拦截

浏览器自动化和目视检查结果：

- AI 复核按钮可见；
- 确认弹窗正常；
- 取消后启动请求为 0；
- 正在生成状态正常；
- 中文结论、置信度、物料评估和主要依据正常；
- 字段建议表正确把 planned_ship_date 显示为“计划发货日期”；
- 长英文原始证据 clientWidth=377、scrollWidth=377，正常换行；
- 技术详情默认折叠；
- 历史英文提示和重新生成入口正常；
- 桌面视口无重叠或裁切；
- 390px 移动视口 documentWidth=390、viewport=390，无页面级横向溢出；
- 外部网络请求次数为 0。

共生成并目视检查 5 张临时截图；截图不纳入提交，检查后清理项目内临时目录。

## 17. 未进行的真实 API 调用

本轮真实豆包 API 调用次数：0。

浏览器使用 FakeProvider；pytest 使用 Fake Transport/FakeProvider。没有产生真实
Token 费用，没有执行连通性探测，没有发送真实网络请求。

## 18. 正式 JSON 和候选 JSON 保护

定向测试在 AI 成功和失败路径前后计算正式业务、解析诊断、字典验证和匹配候选
文件哈希，确认内容不变。AI 结果只写 Sidecar；主 Job 继续保持 completed。

- 正式 20 字段 JSON 修改：否
- 物料候选 JSON 修改：否
- AI 写 ERP：否
- AI 自动写回：否

## 19. API Key 泄露检查

提交前对完整 diff 执行敏感赋值和私钥块检查：

- 潜在 API Key、Authorization、Bearer、Secret 长值赋值：0
- 私钥块：无
- 真实 Job 或 Sidecar 被 Git 跟踪：无
- 测试中的 api_key 字段仅为前端伪造输入占位，并验证后端忽略该输入
- Provider 错误中的敏感 request id 和内部错误详情经过掩码或过滤测试

未输出、提交或记录真实 ARK_API_KEY 原文。

## 20. 最终 Commit

本报告与生产代码、测试处于同一个目标提交：

    feat: localize desktop ai advisory

由于 Git 提交哈希由包含本报告在内的最终 tree 计算，本文件不能自包含其自身提交
哈希；实际完整和短哈希以提交后的 git rev-parse HEAD、git log -1 --oneline
以及本轮最终回复为准。

## 21. 工作区

提交前：

- 11 个半完成已跟踪文件修改；
- 本轮唯一正式报告新增；
- 两个既有根目录未跟踪文档；
- Playwright 临时截图目录待清理。

提交后目标状态：

- 本轮 11 个代码或测试文件和唯一正式报告全部进入目标提交；
- CODEX_HANDOFF_AND_RECOVERY_2026-07-30.md 保持未跟踪，不提交；
- CODEX_RECOVERY_AUDIT_ROUND_1_REPORT_2026-08-01.md 是上一轮既有报告，
  保持未跟踪，不纳入本轮提交；
- 不保留项目内 Playwright 临时截图；
- 不提交真实 Sidecar、Job、API Key 或绝对环境配置。

实际提交后状态以本轮最终回复为准。

## 22. 是否具备一次真实中文调用验收条件

具备。

离线定向测试、FakeProvider 桌面路由、中文边界、用户确认、取消零调用、缓存、
历史英文兼容、正式结果隔离、ZIP 五类结果和 API Key 防泄露均已通过。下一轮可
在明确用户确认和费用知情的前提下，只执行一次正式桌面路由真实调用验收。

## 23. 下一步唯一建议

Gate 4C-D2：通过正式桌面路由执行一次用户确认后的真实中文AI复核调用，
验证中文建议、缓存、费用和正式结果隔离。
