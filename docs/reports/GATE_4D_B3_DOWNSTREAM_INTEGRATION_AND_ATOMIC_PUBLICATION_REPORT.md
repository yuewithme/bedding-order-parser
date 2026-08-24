# Gate 4D-B3｜下游衔接与五类核心 JSON 原子发布报告

## 1. 实际基线和提交

- 开始分支：`master`。
- 开始完整 HEAD：`2c63cd61cad5000cf872aa7d85a3cbede32fd40f`。
- 开始短哈希：`2c63cd6`。
- 开始提交：`feat: add ai full-order cache and recovery`。
- 开始工作区仅有允许保留且未跟踪的恢复文档：`CODEX_HANDOFF_AND_RECOVERY_2026-07-30.md`、`CODEX_RECOVERY_AUDIT_ROUND_1_REPORT_2026-08-01.md`。
- 本报告与本轮实现会一并提交；实际提交哈希在提交后核验记录。

## 2. 下游发布门

- 新增 `src/bedding_order_parser/ai_full_order/downstream.py`，作为 AI 整单模式的独立窄适配与发布边界；没有向标准解析器散布 AI 条件。
- `publish_ready_batch()` 在调用字典或匹配端口前，要求 B2B 结果为 `executed` 或 `cached`，B2A 批次为 `ready_for_downstream`，所有 manifest chunk 均为 `validated`，记录身份唯一，且不存在阻塞字段裁决。
- 缺块、非 validated chunk、隔离批次、重复记录身份或未解决高风险冲突都会在端口调用前拒绝，因此不会生成正式 20 字段或任何核心 JSON。

## 3. 字典验证适配

- 定义 `DictionaryValidator` 窄协议，接收字段裁决后的 `ResolvedRecord` 和只读证据映射。
- 适配层复用既有 `validation_only` 业务类别和既有 `*_dictionary_validation.json` 命名规则，不读取真实字典工作簿，不复制或改变现有字典规则。
- 字典输出必须声明 `mode=validation_only`，并与已裁决记录数量一一对应；适配层不允许字典回写或编造正式业务字段。
- 测试使用计数型 `FakeDictionaryValidator`，验证其只在发布门通过后执行，且必定先于物料匹配执行。

## 4. 物料匹配适配

- 定义 `MaterialMatcher` 窄协议，输入仅为已裁决的临时正式记录与其来源身份。
- 临时记录在进入匹配端口前强制 `物料编码=""`、`相似分数=0.0`；仅匹配端口返回的同身份 `MaterialSelection` 可以填入编码和 `float` 分数。
- 复用现有 `build_order_query()` 作为纯本地查询规范化边界，未加载 BGE-M3、FAISS、向量索引或物料主数据。
- 复用既有 `material_match_candidates.json`、`material_match_summary.json` 名称，并要求摘要保留“相似分数不是准确率”的说明。无候选固定为编码空字符串和 `0.0` 浮点数。
- AI 17 字段结果中没有物料编码或相似分数；适配层拒绝错误身份、非字符串编码、非 float 分数以及不完整选择集。

## 5. 17＋1＋2 到正式 20 字段

- 已裁决的 17 个 AI 业务字段来自 B2A `ResolvedRecord`；`行号`继续使用已在 B2A 核验过的标准模式正式行号。
- 物料编码和相似分数只由匹配层提供，按现有 `FINAL_FIELD_NAMES` 的固定顺序组装为 20 字段。
- 对每条正式记录重新验证：字段集合与顺序完全匹配、前 19 项均为非 null 字符串、相似分数为非 bool 的 `float`。
- `parse_mode`、缓存键、模型、证据和字段裁决信息均不进入正式业务 JSON。

## 6. 五类 JSON

每个成功 bundle 恰好包含以下五类核心 JSON：

