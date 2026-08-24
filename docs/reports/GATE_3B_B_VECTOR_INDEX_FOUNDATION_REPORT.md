# Gate 3B-B 物料向量索引基础报告

## 1. 结论

Gate 3B-B 已完成。项目已使用 `BAAI/bge-m3` 为 Gate 3B-A 的 29,127
条物料检索文档逐条生成归一化 float32 Embedding，并建立两个
`faiss.IndexFlatIP` 精确向量索引：

- 全量索引：29,127 条；
- 被套索引：29,085 条；
- 向量维度：模型实际返回的 1,024 维；
- 20 条真实 embedding_text 自身检索：20/20 进入 Top-10，20/20 为 Top-1。

本轮建立的是独立稠密向量召回基础，不是正式订单物料匹配。没有生成最终
“相似分数”，没有向 20 字段业务 JSON 写入物料编码或任何向量分数，也没有
接入生产解析流程。

## 2. 初始基线

| 项目 | 结果 |
|---|---|
| 仓库 | `D:\AI-Learning\Projects\bedding-order-parser` |
| 分支 | `master` |
| 初始 HEAD | `0fad2b92d2afddc0b16bd0dc422403680949c8fb` |
| 初始提交 | `feat: build canonical material store` |
| Git 作者 | `小艾 <1746762028@qq.com>` |
| 初始工作区 | 干净 |
| 初始测试 | `176 passed` |
| JSONL 记录 | 29,127 |
| SQLite 记录 | 29,127 |
| 被套记录 | 29,085 |
| 源 CSV SHA-256 | `2008a70a8cf057008d096a5f0f4f4e1e256cf4859e4694c6c2c0bad921e0ad97` |

三份 Gate 3B-A 物料库产物在开始前均存在，记录数、物料编码唯一性和源 CSV
SHA 均满足 Gate 3B-B 准入条件。本轮没有重建 Gate 3B-A。

## 3. 范围与边界

本轮完成：

- 本地 BGE-M3 Embedding；
- 全量和被套两个 FAISS 精确索引；
- 两份位置到字符串物料编码的 JSONL 映射；
- 带输入、模型、索引和产物哈希的 manifest；
- 独立 `build-index` 和 `search-index` 命令；
- 可注入 fake embedding adapter 的离线单元测试；
- 真实 29,127 条构建、20 条自身检索和 5 条手工查询验收。

本轮未完成且未接入：

- 正式订单物料匹配；
- 规格、颜色、密度、成分等硬条件过滤；
- CrossEncoder 或其他 reranker；
- 最终综合相似分数；
- 正式物料编码写回；
- 生产 `parse` 命令、20 字段 Schema、正式 JSON 或 parse report；
- LLM、云端 Embedding API、ERP、前端和 Day01。

## 4. 模型与依赖

| 项目 | 实际值 |
|---|---|
| 模型 | `BAAI/bge-m3` |
| Revision / snapshot | `5617a9f61b028005a4858fdac845db406aefb181` |
| 模型缓存 | `C:\Users\alyar\.cache\huggingface\hub\models--BAAI--bge-m3\snapshots\5617a9f61b028005a4858fdac845db406aefb181` |
| 设备 | `cpu` |
| 向量维度 | 1,024 |
| 向量类型 | float32 |
| 归一化 | `normalize_embeddings=True` |
| sentence-transformers | 5.6.1 |
| faiss-cpu | 1.14.3 |
| torch | 2.13.0+cpu |

模型权重只存在于用户级 Hugging Face 缓存，没有放入项目仓库。构建允许首次
下载模型；索引搜索根据 manifest 的 revision 直接读取已缓存 snapshot，并
校验模型名、revision、维度和索引类型。

## 5. 实现结构

