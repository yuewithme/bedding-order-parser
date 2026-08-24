# Gate 3B-C 混合物料匹配原型报告

## 1. Git 基线与最终提交

- 项目：`D:\AI-Learning\Projects\bedding-order-parser`
- 分支：`master`
- 初始完整 HEAD：`bd43d7c29692ab92cf8ec7dbc9bcbd264127504e`
- 初始短 HEAD：`bd43d7c`
- 初始最新提交：`feat: build material vector index`
- 初始工作区：干净
- 初始测试：`190 passed`
- 本轮提交信息：`feat: prototype hybrid material matching`
- 本报告随本轮最终提交交付；提交后的完整、短哈希由 `git rev-parse HEAD`
  和最终交付回执记录。Git 提交无法在自身文件内容中稳定内嵌自身哈希。

## 2. 49 条输入确认

- 只读取 `data/output/gate2d_validation/all_results` 中 12 份 Gate 2D
  正式 JSON。
- 只读取 `data/output/gate2d_validation/all_reports` 中对应的 12 份
  parse report。
- 正式订单记录共 49 条，每条字段集合和顺序均严格等于既有 20 字段
  Schema。
- 49 条正式 `物料编码` 均为空，正式 `相似分数` 均为 `0.0`。
- 未重新解析 PI，未读取 PI 作为匹配输入，未改写正式 JSON 或 parse report。
- 正式 JSON 初始聚合记录值：
  `b57e89b7499307fd2f21ba4bf1b706634a3f17182365734581cc5f43505491c0`。
- parse report 初始聚合记录值：
  `b67aa4b152e184e163056299cdef117f0fbacbd08a717a72a4dcc74e1070ae17`。
- 匹配器对全部输入逐文件计算运行前、运行后 SHA-256 并要求完全相同；
  真实运行保护断言通过。

## 3. 两路候选召回设计

结构化召回使用 SQLite 的产品品类、主颜色、密度、成分和尺寸类型。
查询字段为空时不加限制；候选字段为空时继续保留，交由比较器解释。

向量召回使用冻结的被套 FAISS `IndexFlatIP`、同一
`BAAI/bge-m3` 本地模型和归一化查询向量，每条默认召回 Top 300，
保留原始内积分数。最终候选为：

```text
structured_candidates UNION vector_top_300
```

两路召回不是交集。结构化候选若不在被套索引映射中，不进入默认被套候选
范围。字符串物料编码通过 mapping 恢复，不做整数转换。

运行时验证的冻结产物：

| 产物 | SHA-256 |
|---|---|
| `material_master.sqlite3` | `bc590bd08b617588677c9c79db33c5feb03ce5f3ffd11c8b904c1ffb51374e20` |
| `material_documents.jsonl` | `61d2769e44fb9821d538f3d945c1cf61ee5b8501ac5356e3c9419ae37dea2c8c` |
| `material_store_manifest.json` | `668566f273481ed7e207cba7998478556945f16e5c71766c178f97e91c9a6afc` |
| `duvet_cover.faiss` | `098a35725b90a3ddc5d762715714cc221e7ed476756f4c516c91df5a384b9ab6` |
| `duvet_cover_mapping.jsonl` | `ee31d7b09c67a2724fbe2c1f433a385b1a63865d47eaa73281dcbef18965a3c1` |
| `vector_index_manifest.json` | `d2e2ef9a4e5af792fc2ce285f7c301924c7a7af4c4bff2d987c1157056f73662` |

SQLite 为 29,127 条，被套索引为 29,085 条，维度为 1,024，模型修订为
`5617a9f61b028005a4858fdac845db406aefb181`。

## 4. 硬冲突规则

只在双方都有明确、可标准化证据时应用硬冲突：

- 产品品类：明确被套查询只允许被套候选。
- 规格：复用既有规格规则，统一方向、单位和分隔符；基础长宽明确不一致才
  排除；附加尺寸仅一侧缺失为 `partial_match`。
- 颜色：只比较批准的产品主颜色，不把 ID thread 等工艺色当主颜色。
- 成分：例如 `C100` 与 `C80/T20` 明确冲突。
- 密度：只接受带 `T/TC` 的明确组合面料证据；`100C` 不得推断为 `T100`。
- 面料：只有双方都能映射到互斥标准面料族时才排除。
- 款式、加标方式、尺寸类型只参与排序，不作为硬冲突。

每条订单输出唯一被排除候选数以及各字段的冲突发生次数。一个候选可同时
在多个字段发生冲突，因此字段发生次数之和可大于被排除候选数。

## 5. `hybrid_score_v1` 公式