1. `ai_full_order.json`：仅正式 20 字段记录。
2. `ai_full_order_parse_report.json`：既有 ParseReport 结构，另含 `ai_enhanced` 诊断信封（parse_mode、cache key、chunk ID、机器可读字段裁决原因）。
3. `ai_full_order_dictionary_validation.json`：字典验证 JSON。
4. `material_match_candidates.json`：物料候选 JSON。
5. `material_match_summary.json`：物料匹配摘要 JSON。

- 适配层验证恰好五个名称、正式业务 JSON 的严格字段合同、诊断中 AI 信封的存在，以及字典/候选/摘要的必要业务边界。
- 原始 Provider 请求或响应、缓存状态和 Sidecar 没有发布为第六类业务 JSON。

## 7. 原子发布机制

- 每个缓存身份写入独立的 `bundles/<cache_key>` 版本化 bundle；所有五个 JSON 在唯一 staging 目录使用 UTF-8、`ensure_ascii=False`、`indent=2`、flush 与 fsync 写完并重新验证后，才以目录级原子替换安装。
- `CURRENT` 是唯一的原子文本入口，只有 bundle 安装并 fsync 后才替换。因此读取者不会通过入口看到新旧五文件混合；旧 bundle 保留，不会被不同缓存身份覆盖。
- 已存在同身份 bundle 时重新校验规范化内容 SHA；内容一致则复用，内容不一致则拒绝，防止错误覆盖。
- 单文件临时替换、目录安装和 `CURRENT` 替换均对 Windows 常见 `PermissionError` 使用有界重试。
- 生成、校验或任一写入失败会清理 staging；失败的新 bundle 不会出现为最终 bundle，也不会删除另一个缓存身份已存在的 `CURRENT` 入口。

## 8. 失败注入和 SHA 稳定性测试

执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/ai_full_order/test_contracts.py tests/ai_full_order/test_preprocessing.py tests/ai_full_order/test_resolution.py tests/ai_full_order/test_orchestration.py tests/ai_full_order/test_reliability.py tests/ai_full_order/test_downstream.py tests/pipeline/test_order_parser.py tests/serialization/test_json_writer.py tests/serialization/test_diagnostic_writer.py tests/materials/test_hybrid_matcher.py
```

结果：`84 passed in 4.96s`。

- B3 新增端到端测试覆盖：非 ready 批次不会调用字典/匹配；字典后匹配的固定顺序；17＋1＋2 严格 20 字段；AI 无法写入物料编码或相似分数；无候选；非法整数分数拒绝；五类文件；诊断元数据隔离；第三个写入失败不发布；同输入 SHA 稳定；不同缓存身份隔离；模拟 Windows 占用的有界恢复。
- 关联回归覆盖 B1/B2A/B2B 合同、证据和行号语义、离线编排/恢复，以及标准解析和序列化、既有物料查询边界。
- 没有运行完整 pytest。

## 9. 标准模式保护

- 未修改标准解析算法、标准模式正式输出、单记录 AI Sidecar、现有字典规则、物料匹配权重/阈值/Top-K/硬冲突规则或默认 ZIP 行为。
- B3 发布仅由新模块主动调用；标准模式仍沿用原有 pipeline 与原有五类业务职责。

## 10. 网络/API/模型调用数

- 真实豆包/API 调用：0。
- 网络调用：0；B3 端到端测试禁用 socket 建连，FakeProvider `network_call_count=0`。
- BGE-M3 调用：0；FAISS 调用：0。
- 未解析真实 PI，未安装新依赖。

## 11. 修改文件、工作区和下一步

- `src/bedding_order_parser/ai_full_order/downstream.py`
- `tests/ai_full_order/test_downstream.py`
- `docs/reports/GATE_4D_B3_DOWNSTREAM_INTEGRATION_AND_ATOMIC_PUBLICATION_REPORT.md`
- 提交后工作区应仅保留两份恢复文档为未跟踪文件；它们不暂存、不删除。

下一步唯一建议：Gate 4D-C：在桌面端离线接入标准解析与 AI 增强整单解析双模式，使用 FakeProvider 完成上传、确认、进度、失败选择、结果与历史联调。