| 模块 | 职责 |
|---|---|
| `materials/embedding_model.py` | 封装 sentence-transformers，本地模型加载、归一化编码、维度和 revision 解析 |
| `materials/vector_index.py` | 校验 JSONL/SQLite、批量编码、构建双索引和映射、原子提交、生成 manifest |
| `materials/vector_search.py` | 校验 manifest/产物哈希，加载指定索引，通过 mapping 还原物料编码并返回 Top-K |
| `materials/__main__.py` | 提供 `build-index` 和 `search-index` CLI |
| `tests/materials/test_vector_index.py` | 使用 fake adapter 离线验证索引合同和失败保护 |

Embedding 输入只使用 `material_documents.jsonl` 的 `text` 字段。一条 JSONL
记录对应一个向量，保持原顺序，不切块、不合并、不把物料编码放入文本。

## 6. CLI

构建命令：

```powershell
uv run python -m bedding_order_parser.materials build-index `
  --documents "data/output/material_store/material_documents.jsonl" `
  --store "data/output/material_store/material_master.sqlite3" `
  --output-dir "data/output/material_vector_index" `
  --model "BAAI/bge-m3" `
  --device cpu `
  --batch-size 16 `
  --overwrite
```

搜索命令：

```powershell
uv run python -m bedding_order_parser.materials search-index `
  --index-dir "data/output/material_vector_index" `
  --scope duvet_cover `
  --query "品类:被套；规格:240*260cm；颜色:漂白色；面料品类:贡缎；密度:T300；成分:C100" `
  --top-k 10
