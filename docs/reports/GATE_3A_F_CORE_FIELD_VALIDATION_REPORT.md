# Gate 3A-F Core Field Dictionary Validation Report

## Scope

Gate 3A-F extends the existing `--dictionary-validate` sidecar report only. It validates four fields from independent PI source evidence and approved project rules:

- `物料名称`
- `币种`
- `规格`
- `颜色`

The validation layer does not extract, fill, overwrite, or mutate any official 20-field JSON value. The normal parse path without `--dictionary-validate` still does not load dictionaries and does not create a third report.

## Implementation

Changed files:

- `src/bedding_order_parser/dictionaries/product_validation.py`
- `tests/dictionaries/test_product_validation.py`

The existing CLI and pipeline entry remain unchanged from Gate 3A-E. The implementation reuses:

- `load_dictionary_bundle` for read-only dictionary loading;
- `shadow_matcher._evidence_for_field` for source-cell evidence;
- `shadow_matcher.compare_shadow_field` for field comparison;
- the existing atomic JSON writer helpers.

Validation records now use a nested per-record structure:

```json
{
  "行号": "",
  "source_file": "",
  "sheet": "",
  "fields": {
    "物料名称": {},
    "币种": {},
    "规格": {},
    "颜色": {}
  }
}
```

Each field record includes `source_cells`, `source_text`, `python_value`, `dictionary_candidates`, `validation_status`, `action`, and `reason`. `物料名称` also keeps `detected_category` for the duvet-cover-only category check.

## Field Rules

`物料名称` keeps the Gate 3A-E behavior: it validates only whether the source product category is `被套`. The approved `Dubet cover` typo is normalized only for comparison; the original `source_text` remains unchanged in the report.

`币种` reuses the shadow currency comparison and supplements it only with existing approved metadata currency codes from `CURRENCY_CODE_NAMES`. Code or symbol evidence such as `USD` versus official `美元` is reported as `equivalent_match` in the validation sidecar.

`规格` reuses the Gate 3A-C.2 calibrated size logic through `compare_shadow_field`: width-length to length-width conversion, unit conversion, separator tolerance, same-row flap/overlap evidence, and exclusion of hand hole/location/TC-like numeric evidence.

`颜色` reuses the shadow color comparison and adds validation-layer filtering for craft colors such as ID thread, identification line, color coding, colored stitching, and Chinese 色线/识别线. It also treats explicit `light grey`/`浅灰` evidence as equivalent to official `浅灰色`.

## No-Flag Behavior

Regression run directory:

`data/output/gate3a_f_core_validation/run_20260727_012947_same_path`

Without `--dictionary-validate`:

- input files: 12
- official JSON files generated: 12
- parse report files generated: 12
- dictionary validation reports generated: 0
- dictionaries loaded: no validation side effects observed

## With-Flag Behavior

With `--dictionary-validate` on the same output paths:

- validation reports generated: 12
- records: 49
- validation observations: 196 (`49 x 4`)
- official JSON SHA unchanged after enabling flag: yes
- parse report SHA unchanged after enabling flag: yes

## Four-Field Status Statistics

| Field | exact_match | equivalent_match | partial_match | ambiguous | dictionary_no_match | source_not_provided | conflict | keep_python | manual_review |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 物料名称 | 0 | 49 | 0 | 0 | 0 | 0 | 0 | 49 | 0 |
| 币种 | 0 | 36 | 0 | 0 | 7 | 6 | 0 | 49 | 0 |
| 规格 | 0 | 40 | 6 | 0 | 3 | 0 | 0 | 49 | 0 |
| 颜色 | 47 | 2 | 0 | 0 | 0 | 0 | 0 | 49 | 0 |

## Ambiguous, Conflict, And Partial Records

Ambiguous records: 0.

Conflict records: 0.

Partial records: 6, all in `规格`.

| Source file | Line | Python value | Candidate | Source cells | Reason |
| --- | ---: | --- | --- | --- | --- |
| `20251231 被套 Proforma Invoice（11行）.xlsx` | 1 | `260*340+15cm` | `260*340` | `C13`, `A13`, `B13`, `D13`, `E13` | Base dimensions match; structural extension evidence is not safely extractable because nearby text also includes excluded hand-hole evidence. |
| `20251231 被套 Proforma Invoice（11行）.xlsx` | 5 | `240*290+15cm` | `240*290` | `C17`, `A17`, `B17`, `D17`, `E17` | Base dimensions match; structural extension evidence is not safely extractable because nearby text also includes excluded hand-hole evidence. |
| `20251231 被套 Proforma Invoice（11行）.xlsx` | 8 | `240*200+15cm` | `240*200` | `C20`, `A20`, `B20`, `D20`, `E20` | Base dimensions match; structural extension evidence is not safely extractable because nearby text also includes excluded hand-hole evidence. |
| `3402510MR30051 Proforma Invoice of Double Tree Jeddah - 20251002.xlsx` | 15 | `240*270+5cm` | `240*270+15cm` | `C28`, `A28`, `B28`, `D28`, `F28` | Base dimensions match; source contains multiple opening/flap/hem dimensions, so the extension cannot be safely reduced to the official value. |
| `3402510MR30051 Proforma Invoice of Double Tree Jeddah - 20251002.xlsx` | 16 | `240*230+5cm` | `240*230` | `C29`, `A29`, `B29`, `F29` | Base dimensions match; no same-row structural extension evidence was available in validation evidence. |
| `3402510MR30051 Proforma Invoice of Double Tree Jeddah - 20251002.xlsx` | 17 | `230*150+5cm` | `230*150` | `C30`, `A30`, `B30`, `F30` | Base dimensions match; no same-row structural extension evidence was available in validation evidence. |

All partial records use `action=keep_python`. They are validation observations only and do not change official output.

## Dictionary Failure Fallback

Covered by tests:

- missing dictionary files still leave official JSON and parse report generated;
- validation report is written with `status=failed` and `failure_reason`;
- unexpected validation-side exceptions are isolated after official output succeeds;
- no validation failure overwrites or deletes official outputs.

## Protection Results

- Source PI SHA unchanged during real-data regression: yes.
- Dictionary SHA unchanged during real-data regression: yes.
- Official JSON SHA unchanged after enabling `--dictionary-validate`: yes.
- Parse report SHA unchanged after enabling `--dictionary-validate`: yes.
- Official 20-field JSON schema changed: no.
- Formal parse report schema changed: no.
- Dependencies changed: no.
- LLM/API/Embedding/FAISS used: no.
- Day01 modified: no.

## Tests

Final test command:

```powershell
uv run pytest
```

Result:

```text
159 passed
```

New/updated coverage includes:

- no-flag parse behavior unchanged;
- validation report contains four fields per record;
- USD to `美元` equivalence;
- missing currency evidence;
- width-length to length-width size equivalence;
- same-row flap extension evidence;
- hand hole dimensions excluded from size extension;
- product main color separated from ID thread/color-line evidence;
- multiple main colors become `ambiguous` and `manual_review`;
- `light grey` equivalence to `浅灰色`;
- `partial_match` keeps Python;
- dictionary failure isolation;
- official JSON and parse report unchanged.

## Readiness

The validation framework is now ready to add more verification-only fields using the same sidecar pattern. It is not yet a production overwrite mechanism and should remain validation-only until future Gates explicitly approve dictionary-based field replacement.