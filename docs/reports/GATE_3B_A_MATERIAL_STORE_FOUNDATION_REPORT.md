# Gate 3B-A Material Store Foundation Report

## 1. Source File

The only approved material master source found in the required search order was:

- relative path: `data/reference/material_info.csv`
- SHA-256: `2008a70a8cf057008d096a5f0f4f4e1e256cf4859e4694c6c2c0bad921e0ad97`
- file size: 5,896,564 bytes
- encoding: `utf-8-sig`
- delimiter: comma

`stores/cover/material_info.csv` was not present. No Day01 or external project scan was performed.

## 2. Actual Rows And Fields

- CSV records: 29,127
- header columns: 12
- invalid-width rows: 0

Headers:

1. `物料编码`
2. `物料名称`
3. `规格`
4. `颜色`
5. `面料`
6. `款式`
7. `加标方式`
8. `尺寸类型`
9. `面料-品类`
10. `面料-纱支`
11. `面料-密度`
12. `面料-涤棉成分`

## 3. Quality Statistics

- empty material codes: 0
- duplicate material codes: 0
- exact duplicate rows: 0
- invalid rows: 0

Empty counts:

| Field | Empty |
| --- | ---: |
| 物料编码 | 0 |
| 物料名称 | 0 |
| 规格 | 1 |
| 颜色 | 0 |
| 面料 | 16 |
| 款式 | 36 |
| 加标方式 | 2 |
| 尺寸类型 | 32 |
| 面料-品类 | 16 |
| 面料-纱支 | 1,454 |
| 面料-密度 | 31 |
| 面料-涤棉成分 | 16 |

Unique counts:

| Field | Unique |
| --- | ---: |
| 物料编码 | 29,127 |
| 物料名称 | 6,092 |
| 规格 | 3,228 |
| 颜色 | 105 |
| 面料 | 512 |
| 款式 | 106 |
| 加标方式 | 19 |
| 尺寸类型 | 3 |
| 面料-品类 | 381 |
| 面料-纱支 | 32 |
| 面料-密度 | 15 |
| 面料-涤棉成分 | 10 |

## 4. Product Category Statistics

- duvet-cover records: 29,085
- recognized non-duvet records: 13
- unrecognized product-category records: 29

Recognized non-duvet top types:

| Type | Count |
| --- | ---: |
| 芯类 | 5 |
| 床单 | 4 |
| 枕套 | 3 |
| 保护垫 | 1 |

Unrecognized product-category rows are recorded in `material_store_manifest.json` under `statistics.unrecognized_product_category_rows`.

## 5. Safe Normalization Rules

All raw CSV fields are preserved separately from normalized fields. No source value is overwritten.

Applied deterministic rules only:

- text: NFKC normalization, trim, whitespace collapse;
- product category: recognize approved duvet-cover expressions such as `被套`, `被罩`, `duvet cover`, `dubet cover`, and `quilt cover`; customer/person/sample prefixes are not copied into `product_category`;
- spec: normalize `x`, `X`, `*`, `×`; convert `mm` and `inch` to `cm`; preserve the material-master dimension order; preserve explicit `+Xcm` extensions;
- color: reuse approved deterministic color forms only, with exact shade preservation such as `浅灰色` not being collapsed into `灰色`;
- fabric/yarn/density/composition: prefer the already split CSV fields and do not infer missing components from the full fabric string;
- style: preserve cleaned raw style when present and do not fabricate a normalized style if the source is empty.

## 6. Embedding Text Structure

Each material record produces one stable retrieval text using fixed field order:

`品类 -> 规格 -> 颜色 -> 面料 -> 面料品类 -> 纱支 -> 密度 -> 成分 -> 款式 -> 加标方式 -> 尺寸类型`

Rules:

- empty fields are omitted;
- `material_code` is not included;
- `source_row` is not included;
- customer/person prefixes from `物料名称` are not included;
- UTF-8 Chinese text is preserved;
- repeated builds produce identical JSONL text for the same input.

## 7. SQLite Structure And Indexes

Output SQLite:

`data/output/material_store/material_master.sqlite3`

Table: `materials`

Primary key:

- `material_code TEXT PRIMARY KEY`

Record count:

- SQLite records: 29,127
- distinct material codes in SQLite: 29,127

Indexes:

- `idx_materials_product_category`
- `idx_materials_spec_normalized`
- `idx_materials_color_normalized`
- `idx_materials_fabric_category_normalized`
- `idx_materials_density_normalized`
- `idx_materials_composition_normalized`
- `idx_materials_size_type_normalized`

## 8. JSONL Output

Output JSONL:

`data/output/material_store/material_documents.jsonl`

- JSONL records: 29,127
- blank lines: 0
- duplicate ids: 0
- one source row maps to one JSON object
- one JSON object maps to one material code

Each line has:

```json
{"id":"物料编码","text":"embedding_text","metadata":{}}
```

No Embedding was generated in this Gate.

## 9. Manifest And Output Sizes

Manifest:

`data/output/material_store/material_store_manifest.json`

Output sizes:

| Output | Size bytes |
| --- | ---: |
| `material_master.sqlite3` | 25,260,032 |
| `material_documents.jsonl` | 16,701,976 |
| `material_store_manifest.json` | 4,210 |

Final CLI build command:

```powershell
uv run python -m bedding_order_parser.materials build --source "data/reference/material_info.csv" --output-dir "data/output/material_store" --overwrite
```

Final observed build time: 1.875 seconds.

## 10. Source Protection

- source SHA before build: `2008a70a8cf057008d096a5f0f4f4e1e256cf4859e4694c6c2c0bad921e0ad97`
- source SHA after build: `2008a70a8cf057008d096a5f0f4f4e1e256cf4859e4694c6c2c0bad921e0ad97`
- source CSV modified: no

## 11. Formal Parser Protection

No formal parser or order output behavior was changed.

Not modified:

- `order_parser`
- existing parse CLI command
- field normalizer production rules
- item extractor
- metadata extractor
- party extractor
- final 20-field model
- dictionary validation behavior
- Excel dictionaries
- formal business JSON
- parse reports
- dependencies
- Day01

## 12. Tests

Final test command:

```powershell
uv run pytest
```

Final result:

```text
176 passed
```

New coverage includes UTF-8 BOM CSV loading, header contract validation, empty and duplicate material code rejection, one-row-to-one-material mapping, raw preservation, deterministic normalization, embedding text contract, SQLite primary key/indexes, JSONL one-document-per-material output, stable rebuilds, source SHA preservation, and default no-overwrite behavior.

## 13. Vector Index Readiness

Gate 3B-A is ready for the next vector-index foundation Gate because:

- every valid material row has a stable metadata id: `material_code`;
- SQLite and JSONL record counts match the source record count;
- retrieval text is deterministic and excludes material code/source row;
- manifest records source SHA, quality metrics, category statistics, output counts, and distributions;
- generated outputs are under ignored `data/output/material_store/` and are not committed.

The next Gate may build Embeddings or an index only after explicit approval. This Gate did not generate Embeddings or a FAISS index.

## 14. Data Issues Requiring Business Confirmation

- 29 records do not have a product category recognized by the current safe rules.
- 13 records appear to be non-duvet types and should be confirmed as intentionally retained in this source.
- 1 record has empty `规格`.
- 16 records have empty `面料`, `面料-品类`, or `面料-涤棉成分`.
- 1,454 records have empty `面料-纱支`.
- 36 records have empty `款式`.
- 32 records have empty `尺寸类型`.

These are recorded as data-quality observations only. The source CSV was not modified.