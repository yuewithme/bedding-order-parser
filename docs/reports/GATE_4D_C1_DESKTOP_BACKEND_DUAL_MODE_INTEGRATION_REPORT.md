# Gate 4D-C1｜桌面后端双模式与Job离线接入报告

## 1. 实际基线

- 开始分支：`master`。
- 开始完整 HEAD：`445aaa1693a616f301ad233d78f97e1492c2153e`。
- 开始短哈希：`445aaa1`。
- 开始提交：`feat: publish ai full-order result bundles`。
- 开始工作区仅有允许保留的未跟踪恢复文档：`CODEX_HANDOFF_AND_RECOVERY_2026-07-30.md`、`CODEX_RECOVERY_AUDIT_ROUND_1_REPORT_2026-08-01.md`。

## 2. Job双模式

- `JobService.create_job()` 现严格接受 `standard` 与 `ai_enhanced`；其他值（包括旧布尔式设计）会拒绝。
- 新 Job 原子持久化 `parse_mode`、`effective_parse_mode`、`parse_contract_version=1.0`、`parse_mode_source=explicit`、回退记录和安全 AI 执行摘要。
- 缺少模式字段的旧 Job 仅在读取时解释为 `standard`，返回 `parse_mode_source=legacy_default` 与“标准解析（历史任务）”标签；没有回写旧 `job.json`。
- `standard` 分流继续调用原有 `_run_standard_job()`；`ai_enhanced` 才进入新增离线整单服务链。

## 3. AI离线服务链路

- 新增 `src/bedding_order_parser/web/ai_full_order_service.py`，定义注入式 `AIEnhancedDependencies`，只接受 Provider、字典验证器和物料匹配器端口。
- AI Job 顺序为：本地预处理、Python shadow、本地结构判定、条件式布局识别、分块提取、B2B 可靠性与证据/字段裁决、FakeDictionaryValidator、FakeMaterialMatcher、B3 原子 Bundle 发布。
- 默认没有 AI 整单依赖时安全进入 `awaiting_user_decision`，错误码为 `AI_NOT_READY`；服务不会构造真实 Provider。
- 合成双 Sheet fixture 的本地明确结构不会调用布局识别 FakeProvider；测试中仅发生两个字段提取逻辑调用。

## 4. 阶段和进度

- Job 的 `ai_execution` 安全摘要持久化并公开：当前阶段、已完成/总 chunk、逻辑调用数、HTTP 尝试数、Token 占位汇总、Provider/模型名称、可发布标记和安全错误码。
- 支持阶段：`preprocessing`、`python_shadow_parse`、`local_structure_resolution`、`ai_layout_recognition`、`ai_block_extraction`、`evidence_validation`、`field_resolution`、`dictionary_validation`、`material_matching`、`publishing`、`awaiting_user_decision`。
- 不写入 Job 元数据的内容：完整 Provider 响应、Provider 请求正文、API Key、Authorization、私有思维链或内部 staging 信息。

## 5. 失败、重试和回退

- AI 未就绪、Token 预算超限、Schema/证据失败、瞬时失败耗尽、部分块结果、中断以及下游字典/匹配/发布失败，都映射为可读的安全错误码与 `awaiting_user_decision`；不会静默发布标准结果或半套 AI 结果。
- `retry_missing_chunks()` 只在等待决策的 AI Job 可用，并复用 B2B 状态：已 validated chunk 从缓存恢复，未完成或允许重试 chunk 才会再次执行。
- `keep_failed()` 显式将等待状态保留为失败。
- `fallback_to_standard()` 需要调用时 `confirmed=True` 或已记录预授权。确认后保留 `parse_mode=ai_enhanced`，把 `effective_parse_mode` 改为 `standard`，记录原因和确认时间，并清空 AI 半成品的公开角色引用后才走原标准路径。
- 用户确认回退是唯一允许终态 Job 回到队列的受控原子例外；一般终态保护未放宽。

## 6. 五类产物角色

