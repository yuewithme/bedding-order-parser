# Gate 4D-D3D-2｜AI 整单 V2 结构路径离线修复与标准解析边界对齐报告

## 1. 结果与基线

本 Gate 已完成纯离线实现。D3D-1 确认的两层问题均已修复：

1. V2 预处理优先复用标准解析已经证明的最终记录源行坐标，不再由“所有纯编号行”独立决定正式 V2 record geometry。
2. 桌面 V2 的真正歧义分支通过版本化适配器构造合法 `chunks` manifest 后才进入正式 structure Provider，不再把 `PreprocessedWorkbook.to_request_dict()` 错传给 `resolve_structure()`。

起始仓库事实：

- 项目：`D:\AI-Learning\Projects\bedding-order-parser`
- 分支：`master`
- 完整 HEAD：`34f43d776e046149506bc2c8fa9cd221db9e8cc5`
- 短 HEAD：`34f43d7`
- 最近提交：`docs: diagnose real order structure failure`
- 起始已跟踪工作区：干净。
- 起始未跟踪内容：6 份既有交接、恢复或架构审计文档，均未修改、暂存或提交。

实现提交：

- `fcdd05cd3793faf201eb080e9495fd22ddf79393`
- `fix: align ai v2 structure manifests and record geometry`

## 2. D3D-1 根因修复

### 2.1 本地记录边界

新增 `ai_full_order/standard_geometry.py`，通过现有标准解析函数 `parse_table()` 和 `extract_raw_items()` 只读取以下确定性事实：

- 表头起始与首条标准数据行之间的源行范围；
- 标准模式最终品类筛选已确认的 source row；
- 标准表格的 post-table 边界；
- post-table 内纯编号行计数；
- post-table 是否存在“显式业务表头 + 后续编号行”的第二订单表信号。

适配器不读取标准字段值覆盖 AI，不生成 17 字段候选，不带入物料编码或相似分数。它只输出本地结构坐标。

`preprocess_workbook()` 对每个可见 Sheet 同时建立：

- 原有编号启发式候选；
- 标准解析几何候选；
- 固定计数的 `StructureDiagnostics`。

只有标准记录行、表头行及 A 列正式行号证据都能无歧义映射到当前 sparse evidence catalog 时，才建立标准对齐的 `OrderBlock`、`LocalRecord` 和 evidence。无法映射时继续保持 `ambiguous`，不伪造 source row、scope、record identity 或 evidence。

预处理版本由 `1.0` 提升为 `1.1`。V2 可靠性缓存身份已包含 `PREPROCESSOR_VERSION`，因此旧 geometry 缓存不会与新 geometry 错误复用。

### 2.2 Structure manifest

新增 `ai_full_order/structure_manifest.py`：

- `STRUCTURE_MANIFEST_VERSION = "1.0"`
- `StructureManifestAdapterError`
- `build_structure_manifest()`

本地正式形状为：

```text
manifest_version
source_file_sha256
chunks[]
  source_file_sha256
  scope
  chunk_id
  block_id
  record_identities
  record_local_ids
  evidence_ids
  evidence_range
  order
  status
```

适配器在 Provider 前验证：source SHA 格式、chunk 唯一性、block/scope 对应、record 存在、source record identity 可重算、evidence 存在且同 scope。没有已知 block 的真正自由格式 Sheet 使用本地生成的 unresolved sheet chunk；只包含 sheet ID、used range 和空 record/evidence identities，不包含 Sheet 名、单元格文本、Excel 二进制、本机路径、隐藏内容或付款/银行证据。

正式 `VolcengineArkFullOrderProvider.resolve_structure()` 的既有输出 Schema、严格函数调用和结果枚举未放宽。Provider 继续只把 `chunks` 作为安全 payload 发往 FakeTransport/未来授权 Transport；本地 manifest 版本和 source identity 保留在适配边界。

## 3. 为什么合成 Fixture 是 3 条而不是 60 条

新增测试内运行时 fixture 生成器，生成完全虚构的 `.xlsx`，不提交真实工作簿或真实工作簿脱敏副本。结构为：

- 1 个可见 Sheet；
- 95 行；实际内容 11 列；
- 在 XFD 列仅放格式残留，使 `openpyxl.max_column=16384`；
- 20 个合并区域；
- 1 个无敏感内容公式；
- 主表 60 个连续编号数据行；
- 其中标准品类规则确认 3 条 Duvet Cover 正式记录，其他 57 行为合成的非目标品类；
- 主表后有 2 个无重复业务表头的编号辅助区段，共 12 行。

实际断言：

| 项目 | 结果 |
| --- | ---: |
| 标准表格 data rows | 60 |
| 标准最终记录 | 3（source rows 14、15、16） |
| 旧编号启发式 records | 60 |
| post-table 辅助编号行 | 12 |
| 标准对齐 V2 records | 3 |
| V2 extraction units | 3 |
| Python shadow records | 3 |
| structure status | `locally_resolved` |
| layout 调用 | 0 |