对未被硬冲突过滤的候选：

```text
structured_score =
  sum(available_field_weight * status_score)
  / sum(available_field_weight)

vector_score_normalized =
  (clamp(raw_vector_score, -1, 1) + 1) / 2

prototype_match_score =
  0.75 * structured_score + 0.25 * vector_score_normalized
```

如果没有任何可比较结构化字段，原型分数只保留标准化向量分数，但决策状态
必须为 `insufficient_evidence`。原始 `vector_score` 同时保留且不修改。

## 6. 字段权重

| 字段 | 结构化内部权重 |
|---|---:|
| spec | 0.25 |
| composition | 0.18 |
| fabric | 0.17 |
| density | 0.15 |
| color | 0.10 |
| style | 0.08 |
| label_method | 0.04 |
| size_type | 0.03 |

状态分值为：`exact_match=1.00`、`equivalent_match=0.95`、
`partial_match=0.60`、`no_match=0.00`。这些权重只是工程基线，尚未经过
人工真值校准。

## 7. 缺失字段处理

`missing_query`、`missing_candidate`、`not_comparable` 不进入结构化可用权重
分母，不按零分处罚。查询侧49条中的缺失记录数为：

| 字段 | 缺失订单数 |
|---|---:|
| style | 13 |
| composition | 7 |
| density | 5 |
| 其余查询字段 | 0 |

Top-K 候选侧较明显的缺失为 fabric 33 次、density 32 次、size_type 33 次、
composition 28 次、style 24 次。该口径是已输出 Top-K 候选字段发生次数，
不是物料库全表缺失率。

少于3个加权结构化字段可比较时，决策标记为
`insufficient_evidence`。这只是人工复核证据下限，不是自动落码阈值。

## 8. 重复文本消歧

对候选按完整 `embedding_text` 分组；当同组向量分数近似相同且结构化评分
无法区分时，输出 `ambiguous_duplicate_group`、全部并列字符串物料编码、
相同字段、差异字段和所需业务证据。

原型不使用 CSV 顺序、物料编码字典序、source row 或 FAISS position
作为业务优先级。所有记录的 action 均为 `manual_review`。

## 9. 49 条真实运行统计

| 指标 | 结果 |
|---|---:|
| 订单记录 | 49 |
| 有候选 | 43 |
| `unique_best_candidate` | 14 |
| `ambiguous_tie` | 3 |
| `insufficient_evidence` | 26 |
| `no_candidate` | 6 |
| 重复文本歧义 | 3 |
| 有效候选过多 | 0 |

“有效候选过多”的可复核工程口径为硬过滤后候选数大于100。

平均候选数：

| 阶段 | 每条平均 |
|---|---:|
| 结构化召回 | 1,730.449 |
| 向量召回 | 300.000 |
| 并集 | 1,984.306 |
| 硬冲突排除 | 1,976.265 |
| 硬过滤后 | 8.041 |

硬冲突字段发生次数：规格 96,409、面料族 39,582、密度 8,008、
成分 7,547、颜色 1,114。规格和面料族最能缩小候选；这些是字段发生次数，
不是互斥候选数。

## 10. Top 1 与 Top 2 间隔

43条有候选记录的 Top 1 原型分数：

- 最小值：0.765010
- Q1：0.767131
- 中位数：0.769634
- Q3：0.955842
- 最大值：0.982044

18条至少有两个过滤后候选，因此可计算 Top 1/Top 2 margin：

- 最小值：0.000000
- Q1：0.000489
- 中位数：0.001089
- Q3：0.033939
- 最大值：0.196498

其余有候选记录只有一个过滤后候选，margin 为 `null`，不伪造第二名。

## 11. 十条代表案例

