# Gate 3A-B 最小只读字典加载器最终报告

日期：2026-07-24
结论：已完成最小只读字典加载器与规范化预览 JSON。
边界：字典目前只是能够读取和生成预览，未接入现有 PI 解析器，未改变现有 49 条业务结果，尚未提升新订单正式解析准确率。

## 1. 初始 Git 和测试状态

| 项目 | 结果 |
|---|---|
| 初始分支 | `master` |
| 初始最新提交 | `b3987d2 docs: audit PI rule and style dictionaries` |
| 初始工作区 | 干净 |
| 初始测试 | `65 passed` |

## 2. 新增文件及职责

| 文件 | 职责 |
|---|---|
| `src/bedding_order_parser/dictionaries/__init__.py` | 导出字典预览模块的 dataclass、loader 和 writer。 |
| `src/bedding_order_parser/dictionaries/models.py` | 定义 `DictionarySource`、`RuleRow`、`FabricRow`、`StyleRow`、`DictionaryBundle`。 |
| `src/bedding_order_parser/dictionaries/loader.py` | 只做文件存在性、`.xlsx`、SHA-256、sheet/header 校验、合并单元格继承、固定范围读取和 dataclass 转换。 |
| `src/bedding_order_parser/dictionaries/writer.py` | 只做 UTF-8 JSON 输出、`ensure_ascii=False`、`indent=2`、默认拒绝覆盖和临时文件原子替换。 |
| `src/bedding_order_parser/dictionaries/__main__.py` | 提供独立 `build-preview` 命令，不修改现有 `parse` 命令。 |
| `tests/dictionaries/test_dictionary_preview.py` | 使用合成 xlsx 覆盖 SHA、错误输入、合并单元格、固定范围、行模型、JSON writer 和现有 parse CLI 可见性。 |
| `docs/reports/GATE_3A_B_FINAL_REPORT.md` | 本轮唯一最终报告。 |

## 3. 两份字典 SHA

| 文件 | SHA-256 | 状态 |
|---|---|---|
| `data/reference/PI单提取规则.xlsx` | `8d527595f671b63762a15b1f5aa89004df4e773f68e776c824c37d57dece3c7c` | 匹配批准值，运行前后未变化 |
| `data/reference/款式表_structured.xlsx` | `75faab06a151ee8f9d6d9dcb28ca4679414f4008fb86ae5d88acf5d0ee60660c` | 匹配批准值，运行前后未变化 |

## 4. 读取的工作表和行数

| 文件 | 工作表 | 范围 | 输出行数 |
|---|---|---|---:|
| `PI单提取规则.xlsx` | `被套 提取规则` | 表头第 1 行，数据第 2-36 行，A-E 列 | 35 |
| `PI单提取规则.xlsx` | `面料类价格表` | 表头第 1 行，数据第 2-76 行，A-E 列 | 75 |
| `款式表_structured.xlsx` | `Sheet1` | 表头第 1 行，数据第 2-106 行，A-H 列 | 105 |

## 5. `dictionary_preview.json` 路径

生成路径：

`data/output/gate3a_b_preview/dictionary_preview.json`

绝对路径：

`D:\AI-Learning\Projects\bedding-order-parser\data\output\gate3a_b_preview\dictionary_preview.json`

JSON 已验证可重新读取，中文未转义，summary 为：

```json
{
  "rule_rows": 35,
  "fabric_rows": 75,
  "style_rows": 105
}
```

## 6. 测试数量和结果

| 阶段 | 结果 |
|---|---|
| Gate 3A-B 新增测试 | `16 passed` |
| 全量测试 | `81 passed` |

覆盖项包括：正确 SHA、错误 SHA、文件不存在、非 `.xlsx`、合并单元格继承、固定范围读取、`RuleRow`、`FabricRow`、`StyleRow`、`None` 转空字符串、中文 JSON、默认拒绝覆盖、`--overwrite` 覆盖、原子写失败不留半成品、现有 parse CLI 仍可见、预览 JSON 顶层顺序。

## 7. 是否修改现有 PI 解析流程

否。未修改：

- `src/bedding_order_parser/pipeline/order_parser.py`
- `src/bedding_order_parser/extraction/item_extractor.py`
- `src/bedding_order_parser/normalization/field_normalizer.py`
- `src/bedding_order_parser/extraction/metadata_extractor.py`
- `src/bedding_order_parser/extraction/party_extractor.py`
- 现有主 CLI 的 `parse` 行为

## 8. 是否修改 49 条业务结果

否。未写入 `data/output/gate2d_validation`，未重新生成或改写 Gate 2D 的 49 条业务结果。

## 9. 是否安装依赖

否。未修改 `pyproject.toml`、`uv.lock` 或 `.python-version`。

## 10. Git 提交结果

本报告随本轮功能提交一并提交。提交信息：

`feat: add read-only dictionary preview loader`

最终 commit hash 以 `git log -1` 和本轮最终回复为准。

## 11. 本阶段尚未实现

- 未把字典接入现有 PI 解析器。
- 未用字典填补空款式。
- 未用字典替换现有商品筛选、面料、成分或款式规则。
- 未提升新订单正式解析准确率；新 PI 仍由 Gate 2D 现有 Python 规则解析。
- 未实现优先级、冲突解决、业务匹配、物料编码或相似分数。
- 未接入 LLM、Embedding、FAISS、BGE-M3、ERP、API、前端或 Agent。

## 12. 建议下一步

下一阶段应是“字典影子模式设计”，不是直接覆盖正式 PI 解析结果。影子模式设计前需要继续确认：

- 面料输出粒度是聚合字段还是完整面料条目；
- 排除词是否从现有代码候选迁移到规范字典；
- 默认颜色和成分别名的确认方式；
- 字典 SHA 变化时是警告、拒绝运行还是显式覆盖批准；
- 字典加载器先用于诊断校验，还是在后续 Gate 再接入解析结果生成。