实际 used range 被重新计算为 `A1:K95`，没有把 XFD 格式残留外发或纳入 evidence。三个 unit 的 extraction unit ID、source record identity、source row、scope 和 evidence ID 均唯一且可重算。

## 4. 辅助编号区段政策

后续编号区段不再仅因数字开头就翻转已确认主表：

- 位于标准 parser 已确认的 post-table 区域；
- 没有显式业务表头；
- 标准最终记录筛选未把它识别为目标业务记录；
- 因而记录为辅助编号诊断计数，不生成 V2 records，也不改变已完整映射的主表为 `ambiguous`。

该政策不是“无条件忽略无表头编号区段”。另一个合成 fixture 在 post-table 内放置显式业务表头和后续编号记录，适配器将其标记为 `possible_secondary_order_table`，整体保持 `ambiguous`，原有启发式保留两个候选 block，等待未来安全 layout 应用合同；没有静默删除第二订单表。

标准坐标无法映射 A 列行号证据的故障注入也保持 `ambiguous`，并把 `evidence_mapping_failure_count` 记为 1。

## 5. 真正 Ambiguous 路径

V2 桌面服务现在执行：

```text
ambiguous
  -> build_chunk_manifest()
  -> build_structure_manifest() 本地严格适配
  -> provider.resolve_structure(valid manifest)
  -> 当前没有冻结的 layout 结果应用合同
  -> AI_V2_STRUCTURE_UNRESOLVED
```

使用正式 `VolcengineArkFullOrderProvider` + 内存 FakeTransport 验证：

- manifest 存在非空 `chunks`；
- chunk 含本地 record/evidence identities；
- function 为 `submit_bedding_order_layout`；
- `strict=true`；
- `store=false`；
- 非流式；
- Provider `structure_call_count=1`；
- FakeTransport attempt `1`；
- 真实外部 HTTP `0`；
- extraction `0`；
- 返回 `resolved` 后仍以 `AI_V2_STRUCTURE_UNRESOLVED` 安全暂停，不制造或提取 units。

`run_v2_offline_orchestration()` 也已与桌面语义对齐：遇到 `ambiguous` 时只调用 structure Provider，随后返回 `structure_unresolved` 隔离批次；extraction units、outcomes 和 extraction calls 均为 0。

## 6. 错误码与 UI 映射

原 `AI_V2_STRUCTURE_FAILED` 不再承载全部结构错误。新增：

| 固定码 | 含义 | Provider / HTTP |
| --- | --- | --- |
| `AI_V2_STRUCTURE_MANIFEST_INVALID` | 本地 manifest 构造或 identity/scope/evidence 校验失败 | 0 / 0 |
| `AI_V2_STRUCTURE_PROVIDER_FAILED` | manifest 已通过本地校验，但 Provider/Transport 调用失败 | 按实际计数 |
| `AI_V2_STRUCTURE_UNRESOLVED` | Provider 返回结构状态，但当前本地合同不能安全应用 | 1 / FakeTransport 1 |

现有 UI 仅增加上述两个固定码的受控中文文本，没有视觉、交互或流程重构。异常正文、业务数据和原始响应均不进入页面。

JobService 故障注入证明：manifest 本地失败和 Provider 失败都进入 `awaiting_user_decision`，不调用 extraction、字典、匹配或发布五类结果。

## 7. 修改文件

实现与生产边界：

- `src/bedding_order_parser/ai_full_order/standard_geometry.py`：新增标准几何窄适配器。
- `src/bedding_order_parser/ai_full_order/structure_manifest.py`：新增版本化结构 manifest 适配与本地验证。
- `src/bedding_order_parser/ai_full_order/preprocessing.py`：标准 geometry 优先、evidence 映射、结构诊断、预处理版本提升。
- `src/bedding_order_parser/ai_full_order/orchestration.py`：复用 manifest 适配器；V2 ambiguous 离线编排安全隔离。
- `src/bedding_order_parser/web/ai_full_order_service.py`：正式 manifest 路径和独立固定错误码。
- `src/bedding_order_parser/web/static/app.js`：新增两条受控错误文案。

测试：

- `tests/ai_full_order/test_v2_structure_path.py`：复杂结构、第二订单表、无法映射、正式 Provider/FakeTransport、错误码和全链 Fake 发布。
- `tests/web/test_ai_full_order_jobs.py`：JobService manifest/Provider 错误状态映射。
- `tests/web/test_d3b2d_ui_enablement.py`：错误码 UI 合同。

## 8. 测试命令与精确结果

