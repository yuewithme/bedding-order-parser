# Gate 4D-B2A｜AI整单离线编排与字段裁决报告

## 1. 实际基线与commit

- 开始 HEAD：`f0a58019e23c109794aa529554112dc27844014a`（`feat: add ai full-order contract foundation`）。
- 开始工作区：仅有允许保留的两份未跟踪恢复文档：`CODEX_HANDOFF_AND_RECOVERY_2026-07-30.md`、`CODEX_RECOVERY_AUDIT_ROUND_1_REPORT_2026-08-01.md`。
- 本轮遵守 `AGENTS.md`、`.codex/skills/bedding-gate/SKILL.md`、Gate 4D-A 设计报告和 Gate 4D-B1 报告；旧 18 字段/AI 行号表述按稳定规则收敛为 17 个 AI 字段与本地行号。
- 提交信息：`feat: add ai full-order orchestration and field resolution`；实际提交哈希以提交后 Git 输出和最终回复为准。

## 2. 行号语义核验结论

- 已核验现有标准模式：`src/bedding_order_parser/extraction/item_extractor.py` 从明细行的 `No.`/`No`/`number`/`line`/`序号`列读取 `item.line_number`，并写入正式 20 字段 `行号`。
- `src/bedding_order_parser/excel/table_parser.py` 的 `ParsedRow.excel_row_number` 是 Excel 物理行坐标，只用于证据坐标和相邻行判断，不等同正式 `行号`。
- `tests/extraction/test_item_extractor.py` 证明正式 `行号`保留源编号列值，例如 Excel 第 2 行明细中的 `1`、编号为 `4` 的明细行输出 `4`。
- B2A 新增 `formal_line_number_from_request()` 按标准语义从同记录证据的 A 列编号单元取正式行号；Sheet、scope 和源行坐标继续保存在证据、chunk manifest 与稳定身份中。B1 的 `s1:4` 仅为内部本地坐标，不进入正式业务字段。

## 3. 分块与条件式结构识别

- 新增 `src/bedding_order_parser/ai_full_order/orchestration.py`，实现确定性 `ChunkManifestItem`。
- manifest 包含 source SHA、scope、稳定 chunk ID、block ID、记录身份、证据范围、顺序和状态。
- chunk ID 由 source SHA、scope、block、记录 ID、记录身份和表头证据计算 SHA-256 前缀，重复预处理结果保持稳定。
- `run_offline_orchestration()` 对 `locally_resolved` 结构直接进入 FakeProvider 字段提取，结构识别调用次数为 0；只有 `ambiguous` 结构调用一次 FakeProvider `resolve_structure()`。

## 4. Python shadow接口

- 新增 `src/bedding_order_parser/ai_full_order/resolution.py` 的 `PythonShadowRecord` 与 `PythonFieldCandidate` 窄接口。
- `adapt_python_shadow_records()` 按预处理记录顺序把 Python 确定性正式字段和诊断证据转换为字段裁决输入；不调用也不修改标准解析器。
- shadow 记录持有 `record_local_id`、`source_record_id`、`scope_id`、正式 `line_number` 和 17 个业务字段候选。

## 5. 字段裁决矩阵

- 17 个 AI 业务字段逐字段裁决，输出 `FieldDecision`，包含选用值、来源、AI/Python 候选、证据 ID、机器可读 reason code、blocking 标记和简短消息。
- 已覆盖 reason code：`ai_python_agree`、`ai_fills_python_blank`、`python_retained_ai_omitted`、`direct_evidence_selected_ai`、`direct_evidence_selected_python`、`unresolved_direct_evidence_conflict`、`no_direct_evidence_conflict`、`both_missing`、`ai_rejected_business_constraint`、`ai_contract_failure`。
- 高风险字段集合为 `客户`、`币种`、`业务员`、`数量`、`计划发货日期`；直接证据冲突或 AI 业务约束失败会阻止批次 ready。
- 描述字段只有在 AI 有有效证据时可补 Python 空值；Python 有值而 AI 遗漏时保留 Python。
- 备注字段不保存私有思维链，不允许无证据扩写；物料编码和相似分数不在 AI 字段、裁决字段或 resolved business fields 中出现。

## 6. 批次隔离与ready门

- 新增内存级 `aggregate_batch()`，分块成功不等于整批成功。
- `ready_for_downstream` 必须满足：所有预期 chunk 均 validated、记录数一致、记录身份唯一、scope 不交叉、无未解决高风险冲突、无 Schema 或证据失败。
- 不满足时返回 `isolated`，并给出结构化原因：`missing_chunks`、`record_count_mismatch`、`duplicate_record_identity`、`scope_crossing`、`unresolved_high_risk_conflict`、`schema_or_evidence_failure`。
- 本轮未接正式 Job，也未发布五类核心 JSON。

## 7. 测试命令和结果

```powershell
uv run pytest tests/ai_full_order tests/extraction/test_item_extractor.py tests/excel/test_table_parser.py -q
```

- 结果：`66 passed in 1.21s`。
- 覆盖目标：明确区块不调用结构识别、歧义结构只调用一次、chunk ID 稳定、反序执行不改变最终记录顺序、重复记录身份隔离、缺失块不 ready、17 字段主要裁决分支、高风险冲突阻断、Python 值保留、AI 有效证据补充描述字段、跨 scope/伪造证据失败、正式行号与标准模式一致、物料编码/相似分数不存在、零网络调用。
- 未运行完整 pytest。

## 8. 网络/API调用数

- 真实豆包/API 调用：0。
- 网络调用：0；测试通过 FakeProvider 的 `network_call_count` 和 socket 替换证明离线执行。
- BGE-M3 调用：0；FAISS 调用：0；未解析真实 PI；未安装依赖。

## 9. 修改文件和工作区

- `src/bedding_order_parser/ai_full_order/__init__.py`
- `src/bedding_order_parser/ai_full_order/orchestration.py`
- `src/bedding_order_parser/ai_full_order/resolution.py`
- `tests/ai_full_order/test_orchestration.py`
- `tests/ai_full_order/test_resolution.py`
- `docs/reports/GATE_4D_B2A_OFFLINE_ORCHESTRATION_AND_FIELD_RESOLUTION_REPORT.md`
- 提交后工作区预期：仅保留两份恢复文档为未跟踪文件，不暂存、不删除。

## 10. 下一步

Gate 4D-B2B：实现离线缓存、幂等、single-flight、原子状态和中断恢复。
