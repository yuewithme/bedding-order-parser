# Gate 4D-D4A-4：AI 整单结果用户修订与不可变 Revision 报告

## 1. 基线与提交

- 分支：`master`
- 起始完整 HEAD：`b699c248eeef2575f32cbd0952f1ff06665433d3`
- D4A-3E 离线验收 harness commit：`1dfd3bae29cfd4720346edb4255943f6251a814c`
- D4A-3E 报告 commit：`b699c248eeef2575f32cbd0952f1ff06665433d3`
- 本 Gate implementation commit：`f08d810514d27a9813a35328850da6534c6d7836`
- 开始时工作区只有 7 份既有未跟踪交接/审计文档，没有未知业务代码修改。

## 2. Revision 领域模型

新增 `ai_full_order/revisions.py`，将两个身份彻底分开：

- extraction identity：沿用 V2 `cache_key`，代表 source、Contract、Prompt、Provider、AI candidates、Python comparison 和 provenance 事实；用户修订不会改变它。
- publication revision identity：代表某个 parent 之上的用户选择以及由该选择重新生成的五类结果。

Revision ID 是本地确定性 SHA-256，组成至少包括：Revision 合同版本、本地下游版本、Normalization 版本、初始 Revision、parent Revision、记录身份、17 字段名、动作、手工值的规范化摘要，以及字典/物料端口实现身份。身份中不保存手工值明文。

内部版本：

- `REVISION_CONTRACT_VERSION = 1.0`
- `REVISION_DOWNSTREAM_VERSION = 1.0`
- 复用 `NORMALIZATION_VERSION = 1.0`

## 3. INITIAL、CURRENT 与 History

新完成的 AI Enhanced V2 Job 在标记 `completed` 前执行以下登记：

1. 保留原 extraction bundle；
2. 将第一次成功五类结果登记为不可变 revision 0；
3. 写入 `INITIAL`；
4. 通过原子替换将 `CURRENT` 切到 revision 0。

持久化布局：

```text
ai-bundle/
  INITIAL
  CURRENT
  bundles/<extraction-cache-key>/        # 原提取发布，保持不变
  revisions/<revision-id>/               # 每版恰好五个 JSON
  revision-metadata/<revision-id>.json   # 内部非业务审计元数据
```

History 由不可变 metadata 文件形成，不依赖可被覆盖的单一历史数组。每版保存 `revision_number`、`parent_revision`、`initial_revision`、创建时间、action、override 摘要和五文件 SHA；读取时验证连续序号和 parent 链。所有用户确认提交的 Revision 均保留，本 Gate 不做清理。

## 4. 三种用户动作

### keep_ai

- 只允许 provenance 已绑定且 AI 值非空的候选；content issue 不允许通过此按钮绕过。
- formal 值继续采用 AI。
- `selected_source = ai`。
- `review_status = confirmed_ai`。
- 原 `comparison_status = different` 等事实保持不变。

### use_python

- 只在当前字段存在本地规则值时允许。
- formal 值改为本地规则值。
- `selected_source = user_selected_python`，与自动补空的 `python_fallback` 明确区分。
- `review_status = selected_python`。

### manual_override

- 用户 display value 与本地 normalized/formal value分别记录。
- `selected_source = user_override`。
- `review_status = manual_override`。
- 不伪造 evidence，不改变 AI/Python 原始 comparison。

## 5. 字段权限与输入安全

- 可修改：固定 17 个 AI 业务字段。
- 不可修改：`行号`、`物料编码`、`相似分数`、record/source/scope/evidence 身份。
- API 白名单只有：`expected_current_revision`、`source_record_id`、`field_name`、`action`、`manual_value`。
- 拒绝额外字段、未知 action、非字符串手工值、超过 2,000 字符和非法控制字符。
- 服务端从当前可信诊断和原始上传重建记录，不接收客户端提交的旧值、完整记录、路径或 evidence。

## 6. 规范化、字典与物料