结构路径、正式 Provider、桌面 Job 和 UI：

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\ai_full_order\test_v2_structure_path.py `
  tests\ai_full_order\test_preprocessing.py `
  tests\ai_full_order\test_orchestration.py `
  tests\ai_full_order\test_v2_offline_resolution.py `
  tests\ai_full_order\test_volcengine_ark_full_order_provider.py `
  tests\web\test_ai_full_order_jobs.py `
  tests\web\test_d3b2d_ui_enablement.py -q
# 66 passed in 56.88s
```

可靠性、缓存、恢复、五类发布、标准模式和单记录 Sidecar：

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\ai_full_order\test_v2_reliability.py `
  tests\ai_full_order\test_v2_downstream.py `
  tests\ai_full_order\test_reliability.py `
  tests\ai_full_order\test_downstream.py `
  tests\excel\test_table_parser.py `
  tests\extraction\test_item_extractor.py `
  tests\web\test_services.py `
  tests\web\test_ai_advisory.py -q
# 96 passed in 10.05s
```

V2 Schema、provenance、字段政策和安全诊断：

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\ai_full_order\test_contracts.py `
  tests\ai_full_order\test_provenance.py `
  tests\ai_full_order\test_field_policy.py `
  tests\ai_full_order\test_acceptance_diagnostics.py -q
# 67 passed in 5.21s
```

有效定向测试合计：`229 passed`。另有一次测试命令在收集前因误写不存在的测试文件名停止，结果为 `0 tests`；随后已按仓库实际文件名执行第三组并得到上述 `67 passed`。未运行完整 pytest。

## 9. 调用计数与数据安全

关键验收场景：

| 场景 | layout | extraction | FakeTransport attempts | 真实 HTTP |
| --- | ---: | ---: | ---: | ---: |
| D3D-1 同类复杂 fixture 完整 V2 Fake 链 | 0 | 3 | 0 | 0 |
| 真正 ambiguous + 正式 Provider | 1 | 0 | 1 | 0 |
| manifest 本地 identity 失败 | 0 | 0 | 0 | 0 |
| Fake structure Provider 失败 | 1 | 0 | 0 | 0 |

- 真实 Ark/API：0。
- 真实订单/真实 Job/真实 PI 读取：0。本 Gate 的命令和测试只访问仓库源码、报告及 pytest 临时目录内新生成的合成工作簿；未访问本机桌面任务存储。
- 真实字典、真实物料库、BGE-M3、FAISS：0。
- 外部网络：0。测试使用 socket guard，正式 Provider 仅连接内存 FakeTransport。
- 合成 fixture：pytest 临时目录运行时生成并自动清理；没有提交 `.xlsx`。

## 10. 未改变的冻结合同

以下保持不变并由定向回归覆盖：

- Contract V2 17 字段 sparse candidate Schema；
- provenance binder、quote/span、identity、scope 和 evidence 信任边界；
- 字段风险政策和高风险发布阻断；
- 正式行号本地生成语义；
- 物料编码与相似分数只由匹配层生成；
- V2 缓存、single-flight、中断恢复和五类原子发布合同；
- 正式 20 字段及五类 JSON；
- standard 正式结果、legacy V1、单记录 AI Sidecar、默认 ZIP；
- Ark structure 输出 Schema 和枚举；
- 字典、物料匹配算法、权重和阈值。

## 11. 剩余风险与下一步

本 Gate 已清除 D3D-1 的两个已知离线阻塞：同类结构在合成 fixture 中可由本地标准 geometry 得到 3 个 V2 units，正式 ambiguous Provider 也能收到合法 chunks manifest。因此，从当前离线证据看，已经具备由用户另行授权后重新运行真实订单的离线条件。

仍未完成且唯一需要明确保留的风险是：**真实 layout 返回结果的本地应用合同尚未冻结**。对于本地仍不能确定、真正存在第二订单表或 evidence 无法映射的工作簿，即使 Provider 返回 `resolved`，系统仍会安全进入 `AI_V2_STRUCTURE_UNRESOLVED`，不会生成 units 或发布结果。本 Gate 没有猜测性实现该合同。

此外，本 Gate 按明确禁止没有重新读取 D3D-1 的真实订单，所以“该真实订单在新代码下必然得到 3 条”尚未由真实文件复验；只能确认同等结构特征的纯合成 fixture 已稳定通过。下一步应是一个单独授权的真实订单本机只读预演或正式运行 Gate，并继续保持真实 Ark 调用预算独立审批。

## 12. 提交与工作区

- 实现提交：`fcdd05cd3793faf201eb080e9495fd22ddf79393`
- 实现提交信息：`fix: align ai v2 structure manifests and record geometry`
- 报告提交信息：`docs: report ai v2 structure path fix`
- 报告提交：本报告所在提交；完整哈希在提交后最终交接中给出。
- 报告提交前工作区：仅本报告和 6 份既有未跟踪交接/审计文档；无已跟踪代码修改。
