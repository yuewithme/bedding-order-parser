# Gate 4D-D4A-3E：Layout Contract V2 单次真实 Ark 多 Sheet 合成样本验收报告

## 1. 基线与提交

- 分支：`master`
- 起始完整 HEAD：`2a1438182f351bfa5c3f4a290a8394eaebbeefd0`
- D4A-3D implementation commit：`1b4a83ba48498eea7e1aca4f1f1ab439442d7442`
- D4A-3D report commit：`2a1438182f351bfa5c3f4a290a8394eaebbeefd0`
- 本 Gate harness commit：`1dfd3bae29cfd4720346edb4255943f6251a814c`（`test: add bounded real ark structure acceptance`）
- 起始已跟踪工作区干净；仅有 7 份既有未跟踪交接/审计文档，均未修改、暂存或清理。

本 Gate 未修改生产代码、Prompt、Schema、Provider、AI-first 后半链、UI、Standard 或 Sidecar。

## 2. 验收目标与预算

唯一目标是验证正式 `VolcengineArkFullOrderProvider.resolve_structure()` 能否在 Layout Contract V2、Structure Context V2 和多 Sheet 本地候选约束下返回可由本地 validator/binder/apply 安全应用的真实结构决策。

授权与实际计数：

| 项目 | 授权上限 | 实际 |
| --- | ---: | ---: |
| 真实 Ark layout logical call | 1 | 1 |
| 真实 HTTP attempt | 1 | 1 |
| Provider retry | 0 | 0 |
| 真实 `extract_v2` call | 0 | 0 |
| 真实字段 extraction HTTP | 0 | 0 |

唯一一次真实调用完成后没有重试、重跑 harness 或追加第二次调用。

## 3. Harness 安全边界

新增 `tests/ai_full_order/test_ark_layout_v2_real_acceptance.py`，主要边界如下：

- 使用正式生产 `VolcengineArkFullOrderProvider.resolve_structure()`。
- 使用一次性 direct transport；第二次 `send()` 会在发出前拒绝。
- 系统代理显式绕过，HTTP attempt 由外层 transport 精确计数。
- 调用前验证正式 Responses API、`store=false`、非流式、strict function、正式 function name 与精确 `LAYOUT_OUTPUT_SCHEMA`。
- Provider `max_retries=0`；同时由配置预检和测试双重验证。
- 只允许结构调用，harness 不构造 JobService，不进入 `extract_v2`。
- 原始请求、原始响应和 Authorization 只存在于调用栈内存，不写临时文件、不打印、不提交。
- finally 阶段扫描临时目录，确认没有密钥、Authorization 或 raw payload 文件；随后删除 synthetic workbook 和整个临时目录。

## 4. Synthetic Workbook 安全摘要

人工合成 workbook 仅包含虚构内容：

- s1：可由本地确认的订单表，3 条 synthetic records。
- s2：可见、有辅助说明内容，无编号订单记录，满足本地 auxiliary candidate eligibility。
- s3：hidden synthetic Sheet，用于证明隐藏内容不会进入 structure payload。

没有使用或复制用户真实订单、失败 workbook、真实 PI、客户、业务员、物料、付款或银行信息。

本次真实运行的安全身份摘要：

- source SHA 安全前缀：`39d12533ed5b...`
- context SHA 安全前缀：`32691c95c492...`
- known Sheet：`s1`
- unresolved Sheet：`s2`
- 调用前正式 records：3
- 本地 auxiliary candidate：`layout-candidate:s2:b28994a87f18eb3df981`

## 5. 真实调用前本地条件

全部通过后才允许 transport 发出请求：

| 条件 | 结果 |
| --- | --- |
| Git 基线与工作区 | 通过 |
| Ark 配置 | `ready` |
| Provider | `volcengine_ark` |
| 正式模型 | `doubao-seed-2-0-lite-260428` |
| Base URL | 批准的 Ark 北京 Responses API |
| API Key | 仅确认存在，未输出 |
| `LLM_MAX_RETRIES` | `0` |
| s1 状态 | `confirmed_order` |
| s2 状态 | `unresolved_order_candidate` |
| known context | 仅 s1 |
| unresolved context | 仅 s2 |
| s2 local candidate | 1 个 auxiliary candidate |
| hidden Sheet | 不在 payload |
| workbook binary / 本机路径 | 不在 payload |
| API Key / Authorization | 不在请求正文 |
| 整 Sheet dump | 不存在 |
| 文本数量与长度上限 | 通过 |
| 调用前 Provider / HTTP count | `0 / 0` |

## 6. 正式版本与请求合同

- Structure manifest version：`2.0`
- Structure context version：`2.0`
- Layout contract version：`2.0`
- Layout prompt version：`2.0`
- Ark function：`submit_bedding_order_layout`
- strict function calling：是
- Responses API：是
- `store=false`：是
- stream：否
- bounded max output tokens：1024