| 来源与行号 | 规格 / 面料 | 决策 | 过滤后候选 | Top 1编码 | 分数 / margin | 说明 |
|---|---|---|---:|---|---|---|
| 11行样本 / 1 | `260*340+15cm` / `贡缎/T240/100C` | insufficient | 1 | `F0903000771` | 0.765302 / null | 仅2个加权字段可比，不确认 |
| 11行样本 / 5 | `240*290+15cm` / `缎条/T250/C60/T40` | ambiguous | 11 | `F0903015671` | 0.980295 / 0 | 2个重复文本编码并列 |
| 11行样本 / 6 | `250*155cm` / `贡缎/T300/100C` | unique best | 10 | `F0903008603` | 0.958693 / 0.011767 | 仅表示原型最高分 |
| 11行样本 / 7 | `240*250cm` / `斜纹/T250/C95/T5` | no candidate | 0 | - | - | 300个并集候选全部硬冲突 |
| Okura / 3 | `240*270cm` / `T300/100C` | ambiguous | 75 | `F0903008434` | 0.963902 / 0 | 6个重复文本编码并列 |
| Okura / 6 | `245*275cm` / `斜纹/T250/C95/T5` | no candidate | 0 | - | - | 300个并集候选全部硬冲突 |
| `3402510MH90180` / 4 | `242*277cm` / `贡缎/T300/100C` | no candidate | 0 | - | - | 319个候选规格全部冲突 |
| Welllife / 27 | `250*240cm` / `贡缎/T300/100C` | ambiguous | 15 | `F0903001021` | 0.971124 / 0 | 2个重复文本编码并列 |
| `3402511MH30095` / 4 | `240*255cm` / `T600/100C` | insufficient | 1 | `F0903000771` | 0.769892 / null | 候选主数据证据过少 |
| Makotel / 37 | `260*280cm` / `T300/C80/T20` | insufficient | 1 | `F0903000771` | 0.767131 / null | 候选主数据证据过少 |

所有 Top 1 编码均为候选，不是正式落码。

## 12. 无候选与歧义案例

无候选共6条：

1. 11行样本第7行：浅灰、斜纹、`C95/T5`，300个候选全部排除。
2. Okura第6行：浅灰、斜纹、`C95/T5`，300个候选全部排除。
3. `3402510MH90180`第4行：`242*277cm`，319个候选规格全部冲突。
4. `3402510MH90180`第5行：`240*213cm`，319个候选规格全部冲突。
5. `3402510MH90180`第14行：与第4行相同查询证据，无候选。
6. `3402510MH90180`第15行：与第5行相同查询证据，无候选。

重复文本歧义共3条：

- 11行样本第5行：`F0903015671`、`F0903028633`。
- Okura第3行：6个并列编码，以 `F0903008434` 开头；完整集合已写入候选
  输出的 `duplicate_material_codes`。
- Welllife第27行：`F0903001021`、`F0903021832`。

## 13. 准确率边界

当前49条正式结果没有正确物料编码真值，因此不能计算 Top 1、Top 10、
召回率、准确率或阈值效果。`unique_best_candidate` 只表示当前工程合同下
出现唯一最高分，不能解释为业务正确。

## 14. 负责人确认清单

49条订单全部需要负责人提供或确认正确物料编码，原因是当前没有任何一条
正式真值。两份原型输出的 summary 已按来源文件、工作表和行号列出完整49条
确认清单。

优先确认顺序建议：

1. 6条 `no_candidate`，用于确认主数据是否缺失或正式查询字段是否需纠偏。
2. 3条 `ambiguous_tie`，用于建立重复文本的业务区分键。
3. 26条 `insufficient_evidence`，用于补全候选主数据或确定最小证据合同。
4. 14条 `unique_best_candidate`，用于校准字段权重和分数间隔。

## 15. 正式结果保护

- 正式20字段 JSON：未修改。
- 正式 `物料编码`：未写回。
- 正式 `相似分数`：未写回。
- parse report：未修改。
- PI、字典、CSV、SQLite、JSONL、FAISS、mapping、manifest：未修改。
- 原型只生成：
  `data/output/material_match_prototype/material_match_candidates.json`
  和 `material_match_summary.json`。
- 两份输出均被 `.gitignore` 明确命中，不提交业务结果。
- 未调用 LLM、外部 API、云端 Embedding 或 CrossEncoder。
- 未修改 Day01。

## 16. 测试结果

最终提交前全量测试：`205 passed`。

新增15项定向测试，覆盖并集召回、空查询字段、候选空字段、规格冲突、
附加尺寸部分匹配、手洞排除、成分与密度冲突、工艺色隔离、面料层级、
硬冲突过滤、缺失权重重归一化、原始向量分数、可复现综合分数、重复文本
歧义、margin、原始正式 JSON 保护、原子输出及 `100C` 不误识别为 `T100`。

真实输出合同断言通过：

- 文件数2；
- 记录数49；
- Top-K保留规则通过；
- 所有 action 为 `manual_review`；
- 每个保留候选都有完整字段解释；
- 分数范围与物料编码类型通过。

## 17. 下一阶段准入判断

结论：具备进入“人工标注与评分校准阶段”的工程基础，但不具备生产落码
条件。

下一阶段需要先取得49条正确物料编码真值，确认6条无候选的业务原因，
为3组重复文本建立可用区分字段，并审查候选主数据缺失导致的26条
`insufficient_evidence`。在这些证据完成前，不应审批自动阈值，也不应把
原型分数写入正式结果。