- 手工值继续复用 D4A-1 保守确定性 normalization。
- 数量 `10.0` 可形成 display=`10.0`、formal=`10`、rule=`decimal_quantity`；来源仍是 `user_override`。
- 无确定性规则时保留用户 display，不做模糊业务猜测。
- DictionaryValidator 每次 Revision 全量本地重跑；`completed_with_warnings` 和 unknown 警告不阻止保存，也不静默覆盖用户值。
- MaterialMatcher 每次 Revision 全量本地重跑。
- `物料编码`和`相似分数`仍只接受 MaterialMatcher 返回值，用户和 AI 均不能直接写入。

## 7. Canonical 17、正式 20 与五类发布

Revision 从当前可信 `field_decisions` 重建完整 canonical 17，并保留原本地 `record_local_id`、`source_record_id`、`scope_id` 和正式行号。随后执行：

```text
canonical 17
→ DictionaryValidator
→ MaterialMatcher
→ 17 + 本地行号 + matcher code/score
→ 严格 20 字段
→ 五类 payload 校验
→ immutable revision bundle
→ 原子切换 CURRENT
```

每个 Revision Bundle 仍恰好五个业务 JSON：

1. `official_result`
2. `parse_diagnostics`
3. `dictionary_validation`
4. `material_candidates`
5. `material_summary`

未增加第六类业务 JSON。`official_result` 仍严格只有固定 20 字段；comparison、用户 action、Revision lineage 只进入解析诊断和内部 metadata。

## 8. 原子性、并发与幂等

- 新五类文件先写唯一 staging，逐文件校验 SHA 后形成不可变 `revisions/<id>`。
- metadata 写入成功后才原子切换 `CURRENT`。
- Dictionary、Matcher、20 字段、payload、写盘或 CURRENT 切换任一步失败，旧 CURRENT 保持不变。
- CURRENT 切换失败时清理尚未公开的新 bundle 和 metadata；旧五类结果继续可读。
- `expected_current_revision` 实现乐观并发；旧页面请求返回固定安全冲突，不覆盖新版本。
- 同 parent、同动作、同字段、同输入的重复请求通过 operation identity 返回已存在 Revision，不创建重复版本。
- completed Job 保持 `status = completed`，只增加 `initial_revision/current_revision/revision_number/revision_count` 摘要。

## 9. Review 与原始事实

parse diagnostics 持久保留：

- 初始 AI display/normalized value；
- Python display/normalized value；
- 原 comparison status；
- 原 evidence 和 supporting quote；
- 当前 formal value 与 selected source；
- 独立 review status；
- action、parent/current/initial Revision；
- 手工 display、normalized 和 normalization rule。

`comparison_status` 与 `review_status` 是两个维度。用户选择 Python 或手工输入不会把原 `different` 篡改成 `agree`。待复核数只统计当前仍为 `unreviewed` 的字段。

## 10. API、页面与下载

- 新增 `POST /api/jobs/{job_id}/ai-review/revisions`。
- 201 表示新 Revision；200 表示幂等复用；409 表示 stale Revision。
- Review 卡片按字段条件显示“保留 AI”“使用本地规则”“手动修改”。
- `both_missing` 只提供手动修改；content issue 不提供保留 AI。
- 原生 button、label/input 和既有键盘绑定支持 Tab、Enter、Space。
- 页面显示“当前结果：第 N 版”，保存后重新读取 Job 与 Review，待复核数量即时减少。
- 预览和单文件下载继续通过统一 `artifact_path()` 读取 CURRENT；Revision-aware reader 同时兼容旧 extraction CURRENT。
- 当前 AI Enhanced 的 Excel 导出/ZIP 在现有产品中尚未开放或未生成，本 Gate 未扩大该范围；已有五类预览和下载已验证读取最新 CURRENT。

## 11. 兼容性

- Standard：不支持整单 Revision，解析、五类结果和主值语义未修改。
- Legacy V1：继续使用旧 Bundle 读取，不伪造 Revision。
- 旧 V2：无 `INITIAL`/Revision metadata 时继续可读，但 Review 动作禁用并明确不支持修订。
- 单记录 AI Sidecar：代码与回归行为未修改。
- V2 Contract、Prompt、Provider、structure/layout、provenance、field policy、cache identity 均未修改。