请求只包含 D4A-3D 定义的 `known_chunks + unresolved_sheets` 安全结构视图。所有候选 ID 均由本地生成，模型没有自由坐标、record、scope、block 或 evidence identity 的输出能力。

## 7. 唯一一次真实调用遥测

| 安全事实 | 实际结果 |
| --- | --- |
| Provider / model | `volcengine_ark` / `doubao-seed-2-0-lite-260428` |
| HTTP status class | `2xx` |
| 返回形态 | `function_call` |
| 脱敏 request ID | `resp...a471` |
| latency | 4203 ms |
| input tokens | 1137 |
| output tokens | 128 |
| total tokens | 1265 |
| layout logical calls | 1 |
| HTTP attempts | 1 |
| retry | 0 |
| extract logical calls | 0 |

Token 是新 Provider 实例在调用前后 `usage_summary` 的 operation delta，并与该次 transport telemetry 交叉核对；没有将 Provider 会话累计值冒充本次消耗。

## 8. Ark 真实返回的白名单结构事实

- overall status：`resolved`
- required Sheet decision 数量：1
- Sheet：`s2`
- role：`auxiliary`
- candidate ID：`layout-candidate:s2:b28994a87f18eb3df981`
- reason：`auxiliary_non_order_content`
- candidate 是否来自 request：是
- duplicate/missing Sheet：无
- extra field：无
- 自由坐标、record identity 或解释字段：无

Provider 边界严格 Layout Contract V2 验证通过，没有启用容错解析或兼容放宽。

## 9. Local Validator / Binder / Apply

真实 Provider 输出按正式路径执行：

```text
strict provider output validation
-> apply_structure_decision()
-> required Sheet coverage
-> candidate ID / Sheet ownership / role / reason validation
-> candidate identity recomputation
-> local apply
-> build_v2_extraction_units()
```

结果：

- strict contract：PASS
- local validator/binder：PASS
- local apply：PASS
- s1 保留 records：3
- s2：通过本地 auxiliary eligibility 与真实决策共同确认后安全排除
- final technical structure：resolved
- 本地 extraction units：3
- record identity、scope、evidence：由本地既有结构生成并保持

到 extraction-unit construction 边界后立即停止；没有调用真实字段 extraction。

## 10. 测试结果

真实调用之前：

```text
3 passed in 0.51s
36 passed in 47.10s
py_compile: passed
```

覆盖 synthetic preflight、正式 Provider + FakeTransport、本地 apply、非零 retry 前置拒绝、D4A-3D multi-sheet、structure path 与 Ark Provider 离线回归。

真实调用之后仅运行不读取真实 Ark 配置、不会发起网络的 FakeTransport/本地回归：

```text
21 passed in 2.08s
```

没有运行完整 pytest，没有调用真实 PI、字典、物料、BGE-M3 或 FAISS。

## 11. 数据与落盘安全

- 真实业务数据使用：否。
- raw HTTP request 保存：否。
- raw Ark response 保存：否。
- Authorization/API Key 保存或输出：否。
-完整 Prompt 保存或输出：否。
- CoT 保存或输出：否。
- synthetic workbook：TemporaryDirectory 退出时删除。
- raw payload/secret 文件扫描：0。
- 提交内容：仅 harness 与本报告；不含真实响应、请求、凭证或临时 workbook。

## 12. 真实调用后的修改纪律

真实调用发生后：

- 没有修改生产 Prompt、Schema、Provider 或结构合同。
- 没有针对结果增加兼容分支。
- 没有第二次真实调用。
- 只执行了离线回归并生成本报告。

## 13. 最终结论

**Gate 4D-D4A-3E 完全通过。**

真实 Ark 已证明能够消费新的 multi-sheet Structure Context V2，严格返回 Layout Contract V2，从请求中选择同 Sheet 本地 auxiliary candidate，并由正式本地 validator/binder/apply 成功应用。s1 三条记录得到保留，s2 被安全确认辅助角色，最终形成 3 个 extraction units；全过程只发生 1 次 layout HTTP，真实 `extract_v2` 为 0。

## 14. 下一步建议

可以进入单独授权的“用户真实 multi-sheet 订单结构复验”，但应继续保持：

- 先进行纯本地 preprocessing/manifest 安全审计；
- 真实 layout 调用独立限额；
- 成功后先验证 structure apply，不自动追加字段 extraction；
- 若需要真实整单字段 extraction，应另设调用预算与数据授权；
- 继续禁止 raw request/response 落盘。

当前没有 Layout Contract V2 协议或本地应用层阻塞项。真实业务订单的本地候选质量仍需逐份预检。

## 15. 最终工作区

报告提交前，已跟踪实现工作区干净；仅存在起始时已有的 7 份未跟踪交接/审计文档和本 Gate 待提交报告。报告提交后应仅保留原有 7 份未跟踪文档。
