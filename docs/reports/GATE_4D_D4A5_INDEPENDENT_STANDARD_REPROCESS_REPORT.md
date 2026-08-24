# Gate 4D-D4A-5：独立 Standard 重新处理报告

## 1. 基线与提交

- 分支：`master`
- 起始完整 HEAD：`de88e27105e14b935a6f4e130104b5eaa41be2bf`
- D4A-4 implementation commit：`f08d810514d27a9813a35328850da6534c6d7836`
- D4A-4 report commit：`de88e27105e14b935a6f4e130104b5eaa41be2bf`
- 本 Gate implementation commit：`5d6e23d77723294707a0bad2c542f3126e858734`
- implementation 提交信息：`feat: reprocess ai jobs as independent standard jobs`

开始时没有已跟踪的未提交代码；七份既有未跟踪交接/审计文档保持原样，未暂存、未覆盖、未删除。

## 2. 旧同 Job fallback 写路径审计

| 文件 | 旧函数/API | 旧作用 | 本 Gate 后行为 |
| --- | --- | --- | --- |
| `web/services.py` | `fallback_to_standard()` | 将原 AI Job 的 `effective_parse_mode` 改为 `standard`，清空产物并直接运行标准解析 | 已删除；新写入只能创建独立 Standard Job |
| `web/services.py` | `_confirmed_fallback_update()` | 绕过终态保护，原地改写 AI Job | 已删除 |
| `web/routes.py` | `POST /api/jobs/{id}/ai-actions/fallback` | 接收二次确认并调用同 Job fallback | 已删除；旧 action 现在返回安全的未知操作错误 |
| `web/static/app.js` | fallback 按钮、确认弹窗、`confirmAIFallback()` | 用户点击后在原任务中切换模式 | 已删除；替换为一次点击的“使用标准解析重新处理” |

对 `src/` 和 `tests/` 的静态审计确认，已不存在：`def fallback_to_standard`、`_confirmed_fallback_update`、`data-ai-action="fallback"` 或 `action == "fallback"`。历史 Job 中的 `effective_parse_mode` 与 `fallback` 仍由 `_mode_view()` 只读解释，旧任务及其结果可继续打开。

## 3. 新 API 与生命周期

新增：

```text
POST /api/jobs/{ai_job_id}/reprocess-standard
X-Idempotency-Key: reprocess-...
```

服务层入口为：

```text
JobService.reprocess_ai_job_as_standard(job_id, operation_id=...)
```

仅接受当前 `awaiting_user_decision` 且 `parse_mode/effective_parse_mode` 都为 `ai_enhanced` 的 Job。运行中、排队中、已完成、已失败、已中断以及历史同 Job fallback 均不会成为新的重处理来源。

成功路径：

```text
可信原 AI Job
-> 读取其 input/<file_name>
-> 校验 source_identity SHA-256 和大小
-> create_job(..., parse_mode=standard)
-> 写入新 Job 的 reprocess origin relation
-> start_job(new_job_id)
-> 返回 new_job_id
-> 前端立即跳转 #job/<new_job_id>/progress
```

新 Job 仅保存窄审计关系：`reprocess.origin_job_id`、`reason=standard_reprocess`、操作身份和创建时间。关系只由 Job B 指向 Job A；Job A 不写入任何反向状态。

## 4. 原始上传与 SHA 证明

`_trusted_original_upload()` 仅从 Job A 的可信工作区 `input/<file_name>` 读取字节，不接收浏览器路径、重新上传文件、AI official result、CURRENT Revision 或 comparison 数据。它校验：

- 文件名必须是 Job 内安全基名；
- 文件必须位于该 Job 的 `input/`；
- `source_identity.sha256` 长度和内容必须与重新计算的 SHA-256 一致；
- `source_identity.size_bytes` 必须与实际字节数一致。

随后 `create_job()` 将同一字节写入 Job B 自己的输入目录，且再次校验 Job B 的 source SHA 与 Job A 相同。缺失或篡改输入时拒绝创建，Job A 字节级不变。

## 5. 原 AI Job、Revision 与 AI telemetry 保护

新路径不写 Job A 的：

```text
parse_mode / effective_parse_mode / status / safe_error /
AI calls / HTTP attempts / Token / artifacts / CURRENT /
Revision history / Review / comparison
```

定向测试为原 AI Job 建立了 `INITIAL`、`CURRENT` 和 revision 文件，再执行重处理，验证 Job A `job.json` 与 revision 文件字节完全不变；Job B 的输入仍是原上传而不是 revision artifact。

Job B 是普通 `standard` Job：初始 `parse_mode=requested_parse_mode=effective_parse_mode=standard`，AI logical calls、HTTP attempts 和 Token 都为 0；它走现有 `_run_standard_job()`，不进入整单 AI、AI Review 或 Revision 页面。

## 6. 幂等与失败语义

- 同一个 `X-Idempotency-Key`：通过写在 Job B 中的 operation identity 找回同一 Job B，返回 `reused=true`，不再调度第二次。
- 不同操作身份但已有一个来自同一 Job A 的活动 Standard 子任务：返回该活动 Job B，避免刷新/双击生成 B、C、D。
- Job B 已终态后，新的明确操作身份允许用户再次创建独立 Standard Job；不会永久限制未来重处理。
- 原始文件缺失、SHA/大小不一致或 Job 元数据不符合资格：不创建 Job B，Job A 不变。
- Job B 创建后调度失败：仅将 Job B 安全标记为失败；Job A 仍完全不变。