- 新增统一角色：`official_result`、`parse_diagnostics`、`dictionary_validation`、`material_candidates`、`material_summary`。
- 标准模式将既有 `business/diagnostic/validation/matches/match_summary` 映射到相同角色，保留现有物理路径与 ZIP 行为。
- AI 模式只保存“当前 AI Bundle”角色描述；读取时由服务解析 B3 `CURRENT`，验证缓存身份、五个文件齐全以及诊断中的 `ai_enhanced.cache_key`/`parse_mode`，再返回相应文件。
- API/后续 UI 可按角色预览或下载，无需知道 `ai_full_order.json` 等物理名称；staging、缓存目录和 Sidecar 不会公开为业务产物或第六类 JSON。
- `CURRENT` 损坏、Bundle 不完整或诊断身份不一致时安全失败，Job 不会错误显示完整五类结果。

## 7. 历史任务摘要

- Job 列表和单 Job 读取现在提供原始模式、有效模式、中文标签、回退状态、AI 阶段、模型、Token 占位、调用/HTTP 摘要及 `has_complete_five_results`。
- 旧 Job 继续可读；标准模式的旧 `artifacts` 响应形状保持不变，并额外提供统一 `artifact_roles`。

## 8. 标准模式保护

- 未修改标准解析算法、20 字段、字典规则、物料匹配权重/阈值、默认 ZIP 内容或单记录 AI Sidecar 实现。
- 标准 Job 分流回归确认仍只进入原路径；AI 整单运行不创建也不自动调用 `ai-advisory`。
- AI 部分结果、失败状态和 Bundle 损坏均不会污染标准 Job 产物；确认回退前也不执行标准解析。

## 9. 测试及零网络证明

执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/web/test_ai_full_order_jobs.py tests/web/test_services.py tests/web/test_routes.py tests/web/test_gate4b_routes.py tests/web/test_ai_advisory.py tests/ai_full_order/test_contracts.py tests/ai_full_order/test_preprocessing.py tests/ai_full_order/test_resolution.py tests/ai_full_order/test_orchestration.py tests/ai_full_order/test_reliability.py tests/ai_full_order/test_downstream.py tests/pipeline/test_order_parser.py tests/serialization/test_json_writer.py tests/serialization/test_diagnostic_writer.py tests/materials/test_hybrid_matcher.py
```

结果：`142 passed in 14.29s`。

- 新增 C1 测试覆盖严格双模式、旧 Job 只读兼容、标准分流、完整 Fake 链路、本地明确结构零布局 AI、五角色读取、`CURRENT` 损坏和身份不一致、部分块重试、未确认回退拒绝、确认回退元数据、AI 未就绪、Token 预算拒绝、标准/AI 统一角色。
- 关联回归覆盖 B1-B3 合同/可靠性/发布、标准解析与序列化、Web Job 服务/路由、单记录 AI Sidecar 和既有物料查询边界。
- 网络调用：0；真实豆包/API 调用：0；BGE-M3 调用：0；FAISS 调用：0。全部使用合成 Excel、FakeProvider、FakeDictionaryValidator 和 FakeMaterialMatcher。
- 未解析真实 PI、未安装依赖、未运行完整 pytest。

## 10. 修改文件、实际commit、工作区和下一步

- `src/bedding_order_parser/web/ai_full_order_service.py`
- `src/bedding_order_parser/web/services.py`
- `src/bedding_order_parser/web/routes.py`
- `tests/web/test_ai_full_order_jobs.py`
- `docs/reports/GATE_4D_C1_DESKTOP_BACKEND_DUAL_MODE_INTEGRATION_REPORT.md`
- 本报告与实现将按 `feat: integrate ai full-order desktop jobs` 提交；实际提交哈希以提交后核验为准。
- 提交后工作区仅应保留两份恢复文档为未跟踪文件。

下一步唯一建议：Gate 4D-C2：实现桌面双模式UI、费用确认、进度、失败选择、结果和历史页面离线联调。
