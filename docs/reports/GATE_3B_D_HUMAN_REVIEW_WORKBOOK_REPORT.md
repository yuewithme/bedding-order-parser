# Gate 3B-D Human Review Workbook Report

## 1. Git Baseline And Final Commit

Baseline repository: `D:\AI-Learning\Projects\bedding-order-parser`

Baseline commit before this gate:

- Full HEAD: `6a61fbd685c11dfd8a5c1a4ac0978c9fa5bcbc27`
- Short HEAD: `6a61fbd`
- Latest commit message: `feat: prototype hybrid material matching`
- Baseline test result: `205 passed`

This report is prepared before the final Gate 3B-D commit. The final commit is expected to use:

- Commit message: `feat: build material matching review workbook`

## 2. Workbook Structure

Generated workbook:

- Path: `data/output/material_match_review/material_match_review.xlsx`
- Git status: ignored by `.gitignore` rule `/data/output/material_match_review/`
- Purpose: business-owner review and ground-truth collection only.

Sheets:

1. `审核清单`: one row per order record, 49 data rows.
2. `候选明细`: one row per retained Top-K candidate, 165 data rows.
3. `重点问题`: grouped issue sheet for no-candidate, ambiguous-tie, and insufficient-evidence records.
4. `填写说明`: concise business instructions and suggested review order.
5. `物料编码索引`: hidden searchable material-code index, 29,127 data rows.

The workbook does not expose FAISS positions, model revision, vector dimension, SQLite internal row identifiers, or code module names. It keeps `prototype_match_score` and raw `vector_score` only for review ordering, and labels prototype scores as non-official.

## 3. Real 49-Record Data Statistics

Input files:

- `data/output/material_match_prototype/material_match_candidates.json`
- `data/output/material_match_prototype/material_match_summary.json`
- `data/output/material_store/material_master.sqlite3`

Real-data validation results:

| Metric | Count |
|---|---:|
| Order records | 49 |
| Records with recommended code | 43 |
| No candidate | 6 |
| Ambiguous tie | 3 |
| Insufficient evidence | 26 |
| Unique best candidate | 14 |
| Candidate detail Top-K rows | 165 |
| Material index rows | 29,127 |

All 43 recommended material codes exist in SQLite. All 165 retained Top-K candidate codes exist in SQLite.

## 4. Sheet Row Counts

| Sheet | Data rows / rows |
|---|---:|
| `审核清单` | 49 data rows |
| `候选明细` | 165 data rows |
| `重点问题` | 43 worksheet rows including section headers and blanks |
| `填写说明` | 12 rows |
| `物料编码索引` | 29,127 data rows |

`审核清单` keeps all 49 order records on one sheet. The hidden index is searchable/copyable and avoids a 29,127-item dropdown.

## 5. Data Validation Rules

`审核结论` uses an Excel dropdown with these values:

- `推荐编码正确`
- `Top候选中其他编码正确`
- `物料库不存在对应物料`
- `订单字段解析错误`
- `物料主数据有误`
- `信息不足无法确认`
- `需要补充新的区分字段`

`正确物料编码` uses an Excel validation formula against hidden sheet `物料编码索引`. The independent CLI validator performs stricter checks and does not modify the workbook.

## 6. Business-Owner Fill Fields

The first 19 columns in `审核清单` are system-generated review context. Columns 20-26 are for business-owner input:

- `正确物料编码`
- `审核结论`
- `需要修正的订单字段`
- `正确字段值`
- `审核备注`
- `审核人`
- `审核日期`

No default review conclusion is populated.

## 7. Material-Code Validation Method

New command:

```powershell
uv run python -m bedding_order_parser.materials validate-review `
  --workbook "data/output/material_match_review/material_match_review.xlsx" `
  --store "data/output/material_store/material_master.sqlite3"
```

Validation rules implemented:

- Filled `正确物料编码` must exist in SQLite.
- `推荐编码正确` requires `正确物料编码` to equal `推荐物料编码`.
- `Top候选中其他编码正确` requires the filled code to be present in that order's Top 10 candidates.
- No-material and unable-to-confirm conclusions allow an empty code.
- `订单字段解析错误` requires `需要修正的订单字段`.
- Duplicate `审核序号` is rejected.
- Deleted review rows are rejected by cross-checking `审核清单` against `候选明细` and `重点问题` audit identifiers.
- The validator reports errors and warnings only; it does not write or repair reviewer input.

Blank generated workbook validation result:

- `ok`: true
- Checked rows: 49
- Workbook SHA-256 before validation: `231bfe6b993dd5ce5a2b29eea7ae5ead2e7ea0259edc0492d163df88663d53fa`
- Workbook SHA-256 after validation: `231bfe6b993dd5ce5a2b29eea7ae5ead2e7ea0259edc0492d163df88663d53fa`

## 8. Source Data Protection Result

No matching algorithm, scoring weight, hard-conflict rule, embedding, formal JSON, parse report, dictionary validation report, SQLite store, JSONL store, FAISS index, mapping file, PI workbook, dictionary Excel, or Day01 file was modified.

Protected hash recheck passed for 32 files, including:

- `material_match_candidates.json`
- `material_match_summary.json`
- 12 Gate 2D formal JSON files
- 12 Gate 2D parse report files
- `material_master.sqlite3`
- `material_documents.jsonl`
- `material_store_manifest.json`
- `duvet_cover.faiss`
- `duvet_cover_mapping.jsonl`
- `vector_index_manifest.json`

Key artifact hashes after workbook generation:

| Artifact | SHA-256 |
|---|---|
| `material_match_candidates.json` | `CCA084DBAE8CD095B404FB6558322D137DD1890FDCD96C0E6107427C3B7C52E7` |
| `material_match_summary.json` | `0A05C6C96ACCD14E2E2373D3797E1616E3EB0E9A3D8BDCEF3D5889E62C8D05E7` |
| `material_master.sqlite3` | `BC590BD08B617588677C9C79DB33C5FEB03CE5F3FFD11C8B904C1FFB51374E20` |
| `duvet_cover.faiss` | `098A35725B90A3DDC5D762715714CC221E7ED476756F4C516C91DF5A384B9AB6` |
| `duvet_cover_mapping.jsonl` | `EE31D7B09C67A2724FBE2C1F433A385B1A63865D47EAA73281DCBEF18965A3C1` |

## 9. Test Result

Full test command:

```powershell
uv run pytest
```

Result:

- `214 passed`

This includes the original 205 tests plus 9 Gate 3B-D tests.

## 10. Delivery Readiness

Gate 3B-D is ready to hand to the business owner for manual material-code review.

The workbook is suitable for collecting ground truth, no-material reasons, parse-error corrections, and additional distinguishing business information. The validator gives the project team a reproducible way to check returned workbooks without changing reviewer-entered content.

This gate does not claim material matching accuracy and does not write back any official material code.
