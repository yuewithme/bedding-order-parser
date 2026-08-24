# Gate 3A-C Final Report: Dictionary Shadow Comparison

## 1. Scope

Gate 3A-C implements only an independent dictionary shadow comparison mode.
The existing Gate 2D Python parser output remains the only official business result.

This gate adds:

- field-level shadow comparison models;
- independent source-evidence matcher;
- safe JSON writer for the shadow report;
- `python -m bedding_order_parser.dictionaries shadow-compare`;
- focused regression tests for shadow comparison behavior.

This gate does not modify:

- official 20-field business JSON structure;
- Gate 2D parsing flow;
- `order_parser`;
- field normalization production logic;
- material matching logic;
- dependencies;
- real Excel source files;
- Day01.

## 2. Inputs

The shadow run used the existing Gate 2D corpus:

- source PI directory: `data/input/pi`
- official result directory: `data/output/gate2d_validation/all_results`
- parse report directory: `data/output/gate2d_validation/all_reports`
- rule workbook: `data/reference/PI单提取规则.xlsx`
- style workbook: `data/reference/款式表_structured.xlsx`

The matcher pairs each parse report by `input.file_name` with exactly one source PI workbook and one official Gate 2D result JSON.

## 3. Output

One local ignored output was generated:

- `data/output/gate3a_c_shadow/dictionary_shadow_report.json`

The output contains shadow comparison observations only. It is not committed and is not consumed by the official parser.

## 4. Implementation

New files:

- `src/bedding_order_parser/dictionaries/shadow_models.py`
- `src/bedding_order_parser/dictionaries/shadow_matcher.py`
- `src/bedding_order_parser/dictionaries/shadow_writer.py`
- `tests/dictionaries/test_shadow_compare.py`

Updated file:

- `src/bedding_order_parser/dictionaries/__main__.py`

The `shadow-compare` command loads approved read-only dictionary previews through the existing dictionary loader, reads original PI evidence cells from parse diagnostics, creates dictionary candidates independently, and compares them against the official Python values.

The command does not call the formal parser and does not write back to any official Gate 2D JSON.

## 5. Shadow Fields

The shadow mode compares exactly these 10 fields:

- `币种`
- `物料名称`
- `规格`
- `颜色`
- `面料`
- `面料-涤棉成分`
- `款式`
- `尺寸类型`
- `行备注`
- `是否绣花`

## 6. Status Contract

Each field-level comparison uses only these statuses:

- `exact_match`
- `equivalent_match`
- `dictionary_more_specific`
- `partial_match`
- `ambiguous`
- `conflict`
- `dictionary_no_match`
- `source_not_provided`

## 7. Real Corpus Result

Shadow comparison was run against 12 PI files and 49 official records.

Overall field-level totals:

| Status | Count |
|---|---:|
| exact_match | 116 |
| equivalent_match | 103 |
| dictionary_more_specific | 0 |
| partial_match | 8 |
| ambiguous | 40 |
| conflict | 48 |
| dictionary_no_match | 92 |
| source_not_provided | 83 |

Field-level status counts:

| Field | Exact | Equivalent | Partial | Ambiguous | Conflict | No Match | Source Missing |
|---|---:|---:|---:|---:|---:|---:|---:|
| 币种 | 36 | 0 | 0 | 0 | 0 | 7 | 6 |
| 物料名称 | 0 | 46 | 0 | 0 | 0 | 3 | 0 |
| 规格 | 0 | 0 | 0 | 0 | 46 | 3 | 0 |
| 颜色 | 45 | 0 | 0 | 4 | 0 | 0 | 0 |
| 面料 | 0 | 18 | 0 | 29 | 2 | 0 | 0 |
| 面料-涤棉成分 | 0 | 39 | 0 | 0 | 0 | 10 | 0 |
| 款式 | 0 | 0 | 0 | 7 | 0 | 42 | 0 |
| 尺寸类型 | 12 | 0 | 0 | 0 | 0 | 2 | 35 |
| 行备注 | 16 | 0 | 8 | 0 | 0 | 25 | 0 |
| 是否绣花 | 7 | 0 | 0 | 0 | 0 | 0 | 42 |

## 8. Interpretation

The shadow report is diagnostic evidence, not a replacement for official parsing.

The high conflict count for `规格` shows that a standalone dictionary-side size interpretation still needs design review before it can influence production parsing. The ambiguity counts for `面料`, `颜色`, and `款式` show that the dictionary data can produce multiple candidates for the same PI evidence and therefore still needs tie-breaker rules before runtime use.

`source_not_provided` is expected for fields where Gate 2D used a default or no explicit source cell was recorded, especially `是否绣花` and `尺寸类型`.

## 9. Tests

Full test result:

```text
98 passed
```

New tests cover:

- source cell evidence versus official Python value;
- `100% cotton` versus `100C`;
- `C80/T20` versus `C50/T50`;
- `USD` versus `美元`;
- size unit conversion and width/length order;
- fabric ambiguity and component matching;
- style exact and ambiguous matches;
- source missing status;
- dictionary no-match status;
- defaulted Python status preservation;
- Chinese JSON output;
- writer overwrite protection;
- official JSON non-modification.

## 10. Protection Checks

Confirmed:

- official 20-field JSON contract was not changed;
- formal parser modules were not connected to the dictionary shadow path;
- `src` changes are limited to `bedding_order_parser/dictionaries`;
- `tests` changes are limited to `tests/dictionaries/test_shadow_compare.py`;
- `pyproject.toml` and `uv.lock` were not modified;
- no LLM, API, embedding, FAISS, or material matching path was added;
- generated `data/output/gate3a_c_shadow/` remains ignored and uncommitted;
- no push or tag was performed.

## 11. Gate Result

Gate 3A-C is complete.

The project now has an independent shadow comparison mode that can expose dictionary candidates beside official Gate 2D values without modifying official output or changing production parsing behavior.