## 12. 浏览器真实行为验收

使用系统已安装 Microsoft Edge，通过 Playwright 驱动 `127.0.0.1` 临时服务和 synthetic completed-with-review Job。全部依赖为 FakeProvider、FakeDictionaryValidator、FakeMaterialMatcher。

实际结果：

- 初始待复核：17；
- 键盘 Enter 提交“使用本地规则”：成功进入第 2 版；
- 待复核减少 1；
- 重复提交：HTTP 200，复用原 Revision；
- stale 不同动作：HTTP 409；
- Space 打开手工编辑，Enter 保存 `both_missing`：成功进入第 3 版；
- 刷新后手工值仍存在；
- `official_result` CURRENT 预览包含该手工值；
- 480px 窄窗口 Review 区宽度 386px，无越界；
- 五类结果完整。

浏览器验收没有安装依赖、没有外网访问，也没有读取真实订单。

## 13. 测试

### 语法与前端

```text
node --check src\bedding_order_parser\web\static\app.js
```

结果：通过。

### 定向回归

```text
.\.venv\Scripts\python.exe -m pytest \
  tests\ai_full_order\test_downstream.py \
  tests\ai_full_order\test_v2_downstream.py \
  tests\web\test_ai_full_order_jobs.py \
  tests\web\test_ai_result_revisions.py \
  tests\web\test_ai_review.py \
  tests\web\test_ai_review_frontend.py \
  tests\web\test_d3b2d_ui_enablement.py \
  tests\web\test_gate4c2_routes.py \
  tests\web\test_gate4c2_frontend.py \
  tests\web\test_services.py \
  tests\web\test_ai_advisory.py -q
```

结果：`123 passed in 15.16s`。

覆盖 keep AI、use Python、manual、normalization、字典 warning、Matcher 权限、initial SHA 不变、第二/第三版 parent/history、stale、duplicate、Matcher 失败、CURRENT 切换失败、禁止字段、旧 V2、Standard、Sidecar、五类原子发布及前端键盘行为。

未运行完整 pytest；本 Gate 按范围仅运行最小充分定向测试。

## 14. 调用计数

- Revision 操作 Fake/真实 extraction Provider 调用：`0`
- Revision 操作 structure/layout Provider 调用：`0`
- 外部 HTTP：`0`
- Token delta：`0`
- 真实 Ark：`0`
- 真实 PI：`0`
- 真实字典/物料库：`0`
- BGE-M3：`0`
- FAISS：`0`

## 15. 修改文件

```text
src/bedding_order_parser/ai_full_order/downstream.py
src/bedding_order_parser/ai_full_order/revisions.py
src/bedding_order_parser/web/ai_review.py
src/bedding_order_parser/web/routes.py
src/bedding_order_parser/web/services.py
src/bedding_order_parser/web/static/app.js
src/bedding_order_parser/web/static/styles.css
tests/web/test_ai_result_revisions.py
tests/web/test_ai_review_frontend.py
docs/reports/GATE_4D_D4A4_AI_RESULT_REVISION_REPORT.md
```

## 16. 剩余风险与下一 Gate

- 第一版为保证确定性与可审计性，每次 Revision 重跑整个 Job 的本地下游；大订单可能需要后续性能观测，但不应在没有证据前引入增量依赖图。
- 当前并发模型针对单桌面服务进程，使用 Job 级锁加乐观并发；若未来开放多进程写同一 Job，需要再增加进程级 Revision writer lock。
- 当前结果页展示当前版本、原始 AI/Python 值和当前 formal 值，内部保存完整 History；未实现复杂 Revision 时间线或回滚 UI。
- 下一 Gate 唯一建议：废弃同 Job `fallback_to_standard` mode mutation，改为复用原上传创建一个全新的 Standard Job，并保持原 AI Job 不变。

## 17. 最终工作区

实现提交后仅保留开始时已有的 7 份未跟踪交接/审计文档；本 Gate 未清理、覆盖或提交它们。报告将单独提交，除报告外无新增未提交业务文件。