## 7. 用户界面与导航

等待处理决定页的主按钮已改为：

```text
使用标准解析重新处理
```

说明明确写出：会使用原始订单创建并立即开始新 Standard Job，当前 AI 任务、失败原因和已记录 AI 信息会保留。旧二次确认弹窗已移除；用户的单次点击即创建、启动并导航。AI 确认页的失败处理说明也同步改为“重试、使用标准解析重新处理或保留失败”。

历史列表中旧 `fallback` 标记与筛选仅用于已经存在的历史任务兼容，不是新的写入路径。

## 8. Standard、Sidecar 与 AI Enhanced 保护

- 未修改 Standard parser、字段规则、字典规则、MaterialMatcher、TopK、标准五类 Schema 或默认 ZIP。
- Job B 调用现有正式 Standard dispatch；替身标准解析/匹配测试验证 Job B 完成后五类角色恰好完整，且没有 AI whole-order Review 污染。
- 单记录 AI Sidecar 直接相关回归通过。
- 未修改 AI Enhanced 的 structure/layout、Provider、Prompt、AI-first field policy、normalization、comparison、technical-ready、Review、Revision 或 AI 五类发布。

## 9. 浏览器真实行为验收

使用本机 Microsoft Edge + Playwright、临时 loopback 服务、延迟执行器和合成 `awaiting_user_decision` AI Job 验收。没有使用真实订单、Provider、字典或物料库。

实际点击“使用标准解析重新处理”后：

- 原 AI Job：`4a54f3d4cb0c43bda49dd47c2224ee28`；
- 新 Standard Job：`c929792b1083479f88a1e5950a8f8104`；
- 浏览器已导航至新 Job 的 `#job/<new_job_id>/progress`；
- 新页面是 Standard progress surface，不显示 AI 整单状态面板；
- 新 Job 为 `queued/standard`，AI calls=`0`，Token=`0`；
- 原 Job 仍为 `awaiting_user_decision/ai_enhanced`，Token 保持 `13`；
- 延迟执行器不运行真实 Standard parser，避免 BGE-M3、FAISS、真实字典或真实物料调用。

临时服务、临时脚本和合成 Job 目录均已停止并清理。

## 10. 测试

### 前端语法

```powershell
node --check src\bedding_order_parser\web\static\app.js
```

结果：通过。

### 定向回归

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\web\test_standard_reprocess.py `
  tests\web\test_standard_reprocess_frontend.py `
  tests\web\test_ai_full_order_jobs.py `
  tests\web\test_ai_review.py `
  tests\web\test_ai_review_frontend.py `
  tests\web\test_ai_result_revisions.py `
  tests\web\test_gate4c2_routes.py `
  tests\web\test_gate4c2_frontend.py `
  tests\web\test_services.py `
  tests\web\test_ai_advisory.py `
  tests\web\test_ai_progress_frontend.py -q
```

结果：`101 passed in 11.17s`。

覆盖 AI failure -> new Standard、原 Job 不变、源 SHA、Revision 来源保护、同操作身份幂等、活动子任务去重、终态后再次明确重处理、篡改源拒绝、历史 fallback 只读兼容、Standard 完成五类结果、路由、前端双击合并、前端立即跳转、AI Review、Sidecar 与进度页回归。

```powershell
git diff --check
```

结果：通过；`ruff` 未安装，本 Gate 未新增依赖或以其替代测试。

未运行完整 pytest。

## 11. 真实调用与安全边界

```text
真实 Ark/API：0
外部 HTTP：0
真实 PI：0
真实字典：0
真实物料库：0
BGE-M3：0
FAISS：0
```

所有测试使用合成字节、Fake/替身依赖或本机 loopback。没有保存 API Key、Authorization、请求正文、原始 Provider 响应、真实 Job 或真实 PI。

## 12. 修改文件

```text
AGENTS.md
src/bedding_order_parser/web/services.py
src/bedding_order_parser/web/routes.py
src/bedding_order_parser/web/static/app.js
tests/web/test_standard_reprocess.py
tests/web/test_standard_reprocess_frontend.py
tests/web/test_ai_full_order_jobs.py
tests/web/test_gate4c2_routes.py
tests/web/test_gate4c2_frontend.py
```

## 13. 剩余风险与结论

当前幂等与活动子任务去重基于同一个桌面 JobService 与持久化 child metadata；这符合本地单进程桌面产品。若未来多个独立进程可以同时写同一 jobs root，需要增加进程级 operation lock，不能只依赖内存 Job 锁。

新请求已不存在同 Job fallback mutation。历史 fallback Job 继续可读，但不会迁移、重写或删除。下一步建议在真实用户工作流中以授权的合成/真实验收确认“AI 技术失败 -> 独立 Standard Job”的完整 Standard 执行与业务结果体验；不应再修改 AI-first 解析合同来处理该产品分流。

## 14. 最终工作区

报告提交前，除本 Gate 实现与本报告外，工作区仅保留开始时已有的七份未跟踪交接/审计文档；它们没有被暂存或修改。