```

搜索结果包含 `rank`、`material_code`、`vector_score`、`source_row`、
`embedding_text`、`product_category` 和关键 metadata。字符串物料编码只通过
mapping 还原，不转换为整数 FAISS ID，也不根据 CSV 行号猜测。

## 7. 构建结果

真实构建耗时 `11,345.308` 秒，包含首次模型下载、CPU 编码、索引写入、映射
写入、哈希校验和原子目录提交。该数值是本机首次 CPU 基线，不应外推为其他
设备的固定性能。

| 产物 | 记录数 | 字节数 | SHA-256 |
|---|---:|---:|---|
| `materials_all.faiss` | 29,127 | 119,304,237 | `002778004e9eef7f0e8898c534a259c8743568e9e8a6801dc7f3f7f80f5f8208` |
| `materials_all_mapping.jsonl` | 29,127 | 19,155,307 | `33e25faa4889a20d7dd9c2dafd8a34fbd7ecd32d5b65a23baf4ae001f7a2dfa9` |
| `duvet_cover.faiss` | 29,085 | 119,132,205 | `098a35725b90a3ddc5d762715714cc221e7ed476756f4c516c91df5a384b9ab6` |
| `duvet_cover_mapping.jsonl` | 29,085 | 19,129,463 | `ee31d7b09c67a2724fbe2c1f433a385b1a63865d47eaa73281dcbef18965a3c1` |
| `vector_index_manifest.json` | - | 1,620 | `d2e2ef9a4e5af792fc2ce285f7c301924c7a7af4c4bff2d987c1157056f73662` |

索引目录由 Git 忽略，以上生成产物不提交。

## 8. 索引完整性

| 检查 | 全量索引 | 被套索引 |
|---|---:|---:|
| FAISS `ntotal` | 29,127 | 29,085 |
| Mapping 行数 | 29,127 | 29,085 |
| 唯一物料编码 | 29,127 | 29,085 |
| Position 连续 | 是 | 是 |
| 维度 | 1,024 | 1,024 |
| NaN | 0 | 0 |
| Inf | 0 | 0 |
| 最小范数 | 0.9999998212 | 0.9999998212 |
| 最大范数 | 1.0000001192 | 1.0000001192 |
| 全部归一化 | 是 | 是 |

另外 13 条已识别非被套和 29 条未识别品类记录保留在全量索引，不进入被套
索引，没有从 JSONL 或 SQLite 删除。

## 9. 20 条自身检索

从全量 mapping 中按顺序跨度选取 20 条 embedding_text 唯一的真实记录，以
原 embedding_text 查询全量索引，Top-K 固定为 10。

| 序号 | 物料编码 | CSV 行 | 自身排名 | vector_score |
|---:|---|---:|---:|---:|
| 1 | `F0903000135` | 2 | 1 | 1.0000001192 |
| 2 | `F0903000793` | 807 | 1 | 1.0000001192 |
| 3 | `F0903002459` | 2,594 | 1 | 1.0000000000 |
| 4 | `F0903004058` | 4,096 | 1 | 1.0000000000 |
| 5 | `F0903005804` | 5,690 | 1 | 1.0000001192 |
| 6 | `F0903007196` | 7,128 | 1 | 1.0000001192 |
| 7 | `F0903008735` | 8,708 | 1 | 1.0000001192 |
| 8 | `F0903010409` | 10,192 | 1 | 1.0000001192 |
| 9 | `F0903011782` | 11,658 | 1 | 1.0000000000 |
| 10 | `F0903013523` | 13,217 | 1 | 1.0000000000 |
| 11 | `F0903014897` | 14,625 | 1 | 0.9999999404 |
| 12 | `F0903016681` | 15,991 | 1 | 1.0000000000 |
| 13 | `F0903018153` | 17,538 | 1 | 1.0000000000 |
| 14 | `F0903019647` | 18,834 | 1 | 1.0000000000 |
| 15 | `F0903021104` | 20,309 | 1 | 1.0000001192 |
| 16 | `F0903022685` | 21,816 | 1 | 1.0000000000 |
| 17 | `F0903024290` | 23,265 | 1 | 1.0000002384 |
| 18 | `F0903026020` | 24,925 | 1 | 1.0000000000 |
| 19 | `F0903027661` | 26,366 | 1 | 1.0000001192 |
| 20 | `F0903028923` | 27,722 | 1 | 1.0000002384 |

结果：20/20 通过。浮点结果略高于 1 的最大偏差来自 float32 数值误差，没有
把分数截断、乘 100 或转换到其他区间。

## 10. 五个手工查询摘要

以下只用于确认召回结果可读，不构成匹配准确率评估：

| 查询摘要 | Top-1 | vector_score | 观察 |
|---|---|---:|---|
| `240*260cm / 漂白 / 贡缎 / T300 / C100` | `F0903000135`（行 2） | 0.9631208 | Top-1 规格、颜色、贡缎、密度和成分均可读 |
| `200*230cm / 浅灰 / 平布 / T200 / C60/T40` | `F0903012570`（行 12,301） | 0.9158193 | 语义接近，但颜色和成分未全部满足，后续需硬过滤 |
| `260*240cm+50cm / 漂白 / 缎纹 / T400 / C100` | `F0903024075`（行 23,127） | 0.9436494 | 召回 T400 漂白被套，但附加尺寸未严格满足 |
| `180*220cm / 蓝 / 斜纹 / T250 / C100` | `F0903019026`（行 18,412） | 0.9080085 | 召回蓝色相近规格，但面料和密度不完全满足 |
| `300*300cm / 米色 / 天丝 / T300 / C100` | `F0903001348`（行 1,455） | 0.8884776 | 召回米色 T300，但规格和面料不满足，证明不能直接落码 |

这些结果说明精确向量检索实现正确，同时也证明纯稠密相似度不能替代规格、
颜色、密度、成分等硬条件过滤。

## 11. 重复文本与并列

全量 29,127 条记录中：

- 唯一 embedding_text：17,098；
- 重复文本组：3,360；
- 位于重复文本组中的记录：15,389；
- 最大完全相同文本组：237 条。

完全相同文本会产生相同或近似相同的向量分数，并可能在 Top-K 内并列。FAISS
返回顺序不能被解释为同文物料之间的业务优先级。本轮自身检索选用文本唯一
记录验证索引和 mapping；重复组留待后续硬条件、物料主数据字段和业务规则
处理，没有人为强制自身唯一 Top-1。

## 12. vector_score 合同

`vector_score` 是归一化 query 向量与归一化物料向量在
`IndexFlatIP` 中的内积：

- 不强制转换为 0 到 1；
- 不乘 100；
- 不设置自动通过阈值；
- 只表达稠密向量语义相似度；
- 不代表最终业务可信度；
- 不写入正式 JSON 的“相似分数”；
- 不直接触发物料编码落码。

## 13. 测试

最终命令：

```powershell
uv run pytest
```

结果：`190 passed`。

新增 14 项离线测试，使用可注入 fake embedding adapter，不下载真实模型。
覆盖 JSONL 顺序、双索引数量、连续唯一 mapping、float32 归一化、IndexFlatIP
搜索、字符串编码还原、模型名/revision/维度不一致拒绝、NaN/Inf 拒绝、默认
不覆盖、失败清理、旧索引保护、产物哈希、源数据和正式 JSON 不变。

## 14. 保护结果

构建前后以下 SHA-256 完全一致：

| 受保护对象 | SHA-256 |
|---|---|
| `material_master.sqlite3` | `bc590bd08b617588677c9c79db33c5feb03ce5f3ffd11c8b904c1ffb51374e20` |
| `material_documents.jsonl` | `61d2769e44fb9821d538f3d945c1cf61ee5b8501ac5356e3c9419ae37dea2c8c` |
| `material_store_manifest.json` | `668566f273481ed7e207cba7998478556945f16e5c71766c178f97e91c9a6afc` |
| `material_info.csv` | `2008a70a8cf057008d096a5f0f4f4e1e256cf4859e4694c6c2c0bad921e0ad97` |

排除本轮 `material_vector_index` 后，`data/output` 既有 371 个文件的聚合 SHA
在构建前后均为：

`bf8b760bf55d6524d014b5fc926219bdf1f8f4d9fce04074edef7349f0a2271c`

因此既有正式业务 JSON、parse report 和 Gate 审计输出未变化。生产解析器、
字典验证流程、20 字段 Schema、两份 Excel 字典和依赖范围外文件均未修改。

只读确认 Day01：

- HEAD：`b6206bf28a9ce5499e317cee324b16ea98bf569d`；
- 工作区：干净；
- 本轮修改：无。

仓库根目录存在本地业务资料包 `床品订单day1/`。本轮没有修改、移动或删除
其内容，只在 `.gitignore` 增加精确规则，防止真实 PI、规则表和 CSV 被误提交。

## 15. 原子性与失败处理

索引、mapping 和 manifest 先写入目标目录旁的隐藏临时目录。全部向量、数量、
哈希和源输入复核通过后，才整体切换为正式目录；失败会清理临时目录。使用
`--overwrite` 时，旧完整目录在新目录提交成功前保留为备份。真实构建结束后
没有残留临时或备份目录。

## 16. 下一阶段准入

结论：具备进入“混合物料匹配原型”的工程条件，但不具备直接正式落码条件。

已经具备：

- 稳定物料文档；
- 可复核模型 revision；
- 全量和被套精确向量召回；
- 严格位置映射和物料编码还原；
- 独立搜索 CLI；
- 产物版本和 SHA 合同；
- 离线回归测试。

下一阶段仍需单独设计和验收：

- 规格方向、单位和附加尺寸硬过滤；
- 颜色、面料、密度、成分硬条件；
- 重复 embedding_text 的消歧；
- 候选融合与拒绝策略；
- 最终综合分数的定义和校准；
- 人工复核与正式物料编码落码条件。

## 17. 交付文件

本轮只生成本报告：

`docs/reports/GATE_3B_B_VECTOR_INDEX_FOUNDATION_REPORT.md`

按任务要求未生成 handoff、archive、README 更新或额外报告。
